"""Async SNMP notification listeners."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from types import TracebackType

from trishul_snmp.errors import AuthenticationError, ProtocolError, TransportError
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.notify.events import (
    NotificationEvent,
    notification_event_from_message,
    notification_event_from_v3_envelope,
)
from trishul_snmp.notify.v3 import (
    DropReason,
    V3NotificationEnvelope,
    V3ReceiveVerdict,
    V3ReplayGuard,
    classify_v3_unmatched,
    decode_v3_notification_message,
    drop_reason_from_verdict,
    encode_discovery_report,
    encode_inform_response,
    is_discovery_probe,
)
from trishul_snmp.security.usm import UsmLocalEngine, UsmUser
from trishul_snmp.transport.udp import UdpServer
from trishul_snmp.types import SocketAddress
from trishul_snmp.wire.ber import decode_tlv
from trishul_snmp.wire.message import (
    SNMP_V1_VERSION,
    SNMP_V2C_VERSION,
    SnmpMessage,
    decode_message,
    encode_message,
)
from trishul_snmp.wire.pdu import Pdu, PduType

logger = logging.getLogger(__name__)

_DROP_LOG_INTERVAL_SECONDS = 5.0


class _BaseNotificationListener:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        bundle: MibBundle | None,
        on_error: Callable[[DropReason, SocketAddress, bytes], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._bundle = bundle
        self._server = UdpServer(host, port)
        self._closed = False
        self._on_error = on_error
        self._clock = clock
        self._drop_total = 0
        self._drop_counts: dict[DropReason, int] = {}
        self._drop_log_last: dict[DropReason, float] = {}

    async def __aenter__(self) -> _BaseNotificationListener:
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        del exc_type, exc, tb
        await self.close()

    def __aiter__(self) -> _BaseNotificationListener:
        return self

    async def __anext__(self) -> NotificationEvent:
        try:
            return await self.receive()
        except TransportError:
            if self._closed:
                raise StopAsyncIteration from None
            raise

    @property
    def local_address(self) -> SocketAddress | None:
        return self._server.local_address

    async def open(self) -> None:
        """Bind the listener socket."""
        self._closed = False
        await self._server.open()

    async def close(self) -> None:
        """Close the listener socket."""
        self._closed = True
        await self._server.close()

    async def receive(self) -> NotificationEvent:
        raise NotImplementedError

    @property
    def dropped(self) -> int:
        """Total number of datagrams dropped since this listener was created."""
        return self._drop_total

    @property
    def drop_counts(self) -> Mapping[DropReason, int]:
        """Per-reason drop counts for every drop reason observed so far."""
        return dict(self._drop_counts)

    def _handle_drop(
        self,
        *,
        reason: DropReason,
        source_address: SocketAddress,
        data: bytes,
    ) -> None:
        """Count, warn about, and report a datagram that must be dropped."""
        self._drop_total += 1
        self._drop_counts[reason] = self._drop_counts.get(reason, 0) + 1
        self._log_drop(reason=reason, source_address=source_address, data=data)
        self._notify_drop(reason=reason, source_address=source_address, data=data)

    def _log_drop(
        self,
        *,
        reason: DropReason,
        source_address: SocketAddress,
        data: bytes,
    ) -> None:
        now = self._clock()
        last = self._drop_log_last.get(reason)
        if last is not None and now - last < _DROP_LOG_INTERVAL_SECONDS:
            return
        self._drop_log_last[reason] = now
        logger.warning(
            "Dropping SNMP notification from %s: reason=%s, data_prefix=0x%s",
            _format_source(source_address),
            reason.value,
            data[:8].hex(),
        )

    def _notify_drop(
        self,
        *,
        reason: DropReason,
        source_address: SocketAddress,
        data: bytes,
    ) -> None:
        if self._on_error is None:
            return
        try:
            self._on_error(reason, source_address, data[:8])
        except Exception:
            logger.debug("on_error callback failed for %s drop", reason.value, exc_info=True)


class SnmpNotificationListener(_BaseNotificationListener):
    """Async iterator-style SNMPv1 and SNMPv2c trap and inform listener.

    The same listener serves both community-based versions: v2c traps and
    informs surface unchanged, and v1 Trap-PDUs from legacy devices surface
    with their Trap-PDU metadata. Community allow-listing applies to both
    versions.
    """

    def __init__(
        self,
        *,
        host: str = "0.0.0.0",
        port: int = 162,
        communities: Sequence[str] | None = None,
        bundle: MibBundle | None = None,
        on_error: Callable[[DropReason, SocketAddress, bytes], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(
            host=host,
            port=port,
            bundle=bundle,
            on_error=on_error,
            clock=clock,
        )
        self._communities = _normalize_communities(communities)

    async def receive(self) -> NotificationEvent:
        """Wait for the next matching trap or inform event."""
        while True:
            datagram = await self._server.receive()
            try:
                message = decode_message(datagram.data)
            except ProtocolError:
                self._handle_drop(
                    reason=_classify_v2c_drop(datagram.data),
                    source_address=datagram.source_address,
                    data=datagram.data,
                )
                continue
            if not _community_allowed(communities=self._communities, community=message.community):
                self._handle_drop(
                    reason=DropReason.WRONG_COMMUNITY,
                    source_address=datagram.source_address,
                    data=datagram.data,
                )
                continue
            if message.pdu.pdu_type not in {
                PduType.TRAP,
                PduType.SNMPV2_TRAP,
                PduType.INFORM_REQUEST,
            }:
                self._handle_drop(
                    reason=DropReason.NOT_NOTIFICATION,
                    source_address=datagram.source_address,
                    data=datagram.data,
                )
                continue
            if message.pdu.pdu_type is PduType.INFORM_REQUEST:
                await self._send_inform_ack(message, datagram.source_address)
            return notification_event_from_message(
                message,
                source_address=datagram.source_address,
                bundle=self._bundle,
            )

    async def _send_inform_ack(self, message: SnmpMessage, addr: SocketAddress) -> None:
        response = SnmpMessage(
            version=message.version,
            community=message.community,
            pdu=Pdu(
                pdu_type=PduType.RESPONSE,
                request_id=message.pdu.request_id,
                error_status=0,
                error_index=0,
                varbinds=message.pdu.varbinds,
            ),
        )
        await self._server.sendto(encode_message(response), addr)


class V3NotificationListener(_BaseNotificationListener):
    """Async iterator-style SNMPv3 notification listener for one configured user."""

    def __init__(
        self,
        *,
        host: str = "0.0.0.0",
        port: int = 162,
        user: UsmUser,
        local_engine: UsmLocalEngine,
        bundle: MibBundle | None = None,
        on_error: Callable[[DropReason, SocketAddress, bytes], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(
            host=host,
            port=port,
            bundle=bundle,
            on_error=on_error,
            clock=clock,
        )
        self._user = user
        self._local_engine = local_engine
        self._replay_guard = V3ReplayGuard()

    async def receive(self) -> NotificationEvent:
        """Wait for the next matching SNMPv3 trap or inform event."""
        while True:
            datagram = await self._server.receive()
            if is_discovery_probe(datagram.data):
                try:
                    report = encode_discovery_report(
                        datagram.data,
                        local_engine=self._local_engine,
                    )
                except ProtocolError:
                    self._handle_drop(
                        reason=DropReason.UNDECODABLE_BER,
                        source_address=datagram.source_address,
                        data=datagram.data,
                    )
                    continue
                await self._server.sendto(report, datagram.source_address)
                continue

            try:
                envelope = decode_v3_notification_message(datagram.data, user=self._user)
            except AuthenticationError:
                self._handle_drop(
                    reason=DropReason.AUTHENTICATION_FAILED,
                    source_address=datagram.source_address,
                    data=datagram.data,
                )
                continue
            except ProtocolError:
                self._handle_drop(
                    reason=DropReason.UNDECODABLE_BER,
                    source_address=datagram.source_address,
                    data=datagram.data,
                )
                continue
            if envelope is None:
                self._handle_drop(
                    reason=classify_v3_unmatched(datagram.data, user=self._user),
                    source_address=datagram.source_address,
                    data=datagram.data,
                )
                continue

            params = envelope.view.usm_params
            verdict = self._replay_guard.check(
                engine_id=params.engine_id,
                engine_boots=params.engine_boots,
                engine_time=params.engine_time,
                username=self._user.username,
                salt=params.priv_params,
            )
            if verdict is not V3ReceiveVerdict.ACCEPT:
                self._handle_drop(
                    reason=drop_reason_from_verdict(verdict),
                    source_address=datagram.source_address,
                    data=datagram.data,
                )
                continue

            if envelope.pdu.pdu_type is PduType.INFORM_REQUEST:
                await self._send_inform_ack(envelope, datagram.source_address)
            return notification_event_from_v3_envelope(
                envelope,
                source_address=datagram.source_address,
                bundle=self._bundle,
            )

    async def _send_inform_ack(
        self,
        envelope: V3NotificationEnvelope,
        addr: SocketAddress,
    ) -> None:
        response = encode_inform_response(
            envelope,
            user=self._user,
            local_engine=self._local_engine,
        )
        await self._server.sendto(response, addr)


V2cNotificationListener = SnmpNotificationListener


def _normalize_communities(communities: Sequence[str] | None) -> frozenset[str] | None:
    if communities is None:
        return None
    return frozenset(value for value in communities if value)


def _community_allowed(*, communities: frozenset[str] | None, community: str) -> bool:
    if communities is None:
        return True
    return community in communities


def _format_source(addr: SocketAddress) -> str:
    return f"{addr[0]}:{addr[1]}"


def _classify_v2c_drop(data: bytes) -> DropReason:
    """Pick the reason a datagram failed the v1/v2c decode path."""
    try:
        version = _peek_message_version(data)
    except ProtocolError:
        return DropReason.UNDECODABLE_BER
    if version not in (SNMP_V1_VERSION, SNMP_V2C_VERSION):
        return DropReason.UNSUPPORTED_VERSION
    return DropReason.UNDECODABLE_BER


def _peek_message_version(data: bytes) -> int:
    """Decode just the version INTEGER of a message, without a full decode."""
    tag, content, _offset = decode_tlv(data, 0)
    if tag != 0x30:
        raise ProtocolError(f"Expected SNMP message SEQUENCE, found 0x{tag:02x}")
    tag, raw, _offset = decode_tlv(content, 0)
    if tag != 0x02:
        raise ProtocolError(f"Expected version INTEGER, found 0x{tag:02x}")
    if not raw:
        raise ProtocolError("INTEGER content cannot be empty")
    return int.from_bytes(raw, "big", signed=True)
