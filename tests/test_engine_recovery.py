"""Engine-recovery REPORT delivery: immediate dispatcher surfacing + client retry.

A ``usmStatsNotInTimeWindows`` REPORT is consumed by the USM model (which
adopts the peer's authoritative engine state) and now surfaces as
:class:`EngineRecoveryReportError` from the dispatcher instead of being
swallowed until the pending request times out.  The manager and the
``V3Notifier.send_inform`` path consume the recovery flag and retry once.
"""

from __future__ import annotations

import pytest

from trishul_snmp import V3Manager, V3Notifier
from trishul_snmp.errors import EngineRecoveryReportError
from trishul_snmp.security.usm import AuthProtocol, UsmModel, UsmUser
from trishul_snmp.types import NullValue
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind

_ENGINE_ID = b"\x80\x00\x1f\x88\x80" + b"\x00" * 11

# usmStatsNotInTimeWindows.0 = 1.3.6.1.6.3.15.1.1.2.0
_NOT_IN_TIME_WINDOWS_OID_BYTES = b"\x2b\x06\x01\x06\x03\x0f\x01\x01\x02\x00"


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


def _response_pdu(request_id: int) -> Pdu:
    return Pdu(
        pdu_type=PduType.RESPONSE,
        request_id=request_id,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )


def _make_model(*, flag: bool = False) -> UsmModel:
    """A discovered noAuthNoPriv UsmModel with optional recovery flag pre-set."""
    model = UsmModel(user=UsmUser(username="simulator", auth_protocol=AuthProtocol.NONE))
    model._engine_id = _ENGINE_ID
    model._engine_boots = 2
    model._engine_time = 100
    model._engine_recovery_needed = flag
    return model


# ── manager: report-driven retry ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_v3manager_retries_immediately_on_report_error() -> None:
    """A REPORT-driven error must trigger consume-flag + one immediate retry."""
    mgr = V3Manager(host="127.0.0.1", user=UsmUser(username="simulator"))
    model = mgr._session._security
    assert isinstance(model, UsmModel)
    model._engine_recovery_needed = True  # the report was just processed

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
            raise EngineRecoveryReportError("engine recovery", report=b"report")
        return _response_pdu(1)

    mgr._session._dispatcher.send_pdu = _fake_send_pdu  # type: ignore[method-assign]

    response = await mgr.get("1.3.6.1.2.1.1.1.0")

    assert response.request_id == 1
    assert len(sent) == 2
    assert model.engine_recovery_needed is False


@pytest.mark.asyncio
async def test_v3manager_report_error_without_flag_propagates() -> None:
    """A REPORT error with no recovery flag set must propagate unchanged."""
    mgr = V3Manager(host="127.0.0.1", user=UsmUser(username="simulator"))
    model = mgr._session._security
    assert isinstance(model, UsmModel)
    model._engine_id = _ENGINE_ID

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
        raise EngineRecoveryReportError("engine recovery", report=b"report")

    mgr._session._dispatcher.send_pdu = _fake_send_pdu  # type: ignore[method-assign]

    with pytest.raises(EngineRecoveryReportError):
        await mgr.get("1.3.6.1.2.1.1.1.0")
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_v3manager_retry_report_error_clears_flag_and_propagates() -> None:
    """If the retry also draws a REPORT, the flag is cleared before propagating."""
    mgr = V3Manager(host="127.0.0.1", user=UsmUser(username="simulator"))
    model = mgr._session._security
    assert isinstance(model, UsmModel)
    model._engine_recovery_needed = True

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
        if len(sent) == 2:
            model._engine_recovery_needed = True  # second REPORT was processed
        raise EngineRecoveryReportError("engine recovery", report=b"report")

    mgr._session._dispatcher.send_pdu = _fake_send_pdu  # type: ignore[method-assign]

    with pytest.raises(EngineRecoveryReportError):
        await mgr.get("1.3.6.1.2.1.1.1.0")
    assert len(sent) == 2
    assert model.engine_recovery_needed is False


@pytest.mark.asyncio
async def test_v3manager_recovers_via_report_without_timeout() -> None:
    """End-to-end: REPORT surfaces immediately, one retry, no timeout datagram."""
    from trishul_snmp.wire.v3message import decode_scoped_pdu, decode_v3_message

    mgr = V3Manager(host="127.0.0.1", user=UsmUser(username="simulator"), retries=0)
    model = mgr._session._security
    assert isinstance(model, UsmModel)
    model._engine_id = _ENGINE_ID
    model._engine_boots = 2
    model._engine_time = 100

    report_bytes = _build_report_bytes(_ENGINE_ID, username=b"simulator")

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
        # Echo a RESPONSE for whatever request the recovered attempt sent.
        view = decode_v3_message(last_sent["msg"])
        _eid, _ctx, pdu = decode_scoped_pdu(view.msg_data_bytes)
        return model.wrap_pdu(_response_pdu(pdu.request_id))

    mgr._session._client.send = _fake_send  # type: ignore[method-assign]
    mgr._session._client.receive = _fake_receive  # type: ignore[method-assign]

    response = await mgr.get("1.3.6.1.2.1.1.1.0")

    # Exactly one stale attempt + one recovered attempt.  Under the old
    # swallow-the-REPORT behaviour the response would have matched the first
    # request and only one datagram would ever be sent.
    assert state["sent"] == 2
    retried_view = decode_v3_message(last_sent["msg"])
    _eid, _ctx, retried_pdu = decode_scoped_pdu(retried_view.msg_data_bytes)
    assert response.request_id == retried_pdu.request_id
    assert model.engine_recovery_needed is False
    assert model._engine_boots == 9
    assert model._engine_time == 1234


# ── notifier: report-driven retry in V3Notifier.send_inform ───────────────────


@pytest.mark.asyncio
async def test_v3notifier_send_inform_retries_immediately_on_report_error() -> None:
    """send_inform must consume the flag and re-issue the inform once."""
    notifier = V3Notifier(host="127.0.0.1", user=UsmUser(username="simulator"))
    model = notifier._session._security
    assert isinstance(model, UsmModel)
    model._engine_id = _ENGINE_ID
    model._engine_recovery_needed = True

    calls: list[object] = []
    recovered_request_id: int | None = None

    async def _fake_send_prepared_request(request: object) -> Pdu:
        calls.append(request)
        if len(calls) == 1:
            raise EngineRecoveryReportError("engine recovery", report=b"report")
        from trishul_snmp.wire.v3message import decode_scoped_pdu, decode_v3_message

        encoded = request.encoded_message  # type: ignore[attr-defined]
        view = decode_v3_message(encoded)
        _eid, _ctx, pdu = decode_scoped_pdu(view.msg_data_bytes)
        nonlocal recovered_request_id
        recovered_request_id = pdu.request_id
        return _response_pdu(pdu.request_id)

    notifier._session._dispatcher.send_prepared_request = _fake_send_prepared_request  # type: ignore[method-assign]

    response = await notifier.send_inform("1.3.6.1.6.3.1.1.5.1")

    assert len(calls) == 2
    assert response.request_id == recovered_request_id
    assert model.engine_recovery_needed is False


@pytest.mark.asyncio
async def test_v3notifier_send_inform_report_error_without_flag_propagates() -> None:
    """A REPORT error with no recovery flag set must propagate unchanged."""
    notifier = V3Notifier(host="127.0.0.1", user=UsmUser(username="simulator"))
    model = notifier._session._security
    assert isinstance(model, UsmModel)
    model._engine_id = _ENGINE_ID

    async def _fake_send_prepared_request(request: object) -> Pdu:
        del request
        raise EngineRecoveryReportError("engine recovery", report=b"report")

    notifier._session._dispatcher.send_prepared_request = _fake_send_prepared_request  # type: ignore[method-assign]

    with pytest.raises(EngineRecoveryReportError):
        await notifier.send_inform("1.3.6.1.6.3.1.1.5.1")
    assert model.engine_recovery_needed is False


@pytest.mark.asyncio
async def test_v3notifier_send_inform_retry_report_error_clears_flag_and_propagates() -> None:
    """If the retried inform also draws a REPORT, the flag is cleared before propagating."""
    notifier = V3Notifier(host="127.0.0.1", user=UsmUser(username="simulator"))
    model = notifier._session._security
    assert isinstance(model, UsmModel)
    model._engine_id = _ENGINE_ID
    model._engine_recovery_needed = True

    calls: list[object] = []

    async def _fake_send_prepared_request(request: object) -> Pdu:
        del request
        calls.append(1)
        if len(calls) == 2:
            model._engine_recovery_needed = True  # second REPORT was processed
        raise EngineRecoveryReportError("engine recovery", report=b"report")

    notifier._session._dispatcher.send_prepared_request = _fake_send_prepared_request  # type: ignore[method-assign]

    with pytest.raises(EngineRecoveryReportError):
        await notifier.send_inform("1.3.6.1.6.3.1.1.5.1")
    assert len(calls) == 2
    assert model.engine_recovery_needed is False


@pytest.mark.asyncio
async def test_v3notifier_send_inform_recovers_via_report_without_timeout() -> None:
    """End-to-end: inform REPORT surfaces immediately, one retry, no timeout."""
    from trishul_snmp.wire.v3message import decode_scoped_pdu, decode_v3_message

    notifier = V3Notifier(host="127.0.0.1", user=UsmUser(username="simulator"), retries=0)
    model = notifier._session._security
    assert isinstance(model, UsmModel)
    model._engine_id = _ENGINE_ID
    model._engine_boots = 2
    model._engine_time = 100

    report_bytes = _build_report_bytes(_ENGINE_ID, username=b"simulator")

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
        view = decode_v3_message(last_sent["msg"])
        _eid, _ctx, pdu = decode_scoped_pdu(view.msg_data_bytes)
        return model.wrap_pdu(_response_pdu(pdu.request_id))

    notifier._session._client.send = _fake_send  # type: ignore[method-assign]
    notifier._session._client.receive = _fake_receive  # type: ignore[method-assign]

    response = await notifier.send_inform("1.3.6.1.6.3.1.1.5.1")

    assert state["sent"] == 2
    retried_view = decode_v3_message(last_sent["msg"])
    _eid, _ctx, retried_pdu = decode_scoped_pdu(retried_view.msg_data_bytes)
    assert response.request_id == retried_pdu.request_id
    assert model.engine_recovery_needed is False
    assert model._engine_boots == 9
    assert model._engine_time == 1234
