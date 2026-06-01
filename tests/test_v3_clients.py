"""Tests for V3Manager and V3Notifier constructor wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from trishul_snmp import V3Manager, V3Notifier
from trishul_snmp.errors import ProtocolError
from trishul_snmp.security.usm import AuthProtocol, UsmLocalEngine, UsmModel, UsmUser
from trishul_snmp.types import NullValue
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind


def _make_user(*, username: str = "testuser") -> UsmUser:
    return UsmUser(username=username, auth_protocol=AuthProtocol.NONE)


def _make_local_engine() -> UsmLocalEngine:
    return UsmLocalEngine(
        engine_id=b"\x80\x00\x01\x02\x03" + b"\x55" * 12,
        engine_boots=10,
        engine_time=200,
    )


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


def test_v3notifier_local_engine_is_threaded() -> None:
    user = _make_user()
    local_engine = _make_local_engine()
    notifier = V3Notifier(host="127.0.0.1", user=user, local_engine=local_engine)
    model = notifier._session._security
    assert isinstance(model, UsmModel)
    assert model.local_engine is local_engine


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
async def test_v3notifier_open_skips_prepare_when_local_engine_is_present() -> None:
    user = _make_user()
    notifier = V3Notifier(host="127.0.0.1", user=user, local_engine=_make_local_engine())
    model = notifier._session._security
    assert isinstance(model, UsmModel)

    model.prepare = AsyncMock()  # type: ignore[method-assign]
    with patch.object(notifier._session._client, "open", new_callable=AsyncMock):
        await notifier.open()

    model.prepare.assert_not_awaited()


@pytest.mark.asyncio
async def test_v3notifier_send_trap_requires_local_engine() -> None:
    user = _make_user()
    notifier = V3Notifier(host="127.0.0.1", user=user)

    with pytest.raises(ProtocolError, match="local_engine"):
        await notifier.send_trap("1.3.6.1.6.3.1.1.5.1")


@pytest.mark.asyncio
async def test_v3notifier_send_trap_uses_local_engine_state() -> None:
    from trishul_snmp.wire.v3message import decode_scoped_pdu, decode_v3_message

    user = _make_user()
    local_engine = _make_local_engine()
    notifier = V3Notifier(host="127.0.0.1", user=user, local_engine=local_engine)

    send_only = AsyncMock()
    notifier._session._dispatcher.send_only = send_only  # type: ignore[method-assign]

    request_id = await notifier.send_trap("1.3.6.1.6.3.1.1.5.1")

    awaited = send_only.await_args
    assert awaited is not None
    request = awaited.args[0]
    view = decode_v3_message(request.encoded_message)
    scoped_engine_id, _ctx, pdu = decode_scoped_pdu(view.msg_data_bytes)

    assert request_id == 1
    assert view.usm_params.engine_id == local_engine.engine_id
    assert view.usm_params.engine_boots == local_engine.engine_boots
    assert view.usm_params.engine_time == local_engine.engine_time
    assert scoped_engine_id == local_engine.engine_id
    assert pdu.pdu_type is PduType.SNMPV2_TRAP


@pytest.mark.asyncio
async def test_v3notifier_send_inform_with_local_engine_discovers_peer_lazily() -> None:
    from trishul_snmp.wire.v3message import decode_scoped_pdu, decode_v3_message

    user = _make_user()
    local_engine = _make_local_engine()
    peer_engine_id = b"\x80\x00\x01\x02\x03" + b"\x77" * 12
    notifier = V3Notifier(host="127.0.0.1", user=user, local_engine=local_engine)
    model = notifier._session._security
    assert isinstance(model, UsmModel)

    async def _fake_prepare(_dispatcher: object) -> None:
        model._engine_id = peer_engine_id
        model._engine_boots = 44
        model._engine_time = 55

    async def _fake_send_prepared_request(request: object) -> Pdu:
        encoded = request.encoded_message  # type: ignore[attr-defined]
        view = decode_v3_message(encoded)
        scoped_engine_id, _ctx, pdu = decode_scoped_pdu(view.msg_data_bytes)
        assert view.usm_params.engine_id == peer_engine_id
        assert view.usm_params.engine_boots == 44
        assert view.usm_params.engine_time == 55
        assert scoped_engine_id == peer_engine_id
        assert pdu.pdu_type is PduType.INFORM_REQUEST
        return Pdu(
            pdu_type=PduType.RESPONSE,
            request_id=pdu.request_id,
            error_status=0,
            error_index=0,
            varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
        )

    model.prepare = AsyncMock(side_effect=_fake_prepare)  # type: ignore[method-assign]
    notifier._session._dispatcher.send_prepared_request = _fake_send_prepared_request  # type: ignore[method-assign]

    with patch.object(notifier._session._client, "open", new_callable=AsyncMock):
        await notifier.open()

    await notifier.send_inform("1.3.6.1.6.3.1.1.5.1")
    model.prepare.assert_awaited_once()
