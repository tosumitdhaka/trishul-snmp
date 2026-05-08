from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from trishul_snmp import (
    ErrorStatus,
    IntegerValue,
    ObjectIdentifierValue,
    TimeTicksValue,
    V2cNotificationListener,
    V2cNotifier,
    decode_notification,
    load_bundle,
)
from trishul_snmp.errors import TransportError
from trishul_snmp.notify.events import notification_event_from_message
from trishul_snmp.notify.listener import _community_allowed
from trishul_snmp.types import SocketAddress
from trishul_snmp.wire.message import SnmpMessage, encode_message
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind


def _write_json(path: Path, payload: dict[object, object]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _base_module(*, module: str) -> dict[object, object]:
    return {
        "module": module,
        "language": "SMIv2",
        "generated_by": "trishul-smi",
        "generated_at": "2026-05-06T12:00:00Z",
        "imports": {},
        "objects": {},
        "types": {},
        "notifications": {},
        "module_metadata": {"lastupdated": None, "revisions": []},
    }


def _notification_payload() -> dict[object, object]:
    payload = _base_module(module="NOTIF-MIB")
    payload["objects"] = {
        "ifIndex": {
            "oid": "1.3.6.1.2.1.2.2.1.1",
            "oid_path": [1, 3, 6, 1, 2, 1, 2, 2, 1, 1],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "column",
            "syntax": "Integer32",
            "max_access": "read-only",
            "status": "current",
        }
    }
    payload["notifications"] = {
        "linkDown": {
            "oid": "1.3.6.1.6.3.1.1.5.3",
            "oid_path": [1, 3, 6, 1, 6, 3, 1, 1, 5, 3],
            "object_type": "NOTIFICATION-TYPE",
            "class": "notificationtype",
            "status": "current",
            "description": "A linkDown notification.",
            "members": [{"module": "NOTIF-MIB", "object": "ifIndex"}],
        }
    }
    return payload


def _skip_if_udp_restricted(exc: Exception) -> None:
    cause = exc.__cause__
    if isinstance(cause, OSError) and cause.errno in {1, 13}:
        pytest.skip(f"UDP sockets are not permitted in this environment: {cause}")


def _listener_port(listener: V2cNotificationListener) -> int:
    local = listener.local_address
    assert local is not None
    return local[1]


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


def test_notification_listener_receives_trap_event() -> None:
    async def scenario() -> None:
        try:
            async with V2cNotificationListener(
                host="127.0.0.1",
                port=0,
                communities=["public"],
            ) as listener:
                async with V2cNotifier(
                    host="127.0.0.1",
                    port=_listener_port(listener),
                    community="public",
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

        assert event.pdu_type == "snmpv2-trap"
        assert event.community == "public"
        assert event.source_host == "127.0.0.1"
        assert event.source_port > 0
        assert event.request_id == request_id
        assert event.varbinds[0].oid == (1, 3, 6, 1, 2, 1, 1, 3, 0)
        assert event.varbinds[0].display_value == "123"
        assert event.varbinds[2].oid == (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 7)

    asyncio.run(scenario())


def test_notification_listener_receives_symbolic_trap_with_bundle(tmp_path: Path) -> None:
    _write_json(tmp_path / "NOTIF-MIB.json", _notification_payload())
    bundle = load_bundle(tmp_path / "NOTIF-MIB.json")

    async def scenario() -> None:
        try:
            async with V2cNotificationListener(
                host="127.0.0.1",
                port=0,
                communities=["public"],
                bundle=bundle,
            ) as listener:
                async with V2cNotifier(
                    host="127.0.0.1",
                    port=_listener_port(listener),
                    community="public",
                    timeout=0.2,
                    retries=0,
                    bundle=bundle,
                ) as notifier:
                    send_task = asyncio.create_task(
                        notifier.send_trap(
                            "NOTIF-MIB::linkDown",
                            varbinds=[("NOTIF-MIB::ifIndex.7", IntegerValue(7))],
                            uptime=55,
                        )
                    )
                    event = await asyncio.wait_for(listener.receive(), timeout=1.0)
                    await send_task
        except Exception as exc:
            _skip_if_udp_restricted(exc)
            raise

        assert event.varbinds[2].display_name == "NOTIF-MIB::ifIndex.7"
        assert event.varbinds[2].display_value == "7"
        assert event.notification_name == "NOTIF-MIB::linkDown"
        assert event.notification_description == "A linkDown notification."
        assert event.notification_oid == (1, 3, 6, 1, 6, 3, 1, 1, 5, 3)
        assert event.uptime == 55
        assert [binding.symbolic for binding in event.member_bindings] == ["NOTIF-MIB::ifIndex"]
        assert event.member_bindings[0].varbind == event.varbinds[2]

    asyncio.run(scenario())


def test_notification_listener_acknowledges_informs() -> None:
    async def scenario() -> None:
        try:
            async with V2cNotificationListener(
                host="127.0.0.1",
                port=0,
                communities=["public"],
            ) as listener:
                async with V2cNotifier(
                    host="127.0.0.1",
                    port=_listener_port(listener),
                    community="public",
                    timeout=0.2,
                    retries=0,
                ) as notifier:
                    inform_task = asyncio.create_task(
                        notifier.send_inform(
                            "1.3.6.1.6.3.1.1.5.3",
                            varbinds=[("1.3.6.1.2.1.2.2.1.1.7", IntegerValue(7))],
                            uptime=55,
                        )
                    )
                    event = await asyncio.wait_for(listener.receive(), timeout=1.0)
                    response = await asyncio.wait_for(inform_task, timeout=1.0)
        except Exception as exc:
            _skip_if_udp_restricted(exc)
            raise

        assert event.is_inform is True
        assert response.error_status is ErrorStatus.NO_ERROR
        assert response.request_id == event.request_id
        assert response.varbinds[2].oid == (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 7)

    asyncio.run(scenario())


def test_notification_listener_community_allowlist_filters_events() -> None:
    async def scenario() -> None:
        try:
            async with V2cNotificationListener(
                host="127.0.0.1",
                port=0,
                communities=["private"],
            ) as listener:
                async with V2cNotifier(
                    host="127.0.0.1",
                    port=_listener_port(listener),
                    community="public",
                    timeout=0.2,
                    retries=0,
                ) as bad_notifier:
                    await bad_notifier.send_trap("1.3.6.1.6.3.1.1.5.3")
                    with pytest.raises(asyncio.TimeoutError):
                        await asyncio.wait_for(listener.receive(), timeout=0.05)

                async with V2cNotifier(
                    host="127.0.0.1",
                    port=_listener_port(listener),
                    community="private",
                    timeout=0.2,
                    retries=0,
                ) as good_notifier:
                    send_task = asyncio.create_task(good_notifier.send_trap("1.3.6.1.6.3.1.1.5.3"))
                    event = await asyncio.wait_for(listener.receive(), timeout=1.0)
                    await send_task
        except Exception as exc:
            _skip_if_udp_restricted(exc)
            raise

        assert event.community == "private"

    asyncio.run(scenario())


def test_notification_listener_async_iterator_stops_on_close() -> None:
    async def scenario() -> None:
        listener = V2cNotificationListener(host="127.0.0.1", port=0)
        try:
            await listener.open()
        except Exception as exc:
            _skip_if_udp_restricted(exc)
            raise
        next_task = asyncio.create_task(listener.__anext__())
        await asyncio.sleep(0)
        await listener.close()
        with pytest.raises(StopAsyncIteration):
            await next_task

    asyncio.run(scenario())


def test_notification_listener_iterator_and_receive_skip_invalid_messages() -> None:
    request_varbinds = (RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=IntegerValue(7)),)
    server = _FakeServer(
        [
            _FakeDatagram(data=b"not-snmp", source_address=("127.0.0.1", 40000)),
            _FakeDatagram(
                data=encode_message(
                    SnmpMessage(
                        version=1,
                        community="public",
                        pdu=Pdu(
                            pdu_type=PduType.GET,
                            request_id=8,
                            error_status=0,
                            error_index=0,
                            varbinds=request_varbinds,
                        ),
                    )
                ),
                source_address=("127.0.0.1", 40000),
            ),
            _FakeDatagram(
                data=encode_message(
                    SnmpMessage(
                        version=1,
                        community="public",
                        pdu=Pdu(
                            pdu_type=PduType.SNMPV2_TRAP,
                            request_id=9,
                            error_status=0,
                            error_index=0,
                            varbinds=request_varbinds,
                        ),
                    )
                ),
                source_address=("127.0.0.1", 40001),
            ),
        ]
    )

    async def scenario() -> None:
        listener = V2cNotificationListener()
        listener._server = server  # type: ignore[attr-defined]
        assert listener.__aiter__() is listener
        event = await listener.receive()

        assert event.request_id == 9
        assert event.source_address == ("127.0.0.1", 40001)
        assert server.sent == []

    asyncio.run(scenario())


def test_notification_listener_anext_re_raises_transport_when_not_closed() -> None:
    async def scenario() -> None:
        listener = V2cNotificationListener()
        listener._server = _FakeServer([TransportError("boom")])  # type: ignore[attr-defined]
        with pytest.raises(TransportError, match="boom"):
            await listener.__anext__()

    asyncio.run(scenario())


def test_notification_event_helper_and_community_filter_helper() -> None:
    message = SnmpMessage(
        version=1,
        community="public",
        pdu=Pdu(
            pdu_type=PduType.SNMPV2_TRAP,
            request_id=7,
            error_status=0,
            error_index=0,
            varbinds=(RawVarBind(oid=(1, 3, 6), value=IntegerValue(1)),),
        ),
    )
    event = notification_event_from_message(
        message,
        source_address=("127.0.0.1", 40000),
        bundle=None,
    )

    assert event.request_id == 7
    assert event.source_address == ("127.0.0.1", 40000)
    assert _community_allowed(communities=None, community="public") is True
    assert _community_allowed(communities=frozenset({"private"}), community="public") is False

    with pytest.raises(ValueError):
        notification_event_from_message(
            SnmpMessage(
                version=1,
                community="public",
                pdu=Pdu(
                    pdu_type=PduType.GET,
                    request_id=8,
                    error_status=0,
                    error_index=0,
                    varbinds=(),
                ),
            ),
            source_address=("127.0.0.1", 40000),
            bundle=None,
        )


def test_decode_notification_exposes_metadata_without_source_address(tmp_path: Path) -> None:
    _write_json(tmp_path / "NOTIF-MIB.json", _notification_payload())
    bundle = load_bundle(tmp_path / "NOTIF-MIB.json")
    encoded = encode_message(
        SnmpMessage(
            version=1,
            community="public",
            pdu=Pdu(
                pdu_type=PduType.SNMPV2_TRAP,
                request_id=42,
                error_status=0,
                error_index=0,
                varbinds=(
                    RawVarBind(
                        oid=(1, 3, 6, 1, 2, 1, 1, 3, 0),
                        value=TimeTicksValue(123),
                    ),
                    RawVarBind(
                        oid=(1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0),
                        value=ObjectIdentifierValue((1, 3, 6, 1, 6, 3, 1, 1, 5, 3)),
                    ),
                    RawVarBind(
                        oid=(1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 7),
                        value=IntegerValue(7),
                    ),
                ),
            ),
        )
    )

    event = decode_notification(encoded, bundle=bundle)

    assert event.source_address is None
    assert event.source_host is None
    assert event.source_port is None
    assert event.notification_name == "NOTIF-MIB::linkDown"
    assert event.notification_description == "A linkDown notification."
    assert event.notification_oid == (1, 3, 6, 1, 6, 3, 1, 1, 5, 3)
    assert event.uptime == 123
    assert event.declared_members[0].symbolic == "NOTIF-MIB::ifIndex"
    assert event.member_bindings[0].varbind is not None
    assert event.member_bindings[0].varbind.display_name == "NOTIF-MIB::ifIndex.7"
