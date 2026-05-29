"""SnmpSession — shared transport, dispatcher, lock, and optional MIB bundle."""

from __future__ import annotations

import asyncio
from types import TracebackType

from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.security.model import SecurityModel
from trishul_snmp.transport.dispatcher import RequestDispatcher
from trishul_snmp.transport.udp import UdpClient


class SnmpSession:
    """Owns the UdpClient, RequestDispatcher, asyncio.Lock, and optional MibBundle."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        security: SecurityModel,
        timeout: float,
        retries: int,
        bundle: MibBundle | None,
        max_datagram_size: int,
    ) -> None:
        self.bundle = bundle
        self._security = security
        self._client = UdpClient(host, port, max_datagram_size=max_datagram_size)
        self._dispatcher = RequestDispatcher(
            self._client,
            security=security,
            timeout=timeout,
            retries=retries,
        )
        self._lock = asyncio.Lock()
        self._opened = False

    async def __aenter__(self) -> SnmpSession:
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
        if self._opened:
            return
        await self._client.open()
        try:
            if hasattr(self._security, "prepare"):
                await self._security.prepare(self._dispatcher)
        except BaseException:
            await self._client.close()
            raise
        self._opened = True

    async def close(self) -> None:
        self._opened = False
        await self._client.close()

    @property
    def dispatcher(self) -> RequestDispatcher:
        return self._dispatcher

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock
