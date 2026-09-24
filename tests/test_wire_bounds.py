from __future__ import annotations

import pytest

from trishul_snmp.errors import ProtocolError
from trishul_snmp.types import (
    Counter32Value,
    Counter64Value,
    Gauge32Value,
    TimeTicksValue,
)
from trishul_snmp.wire.asn1 import (
    _decode_base128,
    _decode_oid,
    _decode_unsigned_integer,
    _encode_base128,
    _encode_oid,
    _encode_unsigned_integer,
    decode_value,
    encode_value,
)

_UINT32_MAX = (1 << 32) - 1
_UINT64_MAX = (1 << 64) - 1


def test_encode_unsigned_integer_accepts_exact_bound() -> None:
    assert _encode_unsigned_integer(_UINT32_MAX) == b"\x00\xff\xff\xff\xff"
    assert _encode_unsigned_integer(_UINT64_MAX) == b"\x00" + b"\xff" * 8


def test_encode_unsigned_integer_rejects_value_beyond_bound() -> None:
    with pytest.raises(
        ProtocolError,
        match="Counter64 value 1180591620717411303424 exceeds maximum 18446744073709551615",
    ):
        _encode_unsigned_integer(2**70, max_value=_UINT64_MAX, field="Counter64")


@pytest.mark.parametrize(
    ("value", "field"),
    [
        (Counter32Value(_UINT32_MAX + 1), "Counter32"),
        (Gauge32Value(_UINT32_MAX + 1), "Gauge32"),
        (TimeTicksValue(_UINT32_MAX + 1), "TimeTicks"),
        (Counter64Value(_UINT64_MAX + 1), "Counter64"),
    ],
)
def test_encode_value_rejects_unsigned_values_beyond_bound(value, field: str) -> None:
    with pytest.raises(ProtocolError, match=f"{field} value .* exceeds maximum"):
        encode_value(value)


def test_encode_value_rejects_counter64_two_pow_seventy() -> None:
    with pytest.raises(
        ProtocolError, match="Counter64 value 1180591620717411303424 exceeds maximum"
    ):
        encode_value(Counter64Value(2**70))


@pytest.mark.parametrize(
    "value",
    [
        Counter32Value(_UINT32_MAX),
        Gauge32Value(_UINT32_MAX),
        TimeTicksValue(_UINT32_MAX),
        Counter64Value(_UINT64_MAX),
    ],
)
def test_encode_value_accepts_exact_unsigned_bounds(value) -> None:
    assert decode_value(encode_value(value)) == value


def test_encode_value_counter64_max_uses_minimal_encoding() -> None:
    assert encode_value(Counter64Value(_UINT64_MAX)).hex() == "460900ffffffffffffffff"
    assert encode_value(Counter32Value(_UINT32_MAX)).hex() == "410500ffffffff"


@pytest.mark.parametrize(
    "content",
    [
        b"\x00\x01",
        b"\x00\x00",
        b"\x00\x00\x80",
        b"\x00\x00\xff\xff\xff\xff",
    ],
)
def test_decode_unsigned_integer_rejects_non_minimal_encoding(content: bytes) -> None:
    with pytest.raises(ProtocolError, match="not minimally encoded"):
        _decode_unsigned_integer(content)


def test_decode_value_rejects_non_minimal_counter32() -> None:
    with pytest.raises(ProtocolError, match="Counter32 content is not minimally encoded"):
        decode_value(b"\x41\x02\x00\x01")


def test_decode_unsigned_integer_rejects_value_beyond_uint64() -> None:
    with pytest.raises(
        ProtocolError,
        match="Counter64 value 18446744073709551616 exceeds maximum 18446744073709551615",
    ):
        _decode_unsigned_integer(
            (1 << 64).to_bytes(9, "big"), max_value=_UINT64_MAX, field="Counter64"
        )


def test_decode_value_rejects_counter64_beyond_bound() -> None:
    with pytest.raises(ProtocolError, match="Counter64 value 18446744073709551616 exceeds maximum"):
        decode_value(b"\x46\x09" + (1 << 64).to_bytes(9, "big"))


def test_decode_value_rejects_counter32_beyond_bound() -> None:
    with pytest.raises(ProtocolError, match="Counter32 value 4294967296 exceeds maximum"):
        decode_value(b"\x41\x05" + (1 << 32).to_bytes(5, "big"))


def test_encode_oid_rejects_second_arc_over_39_under_first_arc_two() -> None:
    with pytest.raises(ProtocolError, match="Second OID arc must be < 40"):
        _encode_oid((2, 40))


def test_encode_oid_accepts_second_arc_39_under_first_arc_two() -> None:
    assert _encode_oid((2, 39)) == b"\x77"
    assert _decode_oid(b"\x77") == (2, 39)


def test_encode_oid_rejects_first_arc_beyond_two() -> None:
    with pytest.raises(ProtocolError, match="First OID arc must be 0, 1, or 2"):
        _encode_oid((3, 0))


def test_encode_oid_rejects_arc_beyond_uint32_bound() -> None:
    with pytest.raises(ProtocolError, match="OID arc 4294967296 exceeds maximum 4294967295"):
        _encode_oid((1, 3, 1 << 32))


def test_encode_and_decode_oid_accept_large_arc_up_to_uint32_bound() -> None:
    encoded = _encode_base128(_UINT32_MAX)
    assert _decode_base128(encoded, 0) == (_UINT32_MAX, len(encoded))
    assert _encode_oid((1, 3, _UINT32_MAX)) == b"\x2b" + encoded
    assert _decode_oid(b"\x2b" + encoded) == (1, 3, _UINT32_MAX)


def test_decode_oid_rejects_arc_beyond_uint32_bound() -> None:
    with pytest.raises(
        ProtocolError, match="OID subidentifier 4294967296 exceeds maximum 4294967295"
    ):
        _decode_oid(b"\x2b" + _encode_base128(1 << 32))
