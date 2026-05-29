"""Async SNMP notification sender."""

from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType
from typing import TypeVar

from trishul_snmp._runtime import normalize_targets, response_from_pdu
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.security.community import CommunityModel
from trishul_snmp.security.model import SecurityModel
from trishul_snmp.security.usm import UsmUser
from trishul_snmp.session import SnmpSession
from trishul_snmp.types import (
    OID,
    ObjectIdentifierValue,
    Response,
    SnmpValueType,
    TimeTicksValue,
)
from trishul_snmp.wire.pdu import PduType, RawVarBind, build_raw_varbinds

_TNotifier = TypeVar("_TNotifier", bound="SnmpNotifier")

NotificationVarBindInput = tuple[str | Sequence[int], SnmpValueType]

_SYS_UPTIME_INSTANCE_OID: OID = (1, 3, 6, 1, 2, 1, 1, 3, 0)
_SNMP_TRAP_OID_INSTANCE_OID: OID = (1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0)


class SnmpNotifier:
    """Async SNMP trap and inform sender. Subclass for version-specific constructors."""

    def __init__(
        self,
        *,
        host: str,
        security: SecurityModel,
        port: int = 162,
        timeout: float = 2.0,
        retries: int = 1,
        bundle: MibBundle | None = None,
        max_datagram_size: int = 65535,
    ) -> None:
        self._session = SnmpSession(
            host=host,
            port=port,
            security=security,
            timeout=timeout,
            retries=retries,
            bundle=bundle,
            max_datagram_size=max_datagram_size,
        )

    async def __aenter__(self: _TNotifier) -> _TNotifier:
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

    async def open(self) -> None:
        """Open the UDP transport."""
        await self._session.open()

    async def close(self) -> None:
        """Close the UDP transport."""
        await self._session.close()

    async def send_trap(
        self,
        notification: str | Sequence[int],
        *,
        varbinds: Sequence[NotificationVarBindInput] = (),
        uptime: int = 0,
    ) -> int:
        """Send an SNMP trap and return the assigned request id."""
        notification_oid = _normalize_notification_target(notification, bundle=self._session.bundle)
        raw_varbinds = encode_notification_raw_varbinds(
            notification_oid,
            varbinds=varbinds,
            uptime=uptime,
            bundle=self._session.bundle,
        )
        async with self._session.lock:
            request = self._session.dispatcher.prepare_request(PduType.SNMPV2_TRAP, raw_varbinds)
            await self._session.dispatcher.send_only(request)
        return request.request_id

    async def send_inform(
        self,
        notification: str | Sequence[int],
        *,
        varbinds: Sequence[NotificationVarBindInput] = (),
        uptime: int = 0,
    ) -> Response:
        """Send an SNMP inform and wait for the matching response."""
        notification_oid = _normalize_notification_target(notification, bundle=self._session.bundle)
        raw_varbinds = encode_notification_raw_varbinds(
            notification_oid,
            varbinds=varbinds,
            uptime=uptime,
            bundle=self._session.bundle,
        )
        async with self._session.lock:
            request = self._session.dispatcher.prepare_request(PduType.INFORM_REQUEST, raw_varbinds)
            response_pdu = await self._session.dispatcher.send_prepared_request(request)
        return response_from_pdu(response_pdu, bundle=self._session.bundle)


class V2cNotifier(SnmpNotifier):
    """Async SNMPv2c trap and inform sender."""

    def __init__(
        self,
        *,
        host: str,
        community: str,
        port: int = 162,
        timeout: float = 2.0,
        retries: int = 1,
        bundle: MibBundle | None = None,
        max_datagram_size: int = 65535,
    ) -> None:
        super().__init__(
            host=host,
            security=CommunityModel(community),
            port=port,
            timeout=timeout,
            retries=retries,
            bundle=bundle,
            max_datagram_size=max_datagram_size,
        )


class V3Notifier(SnmpNotifier):
    """Async SNMPv3 USM inform sender. send_trap() is not supported — see class docs."""

    def __init__(
        self,
        *,
        host: str,
        user: UsmUser,
        port: int = 162,
        timeout: float = 2.0,
        retries: int = 1,
        bundle: MibBundle | None = None,
        max_datagram_size: int = 65535,
        context_name: bytes = b"",
    ) -> None:
        from trishul_snmp.security.usm import UsmModel

        super().__init__(
            host=host,
            security=UsmModel(user=user, context_name=context_name),
            port=port,
            timeout=timeout,
            retries=retries,
            bundle=bundle,
            max_datagram_size=max_datagram_size,
        )

    async def send_trap(
        self,
        notification: str | Sequence[int],
        *,
        varbinds: Sequence[NotificationVarBindInput] = (),
        uptime: int = 0,
    ) -> int:
        from trishul_snmp.errors import ProtocolError

        raise ProtocolError(
            "V3Notifier.send_trap() is not supported: SNMPv3 traps require the sender's "
            "own authoritative engine state (RFC 3412 §7.1.9), which is not available after "
            "engine discovery against the trap receiver. Use send_inform() instead."
        )


def _normalize_notification_target(
    notification: str | Sequence[int],
    *,
    bundle: MibBundle | None,
) -> OID:
    return normalize_targets((notification,), bundle=bundle)[0]


def _build_notification_varbinds(
    notification_oid: OID,
    *,
    varbinds: Sequence[NotificationVarBindInput],
    uptime: int,
    bundle: MibBundle | None,
) -> tuple[tuple[OID, SnmpValueType], ...]:
    if uptime < 0:
        raise ValueError("uptime cannot be negative")

    normalized_explicit = _normalize_explicit_varbinds(varbinds, bundle=bundle)
    sys_uptime = TimeTicksValue(uptime)
    trap_oid = ObjectIdentifierValue(notification_oid)
    extras: list[tuple[OID, SnmpValueType]] = []

    for oid, value in normalized_explicit:
        if oid == _SYS_UPTIME_INSTANCE_OID and isinstance(value, TimeTicksValue):
            sys_uptime = value
            continue
        if oid == _SNMP_TRAP_OID_INSTANCE_OID and isinstance(value, ObjectIdentifierValue):
            trap_oid = value
            continue
        extras.append((oid, value))

    return (
        (_SYS_UPTIME_INSTANCE_OID, sys_uptime),
        (_SNMP_TRAP_OID_INSTANCE_OID, trap_oid),
        *extras,
    )


def _normalize_explicit_varbinds(
    varbinds: Sequence[NotificationVarBindInput],
    *,
    bundle: MibBundle | None,
) -> tuple[tuple[OID, SnmpValueType], ...]:
    if not varbinds:
        return ()

    oids = normalize_targets(tuple(target for target, _ in varbinds), bundle=bundle)
    return tuple((oid, value) for oid, (_, value) in zip(oids, varbinds, strict=True))


def build_notification_raw_varbinds(
    notification_oid: OID,
    *,
    varbinds: Sequence[NotificationVarBindInput] = (),
    uptime: int = 0,
    bundle: MibBundle | None = None,
) -> tuple[tuple[OID, SnmpValueType], ...]:
    """Build normalized notification varbinds for tests and future reuse."""
    return _build_notification_varbinds(
        notification_oid,
        varbinds=varbinds,
        uptime=uptime,
        bundle=bundle,
    )


def encode_notification_raw_varbinds(
    notification_oid: OID,
    *,
    varbinds: Sequence[NotificationVarBindInput] = (),
    uptime: int = 0,
    bundle: MibBundle | None = None,
) -> tuple[RawVarBind, ...]:
    """Build low-level notification varbinds for send paths."""
    normalized = build_notification_raw_varbinds(
        notification_oid,
        varbinds=varbinds,
        uptime=uptime,
        bundle=bundle,
    )
    return build_raw_varbinds(normalized)
