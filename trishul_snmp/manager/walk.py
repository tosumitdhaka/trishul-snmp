"""Walk helpers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from trishul_snmp.errors import TsnmpError
from trishul_snmp.types import OID, EndOfMibViewValue, ErrorStatus, Response, VarBind


class WalkError(TsnmpError):
    """Raised when a walk aborts because the agent reported a PDU error.

    A GETBULK or GETNEXT response carrying a nonzero error-status (for
    example tooBig or genErr) terminates the walk as a failure instead of
    silently yielding an empty or partial result. The exception carries the
    agent's error-status and error-index so callers can diagnose the failure.
    Python callers receive it from :meth:`SnmpManager.walk` and
    :meth:`SnmpManager.bulkwalk`, and the CLI surfaces it as a nonzero exit
    code instead of printing a successful partial walk.

    SNMPv1 is a deliberate exception: a GETNEXT past the end of the MIB view
    answers ``noSuchName`` (RFC 1157), which is that protocol's normal walk
    termination signal and is treated as a clean end of the walk, not an
    error.
    """

    def __init__(self, message: str, *, error_status: ErrorStatus, error_index: int) -> None:
        self.error_status = error_status
        self.error_index = error_index
        super().__init__(message)


def is_within_subtree(root: OID, oid: OID) -> bool:
    """Return True when *oid* is within *root*."""
    return len(oid) >= len(root) and oid[: len(root)] == root


async def walk_subtree(
    request_fn: Callable[..., Awaitable[Response]],
    root: OID,
    *,
    bulk: bool,
    max_repetitions: int,
    v1: bool = False,
) -> tuple[VarBind, ...]:
    """Walk a subtree using request_fn returning Response objects.

    *v1* marks an SNMPv1 GETNEXT walk: the agent answers a GETNEXT past the
    end of the MIB view with a noSuchName error, which is the protocol's
    normal termination signal and is treated as a clean walk end rather than
    a failure. Any other nonzero error-status raises :class:`WalkError`.
    """
    current = root
    results: list[VarBind] = []

    while True:
        if bulk:
            response: Response = await request_fn(current, max_repetitions=max_repetitions)
        else:
            response = await request_fn(current)

        if response.error_status is not ErrorStatus.NO_ERROR:
            if v1 and response.error_status is ErrorStatus.NO_SUCH_NAME:
                # SNMPv1 GETNEXT past the end of the MIB view answers
                # noSuchName (RFC 1157); that is the normal walk termination,
                # not an error.
                break
            raise WalkError(
                f"walk aborted: agent reported {response.error_status.label} "
                f"(error-index {response.error_index})",
                error_status=response.error_status,
                error_index=response.error_index,
            )

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
