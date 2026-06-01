"""Tests for SNMPv3 USM AES-128-CFB privacy encryption."""

from __future__ import annotations

import hashlib

import pytest

from trishul_snmp.errors import ProtocolError
from trishul_snmp.security.usm import AuthProtocol, PrivProtocol, UsmLocalEngine, UsmModel, UsmUser
from trishul_snmp.types import NullValue
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind


def _make_authpriv_model(
    *,
    auth: AuthProtocol = AuthProtocol.MD5,
    priv: PrivProtocol = PrivProtocol.AES128,
    auth_key: bytes | None = None,
    priv_key: bytes | None = None,
    local_engine: UsmLocalEngine | None = None,
) -> UsmModel:
    engine_id = b"\x80\x00\x1f\x88\x80" + b"\x00" * 11
    if auth_key is None:
        auth_key = b"\xab" * hashlib.md5(b"").digest_size
    if priv_key is None:
        priv_key = b"privpassword12345"
    user = UsmUser(
        username="authpriv",
        auth_protocol=auth,
        auth_key=auth_key,
        auth_key_localized=True,
        priv_protocol=priv,
        priv_key=priv_key,
    )
    model = UsmModel(user=user, local_engine=local_engine)
    model._engine_id = engine_id
    model._engine_boots = 2
    model._engine_time = 500
    return model


def _make_local_engine() -> UsmLocalEngine:
    return UsmLocalEngine(
        engine_id=b"\x80\x00\xaa\xbb\xcc\xdd" + b"\x21" * 11,
        engine_boots=19,
        engine_time=1234,
    )


# ── AES-128-CFB roundtrip ─────────────────────────────────────────────────────


def test_aes128_encrypt_decrypt_roundtrip() -> None:
    """wrap_pdu + unwrap_message must roundtrip under authPriv AES-128-CFB."""
    model = _make_authpriv_model()
    pdu = Pdu(
        pdu_type=PduType.GET,
        request_id=7,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    raw = model.wrap_pdu(pdu)
    result = model.unwrap_message(raw)

    assert result is not None
    assert result.pdu_type is PduType.GET
    assert result.request_id == 7


def test_aes128_priv_params_length_is_8() -> None:
    """priv_params (IV salt) must be exactly 8 bytes per RFC 3826."""
    from trishul_snmp.wire.v3message import decode_v3_message

    model = _make_authpriv_model()
    pdu = Pdu(
        pdu_type=PduType.RESPONSE,
        request_id=1,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue()),),
    )
    raw = model.wrap_pdu(pdu)
    view = decode_v3_message(raw)
    assert len(view.usm_params.priv_params) == 8


def test_aes128_each_wrap_produces_different_ciphertext() -> None:
    """Two wrap_pdu calls on the same PDU must produce different ciphertext (fresh random IV)."""
    model = _make_authpriv_model()
    pdu = Pdu(
        pdu_type=PduType.GET,
        request_id=1,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    raw1 = model.wrap_pdu(pdu)
    raw2 = model.wrap_pdu(pdu)
    assert raw1 != raw2


def test_aes128_msg_data_is_octet_string() -> None:
    """Under authPriv the outer msgData must be an OCTET STRING (not a SEQUENCE)."""
    from trishul_snmp.wire.v3message import decode_v3_message

    model = _make_authpriv_model()
    pdu = Pdu(
        pdu_type=PduType.GET,
        request_id=1,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    raw = model.wrap_pdu(pdu)
    # decode_v3_message already validates this; if PRIV is set and it's a SEQUENCE it raises
    view = decode_v3_message(raw)
    assert view.msg_data_bytes[0] == 0x04  # OCTET STRING tag


def test_aes128_auth_still_verified_under_authpriv() -> None:
    """Tampering with the auth tag must raise AuthenticationError even when PRIV is set."""
    from trishul_snmp.errors import AuthenticationError
    from trishul_snmp.wire.v3message import decode_v3_message

    model = _make_authpriv_model()
    pdu = Pdu(
        pdu_type=PduType.GET,
        request_id=5,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    raw = model.wrap_pdu(pdu)
    view = decode_v3_message(raw)
    offset = view.auth_params_offset
    tampered = raw[:offset] + bytes([raw[offset] ^ 0xFF]) + raw[offset + 1 :]

    with pytest.raises(AuthenticationError):
        model.unwrap_message(tampered)


def test_aes128_sha1_authpriv_roundtrip() -> None:
    """authPriv works with SHA-1 auth as well as MD5."""
    auth_key = b"\xcd" * hashlib.sha1(b"").digest_size  # noqa: S324
    model = _make_authpriv_model(auth=AuthProtocol.SHA1, auth_key=auth_key)
    pdu = Pdu(
        pdu_type=PduType.RESPONSE,
        request_id=42,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue()),),
    )
    raw = model.wrap_pdu(pdu)
    result = model.unwrap_message(raw)
    assert result is not None
    assert result.request_id == 42


# ── DES disabled ──────────────────────────────────────────────────────────────


def test_des_encrypt_raises_protocol_error() -> None:
    """_encrypt_des must raise ProtocolError (not NotImplementedError)."""
    model = _make_authpriv_model(priv=PrivProtocol.DES)
    pdu = Pdu(
        pdu_type=PduType.GET,
        request_id=1,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    with pytest.raises(ProtocolError, match="DES"):
        model.wrap_pdu(pdu)


def test_des_decrypt_raises_protocol_error() -> None:
    """_decrypt_des must raise ProtocolError when called directly."""
    model = _make_authpriv_model(priv=PrivProtocol.DES)
    with pytest.raises(ProtocolError, match="DES"):
        model._decrypt_des(b"\x04\x04data", b"\x00" * 8)


# ── priv key missing ──────────────────────────────────────────────────────────


def test_aes128_requires_priv_key() -> None:
    """wrap_pdu must raise ProtocolError when no priv_key is configured."""
    engine_id = b"\x80\x00\x1f\x88\x80" + b"\x00" * 11
    auth_key = b"\xab" * hashlib.md5(b"").digest_size
    user = UsmUser(
        username="noprivkey",
        auth_protocol=AuthProtocol.MD5,
        auth_key=auth_key,
        auth_key_localized=True,
        priv_protocol=PrivProtocol.AES128,
        priv_key=b"",
    )
    model = UsmModel(user=user)
    model._engine_id = engine_id
    model._engine_boots = 1
    model._engine_time = 0
    pdu = Pdu(
        pdu_type=PduType.GET,
        request_id=1,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    with pytest.raises(ProtocolError):
        model.wrap_pdu(pdu)


# ── IV uses inbound header boots/time, not cached receiver state ──────────────


def test_aes128_roundtrip_when_sender_engine_time_differs() -> None:
    """Decryption must use the sender's engine_boots/engine_time from the USM header,
    not the receiver's cached _engine_boots/_engine_time.

    Regression for: receiver had _engine_time=500 but sender encoded time=501 in
    the message header; using the wrong IV caused decryption to produce garbage
    and unwrap_message() returned None.
    """
    engine_id = b"\x80\x00\x1f\x88\x80" + b"\x00" * 11
    auth_key = b"\xab" * hashlib.md5(b"").digest_size
    priv_key = b"privpassword12345"

    def _make(engine_time: int) -> UsmModel:
        user = UsmUser(
            username="authpriv",
            auth_protocol=AuthProtocol.MD5,
            auth_key=auth_key,
            auth_key_localized=True,
            priv_protocol=PrivProtocol.AES128,
            priv_key=priv_key,
        )
        m = UsmModel(user=user)
        m._engine_id = engine_id
        m._engine_boots = 2
        m._engine_time = engine_time
        return m

    sender = _make(engine_time=501)
    receiver = _make(engine_time=500)

    pdu = Pdu(
        pdu_type=PduType.GET,
        request_id=99,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    raw = sender.wrap_pdu(pdu)
    result = receiver.unwrap_message(raw)

    assert result is not None, "unwrap_message returned None — likely used wrong IV for decryption"
    assert result.request_id == 99


# ── inbound priv_params length validation ─────────────────────────────────────


def test_aes128_rejects_priv_params_longer_than_8() -> None:
    """unwrap_message must raise ProtocolError when inbound priv_params is not exactly 8 bytes.

    RFC 3826 §3.1.4: privacyParameters is exactly 8 octets (the local IV sent
    by the originator). A 9-byte field must be rejected, not silently truncated.
    Regression: previously _decrypt_aes128 used priv_params[:8], so the extra
    byte was ignored and decryption succeeded.
    """
    from trishul_snmp.errors import ProtocolError
    from trishul_snmp.wire.v3message import UsmParams, decode_v3_message, encode_v3_message

    model = _make_authpriv_model()
    pdu = Pdu(
        pdu_type=PduType.GET,
        request_id=42,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    raw = model.wrap_pdu(pdu)
    view = decode_v3_message(raw)

    # Re-encode the message with priv_params padded by one extra byte.
    p = view.usm_params
    padded_usm = UsmParams(
        engine_id=p.engine_id,
        engine_boots=p.engine_boots,
        engine_time=p.engine_time,
        username=p.username,
        auth_params=b"\x00" * 12,
        priv_params=p.priv_params + b"\x58",  # 9 bytes instead of 8
    )
    reencoded = encode_v3_message(
        msg_id=view.msg_id,
        msg_max_size=view.msg_max_size,
        flags=view.msg_flags[0],
        usm_params=padded_usm,
        msg_data_bytes=view.msg_data_bytes,
    )
    restamped = model._stamp_auth(reencoded)

    with pytest.raises(ProtocolError, match="8 octets"):
        model.unwrap_message(restamped)


def test_aes128_rejects_priv_params_shorter_than_8() -> None:
    """unwrap_message must raise ProtocolError when inbound priv_params is fewer than 8 bytes."""
    from trishul_snmp.errors import ProtocolError
    from trishul_snmp.wire.v3message import UsmParams, decode_v3_message, encode_v3_message

    model = _make_authpriv_model()
    pdu = Pdu(
        pdu_type=PduType.GET,
        request_id=43,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    raw = model.wrap_pdu(pdu)
    view = decode_v3_message(raw)

    p = view.usm_params
    short_usm = UsmParams(
        engine_id=p.engine_id,
        engine_boots=p.engine_boots,
        engine_time=p.engine_time,
        username=p.username,
        auth_params=b"\x00" * 12,
        priv_params=p.priv_params[:7],  # 7 bytes instead of 8
    )
    reencoded = encode_v3_message(
        msg_id=view.msg_id,
        msg_max_size=view.msg_max_size,
        flags=view.msg_flags[0],
        usm_params=short_usm,
        msg_data_bytes=view.msg_data_bytes,
    )
    restamped = model._stamp_auth(reencoded)

    with pytest.raises(ProtocolError, match="8 octets"):
        model.unwrap_message(restamped)


def test_authpriv_trap_roundtrip_uses_local_engine() -> None:
    from trishul_snmp.wire.v3message import decode_scoped_pdu, decode_v3_message

    local_engine = _make_local_engine()
    sender = _make_authpriv_model(local_engine=local_engine)
    receiver = _make_authpriv_model()
    receiver._engine_id = local_engine.engine_id

    pdu = Pdu(
        pdu_type=PduType.SNMPV2_TRAP,
        request_id=144,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    raw = sender.wrap_pdu(pdu)
    view = decode_v3_message(raw)
    scoped_engine_id, _ctx, _decoded = decode_scoped_pdu(
        sender._decrypt_scoped_pdu(
            view.msg_data_bytes,
            view.usm_params.priv_params,
            view.usm_params.engine_id,
            view.usm_params.engine_boots,
            view.usm_params.engine_time,
        )
    )
    result = receiver.unwrap_message(raw)

    assert view.usm_params.engine_id == local_engine.engine_id
    assert view.usm_params.engine_boots == local_engine.engine_boots
    assert view.usm_params.engine_time == local_engine.engine_time
    assert scoped_engine_id == local_engine.engine_id
    assert result is not None
    assert result.pdu_type is PduType.SNMPV2_TRAP
