"""Async UDP client transport."""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from typing import cast

from trishul_snmp.errors import RequestTimeoutError, TransportError
from trishul_snmp.types import SocketAddress


class UdpClient:
    """Connected UDP client used for request/response flows."""

    def __init__(self, host: str, port: int, *, max_datagram_size: int = 65535) -> None:
        self._host = host
        self._port = port
        self._max_datagram_size = max_datagram_size
        self._socket: socket.socket | None = None

    async def open(self) -> None:
        """Create and connect the underlying socket."""
        if self._socket is not None:
            return

        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(
                self._host,
                self._port,
                type=socket.SOCK_DGRAM,
                proto=socket.IPPROTO_UDP,
            )
        except OSError as exc:
            raise TransportError(f"Unable to resolve UDP target {self._host}:{self._port}") from exc
        if not infos:
            raise TransportError(f"Unable to resolve UDP target {self._host}:{self._port}")

        family, socktype, proto, _, sockaddr = infos[0]
        try:
            sock = socket.socket(family, socktype, proto)
        except OSError as exc:
            raise TransportError("Unable to create UDP socket") from exc
        sock.setblocking(False)
        try:
            await loop.sock_connect(sock, sockaddr)
        except OSError as exc:
            sock.close()
            raise TransportError(
                f"Unable to connect UDP socket to {self._host}:{self._port}"
            ) from exc
        self._socket = sock

    async def close(self) -> None:
        """Close the underlying socket if present."""
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    async def send(self, data: bytes) -> None:
        """Send a datagram."""
        if self._socket is None:
            raise TransportError("UDP client is not open")
        loop = asyncio.get_running_loop()
        try:
            await loop.sock_sendall(self._socket, data)
        except OSError as exc:
            raise TransportError("Failed to send UDP datagram") from exc

    async def receive(self, timeout: float) -> bytes:
        """Receive the next datagram with a timeout."""
        if self._socket is None:
            raise TransportError("UDP client is not open")
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.sock_recv(self._socket, self._max_datagram_size),
                timeout=timeout,
            )
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise RequestTimeoutError("SNMP request timed out waiting for a response") from exc
        except OSError as exc:
            raise TransportError("Failed to receive UDP datagram") from exc


@dataclass(frozen=True, slots=True)
class ReceivedDatagram:
    """Inbound UDP datagram received by a bound server transport."""

    data: bytes
    source_address: SocketAddress


@dataclass(frozen=True, slots=True)
class _ServerClosed:
    cause: Exception | None = None


class _QueueingDatagramProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        queue: asyncio.Queue[ReceivedDatagram | _ServerClosed],
        closed: asyncio.Future[None],
    ) -> None:
        self._queue = queue
        self._closed = closed
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = cast(asyncio.DatagramTransport, transport)

    def datagram_received(self, data: bytes, addr: tuple[object, ...]) -> None:
        if not (len(addr) >= 2 and isinstance(addr[0], str) and isinstance(addr[1], int)):
            return
        self._queue.put_nowait(
            ReceivedDatagram(
                data=data,
                source_address=cast(SocketAddress, addr),
            )
        )

    def connection_lost(self, exc: Exception | None) -> None:
        self._queue.put_nowait(_ServerClosed(exc))
        if not self._closed.done():
            if exc is None:
                self._closed.set_result(None)
            else:
                self._closed.set_exception(exc)


class UdpServer:
    """Bound UDP server transport for inbound receive and reply flows."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._transport: asyncio.DatagramTransport | None = None
        self._queue: asyncio.Queue[ReceivedDatagram | _ServerClosed] | None = None
        self._closed: asyncio.Future[None] | None = None

    @property
    def local_address(self) -> SocketAddress | None:
        if self._transport is None:
            return None
        sockname = self._transport.get_extra_info("sockname")
        if (
            isinstance(sockname, tuple)
            and len(sockname) >= 2
            and isinstance(sockname[0], str)
            and isinstance(sockname[1], int)
        ):
            return cast(SocketAddress, sockname)
        return None

    async def open(self) -> None:
        """Bind the UDP server socket."""
        if self._transport is not None:
            return

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[ReceivedDatagram | _ServerClosed] = asyncio.Queue()
        closed = loop.create_future()
        try:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _QueueingDatagramProtocol(queue, closed),
                local_addr=(self._host, self._port),
            )
        except OSError as exc:
            raise TransportError(
                f"Unable to bind UDP server socket on {self._host}:{self._port}"
            ) from exc

        self._transport = transport
        self._queue = queue
        self._closed = closed

    async def close(self) -> None:
        """Close the bound UDP server socket."""
        transport = self._transport
        closed = self._closed
        self._transport = None
        self._queue = None
        self._closed = None

        if transport is None:
            return

        transport.close()
        if closed is not None:
            try:
                await closed
            except Exception:
                return

    async def sendto(self, data: bytes, addr: SocketAddress) -> None:
        """Send a datagram to a specific remote peer."""
        if self._transport is None:
            raise TransportError("UDP server is not open")
        try:
            self._transport.sendto(data, addr)
        except OSError as exc:
            raise TransportError("Failed to send UDP datagram") from exc

    async def receive(self) -> ReceivedDatagram:
        """Wait for the next inbound datagram."""
        if self._queue is None:
            raise TransportError("UDP server is not open")

        item = await self._queue.get()
        if isinstance(item, _ServerClosed):
            raise TransportError("UDP server is closed") from item.cause
        return item
