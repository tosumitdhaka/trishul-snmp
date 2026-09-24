"""Construction-time validation of UsmUser key material (#16).

UsmUser must reject a non-NONE auth/priv protocol configured without key
material, and reject localized auth keys that are not the protocol's digest
length, so misconfiguration surfaces at construction instead of as wire-time
HMAC failures.
"""

from __future__ import annotations

import pytest

from trishul_snmp.errors import ProtocolError
from trishul_snmp.security.usm import AuthProtocol, PrivProtocol, UsmUser

_AUTH_PROTOCOLS = [p for p in AuthProtocol if p is not AuthProtocol.NONE]
_PRIV_PROTOCOLS = [p for p in PrivProtocol if p is not PrivProtocol.NONE]

_AUTH_KEY_LENGTHS = {
    AuthProtocol.MD5: 16,
    AuthProtocol.SHA1: 20,
    AuthProtocol.SHA224: 28,
    AuthProtocol.SHA256: 32,
    AuthProtocol.SHA384: 48,
    AuthProtocol.SHA512: 64,
}


# ── auth: empty/missing key ───────────────────────────────────────────────────


@pytest.mark.parametrize("proto", _AUTH_PROTOCOLS)
def test_auth_protocol_requires_key(proto: AuthProtocol) -> None:
    """auth_protocol != NONE with no auth_key must be rejected at construction."""
    with pytest.raises(ProtocolError, match="auth_key"):
        UsmUser(username="probe", auth_protocol=proto)


@pytest.mark.parametrize("proto", _AUTH_PROTOCOLS)
def test_auth_protocol_rejects_empty_localized_key(proto: AuthProtocol) -> None:
    """An empty key is invalid even when auth_key_localized=True."""
    with pytest.raises(ProtocolError, match="auth_key"):
        UsmUser(username="probe", auth_protocol=proto, auth_key=b"", auth_key_localized=True)


@pytest.mark.parametrize("proto", _AUTH_PROTOCOLS)
def test_auth_accepts_passphrase(proto: AuthProtocol) -> None:
    """A non-empty passphrase of any length is valid (KDF runs at message time)."""
    user = UsmUser(username="probe", auth_protocol=proto, auth_key=b"short")
    assert user.auth_key == b"short"


# ── auth: localized key length ────────────────────────────────────────────────


@pytest.mark.parametrize("proto", _AUTH_PROTOCOLS)
def test_auth_accepts_digest_sized_localized_key(proto: AuthProtocol) -> None:
    user = UsmUser(
        username="probe",
        auth_protocol=proto,
        auth_key=b"\xab" * _AUTH_KEY_LENGTHS[proto],
        auth_key_localized=True,
    )
    assert len(user.auth_key) == _AUTH_KEY_LENGTHS[proto]


@pytest.mark.parametrize("proto", _AUTH_PROTOCOLS)
@pytest.mark.parametrize("delta", [-1, +1])
def test_auth_rejects_wrong_length_localized_key(proto: AuthProtocol, delta: int) -> None:
    required = _AUTH_KEY_LENGTHS[proto]
    with pytest.raises(ProtocolError, match="auth_key"):
        UsmUser(
            username="probe",
            auth_protocol=proto,
            auth_key=b"\xab" * (required + delta),
            auth_key_localized=True,
        )


def test_wrong_length_error_names_field_problem_and_protocol() -> None:
    with pytest.raises(ProtocolError) as excinfo:
        UsmUser(
            username="probe",
            auth_protocol=AuthProtocol.MD5,
            auth_key=b"\xab" * 15,
            auth_key_localized=True,
        )
    msg = str(excinfo.value)
    assert "auth_key" in msg
    assert "16" in msg
    assert "15" in msg
    assert "MD5" in msg


# ── priv: empty/missing key ───────────────────────────────────────────────────


@pytest.mark.parametrize("proto", _PRIV_PROTOCOLS)
def test_priv_protocol_requires_key(proto: PrivProtocol) -> None:
    """priv_protocol != NONE with no priv_key must be rejected at construction."""
    with pytest.raises(ProtocolError, match="priv_key"):
        UsmUser(
            username="probe",
            auth_protocol=AuthProtocol.MD5,
            auth_key=b"auth-passphrase",
            priv_protocol=proto,
        )


@pytest.mark.parametrize("proto", _PRIV_PROTOCOLS)
def test_priv_accepts_passphrase(proto: PrivProtocol) -> None:
    """A non-empty priv passphrase is valid; priv keys are always localized."""
    user = UsmUser(
        username="probe",
        auth_protocol=AuthProtocol.MD5,
        auth_key=b"auth-passphrase",
        priv_protocol=proto,
        priv_key=b"priv-passphrase",
    )
    assert user.priv_key == b"priv-passphrase"


def test_priv_error_names_field_problem_and_protocol() -> None:
    with pytest.raises(ProtocolError) as excinfo:
        UsmUser(
            username="probe",
            auth_protocol=AuthProtocol.MD5,
            auth_key=b"auth-passphrase",
            priv_protocol=PrivProtocol.AES128,
            priv_key=b"",
        )
    msg = str(excinfo.value)
    assert "priv_key" in msg
    assert "empty/missing key" in msg
    assert "AES128" in msg


# ── noAuthNoPriv ──────────────────────────────────────────────────────────────


def test_noauthnopriv_without_keys_is_valid() -> None:
    user = UsmUser(username="probe")
    assert user.auth_protocol is AuthProtocol.NONE
    assert user.priv_protocol is PrivProtocol.NONE
    assert user.auth_key == b""
    assert user.priv_key == b""


def test_noauthnopriv_with_stray_keys_is_valid() -> None:
    """Keys are ignored when both protocols are NONE and must not be rejected."""
    user = UsmUser(username="probe", auth_key=b"x", priv_key=b"y")
    assert user.auth_key == b"x"
    assert user.priv_key == b"y"


# ── DES (#11): enum retained, fail-fast path intact ──────────────────────────


def test_des_with_key_constructs() -> None:
    """DES remains constructible with key material; the fail-fast error stays at
    wire time (no single-DES primitive in installed cryptography, see #11)."""
    user = UsmUser(
        username="probe",
        auth_protocol=AuthProtocol.MD5,
        auth_key=b"auth-passphrase",
        priv_protocol=PrivProtocol.DES,
        priv_key=b"priv-passphrase",
    )
    assert user.priv_protocol is PrivProtocol.DES
