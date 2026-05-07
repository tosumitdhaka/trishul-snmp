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
    last_oid: OID | None = None

    while True:
        if bulk:
            response: Response = await request_fn(current, max_repetitions=max_repetitions)
        else:
            response = await request_fn(current)

        if not response.varbinds:
            break

        stop = False
        for varbind in response.varbinds:
            if isinstance(varbind.value, EndOfMibViewValue):
                stop = True
                break
            if not is_within_subtree(root, varbind.oid):
                stop = True
                break
            if last_oid is not None and varbind.oid <= last_oid:
                stop = True
                break
            results.append(varbind)
            last_oid = varbind.oid
            current = varbind.oid
        if stop:
            break

    return tuple(results)
