"""SNMPv3 USM crypto-parity tests — RFC 7860 SHA-2 auth, Reeder AES-192/256 and 3DES-EDE priv."""

from __future__ import annotations

import hashlib

import pytest

from trishul_snmp.errors import AuthenticationError, ProtocolError
from trishul_snmp.security.usm import AuthProtocol, PrivProtocol, UsmModel, UsmUser
from trishul_snmp.types import NullValue
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind

_ENGINE_ID = b"\x80\x00\x1f\x88\x80" + b"\x00" * 11
_PRIV_PASSWORD = b"privpassword12345"

_AUTH_KEY_SIZES = {
    AuthProtocol.MD5: hashlib.md5(b"").digest_size,  # noqa: S324
    AuthProtocol.SHA1: hashlib.sha1(b"").digest_size,  # noqa: S324
    AuthProtocol.SHA224: hashlib.sha224(b"").digest_size,
    AuthProtocol.SHA256: hashlib.sha256(b"").digest_size,
    AuthProtocol.SHA384: hashlib.sha384(b"").digest_size,
    AuthProtocol.SHA512: hashlib.sha512(b"").digest_size,
}

_SHA2_PROTOCOLS = [AuthProtocol.SHA224, AuthProtocol.SHA384, AuthProtocol.SHA512]
_REEDER_PRIVS = [PrivProtocol.AES192, PrivProtocol.AES256, PrivProtocol.THREEDES_EDE]


def _make_user(
    *,
    auth: AuthProtocol = AuthProtocol.MD5,
    priv: PrivProtocol = PrivProtocol.NONE,
    auth_key: bytes | None = None,
    priv_key: bytes = _PRIV_PASSWORD,
    username: str = "parity",
) -> UsmUser:
    if auth_key is None:
        auth_key = b"\xab" * _AUTH_KEY_SIZES[auth]
    return UsmUser(
        username=username,
        auth_protocol=auth,
        auth_key=auth_key,
        auth_key_localized=True,
        priv_protocol=priv,
        priv_key=priv_key,
    )


def _make_model(
    *,
    auth: AuthProtocol = AuthProtocol.MD5,
    priv: PrivProtocol = PrivProtocol.NONE,
    auth_key: bytes | None = None,
    priv_key: bytes = _PRIV_PASSWORD,
) -> UsmModel:
    model = UsmModel(user=_make_user(auth=auth, priv=priv, auth_key=auth_key, priv_key=priv_key))
    model._engine_id = _ENGINE_ID
    model._engine_boots = 2
    model._engine_time = 500
    return model


def _get_pdu(request_id: int = 7) -> Pdu:
    return Pdu(
        pdu_type=PduType.GET,
        request_id=request_id,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )


# ── RFC 7860 HMAC-SHA-2 authentication ────────────────────────────────────────


@pytest.mark.parametrize("auth", _SHA2_PROTOCOLS)
def test_sha2_auth_roundtrip(auth: AuthProtocol) -> None:
    model = _make_model(auth=auth)
    raw = model.wrap_pdu(_get_pdu(11))
    result = model.unwrap_message(raw)

    assert result is not None
    assert result.request_id == 11


@pytest.mark.parametrize("auth", _SHA2_PROTOCOLS)
def test_sha2_auth_tag_is_12_bytes(auth: AuthProtocol) -> None:
    model = _make_model(auth=auth)
    tag = model._compute_auth_tag(b"some message", model._engine_id)
    assert len(tag) == 12


@pytest.mark.parametrize("auth", _SHA2_PROTOCOLS)
def test_sha2_localized_key_length_equals_digest_size(auth: AuthProtocol) -> None:
    """RFC 7860 HMAC keys are the digest-sized localized keys, like SHA-256."""
    model = _make_model(auth=auth)
    key = model._localize_key(b"maplesyrup", model._engine_id)
    assert len(key) == _AUTH_KEY_SIZES[auth]


def test_sha2_auth_tags_differ_across_protocols() -> None:
    tags = {
        auth: _make_model(auth=auth)._compute_auth_tag(b"msg", _ENGINE_ID)
        for auth in _SHA2_PROTOCOLS
    }
    assert len(set(tags.values())) == len(_SHA2_PROTOCOLS)


def test_sha256_authed_message_rejected_under_sha224() -> None:
    """A message authenticated with SHA-256 must fail under SHA-224 (HMAC mismatch)."""
    sender = _make_model(auth=AuthProtocol.SHA256)
    receiver = _make_model(auth=AuthProtocol.SHA224)
    raw = sender.wrap_pdu(_get_pdu(12))

    with pytest.raises(AuthenticationError):
        receiver.unwrap_message(raw)


@pytest.mark.parametrize("auth", _SHA2_PROTOCOLS)
def test_sha2_auth_fails_with_wrong_key(auth: AuthProtocol) -> None:
    model = _make_model(auth=auth)
    other = _make_model(auth=auth, auth_key=b"\xcd" * _AUTH_KEY_SIZES[auth])
    raw = model.wrap_pdu(_get_pdu(13))

    with pytest.raises(AuthenticationError):
        other.unwrap_message(raw)


# ── Reeder AES-192 / AES-256 (draft-reeder-snmpv3-usm) ───────────────────────


@pytest.mark.parametrize(
    ("priv", "key_length"),
    [(PrivProtocol.AES192, 24), (PrivProtocol.AES256, 32)],
)
def test_aes192_256_authpriv_roundtrip(priv: PrivProtocol, key_length: int) -> None:
    model = _make_model(priv=priv)
    raw = model.wrap_pdu(_get_pdu(21))
    result = model.unwrap_message(raw)

    assert result is not None
    assert result.request_id == 21
    assert len(model._priv_key(_ENGINE_ID)) == key_length


@pytest.mark.parametrize("priv", [PrivProtocol.AES192, PrivProtocol.AES256])
def test_aes192_256_priv_params_is_8_octets(priv: PrivProtocol) -> None:
    from trishul_snmp.wire.v3message import decode_v3_message

    model = _make_model(priv=priv)
    raw = model.wrap_pdu(_get_pdu(22))
    view = decode_v3_message(raw)
    assert len(view.usm_params.priv_params) == 8


def test_reeder_ku_extended_before_localization() -> None:
    """The engine-independent Ku is extended to the cipher key length first."""
    model = _make_model(priv=PrivProtocol.AES256)
    ku = model._ku(_PRIV_PASSWORD)
    ku_ext = model._reeder_ku(_PRIV_PASSWORD)

    assert len(ku) == hashlib.md5(b"").digest_size  # noqa: S324
    assert len(ku_ext) == 32
    assert ku_ext[:16] == ku  # the extension preserves the original digest

    localized = model._localize_priv_key(_PRIV_PASSWORD, _ENGINE_ID)
    reeder_localized = model._localize_priv_key_reeder(_PRIV_PASSWORD, _ENGINE_ID)
    assert reeder_localized != localized
    assert len(reeder_localized) == 32


def test_reeder_localized_key_lengths() -> None:
    assert len(_make_model(priv=PrivProtocol.AES192)._priv_key(_ENGINE_ID)) == 24
    assert len(_make_model(priv=PrivProtocol.AES256)._priv_key(_ENGINE_ID)) == 32
    assert len(_make_model(priv=PrivProtocol.THREEDES_EDE)._priv_key(_ENGINE_ID)) == 32


def test_reeder_key_differs_across_engine_and_password() -> None:
    model = _make_model(priv=PrivProtocol.AES256)
    key_a = model._priv_key(_ENGINE_ID)

    other_engine = b"\x80\x00\x99" + b"\x11" * 14
    assert model._priv_key(other_engine) != key_a

    other_pw = _make_model(priv=PrivProtocol.AES256, priv_key=b"different-password")
    assert other_pw._priv_key(_ENGINE_ID) != key_a


def test_reeder_key_differs_from_aes128_key() -> None:
    aes128_key = _make_model(priv=PrivProtocol.AES128)._priv_key(_ENGINE_ID)
    aes256_key = _make_model(priv=PrivProtocol.AES256)._priv_key(_ENGINE_ID)

    assert len(aes128_key) == 16
    assert len(aes256_key) == 32
    assert aes128_key != aes256_key


def test_aes256_message_fails_to_unwrap_under_aes128() -> None:
    """Cross-protocol negative: wrong cipher key yields undecodable plaintext."""
    sender = _make_model(priv=PrivProtocol.AES256)
    receiver = _make_model(priv=PrivProtocol.AES128)
    raw = sender.wrap_pdu(_get_pdu(23))

    assert receiver.unwrap_message(raw) is None


def test_priv_key_mismatch_fails_to_decode() -> None:
    sender = _make_model(priv=PrivProtocol.AES256, priv_key=b"password-a")
    receiver = _make_model(priv=PrivProtocol.AES256, priv_key=b"password-b")
    raw = sender.wrap_pdu(_get_pdu(24))

    assert receiver.unwrap_message(raw) is None


# ── 3DES-EDE-CBC (draft-reeder usm3DESEDEPrivProtocol) ───────────────────────


def test_3des_ede_authpriv_roundtrip() -> None:
    model = _make_model(priv=PrivProtocol.THREEDES_EDE)
    raw = model.wrap_pdu(_get_pdu(31))
    result = model.unwrap_message(raw)

    assert result is not None
    assert result.request_id == 31


def test_3des_ede_key_material_layout_and_iv() -> None:
    """First 24 octets are the 3DES key, last 8 the pre-IV; IV = pre-IV XOR salt."""
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
    from cryptography.hazmat.primitives.ciphers import Cipher, modes
    from cryptography.hazmat.primitives.padding import PKCS7

    from trishul_snmp.wire.ber import decode_tlv
    from trishul_snmp.wire.v3message import decode_scoped_pdu, decode_v3_message

    model = _make_model(priv=PrivProtocol.THREEDES_EDE)
    raw = model.wrap_pdu(_get_pdu(32))
    view = decode_v3_message(raw)
    salt = view.usm_params.priv_params
    assert len(salt) == 8

    key_material = model._priv_key(_ENGINE_ID)
    des_key = key_material[:24]
    pre_iv = key_material[24:32]
    iv = bytes(a ^ b for a, b in zip(pre_iv, salt, strict=True))

    # Independent cross-check with raw cryptography primitives.
    tag, ciphertext, _ = decode_tlv(view.msg_data_bytes, 0)
    assert tag == 0x04
    cipher = Cipher(TripleDES(des_key), modes.CBC(iv))
    dec = cipher.decryptor()
    padded = dec.update(ciphertext) + dec.finalize()
    unpadder = PKCS7(64).unpadder()
    scoped = unpadder.update(padded) + unpadder.finalize()
    _eid, _ctx, decoded = decode_scoped_pdu(scoped)
    assert decoded.request_id == 32


def test_3des_ede_each_wrap_uses_fresh_salt() -> None:
    from trishul_snmp.wire.v3message import decode_v3_message

    model = _make_model(priv=PrivProtocol.THREEDES_EDE)
    raw1 = model.wrap_pdu(_get_pdu(33))
    raw2 = model.wrap_pdu(_get_pdu(34))
    v1 = decode_v3_message(raw1)
    v2 = decode_v3_message(raw2)

    assert v1.usm_params.priv_params != v2.usm_params.priv_params
    assert raw1 != raw2


def test_3des_ede_salt_first_octet_changes_between_messages() -> None:
    from trishul_snmp.wire.v3message import decode_v3_message

    model = _make_model(priv=PrivProtocol.THREEDES_EDE)
    salts = [
        decode_v3_message(model.wrap_pdu(_get_pdu(i))).usm_params.priv_params for i in range(35, 39)
    ]

    for prev, cur in zip(salts, salts[1:], strict=False):
        assert prev[0] != cur[0]


def test_3des_ede_rejects_priv_params_longer_than_8() -> None:
    from trishul_snmp.wire.v3message import UsmParams, decode_v3_message, encode_v3_message

    model = _make_model(priv=PrivProtocol.THREEDES_EDE)
    raw = model.wrap_pdu(_get_pdu(36))
    view = decode_v3_message(raw)
    p = view.usm_params
    padded_usm = UsmParams(
        engine_id=p.engine_id,
        engine_boots=p.engine_boots,
        engine_time=p.engine_time,
        username=p.username,
        auth_params=b"\x00" * 12,
        priv_params=p.priv_params + b"\x00",
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


@pytest.mark.parametrize("priv", _REEDER_PRIVS)
def test_reeder_priv_mismatch_fails_to_decode(priv: PrivProtocol) -> None:
    sender = _make_model(priv=priv)
    receiver = _make_model(priv=priv, priv_key=b"wrong-password")
    raw = sender.wrap_pdu(_get_pdu(37))

    assert receiver.unwrap_message(raw) is None


# ── Reeder KDF caching (#12) ──────────────────────────────────────────────────


def test_reeder_kdf_caches_reuse_ku_across_wraps() -> None:
    user = UsmUser(
        username="parity",
        auth_protocol=AuthProtocol.MD5,
        auth_key=b"authpassword1",
        priv_protocol=PrivProtocol.AES256,
        priv_key=_PRIV_PASSWORD,
    )
    model = UsmModel(user=user)
    model._engine_id = _ENGINE_ID
    model._engine_boots = 2
    model._engine_time = 500
    ku_calls: list[bytes] = []
    real_ku = model._ku

    def _counting_ku(password: bytes) -> bytes:
        ku_calls.append(password)
        return real_ku(password)

    model._ku = _counting_ku  # type: ignore[method-assign]

    for _ in range(5):
        model.wrap_pdu(_get_pdu())

    # once for the auth passphrase, once for the priv passphrase
    assert len(ku_calls) == 2
    assert len(model._reeder_ku_cache) == 1
    assert len(model._reeder_localized_cache) == 1

    model.wrap_pdu(_get_pdu())
    assert len(ku_calls) == 2


def test_reeder_localized_cache_invalidated_on_boots_change() -> None:
    model = _make_model(priv=PrivProtocol.AES256)
    model.wrap_pdu(_get_pdu())
    assert len(model._reeder_localized_cache) == 1

    model._adopt_engine_state(_ENGINE_ID, boots=3, engine_time=600)
    assert model._reeder_localized_cache == {}

    model.wrap_pdu(_get_pdu())
    assert len(model._reeder_localized_cache) == 1


# ── enum surface ──────────────────────────────────────────────────────────────


def test_auth_protocol_enum_surface() -> None:
    assert {p.name for p in AuthProtocol} == {
        "NONE",
        "MD5",
        "SHA1",
        "SHA224",
        "SHA256",
        "SHA384",
        "SHA512",
    }


def test_priv_protocol_enum_surface() -> None:
    assert {p.name for p in PrivProtocol} == {
        "NONE",
        "DES",
        "AES128",
        "AES192",
        "AES256",
        "THREEDES_EDE",
    }


# ── DES-CBC (#11): stopped — no single-DES primitive in installed cryptography ──


def test_des_cbc_still_unsupported_with_installed_cryptography() -> None:
    """#11 DES-CBC: the installed cryptography exposes no single-DES primitive,
    so PrivProtocol.DES keeps raising ProtocolError instead of vendoring crypto."""
    model = _make_model(priv=PrivProtocol.DES)
    with pytest.raises(ProtocolError, match="DES"):
        model.wrap_pdu(_get_pdu(38))
    with pytest.raises(ProtocolError, match="DES"):
        model._decrypt_des(b"\x04\x04data", b"\x00" * 8)
