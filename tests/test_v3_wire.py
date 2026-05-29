"""Tests for the SNMPv3 wire codec (pure BER, no cryptography)."""

from __future__ import annotations

import pytest

from trishul_snmp.errors import ProtocolError
from trishul_snmp.types import NullValue, OctetStringValue
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind
from trishul_snmp.wire.v3message import (
    MSG_FLAG_AUTH,
    MSG_FLAG_PRIV,
    MSG_FLAG_REPORTABLE,
    UsmParams,
    decode_scoped_pdu,
    decode_v3_message,
    encode_scoped_pdu,
    encode_v3_message,
)

# ── fixtures ─────────────────────────────────────────────────────────────────


def _make_usm(
    *,
    auth_params: bytes = b"",
    priv_params: bytes = b"",
) -> UsmParams:
    return UsmParams(
        engine_id=b"\x80\x00\x1f\x88\x80" + b"\x00" * 11,
        engine_boots=5,
        engine_time=12345,
        username=b"simulator",
        auth_params=auth_params,
        priv_params=priv_params,
    )


def _make_pdu(request_id: int = 1) -> Pdu:
    return Pdu(
        pdu_type=PduType.GET,
        request_id=request_id,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )


# ── UsmParams BER encode/decode roundtrip ────────────────────────────────────


def test_usm_params_roundtrip_no_auth_no_priv() -> None:
    from trishul_snmp.wire.v3message import _decode_usm_params_with_offset, _encode_usm_params

    params = _make_usm()
    encoded = _encode_usm_params(params)
    decoded, _ = _decode_usm_params_with_offset(encoded)

    assert decoded.engine_id == params.engine_id
    assert decoded.engine_boots == params.engine_boots
    assert decoded.engine_time == params.engine_time
    assert decoded.username == params.username
    assert decoded.auth_params == b""
    assert decoded.priv_params == b""


def test_usm_params_roundtrip_with_auth_and_priv() -> None:
    from trishul_snmp.wire.v3message import _decode_usm_params_with_offset, _encode_usm_params

    params = _make_usm(auth_params=b"\xaa" * 12, priv_params=b"\xbb" * 8)
    encoded = _encode_usm_params(params)
    decoded, _ = _decode_usm_params_with_offset(encoded)

    assert decoded.auth_params == b"\xaa" * 12
    assert decoded.priv_params == b"\xbb" * 8


def test_usm_params_auth_params_offset_points_to_content() -> None:
    """auth_params_offset returned by _decode_usm_params_with_offset points at the
    content bytes (past tag+length) within the encoded UsmSecurityParameters blob."""
    from trishul_snmp.wire.v3message import _decode_usm_params_with_offset, _encode_usm_params

    sentinel = b"\xde\xad\xbe\xef\x00\x01\x02\x03\x04\x05\x06\x07"
    params = _make_usm(auth_params=sentinel)
    encoded = _encode_usm_params(params)
    _, offset = _decode_usm_params_with_offset(encoded)

    assert encoded[offset : offset + len(sentinel)] == sentinel


# ── ScopedPDU encode/decode roundtrip ────────────────────────────────────────


def test_scoped_pdu_roundtrip_basic() -> None:
    engine_id = b"\x80\x00\x1f\x88\x80" + b"\x00" * 11
    context_name = b""
    pdu = _make_pdu()

    encoded = encode_scoped_pdu(engine_id, context_name, pdu)
    dec_engine, dec_ctx, dec_pdu = decode_scoped_pdu(encoded)

    assert dec_engine == engine_id
    assert dec_ctx == context_name
    assert dec_pdu.pdu_type is PduType.GET
    assert dec_pdu.request_id == 1
    assert isinstance(dec_pdu.varbinds[0].value, NullValue)
    assert dec_pdu.varbinds[0].oid == (1, 3, 6, 1, 2, 1, 1, 1, 0)


def test_scoped_pdu_roundtrip_with_context_name() -> None:
    engine_id = b"\x80\x00\x01\x02\x03"
    context_name = b"mycontext"
    pdu = Pdu(
        pdu_type=PduType.RESPONSE,
        request_id=42,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 5, 0), value=OctetStringValue(b"router")),),
    )

    encoded = encode_scoped_pdu(engine_id, context_name, pdu)
    dec_engine, dec_ctx, dec_pdu = decode_scoped_pdu(encoded)

    assert dec_engine == engine_id
    assert dec_ctx == context_name
    assert dec_pdu.request_id == 42
    assert isinstance(dec_pdu.varbinds[0].value, OctetStringValue)
    assert dec_pdu.varbinds[0].value.value == b"router"


# ── SNMPv3 outer message encode/decode roundtrip ─────────────────────────────


def test_v3_message_roundtrip_no_auth_no_priv() -> None:
    usm = _make_usm()
    scoped = encode_scoped_pdu(usm.engine_id, b"", _make_pdu())
    flags = MSG_FLAG_REPORTABLE

    raw = encode_v3_message(
        msg_id=1001,
        msg_max_size=65507,
        flags=flags,
        usm_params=usm,
        msg_data_bytes=scoped,
    )
    view = decode_v3_message(raw)

    assert view.msg_id == 1001
    assert view.msg_max_size == 65507
    assert view.msg_flags == bytes([flags])
    assert view.usm_params.engine_boots == 5
    assert view.usm_params.engine_time == 12345
    assert view.usm_params.username == b"simulator"
    assert view.usm_params.auth_params == b""
    assert view.usm_params.priv_params == b""
    assert view.msg_data_bytes == scoped


def test_v3_message_roundtrip_auth_only() -> None:
    usm = _make_usm(auth_params=b"\x00" * 12)
    scoped = encode_scoped_pdu(usm.engine_id, b"", _make_pdu(request_id=77))
    flags = MSG_FLAG_AUTH | MSG_FLAG_REPORTABLE

    raw = encode_v3_message(
        msg_id=2002,
        msg_max_size=65507,
        flags=flags,
        usm_params=usm,
        msg_data_bytes=scoped,
    )
    view = decode_v3_message(raw)

    assert view.msg_flags == bytes([flags])
    assert view.usm_params.auth_params == b"\x00" * 12
    assert view.usm_params.priv_params == b""


def test_v3_message_roundtrip_auth_priv() -> None:
    usm = _make_usm(auth_params=b"\x00" * 12, priv_params=b"\x00" * 8)
    # When PRIV is set msgData must be an encryptedPDU OCTET STRING, not a ScopedPDU SEQUENCE.
    # Use a fake ciphertext blob (real encryption happens in Step 4/5).
    from trishul_snmp.wire.ber import encode_tlv as _etlv

    encrypted_pdu = _etlv(0x04, b"\xab" * 32)
    flags = MSG_FLAG_AUTH | MSG_FLAG_PRIV | MSG_FLAG_REPORTABLE

    raw = encode_v3_message(
        msg_id=3003,
        msg_max_size=65507,
        flags=flags,
        usm_params=usm,
        msg_data_bytes=encrypted_pdu,
    )
    view = decode_v3_message(raw)

    assert view.msg_flags == bytes([flags])
    assert view.usm_params.auth_params == b"\x00" * 12
    assert view.usm_params.priv_params == b"\x00" * 8
    assert view.msg_data_bytes == encrypted_pdu


def test_v3_message_auth_params_offset_is_correct() -> None:
    """auth_params_offset must point at the auth_params content bytes within the
    full encoded message so the verifier can zero-fill them before HMAC re-check."""
    sentinel = b"\xca\xfe\xba\xbe\x00\x01\x02\x03\x04\x05\x06\x07"
    usm = _make_usm(auth_params=sentinel)
    scoped = encode_scoped_pdu(usm.engine_id, b"", _make_pdu())

    raw = encode_v3_message(
        msg_id=9,
        msg_max_size=65507,
        flags=MSG_FLAG_AUTH | MSG_FLAG_REPORTABLE,
        usm_params=usm,
        msg_data_bytes=scoped,
    )
    view = decode_v3_message(raw)
    offset = view.auth_params_offset

    assert raw[offset : offset + len(sentinel)] == sentinel


def test_v3_message_scoped_pdu_survives_roundtrip() -> None:
    """scoped_pdu_bytes in V3MessageView must exactly equal what was passed in."""
    usm = _make_usm()
    pdu = Pdu(
        pdu_type=PduType.GET_BULK,
        request_id=200,
        error_status=0,
        error_index=10,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 2, 2, 1, 1), value=NullValue()),),
    )
    scoped = encode_scoped_pdu(usm.engine_id, b"myctx", pdu)

    raw = encode_v3_message(
        msg_id=5,
        msg_max_size=65507,
        flags=MSG_FLAG_REPORTABLE,
        usm_params=usm,
        msg_data_bytes=scoped,
    )
    view = decode_v3_message(raw)

    dec_engine, dec_ctx, dec_pdu = decode_scoped_pdu(view.msg_data_bytes)
    assert dec_ctx == b"myctx"
    assert dec_pdu.pdu_type is PduType.GET_BULK
    assert dec_pdu.request_id == 200


# ── error cases ───────────────────────────────────────────────────────────────


def test_decode_v3_message_wrong_tag() -> None:
    with pytest.raises(ProtocolError, match="SEQUENCE"):
        decode_v3_message(b"\x04\x01\x00")


def test_decode_v3_message_wrong_version() -> None:
    usm = _make_usm()
    scoped = encode_scoped_pdu(usm.engine_id, b"", _make_pdu())

    from trishul_snmp.wire.ber import encode_tlv as _etlv
    from trishul_snmp.wire.v3message import _encode_header_data, _encode_integer, _encode_usm_params

    header = _encode_header_data(1, 65507, MSG_FLAG_REPORTABLE)
    usm_bytes = _encode_usm_params(usm)
    sp = _etlv(0x04, usm_bytes)
    content = b"".join([_encode_integer(1), header, sp, scoped])  # version=1 (v2c)
    bad = _etlv(0x30, content)

    with pytest.raises(ProtocolError, match="version"):
        decode_v3_message(bad)


def test_decode_scoped_pdu_wrong_tag() -> None:
    with pytest.raises(ProtocolError, match="SEQUENCE"):
        decode_scoped_pdu(b"\x04\x01\x00")


def test_decode_scoped_pdu_trailing_bytes() -> None:
    engine_id = b"\x80\x00\x01"
    encoded = encode_scoped_pdu(engine_id, b"", _make_pdu()) + b"\x00"
    with pytest.raises(ProtocolError):
        decode_scoped_pdu(encoded)


def test_decode_v3_message_missing_scoped_pdu_raises() -> None:
    """A message whose outer SEQUENCE ends after msgSecurityParameters must be rejected."""
    from trishul_snmp.wire.ber import encode_tlv as _etlv
    from trishul_snmp.wire.v3message import _encode_header_data, _encode_integer, _encode_usm_params

    usm = _make_usm()
    usm_bytes = _encode_usm_params(usm)
    sp = _etlv(0x04, usm_bytes)
    # omit scoped PDU entirely
    content = b"".join([_encode_integer(3), _encode_header_data(1, 65507, MSG_FLAG_REPORTABLE), sp])
    bad = _etlv(0x30, content)

    with pytest.raises(ProtocolError):
        decode_v3_message(bad)


def test_v3_message_auth_params_offset_non_canonical_length() -> None:
    """auth_params_offset must be correct even when the outer SEQUENCE uses a
    non-canonical (long-form) BER length encoding for a value that fits in short form."""
    sentinel = b"\xca\xfe\xba\xbe\x00\x01\x02\x03\x04\x05\x06\x07"
    usm = _make_usm(auth_params=sentinel)
    scoped = encode_scoped_pdu(usm.engine_id, b"", _make_pdu())

    canonical = encode_v3_message(
        msg_id=9,
        msg_max_size=65507,
        flags=MSG_FLAG_AUTH | MSG_FLAG_REPORTABLE,
        usm_params=usm,
        msg_data_bytes=scoped,
    )

    # Rewrite the outer SEQUENCE length to long-form 0x81 <n> even if n < 0x80.
    # canonical[0] == 0x30 (SEQUENCE tag), canonical[1] is the short-form length byte.
    assert canonical[0] == 0x30
    inner_len = canonical[1]
    assert inner_len < 0x80, "test assumption: canonical length is short-form"
    non_canonical = bytes([0x30, 0x81, inner_len]) + canonical[2:]

    view = decode_v3_message(non_canonical)
    offset = view.auth_params_offset

    assert non_canonical[offset : offset + len(sentinel)] == sentinel


def test_decode_v3_message_priv_set_but_sequence_msgdata_raises() -> None:
    """PRIV flag set but msgData is a ScopedPDU SEQUENCE must be rejected."""
    usm = _make_usm(auth_params=b"\x00" * 12, priv_params=b"\x00" * 8)
    # plaintext ScopedPDU under PRIV — codec must reject this
    scoped = encode_scoped_pdu(usm.engine_id, b"", _make_pdu())
    flags = MSG_FLAG_AUTH | MSG_FLAG_PRIV | MSG_FLAG_REPORTABLE

    raw = encode_v3_message(
        msg_id=1,
        msg_max_size=65507,
        flags=flags,
        usm_params=usm,
        msg_data_bytes=scoped,  # SEQUENCE, not OCTET STRING — invalid under PRIV
    )
    with pytest.raises(ProtocolError, match="encryptedPDU"):
        decode_v3_message(raw)


def test_decode_v3_message_priv_clear_but_octet_string_msgdata_raises() -> None:
    """PRIV flag clear but msgData is an OCTET STRING must be rejected."""
    from trishul_snmp.wire.ber import encode_tlv as _etlv

    usm = _make_usm()
    encrypted_pdu = _etlv(0x04, b"\xab" * 32)  # OCTET STRING
    flags = MSG_FLAG_REPORTABLE  # no PRIV

    raw = encode_v3_message(
        msg_id=2,
        msg_max_size=65507,
        flags=flags,
        usm_params=usm,
        msg_data_bytes=encrypted_pdu,  # OCTET STRING when no PRIV — invalid
    )
    with pytest.raises(ProtocolError, match="ScopedPDU"):
        decode_v3_message(raw)
