from __future__ import annotations

import pytest

from trishul_snmp.errors import ProtocolError
from trishul_snmp.types import NullValue
from trishul_snmp.wire.ber import decode_length, decode_tlv, encode_tlv
from trishul_snmp.wire.message import SnmpMessage, decode_message, encode_message
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
