from __future__ import annotations

import asyncio

from trishul_snmp.manager.walk import walk_subtree
from trishul_snmp.types import EndOfMibViewValue, ErrorStatus, NullValue, Response, VarBind


def _response(*varbinds: VarBind) -> Response:
    return Response(
        request_id=1,
        error_status=ErrorStatus.NO_ERROR,
        error_index=0,
        varbinds=varbinds,
    )


def _varbind(oid: tuple[int, ...]) -> VarBind:
    return VarBind(oid=oid, value=NullValue(), display_value="null")


def test_walk_stops_when_response_leaves_subtree() -> None:
    async def request_fn(current: tuple[int, ...], *, max_repetitions: int) -> Response:
        del current, max_repetitions
        return _response(
            _varbind((1, 3, 6, 1, 2, 1, 2, 2, 1, 1)),
            _varbind((1, 3, 6, 1, 2, 1, 3, 1)),
        )

    async def scenario():
        return await walk_subtree(
            request_fn,
            (1, 3, 6, 1, 2, 1, 2, 2),
            bulk=True,
            max_repetitions=10,
        )

    walked = asyncio.run(scenario())

    assert [varbind.oid for varbind in walked] == [
        (1, 3, 6, 1, 2, 1, 2, 2, 1, 1),
    ]


def test_walk_stops_on_non_increasing_oids() -> None:
    async def request_fn(current: tuple[int, ...], *, max_repetitions: int) -> Response:
        del current, max_repetitions
        return _response(
            _varbind((1, 3, 6, 1, 2, 1, 2, 2, 1, 1)),
            _varbind((1, 3, 6, 1, 2, 1, 2, 2, 1, 1)),
            _varbind((1, 3, 6, 1, 2, 1, 2, 2, 1, 2)),
        )

    async def scenario():
        return await walk_subtree(
            request_fn,
            (1, 3, 6, 1, 2, 1, 2, 2),
            bulk=True,
            max_repetitions=10,
        )

    walked = asyncio.run(scenario())

    assert [varbind.oid for varbind in walked] == [
        (1, 3, 6, 1, 2, 1, 2, 2, 1, 1),
    ]


def test_walk_stops_on_end_of_mib_view() -> None:
    async def request_fn(current: tuple[int, ...], *, max_repetitions: int) -> Response:
        del current, max_repetitions
        return _response(
            _varbind((1, 3, 6, 1, 2, 1, 2, 2, 1, 1)),
            VarBind(
                oid=(1, 3, 6, 1, 2, 1, 2, 2, 1, 2),
                value=EndOfMibViewValue(),
                display_value="endOfMibView",
            ),
        )

    async def scenario():
        return await walk_subtree(
            request_fn,
            (1, 3, 6, 1, 2, 1, 2, 2),
            bulk=True,
            max_repetitions=10,
        )

    walked = asyncio.run(scenario())

    assert [varbind.oid for varbind in walked] == [
        (1, 3, 6, 1, 2, 1, 2, 2, 1, 1),
    ]


def test_walk_stops_on_empty_response_in_get_next_mode() -> None:
    calls = 0

    async def request_fn(current: tuple[int, ...]) -> Response:
        nonlocal calls
        calls += 1
        assert current == (1, 3, 6, 1, 2, 1, 2, 2)
        return _response()

    async def scenario():
        return await walk_subtree(
            request_fn,
            (1, 3, 6, 1, 2, 1, 2, 2),
            bulk=False,
            max_repetitions=10,
        )

    walked = asyncio.run(scenario())

    assert walked == ()
    assert calls == 1
