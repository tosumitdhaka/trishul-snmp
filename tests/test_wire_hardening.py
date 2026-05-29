from __future__ import annotations

import pytest

from trishul_snmp.errors import ProtocolError
from trishul_snmp.types import NullValue
from trishul_snmp.wire.ber import decode_length, decode_tlv, encode_tlv
from trishul_snmp.wire.message import (
    SnmpMessage,
    decode_message,
    encode_message,
)
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind, decode_pdu, encode_pdu


def _valid_pdu_bytes() -> bytes:
    return encode_pdu(
        Pdu(
            pdu_type=PduType.GET,
            request_id=1,
            error_status=0,
            error_index=0,
            varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue()),),
        )
    )


def test_decode_length_rejects_indefinite_form() -> None:
    with pytest.raises(ProtocolError, match="Indefinite BER lengths are not supported"):
        decode_length(b"\x80", 0)


def test_decode_tlv_rejects_truncated_content() -> None:
    with pytest.raises(ProtocolError, match="BER content is truncated"):
        decode_tlv(b"\x02\x02\x01", 0)


def test_decode_message_rejects_unsupported_version() -> None:
    encoded = encode_message(
        SnmpMessage(
            version=0,
            community="public",
            pdu=Pdu(
                pdu_type=PduType.GET,
                request_id=1,
                error_status=0,
                error_index=0,
                varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue()),),
            ),
        )
    )

    with pytest.raises(ProtocolError, match="Unsupported SNMP version 0"):
        decode_message(encoded)


def test_decode_message_rejects_empty_integer_content() -> None:
    encoded = encode_tlv(
        0x30,
        b"".join(
            [
                encode_tlv(0x02, b""),
                encode_tlv(0x04, b"public"),
                _valid_pdu_bytes(),
            ]
        ),
    )

    with pytest.raises(ProtocolError, match="INTEGER content cannot be empty"):
        decode_message(encoded)


def test_decode_message_rejects_invalid_community_text() -> None:
    encoded = encode_tlv(
        0x30,
        b"".join(
            [
                encode_tlv(0x02, b"\x01"),
                encode_tlv(0x04, b"\xff"),
                _valid_pdu_bytes(),
            ]
        ),
    )

    with pytest.raises(ProtocolError, match="invalid UTF-8"):
        decode_message(encoded)


def _valid_message_bytes() -> bytes:
    return encode_message(
        SnmpMessage(
            version=1,
            community="public",
            pdu=Pdu(
                pdu_type=PduType.GET,
                request_id=1,
                error_status=0,
                error_index=0,
                varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue()),),
            ),
        )
    )


def test_decode_message_rejects_wrong_request_id_tag() -> None:
    data = bytearray(_valid_message_bytes())
    # The PDU tag is 0xA0; the first byte inside PDU content is the request_id INTEGER tag.
    pdu_start = data.index(0xA0) + 2  # skip PDU tag + 1-byte length
    data[pdu_start] = 0x04  # replace INTEGER (0x02) with OCTET STRING (0x04)
    with pytest.raises(ProtocolError):
        decode_message(bytes(data))


def test_decode_message_rejects_wrong_oid_tag() -> None:
    data = bytearray(_valid_message_bytes())
    data[data.index(0x06)] = 0x02  # replace OID tag with INTEGER tag
    with pytest.raises(ProtocolError):
        decode_message(bytes(data))


def test_decode_message_rejects_trailing_bytes() -> None:
    data = _valid_message_bytes() + b"\x00"
    with pytest.raises(ProtocolError, match="Unexpected trailing BER content"):
        decode_message(data)


def test_encode_message_rejects_invalid_oid_first_arc() -> None:
    msg = SnmpMessage(
        version=1,
        community="public",
        pdu=Pdu(
            pdu_type=PduType.GET,
            request_id=1,
            error_status=0,
            error_index=0,
            varbinds=(RawVarBind(oid=(3, 0), value=NullValue()),),
        ),
    )
    with pytest.raises(ProtocolError, match="First OID arc"):
        encode_message(msg)


def test_encode_message_rejects_negative_oid_arc() -> None:
    msg = SnmpMessage(
        version=1,
        community="public",
        pdu=Pdu(
            pdu_type=PduType.GET,
            request_id=1,
            error_status=0,
            error_index=0,
            varbinds=(RawVarBind(oid=(1, 3, -1), value=NullValue()),),
        ),
    )
    with pytest.raises(ProtocolError, match="OID arcs cannot be negative"):
        encode_message(msg)


def test_decode_pdu_rejects_empty_integer_content() -> None:
    encoded = encode_tlv(
        int(PduType.GET),
        b"".join(
            [
                encode_tlv(0x02, b""),
                encode_tlv(0x02, b"\x00"),
                encode_tlv(0x02, b"\x00"),
                encode_tlv(0x30, b""),
            ]
        ),
    )

    with pytest.raises(ProtocolError, match="INTEGER content cannot be empty"):
        decode_pdu(encoded)
