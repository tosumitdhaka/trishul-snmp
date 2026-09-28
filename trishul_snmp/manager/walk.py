"""Walk helpers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from trishul_snmp.types import OID, EndOfMibViewValue, Response, VarBind


def is_within_subtree(root: OID, oid: OID) -> bool:
    """Return True when *oid* is within *root*."""
    return len(oid) >= len(root) and oid[: len(root)] == root


async def walk_subtree(
    request_fn: Callable[..., Awaitable[Response]],
    root: OID,
    *,
    bulk: bool,
    max_repetitions: int,
) -> tuple[VarBind, ...]:
    """Walk a subtree using request_fn returning Response objects."""
    current = root
    results: list[VarBind] = []

    while True:
        if bulk:
            response: Response = await request_fn(current, max_repetitions=max_repetitions)
        else:
            response = await request_fn(current)

        if not response.varbinds:
            break

        stop = False
        progressed = False
        for varbind in response.varbinds:
            if isinstance(varbind.value, EndOfMibViewValue):
                stop = True
                break
            if not is_within_subtree(root, varbind.oid):
                stop = True
                break
            if varbind.oid < current:
                # The agent backtracked below the requested OID: its response
                # is not a well-ordered subtree, so trust nothing further.
                stop = True
                break
            if varbind.oid == current:
                # Echo of the requested OID or a re-sent last row. It carries
                # no new information, so drop it and keep scanning rather than
                # letting a stray duplicate truncate the walk.
                continue
            results.append(varbind)
            current = varbind.oid
            progressed = True
        if stop or not progressed:
            # ``stop`` is a terminal condition. ``not progressed`` means the
            # response only echoed the requested OID back — zero progress, so
            # terminate instead of looping against an agent that never advances.
            break

    return tuple(results)
