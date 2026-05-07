"""Async SNMPv2c manager client."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from types import TracebackType

from trishul_snmp.manager.operations import (
    build_request_varbinds,
    normalize_targets,
    response_from_pdu,
)
from trishul_snmp.manager.walk import walk_subtree
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.transport.dispatcher import RequestDispatcher
from trishul_snmp.transport.udp import UdpClient
from trishul_snmp.types import OID, Response, VarBind
from trishul_snmp.wire.pdu import PduType


class V2cManager:
    """Async SNMPv2c manager client."""

    def __init__(
        self,
        *,
        host: str,
        community: str,
        port: int = 161,
        timeout: float = 2.0,
        retries: int = 1,
        bundle: MibBundle | None = None,
        max_datagram_size: int = 65535,
    ) -> None:
        self._bundle = bundle
        self._client = UdpClient(host, port, max_datagram_size=max_datagram_size)
        self._dispatcher = RequestDispatcher(
            self._client,
            community=community,
            timeout=timeout,
            retries=retries,
        )
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> V2cManager:
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        del exc_type, exc, tb
        await self.close()

    async def open(self) -> None:
        """Open the UDP transport."""
        await self._client.open()

    async def close(self) -> None:
        """Close the UDP transport."""
        await self._client.close()

    async def get(self, *targets: str | Sequence[int]) -> Response:
        """Perform an SNMP GET request."""
        return await self._request(PduType.GET, targets)

    async def get_next(self, *targets: str | Sequence[int]) -> Response:
        """Perform an SNMP GETNEXT request."""
        return await self._request(PduType.GET_NEXT, targets)

    async def get_bulk(
        self,
        *targets: str | Sequence[int],
        non_repeaters: int = 0,
        max_repetitions: int = 10,
    ) -> Response:
        """Perform an SNMP GETBULK request."""
        return await self._request(
            PduType.GET_BULK,
            targets,
            error_status=non_repeaters,
            error_index=max_repetitions,
        )

    async def walk(
        self,
        root: str | Sequence[int],
        *,
        bulk: bool = True,
        max_repetitions: int = 10,
    ) -> tuple[VarBind, ...]:
        """Walk a subtree rooted at *root*."""
        root_oid = normalize_targets((root,), bundle=self._bundle)[0]
        if bulk:
            return await walk_subtree(
                self._walk_bulk_request,
                root_oid,
                bulk=True,
                max_repetitions=max_repetitions,
            )
        return await walk_subtree(
            self._walk_next_request,
            root_oid,
            bulk=False,
            max_repetitions=max_repetitions,
        )

    async def bulkwalk(
        self,
        root: str | Sequence[int],
        *,
        max_repetitions: int = 10,
    ) -> tuple[VarBind, ...]:
        """Walk a subtree using GETBULK requests."""
        return await self.walk(root, bulk=True, max_repetitions=max_repetitions)

    async def _walk_next_request(self, current: OID) -> Response:
        return await self.get_next(current)

    async def _walk_bulk_request(self, current: OID, *, max_repetitions: int) -> Response:
        return await self.get_bulk(current, non_repeaters=0, max_repetitions=max_repetitions)

    async def _request(
        self,
        pdu_type: PduType,
        targets: tuple[str | Sequence[int], ...],
        *,
        error_status: int = 0,
        error_index: int = 0,
    ) -> Response:
        oids = normalize_targets(targets, bundle=self._bundle)
        raw_varbinds = build_request_varbinds(oids)
        async with self._lock:
            pdu = await self._dispatcher.send_pdu(
                pdu_type,
                raw_varbinds,
                error_status=error_status,
                error_index=error_index,
            )
        return response_from_pdu(pdu, bundle=self._bundle)
