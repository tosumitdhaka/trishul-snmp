"""Tests for SnmpSession.open() prepare() hook and send_raw_and_receive."""

from __future__ import annotations

import asyncio

import pytest

from trishul_snmp.errors import RequestTimeoutError
from trishul_snmp.session import SnmpSession
from trishul_snmp.transport.dispatcher import RequestDispatcher
from trishul_snmp.wire.pdu import Pdu

# ── shared fakes ─────────────────────────────────────────────────────────────


class FakeUdpClient:
    def __init__(self, replies: list[bytes | Exception] | None = None) -> None:
        self._replies: list[bytes | Exception] = replies or []
        self.sent: list[bytes] = []
        self.opened = False
        self.closed = False

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True

    async def send(self, data: bytes) -> None:
        self.sent.append(data)

    async def receive(self, timeout: float) -> bytes:
        del timeout
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class _SecurityNoPrep:
    """Security model without a prepare() method."""

    def wrap_pdu(self, pdu: Pdu) -> bytes:
        return b""

    def unwrap_message(self, data: bytes) -> Pdu | None:
        return None


class _SecurityWithPrep(_SecurityNoPrep):
    """Security model with a prepare() method that records the dispatcher it was called with."""

    def __init__(self) -> None:
        self.prepared_with: RequestDispatcher | None = None

    async def prepare(self, dispatcher: RequestDispatcher) -> None:
        self.prepared_with = dispatcher


def _make_session(
    security: _SecurityNoPrep,
    *,
    client: FakeUdpClient | None = None,
) -> tuple[SnmpSession, FakeUdpClient]:
    fake = client or FakeUdpClient()
    session = SnmpSession(
        host="127.0.0.1",
        port=161,
        security=security,  # type: ignore[arg-type]
        timeout=1.0,
        retries=0,
        bundle=None,
        max_datagram_size=65535,
    )
    session._client = fake  # type: ignore[assignment]
    return session, fake


# ── prepare() hook ────────────────────────────────────────────────────────────


def test_open_calls_prepare_when_present() -> None:
    security = _SecurityWithPrep()
    session, _ = _make_session(security)

    asyncio.run(session.open())

    assert security.prepared_with is session._dispatcher


def test_open_succeeds_silently_without_prepare() -> None:
    security = _SecurityNoPrep()
    session, fake = _make_session(security)

    asyncio.run(session.open())

    assert fake.opened


def test_open_passes_dispatcher_not_client() -> None:
    """prepare() must receive the RequestDispatcher, not the raw UdpClient."""
    security = _SecurityWithPrep()
    session, _ = _make_session(security)

    asyncio.run(session.open())

    assert isinstance(security.prepared_with, RequestDispatcher)


def test_open_is_idempotent() -> None:
    """A second open() call must be a no-op: prepare() runs exactly once."""
    security = _SecurityWithPrep()
    call_count = 0
    original_prepare = security.prepare

    async def counting_prepare(dispatcher: RequestDispatcher) -> None:
        nonlocal call_count
        call_count += 1
        await original_prepare(dispatcher)

    security.prepare = counting_prepare  # type: ignore[method-assign]
    session, _ = _make_session(security)

    async def scenario() -> None:
        await session.open()
        await session.open()

    asyncio.run(scenario())

    assert call_count == 1


def test_open_closes_client_if_prepare_raises() -> None:
    """If prepare() raises, open() must close the client before re-raising."""

    class _FailingPrep(_SecurityNoPrep):
        async def prepare(self, dispatcher: RequestDispatcher) -> None:
            raise RuntimeError("discovery failed")

    security = _FailingPrep()
    session, fake = _make_session(security)

    with pytest.raises(RuntimeError, match="discovery failed"):
        asyncio.run(session.open())

    assert fake.opened
    assert fake.closed


def test_close_then_reopen_runs_prepare_again() -> None:
    """close() resets the opened flag so a subsequent open() runs prepare() again."""
    security = _SecurityWithPrep()
    call_count = 0
    original_prepare = security.prepare

    async def counting_prepare(dispatcher: RequestDispatcher) -> None:
        nonlocal call_count
        call_count += 1
        await original_prepare(dispatcher)

    security.prepare = counting_prepare  # type: ignore[method-assign]
    session, _ = _make_session(security)

    async def scenario() -> None:
        await session.open()
        await session.close()
        await session.open()

    asyncio.run(scenario())

    assert call_count == 2


# ── send_raw_and_receive ──────────────────────────────────────────────────────


def test_send_raw_and_receive_returns_first_reply() -> None:
    probe = b"\x30\x03\x02\x01\x03"
    reply = b"\x30\x05\x02\x01\x03\x00\x00"
    client = FakeUdpClient([reply])
    dispatcher = RequestDispatcher(
        client,  # type: ignore[arg-type]
        security=_SecurityNoPrep(),
        timeout=1.0,
        retries=0,
    )

    result = asyncio.run(dispatcher.send_raw_and_receive(probe))

    assert result == reply
    assert client.sent == [probe]


def test_send_raw_and_receive_retries_on_timeout() -> None:
    probe = b"\x30\x03\x02\x01\x03"
    reply = b"\x30\x05\x02\x01\x03\x00\x00"
    client = FakeUdpClient([RequestTimeoutError("timed out"), reply])
    dispatcher = RequestDispatcher(
        client,  # type: ignore[arg-type]
        security=_SecurityNoPrep(),
        timeout=1.0,
        retries=1,
    )

    result = asyncio.run(dispatcher.send_raw_and_receive(probe))

    assert result == reply
    assert len(client.sent) == 2


def test_send_raw_and_receive_raises_after_retries_exhausted() -> None:
    probe = b"\x30\x03\x02\x01\x03"
    client = FakeUdpClient([RequestTimeoutError("timed out"), RequestTimeoutError("timed out")])
    dispatcher = RequestDispatcher(
        client,  # type: ignore[arg-type]
        security=_SecurityNoPrep(),
        timeout=1.0,
        retries=1,
    )

    with pytest.raises(RequestTimeoutError):
        asyncio.run(dispatcher.send_raw_and_receive(probe))

    assert len(client.sent) == 2


def test_send_raw_and_receive_does_not_touch_pdu_flow() -> None:
    """send_raw_and_receive must not call wrap_pdu or unwrap_message."""

    class SpySecurity(_SecurityNoPrep):
        def __init__(self) -> None:
            self.wrap_called = False
            self.unwrap_called = False

        def wrap_pdu(self, pdu: Pdu) -> bytes:
            self.wrap_called = True
            return b""

        def unwrap_message(self, data: bytes) -> Pdu | None:
            self.unwrap_called = True
            return None

    spy = SpySecurity()
    reply = b"\xff" * 4
    client = FakeUdpClient([reply])
    dispatcher = RequestDispatcher(
        client,  # type: ignore[arg-type]
        security=spy,
        timeout=1.0,
        retries=0,
    )

    asyncio.run(dispatcher.send_raw_and_receive(b"\x00"))

    assert not spy.wrap_called
    assert not spy.unwrap_called
