from __future__ import annotations

import pytest

from trishul_snmp.errors import ProtocolError
from trishul_snmp.types import NullValue, OctetStringValue, TimeTicksValue
from trishul_snmp.wire.ber import encode_tlv
from trishul_snmp.wire.message import SnmpMessage, decode_message, encode_message
from trishul_snmp.wire.pdu import (
    Pdu,
    PduType,
    RawVarBind,
    build_trap_pdu,
    decode_pdu,
    encode_pdu,
)

_ENTERPRISE = (1, 3, 6, 1, 4, 1, 999)
_SYS_UPTIME_OID = (1, 3, 6, 1, 2, 1, 1, 3, 0)


def _sys_uptime_varbind(timestamp: int) -> RawVarBind:
    return RawVarBind(oid=_SYS_UPTIME_OID, value=TimeTicksValue(timestamp))


def _trap_pdu(*, generic_trap: int, specific_trap: int = 0, agent_addr: str = "192.0.2.1") -> Pdu:
    return build_trap_pdu(
        enterprise=_ENTERPRISE,
        agent_addr=agent_addr,
        generic_trap=generic_trap,
        specific_trap=specific_trap,
        timestamp=123456,
        varbinds=(_sys_uptime_varbind(123456),),
    )


def _raw_trap_payload(
    *,
    generic_trap: int = 1,
    specific_trap: int = 5,
    agent_addr: bytes = b"\xcb\x00\x71\x07",
) -> bytes:
    return b"".join(
        [
            encode_tlv(0x06, b"\x2b\x06\x01\x04\x01\x87\x67"),  # enterprise 1.3.6.1.4.1.999
            encode_tlv(0x40, agent_addr),
            encode_tlv(0x02, bytes([generic_trap])),
            encode_tlv(0x02, bytes([specific_trap])),
            encode_tlv(0x43, b"\x09\xfb\xf1"),  # timestamp 654321
            encode_tlv(0x30, b""),  # empty varbind-list
        ]
    )


def test_v1_get_request_roundtrip_and_golden_bytes() -> None:
    message = SnmpMessage(
        version=0,
        community="public",
        pdu=Pdu(
            pdu_type=PduType.GET,
            request_id=123,
            error_status=0,
            error_index=0,
            varbinds=(RawVarBind(oid=_SYS_UPTIME_OID, value=NullValue()),),
        ),
    )

    encoded = encode_message(message)

    assert (
        encoded.hex()
        == "302602010004067075626c6963a01902017b020100020100300e300c06082b060102010103000500"
    )

    decoded = decode_message(encoded)
    assert decoded.version == 0
    assert decoded.community == "public"
    assert decoded.pdu.pdu_type is PduType.GET
    assert decoded.pdu.request_id == 123
    assert decoded.pdu.varbinds[0].oid == _SYS_UPTIME_OID
    assert isinstance(decoded.pdu.varbinds[0].value, NullValue)


def test_v1_get_response_roundtrip_and_golden_bytes() -> None:
    message = SnmpMessage(
        version=0,
        community="public",
        pdu=Pdu(
            pdu_type=PduType.RESPONSE,
            request_id=99,
            error_status=0,
            error_index=0,
            varbinds=(
                _sys_uptime_varbind(123456),
                RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=OctetStringValue(b"eth0")),
            ),
        ),
    )

    encoded = encode_message(message)

    assert (
        encoded.hex()
        == "303b02010004067075626c6963a22e0201630201000201003023300f06082b06010201010300430301e240"
        + "301006082b06010201010100040465746830"
    )

    decoded = decode_message(encoded)
    assert decoded.version == 0
    assert decoded.pdu.pdu_type is PduType.RESPONSE
    assert decoded.pdu.request_id == 99
    assert decoded.pdu.varbinds[0].value == TimeTicksValue(123456)
    assert decoded.pdu.varbinds[1].value == OctetStringValue(b"eth0")


def test_v1_trap_roundtrip_and_golden_bytes() -> None:
    message = SnmpMessage(version=0, community="public", pdu=_trap_pdu(generic_trap=0))

    encoded = encode_message(message)

    assert (
        encoded.hex()
        == "303a02010004067075626c6963a42d06072b0601040187674004c0000201020100020100430301e240"
        + "3011300f06082b06010201010300430301e240"
    )

    decoded = decode_message(encoded)
    assert decoded.version == 0
    assert decoded.pdu.pdu_type is PduType.TRAP
    assert decoded.pdu.enterprise == _ENTERPRISE
    assert decoded.pdu.agent_addr == "192.0.2.1"
    assert decoded.pdu.generic_trap == 0
    assert decoded.pdu.specific_trap == 0
    assert decoded.pdu.timestamp == 123456
    assert decoded.pdu.varbinds[0].oid == _SYS_UPTIME_OID


def test_v1_trap_datagram_decodes_from_raw_bytes() -> None:
    # Raw v1 trap datagram (pysnmp-comparable case from issue #8): this used to
    # fail with "ProtocolError: Unsupported PDU tag 0xa4".
    raw = bytes.fromhex(
        "303a02010004067075626c6963a42d06072b0601040187674004cb007107020101020105430309fbf1"
        "3011300f06082b06010201010300430309fbf1"
    )

    decoded = decode_message(raw)

    assert decoded.version == 0
    assert decoded.pdu.pdu_type is PduType.TRAP
    assert decoded.pdu.enterprise == _ENTERPRISE
    assert decoded.pdu.agent_addr == "203.0.113.7"
    assert decoded.pdu.generic_trap == 1
    assert decoded.pdu.specific_trap == 5
    assert decoded.pdu.timestamp == 654321
    assert decoded.pdu.varbinds[0].value == TimeTicksValue(654321)


@pytest.mark.parametrize("generic_trap", range(7))
def test_v1_trap_roundtrip_for_each_generic_trap(generic_trap: int) -> None:
    message = SnmpMessage(version=0, community="public", pdu=_trap_pdu(generic_trap=generic_trap))

    decoded = decode_message(encode_message(message))

    assert decoded.pdu.pdu_type is PduType.TRAP
    assert decoded.pdu.generic_trap == generic_trap
    assert decoded.pdu.enterprise == _ENTERPRISE
    assert decoded.pdu.timestamp == 123456


def test_decode_pdu_handles_bare_trap_pdu() -> None:
    pdu = _trap_pdu(generic_trap=6, specific_trap=42)

    assert decode_pdu(encode_pdu(pdu)) == pdu


def test_encode_rejects_generic_trap_out_of_range() -> None:
    for generic_trap in (-1, 7, 10):
        message = SnmpMessage(
            version=0, community="public", pdu=_trap_pdu(generic_trap=generic_trap)
        )
        with pytest.raises(
            ProtocolError, match=f"generic-trap {generic_trap} must be between 0 and 6"
        ):
            encode_message(message)


def test_decode_rejects_generic_trap_out_of_range() -> None:
    raw = encode_tlv(0xA4, _raw_trap_payload(generic_trap=7))
    with pytest.raises(ProtocolError, match="generic-trap 7 must be between 0 and 6"):
        decode_pdu(raw)


def test_encode_rejects_negative_specific_trap() -> None:
    message = SnmpMessage(
        version=0, community="public", pdu=_trap_pdu(generic_trap=6, specific_trap=-1)
    )
    with pytest.raises(ProtocolError, match="specific-trap -1 cannot be negative"):
        encode_message(message)


def test_decode_rejects_negative_specific_trap() -> None:
    raw = encode_tlv(0xA4, _raw_trap_payload(generic_trap=1, specific_trap=0xFF))
    with pytest.raises(ProtocolError, match="specific-trap -1 cannot be negative"):
        decode_pdu(raw)


def test_trap_agent_addr_requires_four_octets() -> None:
    message = SnmpMessage(
        version=0,
        community="public",
        pdu=_trap_pdu(generic_trap=0, agent_addr="192.0.2"),
    )
    with pytest.raises(ProtocolError, match="four octets"):
        encode_message(message)

    raw = encode_tlv(0xA4, _raw_trap_payload(agent_addr=b"\xc0\x00\x02"))
    with pytest.raises(ProtocolError, match="exactly four octets"):
        decode_pdu(raw)


def test_v1_community_latin1_fallback() -> None:
    message = SnmpMessage(version=0, community="\xff\xfe", pdu=_trap_pdu(generic_trap=0))

    decoded = decode_message(encode_message(message))

    assert decoded.community == "\xff\xfe"
    assert decoded.pdu.pdu_type is PduType.TRAP
