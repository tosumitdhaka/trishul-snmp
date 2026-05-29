"""Tests for SNMPv3 USM — key derivation, auth, discovery, import guard."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from trishul_snmp.errors import AuthenticationError, ProtocolError
from trishul_snmp.security.usm import (
    AuthProtocol,
    UsmModel,
    UsmUser,
    _localize_key_rfc3414,
    _require_cryptography,
)
from trishul_snmp.types import NullValue
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind

# ── _require_cryptography() ───────────────────────────────────────────────────


def test_require_cryptography_raises_when_absent() -> None:
    """_require_cryptography() must raise ImportError with install hint when
    the cryptography package is blocked."""
    with patch.dict(sys.modules, {"cryptography": None}):
        with pytest.raises(ImportError, match="pip install trishul-snmp\\[v3\\]"):
            _require_cryptography()


def test_usm_module_imports_without_cryptography() -> None:
    """usm.py must not import cryptography at module level — reimporting with
    cryptography blocked must succeed without ImportError."""
    # Remove usm from sys.modules so the import machinery re-executes it.
    usm_key = "trishul_snmp.security.usm"
    saved = sys.modules.pop(usm_key, None)
    try:
        with patch.dict(sys.modules, {"cryptography": None}):
            import importlib

            mod = importlib.import_module(usm_key)
            assert hasattr(mod, "UsmModel")
    finally:
        # Restore original module so other tests see the real one.
        if saved is not None:
            sys.modules[usm_key] = saved
        else:
            sys.modules.pop(usm_key, None)


# ── RFC 3414 key localisation known-answer tests ──────────────────────────────
# Test vectors from RFC 3414 Appendix A.


def test_localize_key_md5_rfc3414_vector() -> None:
    """RFC 3414 §A.2.1 MD5 key-localisation vector."""
    password = b"maplesyrup"
    engine_id = bytes.fromhex("000000000000000000000002")
    # Expected Ku (from RFC 3414 A.2.1): 9faf3283884e92834ebc9847d8edd963
    # Expected Kul (localised): 526f5eed9fcce26f8964c2930787d82b
    kul = _localize_key_rfc3414(password, engine_id, AuthProtocol.MD5)
    assert kul == bytes.fromhex("526f5eed9fcce26f8964c2930787d82b")


def test_localize_key_sha1_rfc3414_vector() -> None:
    """RFC 3414 §A.2.2 SHA-1 key-localisation vector."""
    password = b"maplesyrup"
    engine_id = bytes.fromhex("000000000000000000000002")
    # Expected Kul: 6695febc9288e36282235fc7151f128497b38f3f
    kul = _localize_key_rfc3414(password, engine_id, AuthProtocol.SHA1)
    assert kul == bytes.fromhex("6695febc9288e36282235fc7151f128497b38f3f")


# ── auth tag computation ──────────────────────────────────────────────────────


def _make_model(*, auth: AuthProtocol = AuthProtocol.MD5, key: bytes | None = None) -> UsmModel:
    engine_id = b"\x80\x00\x1f\x88\x80" + b"\x00" * 11
    if key is None:
        import hashlib

        digest_len = (
            hashlib.md5(b"").digest_size
            if auth is AuthProtocol.MD5
            else (
                hashlib.sha1(b"").digest_size  # noqa: S324
                if auth is AuthProtocol.SHA1
                else hashlib.sha256(b"").digest_size
            )
        )
        key = b"\xab" * digest_len
    # auth_key_localized=True so the key is used directly without derivation.
    user = UsmUser(username="simulator", auth_protocol=auth, auth_key=key, auth_key_localized=True)
    model = UsmModel(user=user)
    model._engine_id = engine_id
    model._engine_boots = 1
    model._engine_time = 100
    return model


def test_auth_tag_length_is_12_bytes() -> None:
    model = _make_model()
    tag = model._compute_auth_tag(b"some message bytes")
    assert len(tag) == 12


def test_auth_tag_differs_with_different_key() -> None:
    import hashlib

    key_a = b"\xaa" * hashlib.md5(b"").digest_size
    key_b = b"\xbb" * hashlib.md5(b"").digest_size
    model_a = _make_model(key=key_a)
    model_b = _make_model(key=key_b)
    msg = b"hello"
    assert model_a._compute_auth_tag(msg) != model_b._compute_auth_tag(msg)


# ── HMAC failure raises AuthenticationError ───────────────────────────────────


def test_unwrap_raises_authentication_error_on_hmac_failure() -> None:
    """A tampered auth_params must raise AuthenticationError, not return None."""
    model = _make_model()
    pdu = Pdu(
        pdu_type=PduType.GET,
        request_id=1,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    raw = model.wrap_pdu(pdu)

    # Flip a byte in the auth_params region.
    view_for_offset = __import__(
        "trishul_snmp.wire.v3message", fromlist=["decode_v3_message"]
    ).decode_v3_message(raw)
    offset = view_for_offset.auth_params_offset
    tampered = raw[:offset] + bytes([raw[offset] ^ 0xFF]) + raw[offset + 1 :]

    with pytest.raises(AuthenticationError):
        model.unwrap_message(tampered)


# ── noAuthNoPriv wrap/unwrap roundtrip ────────────────────────────────────────


def test_noauthnopriv_roundtrip() -> None:
    engine_id = b"\x80\x00\x1f\x88\x80" + b"\x00" * 11
    user = UsmUser(username="public", auth_protocol=AuthProtocol.NONE)
    model = UsmModel(user=user)
    model._engine_id = engine_id

    pdu = Pdu(
        pdu_type=PduType.GET,
        request_id=42,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    raw = model.wrap_pdu(pdu)
    result = model.unwrap_message(raw)

    assert result is not None
    assert result.pdu_type is PduType.GET
    assert result.request_id == 42


def test_authnoproiv_roundtrip() -> None:
    model = _make_model(auth=AuthProtocol.MD5)
    pdu = Pdu(
        pdu_type=PduType.RESPONSE,
        request_id=99,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue()),),
    )
    raw = model.wrap_pdu(pdu)
    result = model.unwrap_message(raw)

    assert result is not None
    assert result.pdu_type is PduType.RESPONSE
    assert result.request_id == 99


def test_unwrap_returns_none_for_wrong_username() -> None:
    model = _make_model()
    pdu = Pdu(
        pdu_type=PduType.GET,
        request_id=1,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    raw = model.wrap_pdu(pdu)

    other_user = UsmUser(username="otheruser", auth_protocol=AuthProtocol.NONE)
    other_model = UsmModel(user=other_user)
    other_model._engine_id = model._engine_id

    assert other_model.unwrap_message(raw) is None


def test_unwrap_returns_none_for_garbage_bytes() -> None:
    model = _make_model()
    assert model.unwrap_message(b"\x00" * 10) is None


# ── engine discovery probe encoding ──────────────────────────────────────────


def test_discovery_probe_is_valid_v3_message() -> None:
    """The probe emitted by _build_discovery_probe() must be a valid SNMPv3 message
    with empty engineID, empty username, and REPORTABLE flag set."""
    from trishul_snmp.wire.v3message import MSG_FLAG_REPORTABLE, decode_v3_message

    user = UsmUser(username="simulator", auth_protocol=AuthProtocol.NONE)
    model = UsmModel(user=user)
    probe = model._build_discovery_probe()

    view = decode_v3_message(probe)
    assert view.usm_params.engine_id == b""
    assert view.usm_params.username == b""
    assert view.msg_flags[0] & MSG_FLAG_REPORTABLE


def _build_report_bytes(
    engine_id: bytes,
    engine_boots: int = 7,
    engine_time: int = 9876,
) -> bytes:
    """Build a minimal syntactically valid SNMPv3 REPORT message for discovery tests."""
    from trishul_snmp.wire.ber import encode_tlv
    from trishul_snmp.wire.v3message import UsmParams, encode_v3_message

    report_pdu_tag = 0xA8
    sequence_tag = 0x30
    integer_tag = 0x02

    # Encode a bare REPORT PDU manually (tag 0xA8, same wire structure as normal PDUs).
    def _enc_int(v: int) -> bytes:
        return encode_tlv(integer_tag, v.to_bytes((v.bit_length() + 8) // 8 or 1, "big"))

    report_pdu_content = b"".join(
        [_enc_int(1), _enc_int(0), _enc_int(0), encode_tlv(sequence_tag, b"")]
    )
    report_pdu_bytes = encode_tlv(report_pdu_tag, report_pdu_content)

    # Build ScopedPDU manually: SEQUENCE { OCTET STRING(engineID), OCTET STRING(ctx), PDU }
    scoped_raw = encode_tlv(
        0x30, encode_tlv(0x04, engine_id) + encode_tlv(0x04, b"") + report_pdu_bytes
    )
    usm = UsmParams(
        engine_id=engine_id,
        engine_boots=engine_boots,
        engine_time=engine_time,
        username=b"",
        auth_params=b"",
        priv_params=b"",
    )
    return encode_v3_message(
        msg_id=1,
        msg_max_size=65507,
        flags=0,
        usm_params=usm,
        msg_data_bytes=scoped_raw,
    )


def test_parse_discovery_response_caches_engine_params() -> None:
    """_parse_discovery_response() must populate engine_id/boots/time from a REPORT."""
    engine_id = b"\x80\x00\x1f\x88\x80\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b"
    report_bytes = _build_report_bytes(engine_id, engine_boots=7, engine_time=9876)

    user = UsmUser(username="simulator", auth_protocol=AuthProtocol.NONE)
    model = UsmModel(user=user)
    model._parse_discovery_response(report_bytes)

    assert model._engine_id == engine_id
    assert model._engine_boots == 7
    assert model._engine_time == 9876


def test_parse_discovery_rejects_trailing_bytes_after_report() -> None:
    """A REPORT PDU followed by trailing bytes inside the ScopedPDU must be rejected."""
    from trishul_snmp.wire.ber import encode_tlv
    from trishul_snmp.wire.v3message import UsmParams, encode_v3_message

    engine_id = b"\x80\x00\x01\x02\x03"
    report_bytes = _build_report_bytes(engine_id)
    # Unpack the outer message to inject a trailing NULL after the REPORT inside ScopedPDU.
    from trishul_snmp.wire.v3message import decode_v3_message

    view = decode_v3_message(report_bytes)
    usm = UsmParams(
        engine_id=engine_id,
        engine_boots=1,
        engine_time=0,
        username=b"",
        auth_params=b"",
        priv_params=b"",
    )
    # Re-encode with the corrupted scoped bytes.
    # Build raw ScopedPDU with trailing NULL after the REPORT PDU inside the SEQUENCE.
    report_inner = view.msg_data_bytes  # valid REPORT ScopedPDU
    # Extract the SEQUENCE content and add a NULL at the end.
    from trishul_snmp.wire.ber import decode_tlv as _dt

    _, inner_content, _ = _dt(report_inner, 0)
    corrupted_scoped = encode_tlv(0x30, inner_content + b"\x05\x00")
    raw = encode_v3_message(
        msg_id=2, msg_max_size=65507, flags=0, usm_params=usm, msg_data_bytes=corrupted_scoped
    )

    user = UsmUser(username="simulator", auth_protocol=AuthProtocol.NONE)
    model = UsmModel(user=user)
    with pytest.raises(ProtocolError):
        model._parse_discovery_response(raw)


def test_parse_discovery_rejects_empty_integer_in_report_body() -> None:
    """A REPORT with a zero-length INTEGER (e.g. request-id = 0x02 0x00) must be rejected."""
    from trishul_snmp.wire.ber import encode_tlv
    from trishul_snmp.wire.v3message import UsmParams, encode_v3_message

    engine_id = b"\x80\x00\x01\x02\x03"
    report_pdu_tag = 0xA8
    # Build a REPORT whose request-id INTEGER has zero-length content.
    bad_report_body = (
        b"\x02\x00"  # request-id: INTEGER, length 0 — invalid
        + encode_tlv(0x02, b"\x00")  # error-status
        + encode_tlv(0x02, b"\x00")  # error-index
        + encode_tlv(0x30, b"")  # VarBindList (empty)
    )
    bad_report_pdu = encode_tlv(report_pdu_tag, bad_report_body)
    scoped_raw = encode_tlv(
        0x30, encode_tlv(0x04, engine_id) + encode_tlv(0x04, b"") + bad_report_pdu
    )
    usm = UsmParams(
        engine_id=engine_id,
        engine_boots=1,
        engine_time=0,
        username=b"",
        auth_params=b"",
        priv_params=b"",
    )
    raw = encode_v3_message(
        msg_id=3, msg_max_size=65507, flags=0, usm_params=usm, msg_data_bytes=scoped_raw
    )

    user = UsmUser(username="simulator", auth_protocol=AuthProtocol.NONE)
    model = UsmModel(user=user)
    with pytest.raises(ProtocolError):
        model._parse_discovery_response(raw)


def test_parse_discovery_rejects_non_report_pdu() -> None:
    """_parse_discovery_response() must raise ProtocolError for any non-REPORT PDU."""
    from trishul_snmp.wire.v3message import UsmParams, encode_scoped_pdu, encode_v3_message

    engine_id = b"\x80\x00\x01\x02\x03"
    pdu = Pdu(
        pdu_type=PduType.GET,  # not a REPORT
        request_id=1,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    scoped = encode_scoped_pdu(engine_id, b"", pdu)
    usm = UsmParams(
        engine_id=engine_id,
        engine_boots=1,
        engine_time=100,
        username=b"",
        auth_params=b"",
        priv_params=b"",
    )
    raw = encode_v3_message(
        msg_id=1, msg_max_size=65507, flags=0, usm_params=usm, msg_data_bytes=scoped
    )

    user = UsmUser(username="simulator", auth_protocol=AuthProtocol.NONE)
    model = UsmModel(user=user)
    with pytest.raises(ProtocolError, match="REPORT"):
        model._parse_discovery_response(raw)


def test_unwrap_returns_none_for_wrong_engine_id() -> None:
    """unwrap_message() must return None when the message comes from a different engine."""
    engine_a = b"\x80\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f"
    engine_b = b"\x80\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff"

    user = UsmUser(username="simulator", auth_protocol=AuthProtocol.NONE)

    sender = UsmModel(user=user)
    sender._engine_id = engine_b  # message originates from engine B

    receiver = UsmModel(user=user)
    receiver._engine_id = engine_a  # receiver prepared for engine A

    pdu = Pdu(
        pdu_type=PduType.RESPONSE,
        request_id=1,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    raw = sender.wrap_pdu(pdu)

    assert receiver.unwrap_message(raw) is None


def test_hmac_key_passphrase_of_digest_length_is_localized() -> None:
    """A passphrase whose length equals the digest size must still be localized,
    not returned raw — auth_key_localized=False is the default."""
    import hashlib

    engine_id = b"\x80\x00\x1f\x88\x80" + b"\x00" * 11
    # 16-byte passphrase == MD5 digest size; must NOT be treated as pre-localized.
    passphrase = b"abcdefghijklmnop"
    assert len(passphrase) == hashlib.md5(b"").digest_size  # noqa: S324

    user_localized = UsmUser(
        username="u",
        auth_protocol=AuthProtocol.MD5,
        auth_key=passphrase,
        auth_key_localized=True,
    )
    user_passphrase = UsmUser(
        username="u",
        auth_protocol=AuthProtocol.MD5,
        auth_key=passphrase,
        auth_key_localized=False,
    )

    m_loc = UsmModel(user=user_localized)
    m_loc._engine_id = engine_id
    m_pass = UsmModel(user=user_passphrase)
    m_pass._engine_id = engine_id

    # The localized key (returned directly) must differ from the derived key.
    assert m_loc._hmac_key() != m_pass._hmac_key()
    # The passphrase path must produce the RFC-localized result.
    expected = _localize_key_rfc3414(passphrase, engine_id, AuthProtocol.MD5)
    assert m_pass._hmac_key() == expected


# ── RFC 3412 reportableFlag ───────────────────────────────────────────────────


def test_reportable_flag_cleared_for_trap() -> None:
    """SNMPV2-TRAP must have reportableFlag cleared (RFC 3412 §7.1.9)."""
    from trishul_snmp.wire.v3message import MSG_FLAG_REPORTABLE, decode_v3_message

    engine_id = b"\x80\x00\x1f\x88\x80" + b"\x00" * 11
    user = UsmUser(username="u", auth_protocol=AuthProtocol.NONE)
    model = UsmModel(user=user)
    model._engine_id = engine_id

    pdu = Pdu(
        pdu_type=PduType.SNMPV2_TRAP,
        request_id=1,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    raw = model.wrap_pdu(pdu)
    view = decode_v3_message(raw)
    assert not (view.msg_flags[0] & MSG_FLAG_REPORTABLE), (
        "SNMPV2-TRAP must not have reportableFlag set"
    )


def test_reportable_flag_cleared_for_response() -> None:
    """RESPONSE must have reportableFlag cleared (RFC 3412 §7.1.9)."""
    from trishul_snmp.wire.v3message import MSG_FLAG_REPORTABLE, decode_v3_message

    engine_id = b"\x80\x00\x1f\x88\x80" + b"\x00" * 11
    user = UsmUser(username="u", auth_protocol=AuthProtocol.NONE)
    model = UsmModel(user=user)
    model._engine_id = engine_id

    pdu = Pdu(
        pdu_type=PduType.RESPONSE,
        request_id=1,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    raw = model.wrap_pdu(pdu)
    view = decode_v3_message(raw)
    assert not (view.msg_flags[0] & MSG_FLAG_REPORTABLE), (
        "RESPONSE must not have reportableFlag set"
    )


def test_reportable_flag_set_for_get() -> None:
    """GET (confirmed class) must have reportableFlag set (RFC 3412 §7.1.9)."""
    from trishul_snmp.wire.v3message import MSG_FLAG_REPORTABLE, decode_v3_message

    engine_id = b"\x80\x00\x1f\x88\x80" + b"\x00" * 11
    user = UsmUser(username="u", auth_protocol=AuthProtocol.NONE)
    model = UsmModel(user=user)
    model._engine_id = engine_id

    pdu = Pdu(
        pdu_type=PduType.GET,
        request_id=1,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    raw = model.wrap_pdu(pdu)
    view = decode_v3_message(raw)
    assert view.msg_flags[0] & MSG_FLAG_REPORTABLE
