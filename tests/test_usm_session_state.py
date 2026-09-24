"""Tests for SNMPv3 USM session state — key caching, monotonic time, report recovery."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from trishul_snmp import V3Manager
from trishul_snmp.errors import RequestTimeoutError
from trishul_snmp.security.usm import AuthProtocol, PrivProtocol, UsmModel, UsmUser
from trishul_snmp.types import NullValue
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind

_ENGINE_ID = b"\x80\x00\x1f\x88\x80" + b"\x00" * 11

_AUTH_PASSWORD = b"authpassword1"
_PRIV_PASSWORD = b"privpassword1"

# usmStatsNotInTimeWindows.0 = 1.3.6.1.6.3.15.1.1.2.0
_NOT_IN_TIME_WINDOWS_OID_BYTES = b"\x2b\x06\x01\x06\x03\x0f\x01\x01\x02\x00"
# usmStatsUnknownEngineIDs.0 = 1.3.6.1.6.3.15.1.1.3.0
_UNKNOWN_ENGINE_OID_BYTES = b"\x2b\x06\x01\x06\x03\x0f\x01\x01\x03\x00"


def _make_get_pdu(request_id: int = 1) -> Pdu:
    return Pdu(
        pdu_type=PduType.GET,
        request_id=request_id,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )


def _make_authpriv_passphrase_model() -> UsmModel:
    """authPriv model whose keys are passphrases, so the RFC 3414 KDF actually runs."""
    user = UsmUser(
        username="authpriv",
        auth_protocol=AuthProtocol.MD5,
        auth_key=_AUTH_PASSWORD,
        priv_protocol=PrivProtocol.AES128,
        priv_key=_PRIV_PASSWORD,
    )
    model = UsmModel(user=user)
    model._engine_id = _ENGINE_ID
    model._engine_boots = 2
    model._engine_time = 500
    return model


def _build_report_bytes(
    engine_id: bytes,
    *,
    engine_boots: int = 9,
    engine_time: int = 1234,
    username: bytes = b"",
    oid_bytes: bytes = _NOT_IN_TIME_WINDOWS_OID_BYTES,
) -> bytes:
    """Build a minimal syntactically valid SNMPv3 REPORT message (noAuthNoPriv)."""
    from trishul_snmp.wire.ber import encode_tlv
    from trishul_snmp.wire.v3message import UsmParams, encode_v3_message

    report_pdu_tag = 0xA8
    sequence_tag = 0x30
    integer_tag = 0x02

    def _enc_int(v: int) -> bytes:
        return encode_tlv(integer_tag, v.to_bytes((v.bit_length() + 8) // 8 or 1, "big"))

    varbind = encode_tlv(sequence_tag, encode_tlv(0x06, oid_bytes) + encode_tlv(0x41, b"\x01"))
    report_pdu_content = b"".join(
        [_enc_int(1), _enc_int(0), _enc_int(0), encode_tlv(sequence_tag, varbind)]
    )
    report_pdu_bytes = encode_tlv(report_pdu_tag, report_pdu_content)
    scoped_raw = encode_tlv(
        sequence_tag, encode_tlv(0x04, engine_id) + encode_tlv(0x04, b"") + report_pdu_bytes
    )
    usm = UsmParams(
        engine_id=engine_id,
        engine_boots=engine_boots,
        engine_time=engine_time,
        username=username,
        auth_params=b"",
        priv_params=b"",
    )
    return encode_v3_message(
        msg_id=1, msg_max_size=65507, flags=0, usm_params=usm, msg_data_bytes=scoped_raw
    )


# ── RFC 3414 key-derivation caching ───────────────────────────────────────────


def test_localized_key_kdf_runs_once_per_password_across_wraps() -> None:
    """The 1 MiB Ku derivation must run once per (protocol, password), not per message."""
    model = _make_authpriv_passphrase_model()
    pdu = _make_get_pdu()

    ku_calls: list[bytes] = []
    real_ku = model._ku

    def _counting_ku(password: bytes) -> bytes:
        ku_calls.append(password)
        return real_ku(password)

    model._ku = _counting_ku  # type: ignore[method-assign]

    for _ in range(5):
        model.wrap_pdu(pdu)

    assert len(ku_calls) == 2
    assert set(ku_calls) == {_AUTH_PASSWORD, _PRIV_PASSWORD}
    assert len(model._localized_cache) == 2

    model.wrap_pdu(pdu)
    assert len(ku_calls) == 2  # still cached after another wrap


def test_localized_cache_invalidated_when_engine_boots_change() -> None:
    """Adopting new authoritative engine state with different boots drops localized keys."""
    model = _make_authpriv_passphrase_model()
    pdu = _make_get_pdu()

    ku_calls: list[bytes] = []
    real_ku = model._ku

    def _counting_ku(password: bytes) -> bytes:
        ku_calls.append(password)
        return real_ku(password)

    model._ku = _counting_ku  # type: ignore[method-assign]

    model.wrap_pdu(pdu)
    assert len(ku_calls) == 2
    model.wrap_pdu(pdu)
    assert len(ku_calls) == 2  # warm cache

    report = _build_report_bytes(_ENGINE_ID, engine_boots=3, engine_time=600)
    model._parse_discovery_response(report)
    assert model._engine_boots == 3

    model.wrap_pdu(pdu)
    assert len(ku_calls) == 4  # localized cache was invalidated; Ku re-derived once each
    assert set(ku_calls) == {_AUTH_PASSWORD, _PRIV_PASSWORD}

    model.wrap_pdu(pdu)
    assert len(ku_calls) == 4  # warm again


# ── monotonic engine-time advance ─────────────────────────────────────────────


def test_engine_time_advances_with_monotonic_clock() -> None:
    """wrap_pdu must report discovery engineTime plus elapsed monotonic seconds."""
    model = UsmModel(user=UsmUser(username="simulator", auth_protocol=AuthProtocol.NONE))
    report = _build_report_bytes(_ENGINE_ID, engine_boots=7, engine_time=1000)

    with patch("trishul_snmp.security.usm.time.monotonic", return_value=10_000.0):
        model._parse_discovery_response(report)
    assert model._engine_time == 1000

    pdu = _make_get_pdu()
    with patch("trishul_snmp.security.usm.time.monotonic", return_value=10_042.9):
        raw = model.wrap_pdu(pdu)

    from trishul_snmp.wire.v3message import decode_v3_message

    view = decode_v3_message(raw)
    assert view.usm_params.engine_time == 1042  # 1000 + floor(42.9)


def test_engine_time_not_advanced_without_discovery_reference() -> None:
    """Directly-assigned engine time (no discovery) must be used verbatim."""
    model = UsmModel(user=UsmUser(username="simulator", auth_protocol=AuthProtocol.NONE))
    model._engine_id = _ENGINE_ID
    model._engine_boots = 2
    model._engine_time = 500

    raw = model.wrap_pdu(_make_get_pdu())

    from trishul_snmp.wire.v3message import decode_v3_message

    view = decode_v3_message(raw)
    assert view.usm_params.engine_time == 500


# ── usmStatsNotInTimeWindows REPORT handling ──────────────────────────────────


def test_unwrap_sets_recovery_flag_on_not_in_time_windows_report() -> None:
    """A time-window REPORT must be swallowed but adopt authoritative engine state."""
    user = UsmUser(username="simulator", auth_protocol=AuthProtocol.NONE)
    model = UsmModel(user=user)
    model._engine_id = _ENGINE_ID
    model._engine_boots = 2
    model._engine_time = 100
    assert model._monotonic_ref is None

    report_bytes = _build_report_bytes(
        _ENGINE_ID, engine_boots=9, engine_time=1234, username=b"simulator"
    )

    result = model.unwrap_message(report_bytes)

    assert result is None
    assert model.engine_recovery_needed is True
    assert model._engine_boots == 9
    assert model._engine_time == 1234
    assert model._monotonic_ref is not None

    model.clear_engine_recovery()
    assert model.engine_recovery_needed is False


def test_unwrap_ignores_unrelated_reports() -> None:
    """A REPORT without usmStatsNotInTimeWindows must not touch engine state."""
    user = UsmUser(username="simulator", auth_protocol=AuthProtocol.NONE)
    model = UsmModel(user=user)
    model._engine_id = _ENGINE_ID
    model._engine_boots = 2
    model._engine_time = 100

    report_bytes = _build_report_bytes(
        _ENGINE_ID,
        engine_boots=9,
        engine_time=1234,
        username=b"simulator",
        oid_bytes=_UNKNOWN_ENGINE_OID_BYTES,
    )

    result = model.unwrap_message(report_bytes)

    assert result is None
    assert model.engine_recovery_needed is False
    assert model._engine_boots == 2
    assert model._engine_time == 100


# ── manager-level recovery after a time-window timeout ───────────────────────


@pytest.mark.asyncio
async def test_v3manager_retries_once_after_engine_recovery() -> None:
    """The manager must re-issue the request once when the model flagged a report."""
    user = UsmUser(username="simulator", auth_protocol=AuthProtocol.NONE)
    mgr = V3Manager(host="127.0.0.1", user=user)
    model = mgr._session._security
    assert isinstance(model, UsmModel)
    model._engine_id = _ENGINE_ID
    model._engine_boots = 2
    model._engine_time = 100
    model._engine_recovery_needed = True

    response_pdu = Pdu(
        pdu_type=PduType.RESPONSE,
        request_id=1,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )
    sent: list[int] = []

    async def _fake_send_pdu(
        pdu_type: PduType,
        varbinds: tuple[RawVarBind, ...],
        *,
        error_status: int = 0,
        error_index: int = 0,
    ) -> Pdu:
        del pdu_type, varbinds, error_status, error_index
        sent.append(len(sent))
        if len(sent) == 1:
            raise RequestTimeoutError("stale engine time")
        return response_pdu

    mgr._session._dispatcher.send_pdu = _fake_send_pdu  # type: ignore[method-assign]

    response = await mgr.get("1.3.6.1.2.1.1.1.0")

    assert response.request_id == 1
    assert len(sent) == 2
    assert model.engine_recovery_needed is False


@pytest.mark.asyncio
async def test_v3manager_timeout_without_report_propagates() -> None:
    """A plain timeout (no recovery flag) must propagate unchanged."""
    user = UsmUser(username="simulator", auth_protocol=AuthProtocol.NONE)
    mgr = V3Manager(host="127.0.0.1", user=user)
    model = mgr._session._security
    assert isinstance(model, UsmModel)
    model._engine_id = _ENGINE_ID

    async def _fake_send_pdu(
        pdu_type: PduType,
        varbinds: tuple[RawVarBind, ...],
        *,
        error_status: int = 0,
        error_index: int = 0,
    ) -> Pdu:
        del pdu_type, varbinds, error_status, error_index
        raise RequestTimeoutError("no response")

    mgr._session._dispatcher.send_pdu = _fake_send_pdu  # type: ignore[method-assign]

    with pytest.raises(RequestTimeoutError):
        await mgr.get("1.3.6.1.2.1.1.1.0")


@pytest.mark.asyncio
async def test_v3manager_recovers_via_report_then_retries() -> None:
    """End-to-end: stale request -> time-window REPORT -> adopt -> retry succeeds."""
    from trishul_snmp.wire.v3message import decode_scoped_pdu, decode_v3_message

    user = UsmUser(username="simulator", auth_protocol=AuthProtocol.NONE)
    mgr = V3Manager(host="127.0.0.1", user=user, retries=0)
    model = mgr._session._security
    assert isinstance(model, UsmModel)
    model._engine_id = _ENGINE_ID
    model._engine_boots = 2
    model._engine_time = 100

    report_bytes = _build_report_bytes(
        _ENGINE_ID, engine_boots=9, engine_time=1234, username=b"simulator"
    )

    state = {"sent": 0, "report_delivered": False}
    last_sent: dict[str, bytes] = {}

    async def _fake_send(data: bytes) -> None:
        state["sent"] += 1
        last_sent["msg"] = data

    async def _fake_receive(timeout: float) -> bytes:
        del timeout
        if not state["report_delivered"]:
            state["report_delivered"] = True
            return report_bytes
        if state["sent"] == 1:
            # The agent discarded the stale request after the report.
            raise RequestTimeoutError("no response after report")
        # Build a RESPONSE matching the freshly wrapped (recovered) request.
        view = decode_v3_message(last_sent["msg"])
        _eid, _ctx, pdu = decode_scoped_pdu(view.msg_data_bytes)
        response_pdu = Pdu(
            pdu_type=PduType.RESPONSE,
            request_id=pdu.request_id,
            error_status=0,
            error_index=0,
            varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
        )
        return model.wrap_pdu(response_pdu)

    mgr._session._client.send = _fake_send  # type: ignore[method-assign]
    mgr._session._client.receive = _fake_receive  # type: ignore[method-assign]

    response = await mgr.get("1.3.6.1.2.1.1.1.0")

    # The dispatcher issues RFC 3412 random request-ids, so assert the response
    # matched the recovered (second) request rather than a fixed value.
    retried_view = decode_v3_message(last_sent["msg"])
    _eid, _ctx, retried_pdu = decode_scoped_pdu(retried_view.msg_data_bytes)
    assert state["sent"] == 2  # exactly one stale attempt + one recovered attempt
    assert response.request_id == retried_pdu.request_id
    assert model.engine_recovery_needed is False
    assert model._engine_boots == 9
    assert model._engine_time == 1234
