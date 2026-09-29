"""UDP integration tests: walk/bulkwalk termination against scripted quirk agents.

Drives the real V2cManager + dispatcher + UDP transport against deliberately
malformed or quirky response sequences (issue #25). The quirk agent binds an
ephemeral loopback port, decodes the manager's requests, echoes the inbound
request-id (request ids are random), and emits a configured response script
keyed on the requested OID.

Every walk is wrapped in ``asyncio.wait_for`` so a hostile sequence can never
stall the suite, and request counts are asserted so a regression that turns a
quirk into an unbounded request loop fails fast.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import cast

import pytest

from trishul_snmp import RequestTimeoutError, TransportError, V2cManager
from trishul_snmp.manager.walk import WalkError
from trishul_snmp.types import (
    OID,
    EndOfMibViewValue,
    ErrorStatus,
    NullValue,
    SnmpValueType,
    VarBind,
)
from trishul_snmp.wire.message import SnmpMessage, decode_message, encode_message
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind

ROOT: OID = (1, 3, 6, 1, 4, 1, 90000, 1)
A: OID = (1, 3, 6, 1, 4, 1, 90000, 1, 1)
B: OID = (1, 3, 6, 1, 4, 1, 90000, 1, 2)
C: OID = (1, 3, 6, 1, 4, 1, 90000, 1, 3)
LESS: OID = (1, 3, 6, 1, 4, 1, 89999, 1)  # below ROOT, outside its subtree
OUTSIDE: OID = (1, 3, 6, 1, 4, 1, 90000, 2, 1)  # above ROOT, outside its subtree

_MAX_REPETITIONS = 10


def _vb(oid: OID, value: SnmpValueType | None = None) -> RawVarBind:
    """Build a scripted data varbind (NULL value by default)."""
    return RawVarBind(oid=oid, value=value if value is not None else NullValue())


def _eomv(oid: OID) -> RawVarBind:
    """Build a scripted endOfMibView varbind."""
    return RawVarBind(oid=oid, value=EndOfMibViewValue())


def _oids(walked: tuple[VarBind, ...]) -> list[OID]:
    return [varbind.oid for varbind in walked]


class QuirkAgent(asyncio.DatagramProtocol):
    """Scripted UDP agent for walk/bulkwalk termination quirks."""

    def __init__(
        self,
        script: dict[OID, Sequence[RawVarBind]],
        *,
        echo_requests: bool = False,
        error_script: dict[OID, tuple[int, int]] | None = None,
    ) -> None:
        self._script = {oid: tuple(varbinds) for oid, varbinds in script.items()}
        self._echo_requests = echo_requests
        self._error_script = dict(error_script or {})
        self.transport: asyncio.DatagramTransport | None = None
        self.requested_oids: list[OID] = []
        self.requested_pdu_types: list[PduType] = []
        self.requested_max_repetitions: list[int] = []
        self.last_error: Exception | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = cast(asyncio.DatagramTransport, transport)

    def datagram_received(self, data: bytes, addr) -> None:
        try:
            message = decode_message(data)
            pdu = message.pdu
            requested_oid = pdu.varbinds[0].oid
            self.requested_oids.append(requested_oid)
            self.requested_pdu_types.append(pdu.pdu_type)
            self.requested_max_repetitions.append(pdu.error_index)
            error = self._error_script.get(requested_oid)
            if error is not None:
                error_status, error_index = error
                response_varbinds: tuple[RawVarBind, ...] = (_vb(requested_oid),)
            elif self._echo_requests:
                response_varbinds = (_vb(requested_oid),)
                error_status, error_index = 0, 0
            else:
                response_varbinds = self._script.get(requested_oid, (_eomv(requested_oid),))
                error_status, error_index = 0, 0
            response = SnmpMessage(
                version=message.version,
                community=message.community,
                pdu=Pdu(
                    pdu_type=PduType.RESPONSE,
                    request_id=pdu.request_id,
                    error_status=error_status,
                    error_index=error_index,
                    varbinds=response_varbinds,
                ),
            )
            assert self.transport is not None
            self.transport.sendto(encode_message(response), addr)
        except Exception as exc:  # pragma: no cover - surfaced explicitly in tests
            self.last_error = exc


class SilentUdpListener(asyncio.DatagramProtocol):
    """UDP listener that never responds."""

    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = cast(asyncio.DatagramTransport, transport)


async def _start_agent(agent: QuirkAgent) -> tuple[asyncio.DatagramTransport, int]:
    loop = asyncio.get_running_loop()
    try:
        transport, _ = await loop.create_datagram_endpoint(
            lambda: agent,
            local_addr=("127.0.0.1", 0),
        )
    except OSError as exc:
        if exc.errno in {1, 13}:
            pytest.skip(f"UDP sockets are not permitted in this environment: {exc}")
        raise

    sockname = transport.get_extra_info("sockname")
    assert isinstance(sockname, tuple)
    port = cast(int, sockname[1])
    return cast(asyncio.DatagramTransport, transport), port


async def _start_silent_listener() -> tuple[asyncio.DatagramTransport, int]:
    loop = asyncio.get_running_loop()
    listener = SilentUdpListener()
    try:
        transport, _ = await loop.create_datagram_endpoint(
            lambda: listener,
            local_addr=("127.0.0.1", 0),
        )
    except OSError as exc:
        if exc.errno in {1, 13}:
            pytest.skip(f"UDP sockets are not permitted in this environment: {exc}")
        raise

    sockname = transport.get_extra_info("sockname")
    assert isinstance(sockname, tuple)
    port = cast(int, sockname[1])
    return cast(asyncio.DatagramTransport, transport), port


def _skip_if_udp_connect_restricted(exc: TransportError) -> None:
    cause = exc.__cause__
    if isinstance(cause, OSError) and cause.errno in {1, 13}:
        pytest.skip(f"UDP client sockets are not permitted in this environment: {cause}")


async def _walk(
    script: dict[OID, Sequence[RawVarBind]],
    *,
    bulk: bool,
    echo_requests: bool = False,
    max_repetitions: int = _MAX_REPETITIONS,
) -> tuple[tuple[VarBind, ...], QuirkAgent]:
    """Run a walk against the scripted quirk agent over real UDP."""
    agent = QuirkAgent(script, echo_requests=echo_requests)
    transport, port = await _start_agent(agent)
    try:
        try:
            async with V2cManager(
                host="127.0.0.1",
                port=port,
                community="public",
                timeout=0.2,
                retries=0,
            ) as manager:
                # Bound the walk so a hostile sequence can never stall the suite.
                walked = await asyncio.wait_for(
                    manager.walk(ROOT, bulk=bulk, max_repetitions=max_repetitions),
                    timeout=2.0,
                )
        except TransportError as exc:
            _skip_if_udp_connect_restricted(exc)
            raise
        return walked, agent
    finally:
        transport.close()


def test_bulkwalk_terminates_on_reordered_oids() -> None:
    """A backward OID mid-response terminates the walk; earlier rows are kept."""

    async def scenario() -> None:
        walked, agent = await _walk({ROOT: [_vb(A), _vb(B), _vb(A)]}, bulk=True)
        assert _oids(walked) == [A, B]
        assert agent.requested_oids == [ROOT]
        assert agent.last_error is None

    asyncio.run(scenario())


def test_walk_terminates_on_backward_first_response() -> None:
    """A first response already below the root yields an empty walk."""

    async def scenario() -> None:
        walked, agent = await _walk({ROOT: [_vb(LESS)]}, bulk=True)
        assert walked == ()
        assert agent.requested_oids == [ROOT]
        assert agent.last_error is None

    asyncio.run(scenario())


def test_bulkwalk_stops_at_end_of_mib_view_in_non_final_position() -> None:
    """endOfMibView before the final varbind still terminates the walk there."""

    async def scenario() -> None:
        walked, agent = await _walk({ROOT: [_vb(A), _eomv(A), _vb(B)]}, bulk=True)
        assert _oids(walked) == [A]
        assert agent.requested_oids == [ROOT]
        assert agent.last_error is None

    asyncio.run(scenario())


def test_walk_ignores_varbinds_after_leading_end_of_mib_view() -> None:
    """Data after a leading endOfMibView in the same response is discarded."""

    async def scenario() -> None:
        walked, agent = await _walk({ROOT: [_eomv(A), _vb(B)]}, bulk=True)
        assert walked == ()
        assert agent.requested_oids == [ROOT]
        assert agent.last_error is None

    asyncio.run(scenario())


@pytest.mark.parametrize("bulk", [True, False])
def test_walk_terminates_on_zero_progress_echo(bulk: bool) -> None:
    """An agent echoing the requested OID is zero progress: no loop, no phantom row."""

    async def scenario() -> None:
        walked, agent = await _walk({}, bulk=bulk, echo_requests=True)
        assert walked == ()
        assert agent.requested_oids == [ROOT]
        assert agent.last_error is None

    asyncio.run(scenario())


def test_walk_continues_after_agent_skips_ahead() -> None:
    """An agent jumping past intermediate OIDs is trusted; the walk continues."""

    async def scenario() -> None:
        walked, agent = await _walk({ROOT: [_vb(C)], C: [_eomv(C)]}, bulk=True)
        assert _oids(walked) == [C]
        assert agent.requested_oids == [ROOT, C]
        assert agent.last_error is None

    asyncio.run(scenario())


def test_walk_terminates_when_agent_jumps_out_of_subtree() -> None:
    """A response leaving the requested subtree terminates the walk cleanly."""

    async def scenario() -> None:
        walked, agent = await _walk({ROOT: [_vb(OUTSIDE)]}, bulk=True)
        assert walked == ()
        assert agent.requested_oids == [ROOT]
        assert agent.last_error is None

    asyncio.run(scenario())


def test_bulkwalk_survives_agent_clamping_max_repetitions() -> None:
    """An agent returning one row per GETBULK still completes the full walk."""

    async def scenario() -> None:
        walked, agent = await _walk(
            {ROOT: [_vb(A)], A: [_vb(B)], B: [_eomv(B)]},
            bulk=True,
            max_repetitions=_MAX_REPETITIONS,
        )
        assert _oids(walked) == [A, B]
        assert agent.requested_oids == [ROOT, A, B]
        assert agent.requested_max_repetitions == [10, 10, 10]
        assert agent.last_error is None

    asyncio.run(scenario())


def test_bulkwalk_dedupes_repeated_oid_within_response() -> None:
    """A duplicated row in one response is dropped and the walk continues."""

    async def scenario() -> None:
        walked, agent = await _walk({ROOT: [_vb(A), _vb(A), _vb(B)], B: [_eomv(B)]}, bulk=True)
        assert _oids(walked) == [A, B]
        assert agent.requested_oids == [ROOT, B]
        assert agent.last_error is None

    asyncio.run(scenario())


def test_bulkwalk_dedupes_repeated_oid_across_responses() -> None:
    """An agent re-sending the last row at the start of a response is handled."""

    async def scenario() -> None:
        walked, agent = await _walk(
            {ROOT: [_vb(A)], A: [_vb(A), _vb(B)], B: [_eomv(B)]},
            bulk=True,
        )
        assert _oids(walked) == [A, B]
        assert agent.requested_oids == [ROOT, A, B]
        assert agent.last_error is None

    asyncio.run(scenario())


def test_walk_raises_timeout_error_against_silent_agent() -> None:
    """An unresponsive agent surfaces a clear error instead of hanging."""

    async def scenario() -> None:
        transport, port = await _start_silent_listener()
        try:
            try:
                async with V2cManager(
                    host="127.0.0.1",
                    port=port,
                    community="public",
                    timeout=0.2,
                    retries=0,
                ) as manager:
                    with pytest.raises(RequestTimeoutError, match="timed out"):
                        await manager.walk(ROOT, bulk=True, max_repetitions=_MAX_REPETITIONS)
            except TransportError as exc:
                _skip_if_udp_connect_restricted(exc)
                raise
        finally:
            transport.close()

    asyncio.run(scenario())


def test_bulkwalk_raises_walk_error_on_too_big_response() -> None:
    """A tooBig GETBULK response surfaces a WalkError instead of a partial walk."""

    async def scenario() -> None:
        agent = QuirkAgent({}, error_script={ROOT: (1, 0)})
        transport, port = await _start_agent(agent)
        try:
            try:
                async with V2cManager(
                    host="127.0.0.1",
                    port=port,
                    community="public",
                    timeout=0.2,
                    retries=0,
                ) as manager:
                    with pytest.raises(WalkError) as exc_info:
                        await asyncio.wait_for(
                            manager.walk(ROOT, bulk=True, max_repetitions=_MAX_REPETITIONS),
                            timeout=2.0,
                        )
            except TransportError as exc:
                _skip_if_udp_connect_restricted(exc)
                raise
            assert exc_info.value.error_status is ErrorStatus.TOO_BIG
            assert exc_info.value.error_index == 0
            assert agent.requested_oids == [ROOT]
            assert agent.last_error is None
        finally:
            transport.close()

    asyncio.run(scenario())
