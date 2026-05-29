"""Tests for V3Manager and V3Notifier constructor wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from trishul_snmp import V3Manager, V3Notifier
from trishul_snmp.security.usm import AuthProtocol, UsmModel, UsmUser


def _make_user(*, username: str = "testuser") -> UsmUser:
    return UsmUser(username=username, auth_protocol=AuthProtocol.NONE)


# ── V3Manager ─────────────────────────────────────────────────────────────────


def test_v3manager_constructs_usm_model() -> None:
    """V3Manager must wire a UsmModel (not CommunityModel) as the security model."""
    user = _make_user()
    mgr = V3Manager(host="127.0.0.1", user=user)
    assert isinstance(mgr._session._security, UsmModel)


def test_v3manager_usm_model_holds_user() -> None:
    """The UsmModel inside V3Manager must carry the exact UsmUser passed in."""
    user = _make_user(username="alice")
    mgr = V3Manager(host="127.0.0.1", user=user)
    model = mgr._session._security
    assert isinstance(model, UsmModel)
    assert model.user is user


def test_v3manager_context_name_default_is_empty() -> None:
    user = _make_user()
    mgr = V3Manager(host="127.0.0.1", user=user)
    model = mgr._session._security
    assert isinstance(model, UsmModel)
    assert model.context_name == b""


def test_v3manager_context_name_is_threaded() -> None:
    user = _make_user()
    mgr = V3Manager(host="127.0.0.1", user=user, context_name=b"myctx")
    model = mgr._session._security
    assert isinstance(model, UsmModel)
    assert model.context_name == b"myctx"


def test_v3manager_is_snmpmanager_subclass() -> None:
    from trishul_snmp.manager.client import SnmpManager

    assert issubclass(V3Manager, SnmpManager)


def test_v3manager_exported_from_package() -> None:
    """V3Manager must be importable directly from trishul_snmp."""
    import trishul_snmp

    assert trishul_snmp.V3Manager is V3Manager


# ── V3Notifier ────────────────────────────────────────────────────────────────


def test_v3notifier_constructs_usm_model() -> None:
    """V3Notifier must wire a UsmModel as the security model."""
    user = _make_user()
    notifier = V3Notifier(host="127.0.0.1", user=user)
    assert isinstance(notifier._session._security, UsmModel)


def test_v3notifier_usm_model_holds_user() -> None:
    user = _make_user(username="bob")
    notifier = V3Notifier(host="127.0.0.1", user=user)
    model = notifier._session._security
    assert isinstance(model, UsmModel)
    assert model.user is user


def test_v3notifier_context_name_default_is_empty() -> None:
    user = _make_user()
    notifier = V3Notifier(host="127.0.0.1", user=user)
    model = notifier._session._security
    assert isinstance(model, UsmModel)
    assert model.context_name == b""


def test_v3notifier_context_name_is_threaded() -> None:
    user = _make_user()
    notifier = V3Notifier(host="127.0.0.1", user=user, context_name=b"trapctx")
    model = notifier._session._security
    assert isinstance(model, UsmModel)
    assert model.context_name == b"trapctx"


def test_v3notifier_is_snmpnotifier_subclass() -> None:
    from trishul_snmp.notify.client import SnmpNotifier

    assert issubclass(V3Notifier, SnmpNotifier)


def test_v3notifier_exported_from_package() -> None:
    """V3Notifier must be importable directly from trishul_snmp."""
    import trishul_snmp

    assert trishul_snmp.V3Notifier is V3Notifier


# ── open() calls prepare() via session ───────────────────────────────────────


@pytest.mark.asyncio
async def test_v3manager_open_calls_prepare() -> None:
    """V3Manager.open() must trigger UsmModel.prepare() via SnmpSession."""
    user = _make_user()
    mgr = V3Manager(host="127.0.0.1", user=user)
    model = mgr._session._security
    assert isinstance(model, UsmModel)

    prepare_calls: list[object] = []

    async def _fake_prepare(dispatcher: object) -> None:
        prepare_calls.append(dispatcher)

    model.prepare = _fake_prepare  # type: ignore[method-assign]

    with patch.object(mgr._session._client, "open", new_callable=AsyncMock):
        await mgr.open()

    assert len(prepare_calls) == 1


@pytest.mark.asyncio
async def test_v3notifier_open_calls_prepare() -> None:
    """V3Notifier.open() must trigger UsmModel.prepare() via SnmpSession."""
    user = _make_user()
    notifier = V3Notifier(host="127.0.0.1", user=user)
    model = notifier._session._security
    assert isinstance(model, UsmModel)

    prepare_calls: list[object] = []

    async def _fake_prepare(dispatcher: object) -> None:
        prepare_calls.append(dispatcher)

    model.prepare = _fake_prepare  # type: ignore[method-assign]

    with patch.object(notifier._session._client, "open", new_callable=AsyncMock):
        await notifier.open()

    assert len(prepare_calls) == 1


@pytest.mark.asyncio
async def test_v3notifier_send_trap_raises_protocol_error() -> None:
    """V3Notifier.send_trap() must raise ProtocolError immediately.

    SNMPv3 traps require the sender's own authoritative engine state (RFC 3412
    §7.1.9). After engine discovery the model holds the receiver's engine state,
    not the sender's, so emitting a trap would silently produce a protocol-incorrect
    message. Raising ProtocolError is the safe behaviour.
    """
    from trishul_snmp.errors import ProtocolError

    user = _make_user()
    notifier = V3Notifier(host="127.0.0.1", user=user)

    with pytest.raises(ProtocolError, match="send_inform"):
        await notifier.send_trap("1.3.6.1.6.3.1.1.5.1")
