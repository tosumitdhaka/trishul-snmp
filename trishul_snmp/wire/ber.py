"""Minimal BER helpers for SNMP."""

from __future__ import annotations

from trishul_snmp.errors import ProtocolError


def encode_length(length: int) -> bytes:
    """Encode a BER length field."""
    if length < 0:
        raise ProtocolError("BER length cannot be negative")
    if length < 0x80:
        return bytes([length])
    content = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(content)]) + content


def decode_length(data: bytes, offset: int) -> tuple[int, int]:
    """Decode a BER length field."""
    if offset >= len(data):
        raise ProtocolError("BER length is truncated")
    first = data[offset]
    offset += 1
    if first < 0x80:
        return first, offset

    count = first & 0x7F
    if count == 0:
        raise ProtocolError("Indefinite BER lengths are not supported")
    end = offset + count
    if end > len(data):
        raise ProtocolError("BER length payload is truncated")
    return int.from_bytes(data[offset:end], "big"), end


def encode_tlv(tag: int, content: bytes) -> bytes:
    """Encode a BER TLV value."""
    return bytes([tag]) + encode_length(len(content)) + content


def decode_tlv(data: bytes, offset: int = 0) -> tuple[int, bytes, int]:
    """Decode a BER TLV value."""
    if offset >= len(data):
        raise ProtocolError("BER tag is truncated")
    tag = data[offset]
    length, content_offset = decode_length(data, offset + 1)
    end = content_offset + length
    if end > len(data):
        raise ProtocolError("BER content is truncated")
    return tag, data[content_offset:end], end


def expect_end(data: bytes, offset: int) -> None:
    """Require *offset* to point at the end of *data*."""
    if offset != len(data):
        raise ProtocolError("Unexpected trailing BER content")
