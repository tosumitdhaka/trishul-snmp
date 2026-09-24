"""SNMP PDU models and codecs."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import IntEnum

from trishul_snmp.errors import ProtocolError
from trishul_snmp.types import OID, ErrorStatus, NullValue, SnmpValueType
from trishul_snmp.wire.asn1 import decode_value, encode_value
from trishul_snmp.wire.ber import decode_tlv, encode_tlv, expect_end

_SEQUENCE_TAG = 0x30
_GET_REQUEST_TAG = 0xA0
_GET_NEXT_REQUEST_TAG = 0xA1
_RESPONSE_TAG = 0xA2
_SET_REQUEST_TAG = 0xA3
_TRAP_TAG = 0xA4
_GET_BULK_REQUEST_TAG = 0xA5
_INFORM_REQUEST_TAG = 0xA6
_SNMPV2_TRAP_TAG = 0xA7

_UINT32_MAX = (1 << 32) - 1


class PduType(IntEnum):
    """Supported SNMP PDU tags."""

    GET = _GET_REQUEST_TAG
    GET_NEXT = _GET_NEXT_REQUEST_TAG
    RESPONSE = _RESPONSE_TAG
    SET = _SET_REQUEST_TAG
    TRAP = _TRAP_TAG
    GET_BULK = _GET_BULK_REQUEST_TAG
    INFORM_REQUEST = _INFORM_REQUEST_TAG
    SNMPV2_TRAP = _SNMPV2_TRAP_TAG


@dataclass(frozen=True, slots=True)
class RawVarBind:
    """Low-level varbind used by the codec layer."""

    oid: OID
    value: SnmpValueType


@dataclass(frozen=True, slots=True)
class Pdu:
    """Low-level PDU representation."""

    pdu_type: PduType
    request_id: int
    error_status: int
    error_index: int
    varbinds: tuple[RawVarBind, ...]
    # v1 Trap-PDU (0xA4, RFC 1157) fields — populated only when pdu_type is TRAP.
    enterprise: OID = ()
    agent_addr: str = "0.0.0.0"
    generic_trap: int = 0
    specific_trap: int = 0
    timestamp: int = 0


def build_raw_varbinds(
    varbinds: Iterable[tuple[OID, SnmpValueType]],
) -> tuple[RawVarBind, ...]:
    """Build low-level varbinds from numeric OID/value pairs."""
    return tuple(RawVarBind(oid=oid, value=value) for oid, value in varbinds)


def build_null_varbinds(oids: Sequence[OID]) -> tuple[RawVarBind, ...]:
    """Build NULL-valued varbinds for request-style PDUs."""
    return build_raw_varbinds((oid, NullValue()) for oid in oids)


def build_trap_pdu(
    *,
    enterprise: OID,
    agent_addr: str,
    generic_trap: int,
    specific_trap: int,
    timestamp: int,
    varbinds: Iterable[RawVarBind] = (),
) -> Pdu:
    """Build a v1 Trap-PDU (RFC 1157) representation.

    Trap-PDUs carry no request-id/error-status/error-index; those fields are
    set to 0. The trap-specific fields live alongside the regular ``Pdu``
    fields and are only used when ``pdu_type`` is :attr:`PduType.TRAP`.
    """
    return Pdu(
        pdu_type=PduType.TRAP,
        request_id=0,
        error_status=0,
        error_index=0,
        varbinds=tuple(varbinds),
        enterprise=enterprise,
        agent_addr=agent_addr,
        generic_trap=generic_trap,
        specific_trap=specific_trap,
        timestamp=timestamp,
    )


def encode_pdu(pdu: Pdu) -> bytes:
    """Encode a PDU to BER bytes."""
    if pdu.pdu_type is PduType.TRAP:
        return _encode_trap_pdu(pdu)
    content = b"".join(
        [
            _encode_integer(pdu.request_id),
            _encode_integer(pdu.error_status),
            _encode_integer(pdu.error_index),
            _encode_varbind_list(pdu.varbinds),
        ]
    )
    return encode_tlv(int(pdu.pdu_type), content)


def decode_pdu(data: bytes) -> Pdu:
    """Decode a BER-encoded PDU."""
    tag, content, offset = decode_tlv(data, 0)
    expect_end(data, offset)
    try:
        pdu_type = PduType(tag)
    except ValueError as exc:
        raise ProtocolError(f"Unsupported PDU tag 0x{tag:02x}") from exc

    if pdu_type is PduType.TRAP:
        return _decode_trap_pdu(content)

    inner_offset = 0
    request_id, inner_offset = _decode_integer_from(content, inner_offset)
    error_status, inner_offset = _decode_integer_from(content, inner_offset)
    error_index, inner_offset = _decode_integer_from(content, inner_offset)
    varbinds, inner_offset = _decode_varbind_list(content, inner_offset)
    expect_end(content, inner_offset)
    return Pdu(
        pdu_type=pdu_type,
        request_id=request_id,
        error_status=error_status,
        error_index=error_index,
        varbinds=varbinds,
    )


def response_error_status(status: int) -> ErrorStatus:
    """Convert a raw integer status to an ErrorStatus enum when possible."""
    try:
        return ErrorStatus(status)
    except ValueError as exc:
        raise ProtocolError(f"Unsupported SNMP error-status value {status}") from exc


def _encode_integer(value: int) -> bytes:
    from trishul_snmp.types import IntegerValue

    return encode_value(IntegerValue(value))


def _decode_integer_from(data: bytes, offset: int) -> tuple[int, int]:
    tag, content, new_offset = decode_tlv(data, offset)
    if tag != 0x02:
        raise ProtocolError(f"Expected INTEGER tag, found 0x{tag:02x}")
    if not content:
        raise ProtocolError("INTEGER content cannot be empty")
    return int.from_bytes(content, "big", signed=True), new_offset


def _encode_varbind_list(varbinds: tuple[RawVarBind, ...]) -> bytes:
    content = b"".join(_encode_varbind(varbind) for varbind in varbinds)
    return encode_tlv(_SEQUENCE_TAG, content)


def _encode_varbind(varbind: RawVarBind) -> bytes:
    from trishul_snmp.types import ObjectIdentifierValue

    content = encode_value(ObjectIdentifierValue(varbind.oid)) + encode_value(varbind.value)
    return encode_tlv(_SEQUENCE_TAG, content)


def _decode_varbind_list(data: bytes, offset: int) -> tuple[tuple[RawVarBind, ...], int]:
    tag, content, new_offset = decode_tlv(data, offset)
    if tag != _SEQUENCE_TAG:
        raise ProtocolError(f"Expected VarBindList SEQUENCE, found 0x{tag:02x}")
    inner_offset = 0
    varbinds: list[RawVarBind] = []
    while inner_offset < len(content):
        varbind, inner_offset = _decode_varbind(content, inner_offset)
        varbinds.append(varbind)
    expect_end(content, inner_offset)
    return tuple(varbinds), new_offset


def _decode_varbind(data: bytes, offset: int) -> tuple[RawVarBind, int]:
    tag, content, new_offset = decode_tlv(data, offset)
    if tag != _SEQUENCE_TAG:
        raise ProtocolError(f"Expected VarBind SEQUENCE, found 0x{tag:02x}")

    inner_offset = 0
    oid, inner_offset = _decode_oid_from(content, inner_offset)
    value_tag, value_content, value_offset = decode_tlv(content, inner_offset)
    value = decode_value(bytes([value_tag]) + _reencode_length_prefixed(value_content))
    inner_offset = value_offset
    expect_end(content, inner_offset)
    return RawVarBind(oid=oid, value=value), new_offset


def _decode_oid_from(data: bytes, offset: int) -> tuple[OID, int]:
    tag, content, new_offset = decode_tlv(data, offset)
    if tag != 0x06:
        raise ProtocolError(f"Expected OBJECT IDENTIFIER, found 0x{tag:02x}")
    from trishul_snmp.wire.asn1 import _decode_oid  # local import to keep helpers scoped

    return _decode_oid(content), new_offset


def _encode_trap_pdu(pdu: Pdu) -> bytes:
    """Encode a v1 Trap-PDU (RFC 1157) to BER bytes."""
    from trishul_snmp.types import IpAddressValue, ObjectIdentifierValue, TimeTicksValue

    _validate_trap_fields(pdu)
    content = b"".join(
        [
            encode_value(ObjectIdentifierValue(pdu.enterprise)),
            encode_value(IpAddressValue(pdu.agent_addr)),
            _encode_integer(pdu.generic_trap),
            _encode_integer(pdu.specific_trap),
            encode_value(TimeTicksValue(pdu.timestamp)),
            _encode_varbind_list(pdu.varbinds),
        ]
    )
    return encode_tlv(_TRAP_TAG, content)


def _decode_trap_pdu(content: bytes) -> Pdu:
    """Decode a v1 Trap-PDU (RFC 1157) payload into a :class:`Pdu`."""
    offset = 0
    enterprise, offset = _decode_oid_from(content, offset)
    agent_addr, offset = _decode_ip_address_from(content, offset)
    generic_trap, offset = _decode_integer_from(content, offset)
    specific_trap, offset = _decode_integer_from(content, offset)
    timestamp, offset = _decode_timeticks_from(content, offset)
    varbinds, offset = _decode_varbind_list(content, offset)
    expect_end(content, offset)

    pdu = Pdu(
        pdu_type=PduType.TRAP,
        request_id=0,
        error_status=0,
        error_index=0,
        varbinds=varbinds,
        enterprise=enterprise,
        agent_addr=agent_addr,
        generic_trap=generic_trap,
        specific_trap=specific_trap,
        timestamp=timestamp,
    )
    _validate_trap_fields(pdu)
    return pdu


def _validate_trap_fields(pdu: Pdu) -> None:
    """Validate v1 Trap-PDU ranges shared by encode and decode."""
    if not 0 <= pdu.generic_trap <= 6:
        raise ProtocolError(f"generic-trap {pdu.generic_trap} must be between 0 and 6")
    if pdu.specific_trap < 0:
        raise ProtocolError(f"specific-trap {pdu.specific_trap} cannot be negative")


def _decode_ip_address_from(data: bytes, offset: int) -> tuple[str, int]:
    tag, content, new_offset = decode_tlv(data, offset)
    if tag != 0x40:
        raise ProtocolError(f"Expected IpAddress, found 0x{tag:02x}")
    from trishul_snmp.wire.asn1 import _decode_ip_address  # local import to keep helpers scoped

    return _decode_ip_address(content), new_offset


def _decode_timeticks_from(data: bytes, offset: int) -> tuple[int, int]:
    tag, content, new_offset = decode_tlv(data, offset)
    if tag != 0x43:
        raise ProtocolError(f"Expected TimeTicks, found 0x{tag:02x}")
    from trishul_snmp.wire.asn1 import _decode_unsigned_integer

    return (
        _decode_unsigned_integer(content, max_value=_UINT32_MAX, field="TimeTicks"),
        new_offset,
    )


def _reencode_length_prefixed(content: bytes) -> bytes:
    from trishul_snmp.wire.ber import encode_length

    return encode_length(len(content)) + content
