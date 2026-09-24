"""Hypothesis property tests for the BER wire decoder.

The v1/v2c wire decoder (``trishul_snmp.wire.asn1`` + ``wire.message``) parses
untrusted network input. These tests pin two safety properties:

* arbitrary input bytes never crash the decoder with an unexpected exception —
  every input either decodes or raises a :class:`ProtocolError`;
* every supported SNMP value type survives an encode -> decode round trip.

The decode path (``ber.py`` -> ``asn1.py`` -> ``pdu.py`` -> ``message.py``) is
fully iterative, so ``RecursionError`` is impossible by construction and no
recursion-limit handling is required here.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from trishul_snmp.errors import ProtocolError
from trishul_snmp.types import (
    Counter32Value,
    Counter64Value,
    Gauge32Value,
    IntegerValue,
    IpAddressValue,
    NullValue,
    ObjectIdentifierValue,
    OctetStringValue,
    OpaqueValue,
    TimeTicksValue,
)
from trishul_snmp.wire.asn1 import _decode_oid, decode_value, encode_value
from trishul_snmp.wire.ber import decode_length, decode_tlv
from trishul_snmp.wire.message import decode_message
from trishul_snmp.wire.pdu import decode_pdu

_INT_MIN = -(1 << 31)
_INT_MAX = (1 << 31) - 1
_UINT32_MAX = (1 << 32) - 1
_UINT64_MAX = (1 << 64) - 1
_OID_ARC_MAX = (1 << 32) - 1

_UINT32_STRATEGY = st.integers(min_value=0, max_value=_UINT32_MAX)


@st.composite
def _valid_oids(draw: st.DrawFn) -> tuple[int, ...]:
    first = draw(st.integers(min_value=0, max_value=2))
    second = draw(st.integers(min_value=0, max_value=39))
    tail = draw(st.lists(st.integers(min_value=0, max_value=_OID_ARC_MAX), max_size=8))
    return (first, second, *tail)


@st.composite
def _ipv4_addresses(draw: st.DrawFn) -> str:
    octets = draw(st.lists(st.integers(min_value=0, max_value=255), min_size=4, max_size=4))
    return ".".join(str(octet) for octet in octets)


# --------------------------------------------------------------------------- #
# Fuzz properties: arbitrary input never leaks an unexpected exception.
# --------------------------------------------------------------------------- #


@settings(max_examples=200, deadline=None)
@given(data=st.binary(max_size=4096))
def test_decode_message_never_leaks_unexpected_exceptions(data: bytes) -> None:
    try:
        decode_message(data)
    except ProtocolError:
        pass


@settings(max_examples=100, deadline=None)
@given(data=st.binary(max_size=4096))
def test_decode_pdu_never_leaks_unexpected_exceptions(data: bytes) -> None:
    try:
        decode_pdu(data)
    except ProtocolError:
        pass


@settings(max_examples=100, deadline=None)
@given(data=st.binary(max_size=4096))
def test_decode_value_never_leaks_unexpected_exceptions(data: bytes) -> None:
    try:
        decode_value(data)
    except ProtocolError:
        pass


@settings(max_examples=100, deadline=None)
@given(data=st.binary(max_size=4096))
def test_decode_tlv_never_leaks_unexpected_exceptions(data: bytes) -> None:
    try:
        decode_tlv(data, 0)
    except ProtocolError:
        pass


@settings(max_examples=100, deadline=None)
@given(data=st.binary(max_size=4096))
def test_decode_length_never_leaks_unexpected_exceptions(data: bytes) -> None:
    try:
        decode_length(data, 0)
    except ProtocolError:
        pass


@settings(max_examples=100, deadline=None)
@given(data=st.binary(max_size=4096))
def test_decode_oid_never_leaks_unexpected_exceptions(data: bytes) -> None:
    try:
        _decode_oid(data)
    except ProtocolError:
        pass


# --------------------------------------------------------------------------- #
# Round-trip properties for every SNMP value type.
# --------------------------------------------------------------------------- #


@settings(max_examples=100)
@given(value=st.integers(min_value=_INT_MIN, max_value=_INT_MAX))
def test_integer_round_trip(value: int) -> None:
    assert decode_value(encode_value(IntegerValue(value))) == IntegerValue(value)


@settings(max_examples=100)
@given(value=st.binary())
def test_octet_string_round_trip(value: bytes) -> None:
    assert decode_value(encode_value(OctetStringValue(value))) == OctetStringValue(value)


def test_null_round_trip() -> None:
    assert decode_value(encode_value(NullValue())) == NullValue()


@settings(max_examples=100)
@given(oid=_valid_oids())
def test_oid_round_trip(oid: tuple[int, ...]) -> None:
    assert decode_value(encode_value(ObjectIdentifierValue(oid))) == ObjectIdentifierValue(oid)


@settings(max_examples=100)
@given(value=_UINT32_STRATEGY)
def test_counter32_round_trip(value: int) -> None:
    assert decode_value(encode_value(Counter32Value(value))) == Counter32Value(value)


@settings(max_examples=100)
@given(value=_UINT32_STRATEGY)
def test_gauge32_round_trip(value: int) -> None:
    # SMIv2 Unsigned32 shares Gauge32's BER tag (0x42) and unsigned-32-bit
    # encoding, so this round trip also pins the Unsigned32 wire format.
    assert decode_value(encode_value(Gauge32Value(value))) == Gauge32Value(value)


@settings(max_examples=100)
@given(value=_UINT32_STRATEGY)
def test_timeticks_round_trip(value: int) -> None:
    assert decode_value(encode_value(TimeTicksValue(value))) == TimeTicksValue(value)


@settings(max_examples=100)
@given(value=st.integers(min_value=0, max_value=_UINT64_MAX))
def test_counter64_round_trip(value: int) -> None:
    assert decode_value(encode_value(Counter64Value(value))) == Counter64Value(value)


@settings(max_examples=100)
@given(value=st.binary())
def test_opaque_round_trip(value: bytes) -> None:
    assert decode_value(encode_value(OpaqueValue(value))) == OpaqueValue(value)


@settings(max_examples=100)
@given(address=_ipv4_addresses())
def test_ip_address_round_trip(address: str) -> None:
    assert decode_value(encode_value(IpAddressValue(address))) == IpAddressValue(address)


# --------------------------------------------------------------------------- #
# Boundary-length inputs.
# --------------------------------------------------------------------------- #


def test_decode_message_rejects_empty_payload() -> None:
    with pytest.raises(ProtocolError):
        decode_message(b"")


def test_decode_message_rejects_empty_sequence() -> None:
    with pytest.raises(ProtocolError):
        decode_message(b"\x30\x00")


def test_decode_pdu_rejects_empty_payload() -> None:
    with pytest.raises(ProtocolError):
        decode_pdu(b"")


def test_decode_value_rejects_empty_payload() -> None:
    with pytest.raises(ProtocolError):
        decode_value(b"")


def test_decode_tlv_rejects_length_claim_beyond_payload() -> None:
    # Long-form length prefix claims 16 content bytes but only 1 is present.
    with pytest.raises(ProtocolError):
        decode_tlv(b"\x04\x83\x00\x00\x10\xaa")


def test_decode_tlv_accepts_maximum_short_form_length() -> None:
    tag, content, offset = decode_tlv(b"\x04\x7f" + b"\x00" * 127)
    assert tag == 0x04
    assert content == b"\x00" * 127
    assert offset == 129


def test_decode_tlv_accepts_minimal_long_form_length() -> None:
    tag, content, offset = decode_tlv(b"\x04\x81\x80" + b"\x00" * 128)
    assert tag == 0x04
    assert content == b"\x00" * 128
    assert offset == 131
