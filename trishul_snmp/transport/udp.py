"""Async UDP client transport."""

from __future__ import annotations

import asyncio
import socket

from trishul_snmp.errors import RequestTimeoutError, TransportError


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
        except TimeoutError as exc:
            raise RequestTimeoutError("SNMP request timed out waiting for a response") from exc
        except OSError as exc:
            raise TransportError("Failed to receive UDP datagram") from exc
