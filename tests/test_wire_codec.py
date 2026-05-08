from __future__ import annotations

from trishul_snmp.types import NullValue, OctetStringValue, TimeTicksValue
from trishul_snmp.wire.message import SnmpMessage, decode_message, encode_message
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind, build_null_varbinds, build_raw_varbinds


def test_snmp_get_message_roundtrip() -> None:
    message = SnmpMessage(
        version=1,
        community="public",
        pdu=Pdu(
            pdu_type=PduType.GET,
            request_id=123,
            error_status=0,
            error_index=0,
            varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue()),),
        ),
    )

    encoded = encode_message(message)
    decoded = decode_message(encoded)

    assert decoded.version == 1
    assert decoded.community == "public"
    assert decoded.pdu.pdu_type is PduType.GET
    assert decoded.pdu.request_id == 123
    assert decoded.pdu.varbinds[0].oid == (1, 3, 6, 1, 2, 1, 1, 3, 0)
    assert isinstance(decoded.pdu.varbinds[0].value, NullValue)


def test_snmp_response_message_roundtrip() -> None:
    message = SnmpMessage(
        version=1,
        community="public",
        pdu=Pdu(
            pdu_type=PduType.RESPONSE,
            request_id=99,
            error_status=0,
            error_index=0,
            varbinds=(
                RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=TimeTicksValue(12345)),
                RawVarBind(
                    oid=(1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 1),
                    value=OctetStringValue(b"eth0"),
                ),
            ),
        ),
    )

    encoded = encode_message(message)
    decoded = decode_message(encoded)

    assert decoded.pdu.pdu_type is PduType.RESPONSE
    assert decoded.pdu.request_id == 99
    assert isinstance(decoded.pdu.varbinds[0].value, TimeTicksValue)
    assert decoded.pdu.varbinds[0].value.value == 12345
    assert isinstance(decoded.pdu.varbinds[1].value, OctetStringValue)
    assert decoded.pdu.varbinds[1].value.value == b"eth0"


def test_raw_varbind_builder_helpers() -> None:
    null_varbinds = build_null_varbinds(((1, 3, 6), (1, 3, 7)))
    explicit_varbinds = build_raw_varbinds(
        [
            ((1, 3, 6, 1), OctetStringValue(b"eth0")),
            ((1, 3, 6, 2), TimeTicksValue(42)),
        ]
    )

    assert len(null_varbinds) == 2
    assert isinstance(null_varbinds[0].value, NullValue)
    assert explicit_varbinds[0].oid == (1, 3, 6, 1)
    assert isinstance(explicit_varbinds[0].value, OctetStringValue)
    assert isinstance(explicit_varbinds[1].value, TimeTicksValue)
