from __future__ import annotations

import asyncio

import pytest

from trishul_snmp.errors import ProtocolError, RequestTimeoutError
from trishul_snmp.transport.dispatcher import RequestDispatcher
from trishul_snmp.types import NullValue
from trishul_snmp.wire.message import SnmpMessage, decode_message, encode_message
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind


class FakeUdpClient:
    def __init__(self, replies: list[bytes | Exception]) -> None:
        self._replies = list(replies)
        self.sent: list[bytes] = []

    async def send(self, data: bytes) -> None:
        self.sent.append(data)

    async def receive(self, timeout: float) -> bytes:
        del timeout
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


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
                varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue()),),
            ),
        )
    )


def test_dispatcher_retries_after_timeout_then_succeeds() -> None:
    client = FakeUdpClient(
        [
            RequestTimeoutError("timed out"),
            _response_bytes(request_id=1, pdu_type=PduType.RESPONSE),
        ]
    )
    dispatcher = RequestDispatcher(client, community="public", timeout=0.5, retries=1)

    async def scenario():
        return await dispatcher.send_pdu(
            PduType.GET,
            (RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue()),),
        )

    response = asyncio.run(scenario())

    assert response.pdu_type is PduType.RESPONSE
    assert response.request_id == 1
    assert len(client.sent) == 2


def test_dispatcher_ignores_unmatched_responses_until_match() -> None:
    client = FakeUdpClient(
        [
            _response_bytes(request_id=1, community="private", pdu_type=PduType.RESPONSE),
            _response_bytes(request_id=99, pdu_type=PduType.RESPONSE),
            _response_bytes(request_id=1, pdu_type=PduType.RESPONSE),
        ]
    )
    dispatcher = RequestDispatcher(client, community="public", timeout=0.5, retries=0)

    async def scenario():
        return await dispatcher.send_pdu(
            PduType.GET,
            (RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue()),),
        )

    response = asyncio.run(scenario())

    assert response.request_id == 1
    assert len(client.sent) == 1


def test_dispatcher_raises_protocol_error_for_non_response_pdu() -> None:
    client = FakeUdpClient([_response_bytes(request_id=1, pdu_type=PduType.GET)])
    dispatcher = RequestDispatcher(client, community="public", timeout=0.5, retries=0)

    async def scenario():
        return await dispatcher.send_pdu(
            PduType.GET,
            (RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue()),),
        )

    with pytest.raises(ProtocolError, match="Expected RESPONSE PDU"):
        asyncio.run(scenario())


def test_dispatcher_raises_after_retry_budget_exhausted() -> None:
    client = FakeUdpClient(
        [
            RequestTimeoutError("timed out"),
            RequestTimeoutError("timed out"),
        ]
    )
    dispatcher = RequestDispatcher(client, community="public", timeout=0.5, retries=1)

    async def scenario():
        return await dispatcher.send_pdu(
            PduType.GET,
            (RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue()),),
        )

    with pytest.raises(RequestTimeoutError, match="timed out"):
        asyncio.run(scenario())
    assert len(client.sent) == 2


def test_dispatcher_prepare_request_and_send_only_helpers() -> None:
    client = FakeUdpClient([])
    dispatcher = RequestDispatcher(client, community="public", timeout=0.5, retries=0)
    request = dispatcher.prepare_request(
        PduType.GET,
        (RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue()),),
    )
    next_request = dispatcher.prepare_request(
        PduType.GET_NEXT,
        (RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1), value=NullValue()),),
    )

    decoded = decode_message(request.encoded_message)

    async def scenario() -> None:
        await dispatcher.send_only(request)

    asyncio.run(scenario())

    assert request.request_id == 1
    assert next_request.request_id == 2
    assert decoded.community == "public"
    assert decoded.pdu.pdu_type is PduType.GET
    assert client.sent == [request.encoded_message]


def test_dispatcher_validates_timeout_and_retries() -> None:
    client = FakeUdpClient([])

    with pytest.raises(ValueError, match="timeout must be > 0"):
        RequestDispatcher(client, community="public", timeout=0, retries=0)

    with pytest.raises(ValueError, match="retries cannot be negative"):
        RequestDispatcher(client, community="public", timeout=1.0, retries=-1)
