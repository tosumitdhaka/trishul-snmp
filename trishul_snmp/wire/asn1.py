"""ASN.1 value encode/decode helpers for SNMP."""

from __future__ import annotations

from trishul_snmp.errors import ProtocolError
from trishul_snmp.types import (
    Counter32Value,
    Counter64Value,
    EndOfMibViewValue,
    Gauge32Value,
    IntegerValue,
    IpAddressValue,
    NoSuchInstanceValue,
    NoSuchObjectValue,
    NullValue,
    ObjectIdentifierValue,
    OctetStringValue,
    OpaqueValue,
    SnmpValueType,
    TimeTicksValue,
)
from trishul_snmp.wire.ber import decode_tlv, encode_tlv, expect_end

_INTEGER_TAG = 0x02
_OCTET_STRING_TAG = 0x04
_NULL_TAG = 0x05
_OBJECT_IDENTIFIER_TAG = 0x06
_IP_ADDRESS_TAG = 0x40
_COUNTER32_TAG = 0x41
_GAUGE32_TAG = 0x42
_TIMETICKS_TAG = 0x43
_OPAQUE_TAG = 0x44
_COUNTER64_TAG = 0x46
_NO_SUCH_OBJECT_TAG = 0x80
_NO_SUCH_INSTANCE_TAG = 0x81
_END_OF_MIB_VIEW_TAG = 0x82


def encode_value(value: SnmpValueType) -> bytes:
    """Encode an SNMP value object to BER."""
    if isinstance(value, IntegerValue):
        return encode_tlv(_INTEGER_TAG, _encode_signed_integer(value.value))
    if isinstance(value, OctetStringValue):
        return encode_tlv(_OCTET_STRING_TAG, value.value)
    if isinstance(value, NullValue):
        return encode_tlv(_NULL_TAG, b"")
    if isinstance(value, ObjectIdentifierValue):
        return encode_tlv(_OBJECT_IDENTIFIER_TAG, _encode_oid(value.value))
    if isinstance(value, IpAddressValue):
        return encode_tlv(_IP_ADDRESS_TAG, _encode_ip_address(value.value))
    if isinstance(value, Counter32Value):
        return encode_tlv(_COUNTER32_TAG, _encode_unsigned_integer(value.value))
    if isinstance(value, Gauge32Value):
        return encode_tlv(_GAUGE32_TAG, _encode_unsigned_integer(value.value))
    if isinstance(value, TimeTicksValue):
        return encode_tlv(_TIMETICKS_TAG, _encode_unsigned_integer(value.value))
    if isinstance(value, OpaqueValue):
        return encode_tlv(_OPAQUE_TAG, value.value)
    if isinstance(value, Counter64Value):
        return encode_tlv(_COUNTER64_TAG, _encode_unsigned_integer(value.value))
    if isinstance(value, NoSuchObjectValue):
        return encode_tlv(_NO_SUCH_OBJECT_TAG, b"")
    if isinstance(value, NoSuchInstanceValue):
        return encode_tlv(_NO_SUCH_INSTANCE_TAG, b"")
    if isinstance(value, EndOfMibViewValue):
        return encode_tlv(_END_OF_MIB_VIEW_TAG, b"")
    raise ProtocolError(f"Unsupported SNMP value type: {type(value)!r}")


def decode_value(data: bytes) -> SnmpValueType:
    """Decode a BER-encoded SNMP value object."""
    tag, content, offset = decode_tlv(data, 0)
    expect_end(data, offset)

    if tag == _INTEGER_TAG:
        return IntegerValue(_decode_signed_integer(content))
    if tag == _OCTET_STRING_TAG:
        return OctetStringValue(content)
    if tag == _NULL_TAG:
        _require_empty(content, tag=tag)
        return NullValue()
    if tag == _OBJECT_IDENTIFIER_TAG:
        return ObjectIdentifierValue(_decode_oid(content))
    if tag == _IP_ADDRESS_TAG:
        return IpAddressValue(_decode_ip_address(content))
    if tag == _COUNTER32_TAG:
        return Counter32Value(_decode_unsigned_integer(content))
    if tag == _GAUGE32_TAG:
        return Gauge32Value(_decode_unsigned_integer(content))
    if tag == _TIMETICKS_TAG:
        return TimeTicksValue(_decode_unsigned_integer(content))
    if tag == _OPAQUE_TAG:
        return OpaqueValue(content)
    if tag == _COUNTER64_TAG:
        return Counter64Value(_decode_unsigned_integer(content))
    if tag == _NO_SUCH_OBJECT_TAG:
        _require_empty(content, tag=tag)
        return NoSuchObjectValue()
    if tag == _NO_SUCH_INSTANCE_TAG:
        _require_empty(content, tag=tag)
        return NoSuchInstanceValue()
    if tag == _END_OF_MIB_VIEW_TAG:
        _require_empty(content, tag=tag)
        return EndOfMibViewValue()
    raise ProtocolError(f"Unsupported SNMP value tag 0x{tag:02x}")


def _encode_signed_integer(value: int) -> bytes:
    if value == 0:
        return b"\x00"
    length = max(1, (value.bit_length() + 8) // 8)
    encoded = value.to_bytes(length, "big", signed=True)
    while len(encoded) > 1 and (
        (encoded[0] == 0x00 and (encoded[1] & 0x80) == 0)
        or (encoded[0] == 0xFF and (encoded[1] & 0x80) == 0x80)
    ):
        encoded = encoded[1:]
    return encoded


def _decode_signed_integer(content: bytes) -> int:
    if not content:
        raise ProtocolError("INTEGER content cannot be empty")
    return int.from_bytes(content, "big", signed=True)


def _encode_unsigned_integer(value: int) -> bytes:
    if value < 0:
        raise ProtocolError("Unsigned SNMP values cannot be negative")
    if value == 0:
        return b"\x00"
    encoded = value.to_bytes((value.bit_length() + 7) // 8, "big")
    if encoded[0] & 0x80:
        encoded = b"\x00" + encoded
    return encoded


def _decode_unsigned_integer(content: bytes) -> int:
    if not content:
        raise ProtocolError("Unsigned integer content cannot be empty")
    return int.from_bytes(content, "big", signed=False)


def _encode_oid(oid: tuple[int, ...]) -> bytes:
    if len(oid) < 2:
        raise ProtocolError("OBJECT IDENTIFIER requires at least two arcs")
    if oid[0] > 2:
        raise ProtocolError("First OID arc must be 0, 1, or 2")
    if oid[0] < 2 and oid[1] >= 40:
        raise ProtocolError("Second OID arc must be < 40 when the first arc is 0 or 1")

    content = bytearray([oid[0] * 40 + oid[1]])
    for arc in oid[2:]:
        if arc < 0:
            raise ProtocolError("OID arcs cannot be negative")
        content.extend(_encode_base128(arc))
    return bytes(content)


def _decode_oid(content: bytes) -> tuple[int, ...]:
    if not content:
        raise ProtocolError("OBJECT IDENTIFIER content cannot be empty")
    first = content[0]
    if first < 40:
        first_arc, second_arc = 0, first
    elif first < 80:
        first_arc, second_arc = 1, first - 40
    else:
        first_arc, second_arc = 2, first - 80

    arcs = [first_arc, second_arc]
    offset = 1
    while offset < len(content):
        arc, offset = _decode_base128(content, offset)
        arcs.append(arc)
    return tuple(arcs)


def _encode_base128(value: int) -> bytes:
    if value == 0:
        return b"\x00"
    chunks: list[int] = []
    while value:
        chunks.append(value & 0x7F)
        value >>= 7
    encoded = bytearray()
    for index, chunk in enumerate(reversed(chunks)):
        if index < len(chunks) - 1:
            encoded.append(0x80 | chunk)
        else:
            encoded.append(chunk)
    return bytes(encoded)


def _decode_base128(content: bytes, offset: int) -> tuple[int, int]:
    value = 0
    while True:
        if offset >= len(content):
            raise ProtocolError("Truncated base-128 value")
        byte = content[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if (byte & 0x80) == 0:
            return value, offset


def _encode_ip_address(value: str) -> bytes:
    parts = value.split(".")
    if len(parts) != 4:
        raise ProtocolError(f"IPv4 address must contain four octets: {value!r}")
    try:
        octets = [int(part) for part in parts]
    except ValueError as exc:
        raise ProtocolError(f"IPv4 address contains a non-numeric octet: {value!r}") from exc
    if any(octet < 0 or octet > 255 for octet in octets):
        raise ProtocolError(f"IPv4 octets must be between 0 and 255: {value!r}")
    return bytes(octets)


def _decode_ip_address(content: bytes) -> str:
    if len(content) != 4:
        raise ProtocolError("IpAddress values must contain exactly four octets")
    return ".".join(str(octet) for octet in content)


def _require_empty(content: bytes, *, tag: int) -> None:
    if content:
        raise ProtocolError(f"Zero-length value expected for tag 0x{tag:02x}")
