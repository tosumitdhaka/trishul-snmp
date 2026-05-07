"""SNMP message models and codecs."""

from __future__ import annotations

from dataclasses import dataclass

from trishul_snmp.errors import ProtocolError
from trishul_snmp.wire.ber import decode_tlv, encode_tlv, expect_end
from trishul_snmp.wire.pdu import Pdu, decode_pdu, encode_pdu

_SEQUENCE_TAG = 0x30
_INTEGER_TAG = 0x02
_OCTET_STRING_TAG = 0x04
_SNMP_V2C_VERSION = 1


@dataclass(frozen=True, slots=True)
class SnmpMessage:
    """Low-level SNMP message."""

    version: int
    community: str
    pdu: Pdu


def encode_message(message: SnmpMessage) -> bytes:
    """Encode an SNMP message."""
    content = b"".join(
        [
            _encode_integer(message.version),
            _encode_octet_string(message.community.encode("utf-8")),
            encode_pdu(message.pdu),
        ]
    )
    return encode_tlv(_SEQUENCE_TAG, content)


def decode_message(data: bytes) -> SnmpMessage:
    """Decode an SNMP message."""
    tag, content, offset = decode_tlv(data, 0)
    if tag != _SEQUENCE_TAG:
        raise ProtocolError(f"Expected SNMP message SEQUENCE, found 0x{tag:02x}")
    expect_end(data, offset)

    inner_offset = 0
    version, inner_offset = _decode_integer(content, inner_offset)
    community, inner_offset = _decode_octet_string(content, inner_offset)
    pdu_tag, pdu_content, pdu_offset = decode_tlv(content, inner_offset)
    pdu = decode_pdu(bytes([pdu_tag]) + _reencode_length_prefixed(pdu_content))
    inner_offset = pdu_offset
    expect_end(content, inner_offset)
    if version != _SNMP_V2C_VERSION:
        raise ProtocolError(f"Unsupported SNMP version {version}")
    return SnmpMessage(version=version, community=community, pdu=pdu)


def _encode_integer(value: int) -> bytes:
    from trishul_snmp.types import IntegerValue
    from trishul_snmp.wire.asn1 import encode_value

    return encode_value(IntegerValue(value))


def _encode_octet_string(value: bytes) -> bytes:
    from trishul_snmp.types import OctetStringValue
    from trishul_snmp.wire.asn1 import encode_value

    return encode_value(OctetStringValue(value))


def _decode_integer(data: bytes, offset: int) -> tuple[int, int]:
    tag, content, new_offset = decode_tlv(data, offset)
    if tag != _INTEGER_TAG:
        raise ProtocolError(f"Expected INTEGER tag, found 0x{tag:02x}")
    if not content:
        raise ProtocolError("INTEGER content cannot be empty")
    return int.from_bytes(content, "big", signed=True), new_offset


def _decode_octet_string(data: bytes, offset: int) -> tuple[str, int]:
    tag, content, new_offset = decode_tlv(data, offset)
    if tag != _OCTET_STRING_TAG:
        raise ProtocolError(f"Expected OCTET STRING tag, found 0x{tag:02x}")
    try:
        return content.decode("utf-8"), new_offset
    except UnicodeDecodeError as exc:
        raise ProtocolError("SNMP OCTET STRING contained invalid UTF-8 text") from exc


def _reencode_length_prefixed(content: bytes) -> bytes:
    from trishul_snmp.wire.ber import encode_length

    return encode_length(len(content)) + content
