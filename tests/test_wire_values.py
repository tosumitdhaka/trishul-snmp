from __future__ import annotations

import pytest

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
    TimeTicksValue,
)
from trishul_snmp.wire.asn1 import (
    _decode_base128,
    _decode_ip_address,
    _decode_oid,
    _decode_signed_integer,
    _decode_unsigned_integer,
    _encode_base128,
    _encode_ip_address,
    _encode_oid,
    _encode_signed_integer,
    _encode_unsigned_integer,
    _require_empty,
    decode_value,
    encode_value,
)
from trishul_snmp.wire.ber import decode_length, decode_tlv, encode_length, encode_tlv, expect_end
from trishul_snmp.wire.message import decode_message
from trishul_snmp.wire.pdu import (
    Pdu,
    PduType,
    RawVarBind,
    decode_pdu,
    encode_pdu,
    response_error_status,
)


def _valid_varbind() -> RawVarBind:
    return RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue())


def _valid_pdu_payload() -> bytes:
    varbind_content = encode_value(ObjectIdentifierValue((1, 3, 6, 1))) + encode_value(NullValue())
    return b"".join(
        [
            encode_tlv(0x02, b"\x01"),
            encode_tlv(0x02, b"\x00"),
            encode_tlv(0x02, b"\x00"),
            encode_tlv(0x30, encode_tlv(0x30, varbind_content)),
        ]
    )


@pytest.mark.parametrize(
    ("value", "encoded_hex"),
    [
        (IntegerValue(-128), "020180"),
        (IntegerValue(128), "02020080"),
        (OctetStringValue(b"eth0"), "040465746830"),
        (NullValue(), "0500"),
        (ObjectIdentifierValue((1, 3, 6, 1, 4, 1, 128)), "06072b060104018100"),
        (IpAddressValue("192.0.2.1"), "4004c0000201"),
        (Counter32Value(128), "41020080"),
        (Gauge32Value(7), "420107"),
        (TimeTicksValue(12345), "43023039"),
        (OpaqueValue(b"\x00\xff"), "440200ff"),
        (Counter64Value(2**40), "4606010000000000"),
        (NoSuchObjectValue(), "8000"),
        (NoSuchInstanceValue(), "8100"),
        (EndOfMibViewValue(), "8200"),
    ],
)
def test_encode_value_roundtrip_for_supported_types(value, encoded_hex: str) -> None:
    encoded = encode_value(value)

    assert encoded.hex() == encoded_hex
    assert decode_value(encoded) == value


def test_encode_value_rejects_unsupported_type() -> None:
    with pytest.raises(ProtocolError, match="Unsupported SNMP value type"):
        encode_value(object())  # type: ignore[arg-type]


def test_decode_value_rejects_unsupported_tag() -> None:
    with pytest.raises(ProtocolError, match="Unsupported SNMP value tag 0x7f"):
        decode_value(b"\x7f\x00")


def test_encode_signed_integer_handles_negative_trim_case() -> None:
    assert _encode_signed_integer(-128) == b"\x80"
    assert _encode_signed_integer(-32768) == b"\x80\x00"


def test_decode_signed_integer_rejects_empty_content() -> None:
    with pytest.raises(ProtocolError, match="INTEGER content cannot be empty"):
        _decode_signed_integer(b"")


def test_encode_unsigned_integer_handles_zero_and_leading_sign_bit() -> None:
    assert _encode_unsigned_integer(0) == b"\x00"
    assert _encode_unsigned_integer(128) == b"\x00\x80"


def test_encode_unsigned_integer_rejects_negative_values() -> None:
    with pytest.raises(ProtocolError, match="cannot be negative"):
        _encode_unsigned_integer(-1)


def test_decode_unsigned_integer_rejects_empty_content() -> None:
    with pytest.raises(ProtocolError, match="Unsigned integer content cannot be empty"):
        _decode_unsigned_integer(b"")


def test_encode_oid_rejects_invalid_shapes() -> None:
    with pytest.raises(ProtocolError, match="requires at least two arcs"):
        _encode_oid((1,))
    with pytest.raises(ProtocolError, match="First OID arc must be 0, 1, or 2"):
        _encode_oid((3, 0))
    with pytest.raises(ProtocolError, match="Second OID arc must be < 40"):
        _encode_oid((1, 40))
    with pytest.raises(ProtocolError, match="OID arcs cannot be negative"):
        _encode_oid((1, 3, -1))


def test_decode_oid_handles_all_first_arc_ranges_and_rejects_empty_content() -> None:
    assert _decode_oid(b"\x03") == (0, 3)
    assert _decode_oid(b"\x2d") == (1, 5)
    assert _decode_oid(b"\x51") == (2, 1)
    with pytest.raises(ProtocolError, match="OBJECT IDENTIFIER content cannot be empty"):
        _decode_oid(b"")


def test_encode_and_decode_base128_values() -> None:
    assert _encode_base128(0) == b"\x00"
    assert _encode_base128(128) == b"\x81\x00"
    assert _decode_base128(b"\x81\x00", 0) == (128, 2)


def test_decode_base128_rejects_truncation() -> None:
    with pytest.raises(ProtocolError, match="Truncated base-128 value"):
        _decode_base128(b"\x81", 0)


def test_encode_ip_address_rejects_invalid_shapes() -> None:
    assert _encode_ip_address("192.0.2.1") == b"\xc0\x00\x02\x01"
    with pytest.raises(ProtocolError, match="must contain four octets"):
        _encode_ip_address("192.0.2")
    with pytest.raises(ProtocolError, match="non-numeric octet"):
        _encode_ip_address("192.0.two.1")
    with pytest.raises(ProtocolError, match="between 0 and 255"):
        _encode_ip_address("256.0.2.1")


def test_decode_ip_address_rejects_invalid_length() -> None:
    assert _decode_ip_address(b"\x7f\x00\x00\x01") == "127.0.0.1"
    with pytest.raises(ProtocolError, match="exactly four octets"):
        _decode_ip_address(b"\x7f\x00\x00")


def test_require_empty_rejects_non_empty_content() -> None:
    with pytest.raises(ProtocolError, match="Zero-length value expected"):
        _require_empty(b"\x00", tag=0x80)


def test_encode_length_supports_short_and_long_forms_and_rejects_negative() -> None:
    assert encode_length(127) == b"\x7f"
    assert encode_length(128) == b"\x81\x80"
    assert encode_length(256) == b"\x82\x01\x00"
    with pytest.raises(ProtocolError, match="BER length cannot be negative"):
        encode_length(-1)


def test_decode_length_supports_short_and_long_forms_and_rejects_truncation() -> None:
    assert decode_length(b"\x7f", 0) == (127, 1)
    assert decode_length(b"\x81\x80", 0) == (128, 2)
    with pytest.raises(ProtocolError, match="BER length is truncated"):
        decode_length(b"", 0)
    with pytest.raises(ProtocolError, match="BER length payload is truncated"):
        decode_length(b"\x82\x01", 0)


def test_decode_tlv_and_expect_end_reject_invalid_framing() -> None:
    assert decode_tlv(b"\x04\x03abc") == (0x04, b"abc", 5)
    with pytest.raises(ProtocolError, match="BER tag is truncated"):
        decode_tlv(b"", 0)
    with pytest.raises(ProtocolError, match="Unexpected trailing BER content"):
        expect_end(b"\x00", 0)


def test_decode_message_rejects_invalid_message_shape() -> None:
    with pytest.raises(ProtocolError, match="Expected SNMP message SEQUENCE"):
        decode_message(b"\x02\x01\x01")

    wrong_version_tag = encode_tlv(
        0x30,
        b"".join(
            [
                encode_tlv(0x04, b"\x01"),
                encode_tlv(0x04, b"public"),
                encode_pdu(Pdu(PduType.GET, 1, 0, 0, (_valid_varbind(),))),
            ]
        ),
    )
    with pytest.raises(ProtocolError, match="Expected INTEGER tag"):
        decode_message(wrong_version_tag)

    wrong_community_tag = encode_tlv(
        0x30,
        b"".join(
            [
                encode_tlv(0x02, b"\x01"),
                encode_tlv(0x02, b"\x01"),
                encode_pdu(Pdu(PduType.GET, 1, 0, 0, (_valid_varbind(),))),
            ]
        ),
    )
    with pytest.raises(ProtocolError, match="Expected OCTET STRING tag"):
        decode_message(wrong_community_tag)


def test_decode_pdu_rejects_invalid_shapes() -> None:
    unsupported_tag = encode_tlv(0xA8, _valid_pdu_payload())
    with pytest.raises(ProtocolError, match="Unsupported PDU tag 0xa8"):
        decode_pdu(unsupported_tag)

    wrong_integer_tag = encode_tlv(
        int(PduType.GET),
        b"".join(
            [
                encode_tlv(0x04, b"\x01"),
                encode_tlv(0x02, b"\x00"),
                encode_tlv(0x02, b"\x00"),
                encode_tlv(0x30, b""),
            ]
        ),
    )
    with pytest.raises(ProtocolError, match="Expected INTEGER tag"):
        decode_pdu(wrong_integer_tag)

    wrong_varbind_list_tag = encode_tlv(
        int(PduType.GET),
        b"".join(
            [
                encode_tlv(0x02, b"\x01"),
                encode_tlv(0x02, b"\x00"),
                encode_tlv(0x02, b"\x00"),
                encode_tlv(0x02, b"\x00"),
            ]
        ),
    )
    with pytest.raises(ProtocolError, match="Expected VarBindList SEQUENCE"):
        decode_pdu(wrong_varbind_list_tag)

    wrong_varbind_tag = encode_tlv(
        int(PduType.GET),
        b"".join(
            [
                encode_tlv(0x02, b"\x01"),
                encode_tlv(0x02, b"\x00"),
                encode_tlv(0x02, b"\x00"),
                encode_tlv(0x30, encode_tlv(0x02, b"\x00")),
            ]
        ),
    )
    with pytest.raises(ProtocolError, match="Expected VarBind SEQUENCE"):
        decode_pdu(wrong_varbind_tag)

    wrong_oid_tag = encode_tlv(
        int(PduType.GET),
        b"".join(
            [
                encode_tlv(0x02, b"\x01"),
                encode_tlv(0x02, b"\x00"),
                encode_tlv(0x02, b"\x00"),
                encode_tlv(
                    0x30,
                    encode_tlv(
                        0x30,
                        encode_tlv(0x02, b"\x01") + encode_value(NullValue()),
                    ),
                ),
            ]
        ),
    )
    with pytest.raises(ProtocolError, match="Expected OBJECT IDENTIFIER"):
        decode_pdu(wrong_oid_tag)


def test_response_error_status_rejects_unknown_values() -> None:
    with pytest.raises(ProtocolError, match="Unsupported SNMP error-status value 999"):
        response_error_status(999)
