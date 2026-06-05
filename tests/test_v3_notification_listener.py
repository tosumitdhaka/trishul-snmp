from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass

import pytest

from trishul_snmp import (
    ErrorStatus,
    IntegerValue,
    V3NotificationListener,
    V3Notifier,
)
from trishul_snmp.errors import TransportError
from trishul_snmp.security.usm import (
    AuthProtocol,
    PrivProtocol,
    UsmLocalEngine,
    UsmModel,
    UsmUser,
)
from trishul_snmp.types import SocketAddress
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind
from trishul_snmp.wire.v3message import (
    MSG_FLAG_REPORTABLE,
    UsmParams,
    decode_v3_message,
    encode_v3_message,
)


def _make_user(*, level: str, username: str = "listener") -> UsmUser:
    md5_len = hashlib.md5(b"").digest_size
    if level == "noAuthNoPriv":
        return UsmUser(username=username, auth_protocol=AuthProtocol.NONE)
    if level == "authNoPriv":
        return UsmUser(
            username=username,
            auth_protocol=AuthProtocol.MD5,
            auth_key=b"\xaa" * md5_len,
            auth_key_localized=True,
        )
    if level == "authPriv":
        return UsmUser(
            username=username,
            auth_protocol=AuthProtocol.MD5,
            auth_key=b"\xaa" * md5_len,
            auth_key_localized=True,
            priv_protocol=PrivProtocol.AES128,
            priv_key=b"privpassword12345",
        )
    raise AssertionError(f"unexpected test security level: {level}")


def _make_local_engine(fill: int, *, boots: int = 7, time: int = 111) -> UsmLocalEngine:
    return UsmLocalEngine(
        engine_id=b"\x80\x00\x01\x02\x03" + bytes([fill]) * 12,
        engine_boots=boots,
        engine_time=time,
    )


def _skip_if_udp_restricted(exc: Exception) -> None:
    cause = exc.__cause__
    if isinstance(cause, OSError) and cause.errno in {1, 13}:
        pytest.skip(f"UDP sockets are not permitted in this environment: {cause}")


def _listener_port(listener: V3NotificationListener) -> int:
    local = listener.local_address
    assert local is not None
    return local[1]


def _make_raw_notification(
    *,
    user: UsmUser,
    pdu_type: PduType,
    request_id: int,
    username: str | None = None,
    local_engine: UsmLocalEngine | None = None,
    peer_engine: UsmLocalEngine | None = None,
) -> bytes:
    selected_user = (
        user if username is None else _make_user(level="noAuthNoPriv", username=username)
    )
    model = UsmModel(user=selected_user, local_engine=local_engine)
    if peer_engine is not None:
        model._engine_id = peer_engine.engine_id
        model._engine_boots = peer_engine.engine_boots
        model._engine_time = peer_engine.engine_time
    return model.wrap_pdu(
        Pdu(
            pdu_type=pdu_type,
            request_id=request_id,
            error_status=0,
            error_index=0,
            varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=IntegerValue(7)),),
        )
    )


@dataclass(frozen=True, slots=True)
class _FakeDatagram:
    data: bytes
    source_address: SocketAddress


class _FakeServer:
    def __init__(self, items: list[_FakeDatagram | Exception]) -> None:
        self._items = list(items)
        self.sent: list[tuple[bytes, SocketAddress]] = []
        self.local_address: SocketAddress | None = ("127.0.0.1", 40162)

    async def receive(self) -> _FakeDatagram:
        item = self._items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def sendto(self, data: bytes, addr: SocketAddress) -> None:
        self.sent.append((data, addr))


@pytest.mark.parametrize(
    ("level", "fill"),
    [
        ("noAuthNoPriv", 0x11),
        ("authNoPriv", 0x22),
        ("authPriv", 0x33),
    ],
)
def test_v3_notification_listener_receives_trap_event(level: str, fill: int) -> None:
    async def scenario() -> None:
        user = _make_user(level=level)
        listener_engine = _make_local_engine(fill + 1)
        sender_engine = _make_local_engine(fill + 2)
        try:
            async with V3NotificationListener(
                host="127.0.0.1",
                port=0,
                user=user,
                local_engine=listener_engine,
            ) as listener:
                async with V3Notifier(
                    host="127.0.0.1",
                    port=_listener_port(listener),
                    user=user,
                    local_engine=sender_engine,
                    timeout=0.2,
                    retries=0,
                ) as notifier:
                    send_task = asyncio.create_task(
                        notifier.send_trap(
                            "1.3.6.1.6.3.1.1.5.3",
                            varbinds=[("1.3.6.1.2.1.2.2.1.1.7", IntegerValue(7))],
                            uptime=123,
                        )
                    )
                    event = await asyncio.wait_for(listener.receive(), timeout=1.0)
                    request_id = await send_task
        except Exception as exc:
            _skip_if_udp_restricted(exc)
            raise

        assert event.community is None
        assert event.snmp_version == "3"
        assert event.username == "listener"
        assert event.security_level == level
        assert event.pdu_type == "snmpv2-trap"
        assert event.request_id == request_id
        assert event.source_host == "127.0.0.1"
        assert event.source_port > 0
        assert event.authoritative_engine_id == sender_engine.engine_id
        assert event.context_engine_id == sender_engine.engine_id

    asyncio.run(scenario())


def test_v3_notification_listener_acknowledges_authpriv_informs() -> None:
    async def scenario() -> None:
        user = _make_user(level="authPriv")
        listener_engine = _make_local_engine(0x44, boots=13, time=456)
        notifier_engine = _make_local_engine(0x45, boots=2, time=33)
        try:
            async with V3NotificationListener(
                host="127.0.0.1",
                port=0,
                user=user,
                local_engine=listener_engine,
            ) as listener:
                async with V3Notifier(
                    host="127.0.0.1",
                    port=_listener_port(listener),
                    user=user,
                    local_engine=notifier_engine,
                    timeout=1.0,
                    retries=0,
                ) as notifier:
                    inform_task = asyncio.create_task(
                        notifier.send_inform(
                            "1.3.6.1.6.3.1.1.5.3",
                            varbinds=[("1.3.6.1.2.1.2.2.1.1.7", IntegerValue(7))],
                            uptime=55,
                        )
                    )
                    event = await asyncio.wait_for(listener.receive(), timeout=2.0)
                    response = await asyncio.wait_for(inform_task, timeout=2.0)
        except Exception as exc:
            _skip_if_udp_restricted(exc)
            raise

        assert event.is_inform is True
        assert event.security_level == "authPriv"
        assert event.authoritative_engine_id == listener_engine.engine_id
        assert event.context_engine_id == listener_engine.engine_id
        assert response.error_status is ErrorStatus.NO_ERROR
        assert response.request_id == event.request_id

    asyncio.run(scenario())


def test_v3_notification_listener_skips_wrong_user_and_bad_auth() -> None:
    user = _make_user(level="authNoPriv", username="good")
    other_user = _make_user(level="authNoPriv", username="other")
    peer_engine = _make_local_engine(0x55)
    valid = _make_raw_notification(
        user=user,
        pdu_type=PduType.SNMPV2_TRAP,
        request_id=3,
        local_engine=peer_engine,
    )
    wrong_user = _make_raw_notification(
        user=other_user,
        pdu_type=PduType.SNMPV2_TRAP,
        request_id=1,
        local_engine=peer_engine,
    )
    downgraded = _make_raw_notification(
        user=user,
        pdu_type=PduType.SNMPV2_TRAP,
        request_id=2,
        username="good",
        local_engine=peer_engine,
    )
    view = decode_v3_message(valid)
    invalid_reportable = encode_v3_message(
        view.msg_id,
        view.msg_max_size,
        view.msg_flags[0] | MSG_FLAG_REPORTABLE,
        UsmParams(
            engine_id=view.usm_params.engine_id,
            engine_boots=view.usm_params.engine_boots,
            engine_time=view.usm_params.engine_time,
            username=view.usm_params.username,
            auth_params=b"\x00" * 12,
            priv_params=view.usm_params.priv_params,
        ),
        view.msg_data_bytes,
    )
    invalid_reportable = UsmModel(user=user)._stamp_auth(invalid_reportable, peer_engine.engine_id)
    bad_auth = (
        valid[: view.auth_params_offset]
        + bytes([valid[view.auth_params_offset] ^ 0xFF])
        + valid[view.auth_params_offset + 1 :]
    )
    server = _FakeServer(
        [
            _FakeDatagram(data=wrong_user, source_address=("127.0.0.1", 40000)),
            _FakeDatagram(data=downgraded, source_address=("127.0.0.1", 40001)),
            _FakeDatagram(data=invalid_reportable, source_address=("127.0.0.1", 40002)),
            _FakeDatagram(data=bad_auth, source_address=("127.0.0.1", 40003)),
            _FakeDatagram(data=valid, source_address=("127.0.0.1", 40004)),
        ]
    )

    async def scenario() -> None:
        listener = V3NotificationListener(user=user, local_engine=_make_local_engine(0x56))
        listener._server = server  # type: ignore[attr-defined]
        event = await listener.receive()

        assert event.request_id == 3
        assert event.source_address == ("127.0.0.1", 40004)
        assert server.sent == []

    asyncio.run(scenario())


def test_v3_notification_listener_responds_to_discovery_probe() -> None:
    user = _make_user(level="noAuthNoPriv")
    listener_engine = _make_local_engine(0x66, boots=9, time=222)
    probe = UsmModel(user=user)._build_discovery_probe()
    valid = _make_raw_notification(
        user=user,
        pdu_type=PduType.SNMPV2_TRAP,
        request_id=4,
        local_engine=_make_local_engine(0x67),
    )
    server = _FakeServer(
        [
            _FakeDatagram(data=probe, source_address=("127.0.0.1", 40010)),
            _FakeDatagram(data=valid, source_address=("127.0.0.1", 40011)),
        ]
    )

    async def scenario() -> None:
        listener = V3NotificationListener(user=user, local_engine=listener_engine)
        listener._server = server  # type: ignore[attr-defined]
        event = await listener.receive()

        assert event.request_id == 4
        assert len(server.sent) == 1
        response, addr = server.sent[0]
        assert addr == ("127.0.0.1", 40010)
        view = decode_v3_message(response)
        assert view.usm_params.engine_id == listener_engine.engine_id
        assert view.usm_params.engine_boots == listener_engine.engine_boots
        assert view.usm_params.engine_time == listener_engine.engine_time

    asyncio.run(scenario())


def test_v3_notification_listener_exported_from_package() -> None:
    import trishul_snmp

    assert trishul_snmp.V3NotificationListener is V3NotificationListener


def test_v3_notification_listener_anext_re_raises_transport_when_not_closed() -> None:
    async def scenario() -> None:
        listener = V3NotificationListener(
            user=_make_user(level="noAuthNoPriv"),
            local_engine=_make_local_engine(0x77),
        )
        listener._server = _FakeServer([TransportError("boom")])  # type: ignore[attr-defined]
        with pytest.raises(TransportError, match="boom"):
            await listener.__anext__()

    asyncio.run(scenario())
