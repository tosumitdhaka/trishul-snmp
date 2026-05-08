"""Notification event models and helpers."""

from __future__ import annotations

from dataclasses import dataclass

from trishul_snmp._runtime import public_varbinds_from_raw_varbinds
from trishul_snmp.errors import UnknownOidError
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.mib.models import MibMemberRef, MibNode
from trishul_snmp.types import (
    OID,
    ObjectIdentifierValue,
    SocketAddress,
    TimeTicksValue,
    VarBind,
)
from trishul_snmp.wire.message import SnmpMessage, decode_message
from trishul_snmp.wire.pdu import PduType

_PDU_TYPE_NAMES = {
    PduType.SNMPV2_TRAP: "snmpv2-trap",
    PduType.INFORM_REQUEST: "inform-request",
}
_SYS_UPTIME_INSTANCE_OID: OID = (1, 3, 6, 1, 2, 1, 1, 3, 0)
_SNMP_TRAP_OID_INSTANCE_OID: OID = (1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0)


@dataclass(frozen=True, slots=True)
class NotificationMemberBinding:
    """A declared notification member paired with its received varbind."""

    member: MibMemberRef
    varbind: VarBind | None

    @property
    def symbolic(self) -> str:
        return self.member.symbolic


@dataclass(frozen=True, slots=True)
class NotificationEvent:
    """Structured inbound notification event."""

    request_id: int
    community: str
    source_address: SocketAddress | None
    pdu_type: str
    varbinds: tuple[VarBind, ...]
    notification_oid: OID | None = None
    notification_name: str | None = None
    notification_description: str | None = None
    uptime: int | None = None
    member_bindings: tuple[NotificationMemberBinding, ...] = ()

    @property
    def source_host(self) -> str | None:
        if self.source_address is None:
            return None
        return self.source_address[0]

    @property
    def source_port(self) -> int | None:
        if self.source_address is None:
            return None
        return self.source_address[1]

    @property
    def is_inform(self) -> bool:
        return self.pdu_type == "inform-request"

    @property
    def declared_members(self) -> tuple[MibMemberRef, ...]:
        return tuple(binding.member for binding in self.member_bindings)


def notification_event_from_message(
    message: SnmpMessage,
    *,
    source_address: SocketAddress | None,
    bundle: MibBundle | None,
) -> NotificationEvent:
    """Convert a low-level notification message into the public event model."""
    pdu_type = _PDU_TYPE_NAMES.get(message.pdu.pdu_type)
    if pdu_type is None:
        raise ValueError(f"Unsupported notification PDU type: {message.pdu.pdu_type!r}")

    varbinds = public_varbinds_from_raw_varbinds(message.pdu.varbinds, bundle=bundle)
    notification_oid = _extract_notification_oid(varbinds)
    uptime = _extract_uptime(varbinds)
    metadata = _notification_metadata(
        bundle=bundle,
        notification_oid=notification_oid,
        varbinds=varbinds,
    )

    return NotificationEvent(
        request_id=message.pdu.request_id,
        community=message.community,
        source_address=source_address,
        pdu_type=pdu_type,
        varbinds=varbinds,
        notification_oid=notification_oid,
        notification_name=metadata[0],
        notification_description=metadata[1],
        uptime=uptime,
        member_bindings=metadata[2],
    )


def decode_notification(
    data: bytes,
    *,
    bundle: MibBundle | None = None,
    source_address: SocketAddress | None = None,
) -> NotificationEvent:
    """Decode a BER-encoded SNMPv2c trap or inform message."""
    return notification_event_from_message(
        decode_message(data),
        source_address=source_address,
        bundle=bundle,
    )


def _extract_notification_oid(varbinds: tuple[VarBind, ...]) -> OID | None:
    for varbind in varbinds:
        if varbind.oid == _SNMP_TRAP_OID_INSTANCE_OID and isinstance(
            varbind.value,
            ObjectIdentifierValue,
        ):
            return varbind.value.value
    return None


def _extract_uptime(varbinds: tuple[VarBind, ...]) -> int | None:
    for varbind in varbinds:
        if varbind.oid == _SYS_UPTIME_INSTANCE_OID and isinstance(varbind.value, TimeTicksValue):
            return varbind.value.value
    return None


def _notification_metadata(
    *,
    bundle: MibBundle | None,
    notification_oid: OID | None,
    varbinds: tuple[VarBind, ...],
) -> tuple[str | None, str | None, tuple[NotificationMemberBinding, ...]]:
    if bundle is None or notification_oid is None:
        return None, None, ()

    try:
        match = bundle.lookup(notification_oid)
    except UnknownOidError:
        return None, None, ()

    if match.matched_oid != notification_oid or match.suffix:
        return bundle.display_symbolic_from_match(match), None, ()

    notification_name = bundle.display_symbolic_from_match(match)
    notification_node = bundle.resolve_node(match.module, match.symbol)
    if notification_node is None or not _is_notification_node(notification_node):
        return notification_name, None, ()

    return (
        notification_name,
        notification_node.description,
        _build_member_bindings(notification_node, varbinds=varbinds),
    )


def _is_notification_node(node: MibNode) -> bool:
    return node.object_type == "NOTIFICATION-TYPE"


def _build_member_bindings(
    notification_node: MibNode,
    *,
    varbinds: tuple[VarBind, ...],
) -> tuple[NotificationMemberBinding, ...]:
    declared_members = notification_node.members or ()
    if not declared_members:
        return ()

    payload_varbinds = tuple(
        varbind
        for varbind in varbinds
        if varbind.oid not in {_SYS_UPTIME_INSTANCE_OID, _SNMP_TRAP_OID_INSTANCE_OID}
    )

    bindings: list[NotificationMemberBinding] = []
    for index, member in enumerate(declared_members):
        varbind = payload_varbinds[index] if index < len(payload_varbinds) else None
        bindings.append(NotificationMemberBinding(member=member, varbind=varbind))
    return tuple(bindings)
