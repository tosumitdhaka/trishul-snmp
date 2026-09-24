from __future__ import annotations

import asyncio
import os

import pytest

from tests.test_engine_recovery import _ENGINE_ID, _build_report_bytes
from trishul_snmp.errors import EngineRecoveryReportError, ProtocolError, RequestTimeoutError
from trishul_snmp.security.community import CommunityModel
from trishul_snmp.security.usm import AuthProtocol, UsmModel, UsmUser
from trishul_snmp.transport.dispatcher import PreparedRequest, RequestDispatcher
from trishul_snmp.types import NullValue
from trishul_snmp.wire.message import SnmpMessage, decode_message, encode_message
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind


class FakeUdpClient:
    def __init__(self, replies: list[bytes | Exception]) -> None:
        self._replies = list(replies)
        self.sent: list[bytes] = []

    def set_replies(self, replies: list[bytes | Exception]) -> None:
        self._replies = list(replies)

    async def send(self, data: bytes) -> None:
        self.sent.append(data)

    async def receive(self, timeout: float) -> bytes:
        del timeout
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


_GET_VARBINDS = (RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue()),)


def _response_bytes(*, request_id: int, community: str = "public", pdu_type: PduType) -> bytes:
    return encode_message(
        SnmpMessage(
            version=1,
            community=community,
            pdu=Pdu(
                pdu_type=pdu_type,
                request_id=request_id,
                error_status=0,
                error_index=0,
                varbinds=_GET_VARBINDS,
            ),
        )
    )


def _make_dispatcher(
    *, timeout: float = 0.5, retries: int = 0
) -> tuple[RequestDispatcher, FakeUdpClient]:
    client = FakeUdpClient([])
    dispatcher = RequestDispatcher(
        client, security=CommunityModel("public"), timeout=timeout, retries=retries
    )
    return dispatcher, client


def _get_request(
    dispatcher: RequestDispatcher, *, pdu_type: PduType = PduType.GET
) -> PreparedRequest:
    return dispatcher.prepare_request(pdu_type, _GET_VARBINDS)


def test_dispatcher_retries_after_timeout_then_succeeds() -> None:
    dispatcher, client = _make_dispatcher(retries=1)
    request = _get_request(dispatcher)
    client.set_replies(
        [
            RequestTimeoutError("timed out"),
            _response_bytes(request_id=request.request_id, pdu_type=PduType.RESPONSE),
        ]
    )

    async def scenario():
        return await dispatcher.send_prepared_request(request)

    response = asyncio.run(scenario())

    assert response.pdu_type is PduType.RESPONSE
    assert response.request_id == request.request_id
    assert len(client.sent) == 2


def test_dispatcher_ignores_unmatched_responses_until_match() -> None:
    dispatcher, client = _make_dispatcher()
    request = _get_request(dispatcher)
    client.set_replies(
        [
            _response_bytes(
                request_id=request.request_id, community="private", pdu_type=PduType.RESPONSE
            ),
            _response_bytes(request_id=999, pdu_type=PduType.RESPONSE),
            _response_bytes(request_id=request.request_id, pdu_type=PduType.RESPONSE),
        ]
    )

    async def scenario():
        return await dispatcher.send_prepared_request(request)

    response = asyncio.run(scenario())

    assert response.request_id == request.request_id
    assert len(client.sent) == 1


def test_dispatcher_skips_malformed_datagram_mid_request() -> None:
    dispatcher, client = _make_dispatcher()
    request = _get_request(dispatcher)
    client.set_replies(
        [
            b"\x30\x03\x02\x01\xff",  # SNMP-shaped but undecodable datagram
            _response_bytes(request_id=request.request_id, pdu_type=PduType.RESPONSE),
        ]
    )

    async def scenario():
        return await dispatcher.send_prepared_request(request)

    response = asyncio.run(scenario())

    assert response.pdu_type is PduType.RESPONSE
    assert response.request_id == request.request_id
    assert len(client.sent) == 1


def test_dispatcher_raises_protocol_error_for_non_response_pdu() -> None:
    dispatcher, client = _make_dispatcher()
    request = _get_request(dispatcher)
    client.set_replies([_response_bytes(request_id=request.request_id, pdu_type=PduType.GET)])

    async def scenario():
        return await dispatcher.send_prepared_request(request)

    with pytest.raises(ProtocolError, match="Expected RESPONSE PDU"):
        asyncio.run(scenario())


def test_dispatcher_raises_after_retry_budget_exhausted() -> None:
    dispatcher, client = _make_dispatcher(retries=1)
    request = _get_request(dispatcher)
    client.set_replies([RequestTimeoutError("timed out"), RequestTimeoutError("timed out")])

    async def scenario():
        return await dispatcher.send_prepared_request(request)

    with pytest.raises(RequestTimeoutError, match="timed out"):
        asyncio.run(scenario())
    assert len(client.sent) == 2


def test_dispatcher_surfaces_engine_recovery_report() -> None:
    """A usmStatsNotInTimeWindows REPORT must raise immediately, not after timeout."""
    model = UsmModel(user=UsmUser(username="simulator", auth_protocol=AuthProtocol.NONE))
    model._engine_id = _ENGINE_ID
    model._engine_boots = 2
    model._engine_time = 100

    report = _build_report_bytes(_ENGINE_ID, username=b"simulator")
    client = FakeUdpClient([report])
    dispatcher = RequestDispatcher(client, security=model, timeout=0.5, retries=0)
    request = _get_request(dispatcher)

    async def scenario():
        return await dispatcher.send_prepared_request(request)

    with pytest.raises(EngineRecoveryReportError) as excinfo:
        asyncio.run(scenario())

    assert excinfo.value.report == report
    assert len(client.sent) == 1  # raised on the first datagram — no timeout wait
    # The dispatcher must not consume the flag; the client owns that decision.
    assert model.engine_recovery_needed is True
    assert model._engine_boots == 9  # authoritative state was adopted from the report
    assert model._engine_time == 1234


def test_dispatcher_continues_past_none_datagram_without_recovery_flag() -> None:
    """A None datagram that did not set the recovery flag must be skipped."""
    model = UsmModel(user=UsmUser(username="simulator", auth_protocol=AuthProtocol.NONE))
    model._engine_id = _ENGINE_ID
    model._engine_boots = 2
    model._engine_time = 100

    # Wrong-username REPORT: unwrap_message returns None without touching the flag.
    foreign_report = _build_report_bytes(_ENGINE_ID, username=b"someone-else")
    client = FakeUdpClient([foreign_report])
    dispatcher = RequestDispatcher(client, security=model, timeout=0.5, retries=0)
    request = _get_request(dispatcher)
    response = model.wrap_pdu(
        Pdu(
            pdu_type=PduType.RESPONSE,
            request_id=request.request_id,
            error_status=0,
            error_index=0,
            varbinds=_GET_VARBINDS,
        )
    )
    client.set_replies([foreign_report, response])

    async def scenario():
        return await dispatcher.send_prepared_request(request)

    result = asyncio.run(scenario())

    assert result.request_id == request.request_id
    assert len(client.sent) == 1
    assert model.engine_recovery_needed is False


def test_dispatcher_prepare_request_and_send_only_helpers() -> None:
    dispatcher, client = _make_dispatcher()
    request = dispatcher.prepare_request(PduType.GET, _GET_VARBINDS)
    next_request = dispatcher.prepare_request(
        PduType.GET_NEXT,
        (RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1), value=NullValue()),),
    )

    decoded = decode_message(request.encoded_message)

    async def scenario() -> None:
        await dispatcher.send_only(request)

    asyncio.run(scenario())

    assert 0 < request.request_id < (1 << 31)
    assert 0 < next_request.request_id < (1 << 31)
    assert request.request_id != next_request.request_id
    assert decoded.community == "public"
    assert decoded.pdu.pdu_type is PduType.GET
    assert client.sent == [request.encoded_message]


def test_dispatcher_request_ids_are_derived_from_urandom(monkeypatch) -> None:
    values = iter([b"\x00\x00\x00\x01", b"\x00\x00\x00\x07"])
    monkeypatch.setattr(os, "urandom", lambda n: next(values))

    dispatcher, _ = _make_dispatcher()
    first = dispatcher.prepare_request(PduType.GET, _GET_VARBINDS)
    second = dispatcher.prepare_request(PduType.GET_NEXT, _GET_VARBINDS)

    assert first.request_id == 1
    assert second.request_id == 7
    assert second.request_id != first.request_id + 1  # no predictable counter sequence


def test_dispatcher_request_ids_never_zero(monkeypatch) -> None:
    calls = 0

    def fake_urandom(n: int) -> bytes:
        nonlocal calls
        del n
        calls += 1
        return b"\x00\x00\x00\x00" if calls == 1 else b"\x00\x00\x00\x05"

    monkeypatch.setattr(os, "urandom", fake_urandom)

    dispatcher, _ = _make_dispatcher()
    request = dispatcher.prepare_request(PduType.GET, _GET_VARBINDS)

    assert request.request_id == 5
    assert calls == 2  # the zero candidate was rejected and regenerated


def test_dispatcher_validates_timeout_and_retries() -> None:
    client = FakeUdpClient([])

    with pytest.raises(ValueError, match="timeout must be > 0"):
        RequestDispatcher(client, security=CommunityModel("public"), timeout=0, retries=0)

    with pytest.raises(ValueError, match="retries cannot be negative"):
        RequestDispatcher(client, security=CommunityModel("public"), timeout=1.0, retries=-1)
