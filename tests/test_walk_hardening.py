from __future__ import annotations

import asyncio

import pytest

from trishul_snmp.manager.walk import WalkError, walk_subtree
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


def test_walk_stops_on_backward_oid() -> None:
    async def request_fn(current: tuple[int, ...], *, max_repetitions: int) -> Response:
        del current, max_repetitions
        return _response(
            _varbind((1, 3, 6, 1, 2, 1, 2, 2, 1, 1)),
            _varbind((1, 3, 6, 1, 2, 1, 2, 2, 1, 2)),
            _varbind((1, 3, 6, 1, 2, 1, 2, 2, 1, 1)),
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
        (1, 3, 6, 1, 2, 1, 2, 2, 1, 2),
    ]


def test_walk_dedupes_repeated_oids() -> None:
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
        (1, 3, 6, 1, 2, 1, 2, 2, 1, 2),
    ]


def test_walk_dedupes_duplicate_across_responses() -> None:
    async def request_fn(current: tuple[int, ...], *, max_repetitions: int) -> Response:
        del max_repetitions
        if current == (1, 3, 6, 1, 2, 1, 2, 2):
            return _response(_varbind((1, 3, 6, 1, 2, 1, 2, 2, 1, 1)))
        if current == (1, 3, 6, 1, 2, 1, 2, 2, 1, 1):
            return _response(
                _varbind((1, 3, 6, 1, 2, 1, 2, 2, 1, 1)),
                _varbind((1, 3, 6, 1, 2, 1, 2, 2, 1, 2)),
            )
        return _response()

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
        (1, 3, 6, 1, 2, 1, 2, 2, 1, 2),
    ]


def test_walk_stops_on_zero_progress() -> None:
    requested: list[tuple[int, ...]] = []

    async def request_fn(current: tuple[int, ...], *, max_repetitions: int) -> Response:
        del max_repetitions
        requested.append(current)
        return _response(_varbind(current))

    async def scenario():
        return await walk_subtree(
            request_fn,
            (1, 3, 6, 1, 2, 1, 2, 2),
            bulk=True,
            max_repetitions=10,
        )

    walked = asyncio.run(scenario())

    assert walked == ()
    assert requested == [(1, 3, 6, 1, 2, 1, 2, 2)]


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


def test_walk_raises_walk_error_on_too_big_response() -> None:
    async def request_fn(current: tuple[int, ...], *, max_repetitions: int) -> Response:
        del current, max_repetitions
        return Response(
            request_id=1,
            error_status=ErrorStatus.TOO_BIG,
            error_index=0,
            varbinds=(),
        )

    async def scenario():
        return await walk_subtree(
            request_fn,
            (1, 3, 6, 1, 2, 1, 2, 2),
            bulk=True,
            max_repetitions=10,
        )

    with pytest.raises(WalkError) as exc_info:
        asyncio.run(scenario())

    assert exc_info.value.error_status is ErrorStatus.TOO_BIG
    assert exc_info.value.error_index == 0


def test_walk_raises_walk_error_on_gen_err_after_progress() -> None:
    async def request_fn(current: tuple[int, ...], *, max_repetitions: int) -> Response:
        del max_repetitions
        if current == (1, 3, 6, 1, 2, 1, 2, 2):
            return _response(_varbind((1, 3, 6, 1, 2, 1, 2, 2, 1, 1)))
        return Response(
            request_id=2,
            error_status=ErrorStatus.GEN_ERR,
            error_index=1,
            varbinds=(),
        )

    async def scenario():
        return await walk_subtree(
            request_fn,
            (1, 3, 6, 1, 2, 1, 2, 2),
            bulk=True,
            max_repetitions=10,
        )

    with pytest.raises(WalkError) as exc_info:
        asyncio.run(scenario())

    assert exc_info.value.error_status is ErrorStatus.GEN_ERR
    assert exc_info.value.error_index == 1


def test_walk_v1_treats_no_such_name_as_clean_termination() -> None:
    async def request_fn(current: tuple[int, ...]) -> Response:
        del current
        return Response(
            request_id=1,
            error_status=ErrorStatus.NO_SUCH_NAME,
            error_index=1,
            varbinds=(),
        )

    async def scenario():
        return await walk_subtree(
            request_fn,
            (1, 3, 6, 1, 2, 1, 2, 2),
            bulk=False,
            max_repetitions=10,
            v1=True,
        )

    assert asyncio.run(scenario()) == ()


def test_walk_no_such_name_raises_walk_error_outside_v1() -> None:
    async def request_fn(current: tuple[int, ...]) -> Response:
        del current
        return Response(
            request_id=1,
            error_status=ErrorStatus.NO_SUCH_NAME,
            error_index=1,
            varbinds=(),
        )

    async def scenario():
        return await walk_subtree(
            request_fn,
            (1, 3, 6, 1, 2, 1, 2, 2),
            bulk=False,
            max_repetitions=10,
        )

    with pytest.raises(WalkError) as exc_info:
        asyncio.run(scenario())

    assert exc_info.value.error_status is ErrorStatus.NO_SUCH_NAME
    assert exc_info.value.error_index == 1
