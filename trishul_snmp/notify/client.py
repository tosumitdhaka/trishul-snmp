"""Async SNMPv2c notification sender."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from types import TracebackType

from trishul_snmp._runtime import normalize_targets, response_from_pdu
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.transport.dispatcher import RequestDispatcher
from trishul_snmp.transport.udp import UdpClient
from trishul_snmp.types import (
    OID,
    ObjectIdentifierValue,
    Response,
    SnmpValueType,
    TimeTicksValue,
)
from trishul_snmp.wire.pdu import PduType, RawVarBind, build_raw_varbinds

NotificationVarBindInput = tuple[str | Sequence[int], SnmpValueType]

_SYS_UPTIME_INSTANCE_OID: OID = (1, 3, 6, 1, 2, 1, 1, 3, 0)
_SNMP_TRAP_OID_INSTANCE_OID: OID = (1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0)


class V2cNotifier:
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
        self._bundle = bundle
        self._client = UdpClient(host, port, max_datagram_size=max_datagram_size)
        self._dispatcher = RequestDispatcher(
            self._client,
            community=community,
            timeout=timeout,
            retries=retries,
        )
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> V2cNotifier:
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
        await self._client.open()

    async def close(self) -> None:
        """Close the UDP transport."""
        await self._client.close()

    async def send_trap(
        self,
        notification: str | Sequence[int],
        *,
        varbinds: Sequence[NotificationVarBindInput] = (),
        uptime: int = 0,
    ) -> int:
        """Send an SNMPv2c trap and return the assigned request id."""
        notification_oid = _normalize_notification_target(notification, bundle=self._bundle)
        raw_varbinds = encode_notification_raw_varbinds(
            notification_oid,
            varbinds=varbinds,
            uptime=uptime,
            bundle=self._bundle,
        )
        async with self._lock:
            request = self._dispatcher.prepare_request(PduType.SNMPV2_TRAP, raw_varbinds)
            await self._dispatcher.send_only(request)
        return request.request_id

    async def send_inform(
        self,
        notification: str | Sequence[int],
        *,
        varbinds: Sequence[NotificationVarBindInput] = (),
        uptime: int = 0,
    ) -> Response:
        """Send an SNMPv2c inform and wait for the matching response."""
        notification_oid = _normalize_notification_target(notification, bundle=self._bundle)
        raw_varbinds = encode_notification_raw_varbinds(
            notification_oid,
            varbinds=varbinds,
            uptime=uptime,
            bundle=self._bundle,
        )
        async with self._lock:
            request = self._dispatcher.prepare_request(PduType.INFORM_REQUEST, raw_varbinds)
            response_pdu = await self._dispatcher.send_prepared_request(request)
        return response_from_pdu(response_pdu, bundle=self._bundle)


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
