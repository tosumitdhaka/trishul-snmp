"""SNMP PDU models and codecs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from trishul_snmp.errors import ProtocolError
from trishul_snmp.types import OID, ErrorStatus, SnmpValueType
from trishul_snmp.wire.asn1 import decode_value, encode_value
from trishul_snmp.wire.ber import decode_tlv, encode_tlv, expect_end

_SEQUENCE_TAG = 0x30
_GET_REQUEST_TAG = 0xA0
_GET_NEXT_REQUEST_TAG = 0xA1
_RESPONSE_TAG = 0xA2
_SET_REQUEST_TAG = 0xA3
_GET_BULK_REQUEST_TAG = 0xA5


class PduType(IntEnum):
    """Supported SNMP PDU tags."""

    GET = _GET_REQUEST_TAG
    GET_NEXT = _GET_NEXT_REQUEST_TAG
    RESPONSE = _RESPONSE_TAG
    SET = _SET_REQUEST_TAG
    GET_BULK = _GET_BULK_REQUEST_TAG


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


def encode_pdu(pdu: Pdu) -> bytes:
    """Encode a PDU to BER bytes."""
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


def _reencode_length_prefixed(content: bytes) -> bytes:
    from trishul_snmp.wire.ber import encode_length

    return encode_length(len(content)) + content
