"""Async SNMP notification listeners."""

from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType

from trishul_snmp.errors import ProtocolError, TransportError
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.notify.events import (
    NotificationEvent,
    notification_event_from_message,
    notification_event_from_v3_envelope,
)
from trishul_snmp.notify.v3 import (
    V3NotificationEnvelope,
    decode_v3_notification_message,
    encode_discovery_report,
    encode_inform_response,
    is_discovery_probe,
)
from trishul_snmp.security.usm import UsmLocalEngine, UsmUser
from trishul_snmp.transport.udp import UdpServer
from trishul_snmp.types import SocketAddress
from trishul_snmp.wire.message import SnmpMessage, decode_message, encode_message
from trishul_snmp.wire.pdu import Pdu, PduType


class _BaseNotificationListener:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        bundle: MibBundle | None,
    ) -> None:
        self._bundle = bundle
        self._server = UdpServer(host, port)
        self._closed = False

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


class SnmpNotificationListener(_BaseNotificationListener):
    """Async iterator-style SNMPv2c trap and inform listener."""

    def __init__(
        self,
        *,
        host: str = "0.0.0.0",
        port: int = 162,
        communities: Sequence[str] | None = None,
        bundle: MibBundle | None = None,
    ) -> None:
        super().__init__(host=host, port=port, bundle=bundle)
        self._communities = _normalize_communities(communities)

    async def receive(self) -> NotificationEvent:
        """Wait for the next matching trap or inform event."""
        while True:
            datagram = await self._server.receive()
            try:
                message = decode_message(datagram.data)
            except ProtocolError:
                continue
            if not _community_allowed(communities=self._communities, community=message.community):
                continue
            if message.pdu.pdu_type not in {PduType.SNMPV2_TRAP, PduType.INFORM_REQUEST}:
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
    ) -> None:
        super().__init__(host=host, port=port, bundle=bundle)
        self._user = user
        self._local_engine = local_engine

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
                    continue
                await self._server.sendto(report, datagram.source_address)
                continue

            try:
                envelope = decode_v3_notification_message(datagram.data, user=self._user)
            except ProtocolError:
                continue
            if envelope is None:
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
