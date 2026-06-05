"""Notification event models and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trishul_snmp._runtime import public_varbinds_from_raw_varbinds
from trishul_snmp.errors import ProtocolError, UnknownOidError
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.mib.models import MibMemberRef, MibNode
from trishul_snmp.notify.v3 import V3NotificationEnvelope, decode_v3_notification_message
from trishul_snmp.security.usm import UsmUser
from trishul_snmp.types import (
    OID,
    ObjectIdentifierValue,
    SocketAddress,
    TimeTicksValue,
    VarBind,
)
from trishul_snmp.wire.message import SnmpMessage, decode_message
from trishul_snmp.wire.pdu import Pdu, PduType

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
    community: str | None
    source_address: SocketAddress | None
    pdu_type: str
    varbinds: tuple[VarBind, ...]
    notification_oid: OID | None = None
    notification_name: str | None = None
    notification_description: str | None = None
    uptime: int | None = None
    member_bindings: tuple[NotificationMemberBinding, ...] = ()
    snmp_version: str | None = None
    username: str | None = None
    security_level: str | None = None
    context_engine_id: bytes | None = None
    context_name: bytes | None = None
    authoritative_engine_id: bytes | None = None
    authoritative_engine_boots: int | None = None
    authoritative_engine_time: int | None = None

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

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict representation of this event."""
        payload: dict[str, Any] = {
            "request_id": self.request_id,
            "community": self.community,
            "source_host": self.source_host,
            "source_port": self.source_port,
            "pdu_type": self.pdu_type,
            "notification_oid": (
                ".".join(str(arc) for arc in self.notification_oid)
                if self.notification_oid is not None
                else None
            ),
            "notification_name": self.notification_name,
            "notification_description": self.notification_description,
            "uptime": self.uptime,
            "varbinds": [
                {
                    "oid": vb.oid_str,
                    "display_name": vb.display_name,
                    "value_type": vb.value_type,
                    "value": vb.display_value,
                }
                for vb in self.varbinds
            ],
            "member_bindings": [
                {
                    "symbolic": binding.symbolic,
                    "oid": binding.varbind.oid_str if binding.varbind is not None else None,
                    "value_type": (
                        binding.varbind.value_type if binding.varbind is not None else None
                    ),
                    "value": binding.varbind.display_value if binding.varbind is not None else None,
                }
                for binding in self.member_bindings
            ],
        }
        if self.snmp_version is not None:
            payload["snmp_version"] = self.snmp_version
        if self.username is not None:
            payload["username"] = self.username
        if self.security_level is not None:
            payload["security_level"] = self.security_level
        if self.context_engine_id is not None:
            payload["context_engine_id"] = self.context_engine_id.hex()
        if self.context_name is not None:
            payload["context_name"] = self.context_name.hex()
        if self.authoritative_engine_id is not None:
            payload["authoritative_engine_id"] = self.authoritative_engine_id.hex()
        if self.authoritative_engine_boots is not None:
            payload["authoritative_engine_boots"] = self.authoritative_engine_boots
        if self.authoritative_engine_time is not None:
            payload["authoritative_engine_time"] = self.authoritative_engine_time
        return payload


def notification_event_from_message(
    message: SnmpMessage,
    *,
    source_address: SocketAddress | None,
    bundle: MibBundle | None,
) -> NotificationEvent:
    """Convert a low-level notification message into the public event model."""
    return _notification_event_from_pdu(
        pdu=message.pdu,
        request_id=message.pdu.request_id,
        community=message.community,
        source_address=source_address,
        bundle=bundle,
    )


def notification_event_from_v3_envelope(
    envelope: V3NotificationEnvelope,
    *,
    source_address: SocketAddress | None,
    bundle: MibBundle | None,
) -> NotificationEvent:
    """Convert a decoded v3 notification envelope into the public event model."""
    return _notification_event_from_pdu(
        pdu=envelope.pdu,
        request_id=envelope.pdu.request_id,
        community=None,
        source_address=source_address,
        bundle=bundle,
        snmp_version="3",
        username=envelope.view.usm_params.username.decode("utf-8"),
        security_level=envelope.security_level,
        context_engine_id=envelope.context_engine_id,
        context_name=envelope.context_name,
        authoritative_engine_id=envelope.view.usm_params.engine_id,
        authoritative_engine_boots=envelope.view.usm_params.engine_boots,
        authoritative_engine_time=envelope.view.usm_params.engine_time,
    )


def decode_notification(
    data: bytes,
    *,
    bundle: MibBundle | None = None,
    source_address: SocketAddress | None = None,
    user: UsmUser | None = None,
) -> NotificationEvent:
    """Decode a BER-encoded trap or inform message.

    When ``user`` is omitted, the current SNMPv2c path is used. Supplying
    ``user=...`` switches the function to strict SNMPv3 USM decode.
    """
    if user is None:
        return notification_event_from_message(
            decode_message(data),
            source_address=source_address,
            bundle=bundle,
        )

    envelope = decode_v3_notification_message(data, user=user)
    if envelope is None:
        raise ProtocolError("Message is not a valid SNMPv3 trap or inform for the configured user")
    return notification_event_from_v3_envelope(
        envelope,
        source_address=source_address,
        bundle=bundle,
    )


def _notification_event_from_pdu(
    *,
    pdu: Pdu,
    request_id: int,
    community: str | None,
    source_address: SocketAddress | None,
    bundle: MibBundle | None,
    snmp_version: str | None = None,
    username: str | None = None,
    security_level: str | None = None,
    context_engine_id: bytes | None = None,
    context_name: bytes | None = None,
    authoritative_engine_id: bytes | None = None,
    authoritative_engine_boots: int | None = None,
    authoritative_engine_time: int | None = None,
) -> NotificationEvent:
    pdu_type = _PDU_TYPE_NAMES.get(pdu.pdu_type)
    if pdu_type is None:
        raise ValueError(f"Unsupported notification PDU type: {pdu.pdu_type!r}")

    varbinds = public_varbinds_from_raw_varbinds(pdu.varbinds, bundle=bundle)
    notification_oid = _extract_notification_oid(varbinds)
    uptime = _extract_uptime(varbinds)
    metadata = _notification_metadata(
        bundle=bundle,
        notification_oid=notification_oid,
        varbinds=varbinds,
    )

    return NotificationEvent(
        request_id=request_id,
        community=community,
        source_address=source_address,
        pdu_type=pdu_type,
        varbinds=varbinds,
        notification_oid=notification_oid,
        notification_name=metadata[0],
        notification_description=metadata[1],
        uptime=uptime,
        member_bindings=metadata[2],
        snmp_version=snmp_version,
        username=username,
        security_level=security_level,
        context_engine_id=context_engine_id,
        context_name=context_name,
        authoritative_engine_id=authoritative_engine_id,
        authoritative_engine_boots=authoritative_engine_boots,
        authoritative_engine_time=authoritative_engine_time,
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
