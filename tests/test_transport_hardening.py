from __future__ import annotations

import asyncio
import socket

import pytest

from trishul_snmp.errors import RequestTimeoutError, TransportError
from trishul_snmp.transport.udp import UdpClient


class _ResolveFailLoop:
    async def getaddrinfo(self, *args, **kwargs):
        del args, kwargs
        raise OSError("dns failed")


class _FakeSocket:
    def __init__(self) -> None:
        self.blocking: bool | None = None
        self.closed = False

    def setblocking(self, blocking: bool) -> None:
        self.blocking = blocking

    def close(self) -> None:
        self.closed = True


class _HappyLoop:
    def __init__(self, *, recv_data: bytes = b"reply") -> None:
        self.recv_data = recv_data
        self.getaddrinfo_calls: list[tuple[str, int, int, int]] = []
        self.sock_connect_calls: list[tuple[_FakeSocket, tuple[str, int]]] = []
        self.sock_sendall_calls: list[tuple[_FakeSocket, bytes]] = []
        self.sock_recv_calls: list[tuple[_FakeSocket, int]] = []

    async def getaddrinfo(
        self,
        host: str,
        port: int,
        *,
        type: int,
        proto: int,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        self.getaddrinfo_calls.append((host, port, type, proto))
        return [
            (socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP, "", ("127.0.0.1", port)),
        ]

    async def sock_connect(self, sock: _FakeSocket, sockaddr: tuple[str, int]) -> None:
        self.sock_connect_calls.append((sock, sockaddr))

    async def sock_sendall(self, sock: _FakeSocket, data: bytes) -> None:
        self.sock_sendall_calls.append((sock, data))

    async def sock_recv(self, sock: _FakeSocket, size: int) -> bytes:
        self.sock_recv_calls.append((sock, size))
        return self.recv_data


class _NoInfoLoop:
    async def getaddrinfo(self, *args, **kwargs):
        del args, kwargs
        return []


class _ConnectFailLoop(_HappyLoop):
    async def sock_connect(self, sock: _FakeSocket, sockaddr: tuple[str, int]) -> None:
        del sock, sockaddr
        raise OSError("connect failed")


class _SendFailLoop(_HappyLoop):
    async def sock_sendall(self, sock: _FakeSocket, data: bytes) -> None:
        del sock, data
        raise OSError("send failed")


class _ReceiveFailLoop(_HappyLoop):
    async def sock_recv(self, sock: _FakeSocket, size: int) -> bytes:
        del sock, size
        raise OSError("recv failed")


def test_udp_client_open_wraps_resolution_failure(monkeypatch) -> None:
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: _ResolveFailLoop())
    client = UdpClient("bad.example.invalid", 161)

    async def scenario() -> None:
        with pytest.raises(TransportError, match="Unable to resolve UDP target"):
            await client.open()

    asyncio.run(scenario())


def test_udp_client_send_and_receive_require_open_socket() -> None:
    client = UdpClient("127.0.0.1", 161)

    async def send_scenario() -> None:
        with pytest.raises(TransportError, match="UDP client is not open"):
            await client.send(b"test")

    async def receive_scenario() -> None:
        with pytest.raises(TransportError, match="UDP client is not open"):
            await client.receive(timeout=0.1)

    asyncio.run(send_scenario())
    asyncio.run(receive_scenario())


def test_udp_client_open_send_receive_and_close_success(monkeypatch) -> None:
    loop = _HappyLoop(recv_data=b"response-bytes")
    fake_socket = _FakeSocket()
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)

    client = UdpClient("127.0.0.1", 161, max_datagram_size=2048)

    async def scenario() -> None:
        with monkeypatch.context() as context:
            context.setattr(
                socket,
                "socket",
                lambda family, socktype, proto, fileno=None: fake_socket,
            )
            await client.open()
            await client.open()
        await client.send(b"payload")
        data = await client.receive(timeout=0.25)
        assert data == b"response-bytes"
        await client.close()
        await client.close()

    asyncio.run(scenario())

    assert loop.getaddrinfo_calls == [("127.0.0.1", 161, socket.SOCK_DGRAM, socket.IPPROTO_UDP)]
    assert fake_socket.blocking is False
    assert loop.sock_connect_calls == [(fake_socket, ("127.0.0.1", 161))]
    assert loop.sock_sendall_calls == [(fake_socket, b"payload")]
    assert loop.sock_recv_calls == [(fake_socket, 2048)]
    assert fake_socket.closed is True


def test_udp_client_open_wraps_empty_resolution_result(monkeypatch) -> None:
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: _NoInfoLoop())
    client = UdpClient("missing.example.invalid", 161)

    async def scenario() -> None:
        with pytest.raises(TransportError, match="Unable to resolve UDP target"):
            await client.open()

    asyncio.run(scenario())


def test_udp_client_open_wraps_socket_creation_failure(monkeypatch) -> None:
    loop = _HappyLoop()
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)

    def _raise_socket_error(*args, **kwargs):
        del args, kwargs
        raise OSError("socket failed")

    client = UdpClient("127.0.0.1", 161)

    async def scenario() -> None:
        with monkeypatch.context() as context:
            context.setattr(socket, "socket", _raise_socket_error)
            with pytest.raises(TransportError, match="Unable to create UDP socket"):
                await client.open()

    asyncio.run(scenario())


def test_udp_client_open_wraps_connect_failure_and_closes_socket(monkeypatch) -> None:
    loop = _ConnectFailLoop()
    fake_socket = _FakeSocket()
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)
    client = UdpClient("127.0.0.1", 161)

    async def scenario() -> None:
        with monkeypatch.context() as context:
            context.setattr(
                socket,
                "socket",
                lambda family, socktype, proto, fileno=None: fake_socket,
            )
            with pytest.raises(TransportError, match="Unable to connect UDP socket"):
                await client.open()

    asyncio.run(scenario())

    assert fake_socket.closed is True


def test_udp_client_send_wraps_socket_oserror(monkeypatch) -> None:
    loop = _SendFailLoop()
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)
    client = UdpClient("127.0.0.1", 161)
    client._socket = _FakeSocket()

    async def scenario() -> None:
        with pytest.raises(TransportError, match="Failed to send UDP datagram"):
            await client.send(b"payload")

    asyncio.run(scenario())


def test_udp_client_receive_wraps_timeout(monkeypatch) -> None:
    loop = _HappyLoop()
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)

    async def _raise_timeout(awaitable, *, timeout: float):
        del timeout
        close = getattr(awaitable, "close", None)
        if close is not None:
            close()
        raise TimeoutError("timed out")

    monkeypatch.setattr(asyncio, "wait_for", _raise_timeout)
    client = UdpClient("127.0.0.1", 161)
    client._socket = _FakeSocket()

    async def scenario() -> None:
        with pytest.raises(RequestTimeoutError, match="timed out waiting for a response"):
            await client.receive(timeout=0.1)

    asyncio.run(scenario())


def test_udp_client_receive_wraps_socket_oserror(monkeypatch) -> None:
    loop = _ReceiveFailLoop()
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)
    client = UdpClient("127.0.0.1", 161)
    client._socket = _FakeSocket()

    async def scenario() -> None:
        with pytest.raises(TransportError, match="Failed to receive UDP datagram"):
            await client.receive(timeout=0.1)

    asyncio.run(scenario())
