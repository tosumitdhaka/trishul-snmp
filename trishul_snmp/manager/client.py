"""Async SNMP manager client."""

from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType
from typing import TypeVar

from trishul_snmp.manager.operations import (
    build_request_varbinds,
    normalize_targets,
    response_from_pdu,
)
from trishul_snmp.manager.walk import walk_subtree
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.security.community import CommunityModel
from trishul_snmp.security.model import SecurityModel
from trishul_snmp.security.usm import UsmUser
from trishul_snmp.session import SnmpSession
from trishul_snmp.types import OID, Response, VarBind
from trishul_snmp.wire.pdu import PduType

_TManager = TypeVar("_TManager", bound="SnmpManager")


class SnmpManager:
    """Async SNMP manager. Subclass for version-specific constructors."""

    def __init__(
        self,
        *,
        host: str,
        security: SecurityModel,
        port: int = 161,
        timeout: float = 2.0,
        retries: int = 1,
        bundle: MibBundle | None = None,
        max_datagram_size: int = 65535,
    ) -> None:
        self._session = SnmpSession(
            host=host,
            port=port,
            security=security,
            timeout=timeout,
            retries=retries,
            bundle=bundle,
            max_datagram_size=max_datagram_size,
        )

    async def __aenter__(self: _TManager) -> _TManager:
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
        await self._session.open()

    async def close(self) -> None:
        """Close the UDP transport."""
        await self._session.close()

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
        root_oid = normalize_targets((root,), bundle=self._session.bundle)[0]
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
        oids = normalize_targets(targets, bundle=self._session.bundle)
        raw_varbinds = build_request_varbinds(oids)
        async with self._session.lock:
            pdu = await self._session.dispatcher.send_pdu(
                pdu_type,
                raw_varbinds,
                error_status=error_status,
                error_index=error_index,
            )
        return response_from_pdu(pdu, bundle=self._session.bundle)


class V2cManager(SnmpManager):
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
        super().__init__(
            host=host,
            security=CommunityModel(community),
            port=port,
            timeout=timeout,
            retries=retries,
            bundle=bundle,
            max_datagram_size=max_datagram_size,
        )


class V3Manager(SnmpManager):
    """Async SNMPv3 USM manager client."""

    def __init__(
        self,
        *,
        host: str,
        user: UsmUser,
        port: int = 161,
        timeout: float = 2.0,
        retries: int = 1,
        bundle: MibBundle | None = None,
        max_datagram_size: int = 65535,
        context_name: bytes = b"",
    ) -> None:
        from trishul_snmp.security.usm import UsmModel

        super().__init__(
            host=host,
            security=UsmModel(user=user, context_name=context_name),
            port=port,
            timeout=timeout,
            retries=retries,
            bundle=bundle,
            max_datagram_size=max_datagram_size,
        )
