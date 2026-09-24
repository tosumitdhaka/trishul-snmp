from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from trishul_snmp import (
    IntegerValue,
    TimeTicksValue,
    V2cNotificationListener,
    V2cNotifier,
    decode_notification,
    load_bundle,
)
from trishul_snmp.errors import ProtocolError
from trishul_snmp.notify.client import (
    V1Notifier,
    build_v1_notification_raw_varbinds,
)
from trishul_snmp.notify.events import notification_event_from_message
from trishul_snmp.notify.v3 import DropReason
from trishul_snmp.security.community import CommunityModel
from trishul_snmp.transport.dispatcher import RequestDispatcher
from trishul_snmp.types import SocketAddress
from trishul_snmp.wire.message import SnmpMessage, decode_message, encode_message
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind, build_trap_pdu

_ENTERPRISE = (1, 3, 6, 1, 4, 1, 999)
_AGENT_ADDR = "192.0.2.10"
_SYS_UPTIME_OID = (1, 3, 6, 1, 2, 1, 1, 3, 0)


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
        "enterpriseAlarm": {
            "oid": "1.3.6.1.4.1.999.0.1",
            "oid_path": [1, 3, 6, 1, 4, 1, 999, 0, 1],
            "object_type": "NOTIFICATION-TYPE",
            "class": "notificationtype",
            "status": "current",
            "members": [{"module": "NOTIF-MIB", "object": "ifIndex"}],
        }
    }
    return payload


class FakeUdpClient:
    def __init__(self, replies: list[bytes | Exception | Callable[[bytes], bytes]]) -> None:
        self._replies = list(replies)
        self.sent: list[bytes] = []

    async def send(self, data: bytes) -> None:
        self.sent.append(data)

    async def receive(self, timeout: float) -> bytes:
        del timeout
        reply = self._replies.pop(0)
        if callable(reply):
            reply = reply(self.sent[-1])
        if isinstance(reply, Exception):
            raise reply
        return reply


def _build_v1_notifier(
    *,
    bundle_path: Path | None = None,
    replies: list[bytes | Exception | Callable[[bytes], bytes]] | None = None,
):
    bundle = load_bundle(bundle_path) if bundle_path is not None else None
    notifier = V1Notifier(host="127.0.0.1", port=162, community="public", bundle=bundle, retries=0)
    fake_client = FakeUdpClient(replies or [])
    notifier._session._client = fake_client  # type: ignore[attr-defined]
    notifier._session._dispatcher = RequestDispatcher(  # type: ignore[attr-defined]
        fake_client,
        security=CommunityModel("public", version=0),
        timeout=0.2,
        retries=0,
    )
    return notifier, fake_client


def _v1_trap_message(
    *,
    community: str,
    generic_trap: int = 6,
    specific_trap: int = 0,
    timestamp: int = 654321,
) -> bytes:
    return encode_message(
        SnmpMessage(
            version=0,
            community=community,
            pdu=build_trap_pdu(
                enterprise=_ENTERPRISE,
                agent_addr=_AGENT_ADDR,
                generic_trap=generic_trap,
                specific_trap=specific_trap,
                timestamp=timestamp,
                varbinds=(RawVarBind(oid=_SYS_UPTIME_OID, value=TimeTicksValue(timestamp)),),
            ),
        )
    )


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


def test_v1_notifier_send_trap_encodes_v1_trap_pdu() -> None:
    notifier, fake_client = _build_v1_notifier()

    async def scenario() -> int:
        return await notifier.send_trap(
            "1.3.6.1.4.1.999",
            agent_addr=_AGENT_ADDR,
            generic_trap=1,
            specific_trap=0,
            timestamp=123456,
            varbinds=[("1.3.6.1.2.1.2.2.1.1.7", IntegerValue(7))],
        )

    timestamp = asyncio.run(scenario())
    message = decode_message(fake_client.sent[0])

    assert timestamp == 123456
    assert message.version == 0
    assert message.community == "public"
    assert message.pdu.pdu_type is PduType.TRAP
    assert message.pdu.enterprise == (1, 3, 6, 1, 4, 1, 999)
    assert message.pdu.agent_addr == _AGENT_ADDR
    assert message.pdu.generic_trap == 1
    assert message.pdu.specific_trap == 0
    assert message.pdu.timestamp == 123456
    assert message.pdu.varbinds[0].oid == _SYS_UPTIME_OID
    assert message.pdu.varbinds[0].value == TimeTicksValue(123456)
    assert message.pdu.varbinds[1].oid == (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 7)
    assert message.pdu.varbinds[1].value == IntegerValue(7)


def test_v1_notifier_defaults_generic_trap_to_enterprise_specific() -> None:
    notifier, fake_client = _build_v1_notifier()

    async def scenario() -> int:
        return await notifier.send_trap(
            "1.3.6.1.4.1.999",
            specific_trap=42,
        )

    asyncio.run(scenario())
    message = decode_message(fake_client.sent[0])

    assert message.pdu.generic_trap == 6
    assert message.pdu.specific_trap == 42


def test_v1_notifier_explicit_sysuptime_varbind_overrides_header_timestamp() -> None:
    notifier, fake_client = _build_v1_notifier()

    async def scenario() -> int:
        return await notifier.send_trap(
            "1.3.6.1.4.1.999",
            timestamp=10,
            varbinds=[("1.3.6.1.2.1.1.3.0", TimeTicksValue(555))],
        )

    timestamp = asyncio.run(scenario())
    message = decode_message(fake_client.sent[0])

    assert timestamp == 555
    assert message.pdu.timestamp == 555
    assert message.pdu.varbinds[0].value == TimeTicksValue(555)


def test_v1_notifier_supports_symbolic_varbinds_with_bundle(tmp_path: Path) -> None:
    _write_json(tmp_path / "NOTIF-MIB.json", _notification_payload())
    notifier, fake_client = _build_v1_notifier(bundle_path=tmp_path / "NOTIF-MIB.json")

    async def scenario() -> int:
        return await notifier.send_trap(
            "1.3.6.1.4.1.999",
            specific_trap=1,
            varbinds=[("NOTIF-MIB::ifIndex.7", IntegerValue(7))],
        )

    asyncio.run(scenario())
    message = decode_message(fake_client.sent[0])

    assert message.pdu.enterprise == (1, 3, 6, 1, 4, 1, 999)
    assert message.pdu.generic_trap == 6
    assert message.pdu.specific_trap == 1
    assert message.pdu.varbinds[1].oid == (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 7)


def test_v1_notifier_rejects_negative_timestamp() -> None:
    notifier, _ = _build_v1_notifier()

    async def scenario() -> None:
        await notifier.send_trap("1.3.6.1.4.1.999", timestamp=-1)

    with pytest.raises(ValueError, match="timestamp cannot be negative"):
        asyncio.run(scenario())


def test_v1_notifier_rejects_out_of_range_generic_trap() -> None:
    notifier, _ = _build_v1_notifier()

    async def scenario() -> None:
        await notifier.send_trap("1.3.6.1.4.1.999", generic_trap=7)

    with pytest.raises(ProtocolError, match="generic-trap 7 must be between 0 and 6"):
        asyncio.run(scenario())


def test_v1_notifier_has_no_inform() -> None:
    notifier, _ = _build_v1_notifier()

    async def scenario() -> None:
        await notifier.send_inform("1.3.6.1.4.1.999")

    with pytest.raises(ProtocolError, match="does not support informs"):
        asyncio.run(scenario())


def test_v1_notification_varbind_builder_uses_sysuptime_without_snmptrapoid() -> None:
    varbinds = build_v1_notification_raw_varbinds(
        varbinds=[("1.3.6.1.2.1.2.2.1.1.7", IntegerValue(7))],
        timestamp=123,
    )

    assert varbinds[0] == (_SYS_UPTIME_OID, TimeTicksValue(123))
    assert varbinds[1] == ((1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 7), IntegerValue(7))
    assert all(oid != (1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0) for oid, _ in varbinds)


def test_listener_receives_v1_trap_event() -> None:
    async def scenario() -> None:
        try:
            async with V2cNotificationListener(
                host="127.0.0.1",
                port=0,
                communities=["public"],
            ) as listener:
                async with V1Notifier(
                    host="127.0.0.1",
                    port=_listener_port(listener),
                    community="public",
                    timeout=0.2,
                    retries=0,
                ) as notifier:
                    send_task = asyncio.create_task(
                        notifier.send_trap(
                            "1.3.6.1.4.1.999",
                            agent_addr=_AGENT_ADDR,
                            generic_trap=1,
                            timestamp=123456,
                            varbinds=[("1.3.6.1.2.1.2.2.1.1.7", IntegerValue(7))],
                        )
                    )
                    event = await asyncio.wait_for(listener.receive(), timeout=1.0)
                    timestamp = await send_task
        except Exception as exc:
            _skip_if_udp_restricted(exc)
            raise

        assert event.pdu_type == "trap"
        assert event.community == "public"
        assert event.source_host == "127.0.0.1"
        assert event.source_port > 0
        assert event.request_id == 0
        assert event.enterprise == (1, 3, 6, 1, 4, 1, 999)
        assert event.agent_addr == _AGENT_ADDR
        assert event.generic_trap == 1
        assert event.specific_trap == 0
        assert event.timestamp == 123456
        assert event.timestamp == timestamp
        assert event.uptime == 123456
        assert event.varbinds[1].oid == (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 7)

    asyncio.run(scenario())


def test_listener_receives_mixed_v1_and_v2c_traps() -> None:
    async def scenario() -> None:
        try:
            async with V2cNotificationListener(
                host="127.0.0.1",
                port=0,
                communities=["public"],
            ) as listener:
                port = _listener_port(listener)
                async with (
                    V2cNotifier(
                        host="127.0.0.1",
                        port=port,
                        community="public",
                        timeout=0.2,
                        retries=0,
                    ) as v2c_notifier,
                    V1Notifier(
                        host="127.0.0.1",
                        port=port,
                        community="public",
                        timeout=0.2,
                        retries=0,
                    ) as v1_notifier,
                ):
                    v2c_task = asyncio.create_task(v2c_notifier.send_trap("1.3.6.1.6.3.1.1.5.3"))
                    v2c_event = await asyncio.wait_for(listener.receive(), timeout=1.0)
                    await v2c_task
                    v1_task = asyncio.create_task(v1_notifier.send_trap("1.3.6.1.4.1.999"))
                    v1_event = await asyncio.wait_for(listener.receive(), timeout=1.0)
                    await v1_task
        except Exception as exc:
            _skip_if_udp_restricted(exc)
            raise

        assert v2c_event.pdu_type == "snmpv2-trap"
        assert v2c_event.enterprise is None
        assert v2c_event.generic_trap is None
        assert v1_event.pdu_type == "trap"
        assert v1_event.enterprise == (1, 3, 6, 1, 4, 1, 999)
        assert v1_event.community == "public"

    asyncio.run(scenario())


def test_listener_v1_wrong_community_drops_as_wrong_community() -> None:
    wrong_community = _v1_trap_message(community="public")
    accepted = _v1_trap_message(community="private")
    server = _FakeServer(
        [
            _FakeDatagram(data=wrong_community, source_address=("127.0.0.1", 40010)),
            _FakeDatagram(data=accepted, source_address=("127.0.0.1", 40011)),
        ]
    )

    async def scenario() -> None:
        listener = V2cNotificationListener(communities=["private"])
        listener._server = server  # type: ignore[attr-defined]
        event = await listener.receive()

        assert event.community == "private"
        assert event.pdu_type == "trap"
        assert listener.dropped == 1
        assert listener.drop_counts == {DropReason.WRONG_COMMUNITY: 1}
        assert server.sent == []

    asyncio.run(scenario())


def test_listener_v1_trap_surfaces_after_other_drops() -> None:
    server = _FakeServer(
        [
            _FakeDatagram(data=b"not-snmp", source_address=("127.0.0.1", 40020)),
            _FakeDatagram(
                # v1 message with valid BER framing but no community OCTET
                # STRING: version 0 peeks cleanly, full decode fails
                data=b"\x30\x05\x02\x01\x00\x05\x00",
                source_address=("127.0.0.1", 40021),
            ),
            _FakeDatagram(
                data=_v1_trap_message(community="public"),
                source_address=("127.0.0.1", 40022),
            ),
        ]
    )

    async def scenario() -> None:
        listener = V2cNotificationListener()
        listener._server = server  # type: ignore[attr-defined]
        event = await listener.receive()

        assert event.pdu_type == "trap"
        assert event.enterprise == _ENTERPRISE
        assert listener.dropped == 2
        assert listener.drop_counts == {DropReason.UNDECODABLE_BER: 2}

    asyncio.run(scenario())


def test_decode_notification_decodes_v1_trap_datagram() -> None:
    event = decode_notification(
        _v1_trap_message(community="public"),
        source_address=("203.0.113.7", 40162),
    )

    assert event.pdu_type == "trap"
    assert event.request_id == 0
    assert event.community == "public"
    assert event.source_host == "203.0.113.7"
    assert event.enterprise == _ENTERPRISE
    assert event.agent_addr == _AGENT_ADDR
    assert event.generic_trap == 6
    assert event.specific_trap == 0
    assert event.timestamp == 654321
    assert event.uptime == 654321


def test_decode_notification_decodes_v1_trap_hex_roundtrip() -> None:
    raw = _v1_trap_message(community="public", generic_trap=1, specific_trap=5)
    event = decode_notification(bytes.fromhex(raw.hex()))

    assert event.pdu_type == "trap"
    assert event.generic_trap == 1
    assert event.specific_trap == 5
    assert event.timestamp == 654321


def test_v1_event_to_dict_includes_trap_fields_and_is_json_safe() -> None:
    event = notification_event_from_message(
        SnmpMessage(
            version=0,
            community="public",
            pdu=build_trap_pdu(
                enterprise=_ENTERPRISE,
                agent_addr=_AGENT_ADDR,
                generic_trap=6,
                specific_trap=3,
                timestamp=777,
                varbinds=(RawVarBind(oid=_SYS_UPTIME_OID, value=TimeTicksValue(777)),),
            ),
        ),
        source_address=("10.0.0.9", 40000),
        bundle=None,
    )
    d = event.to_dict()

    json.dumps(d)
    assert d["pdu_type"] == "trap"
    assert d["enterprise"] == "1.3.6.1.4.1.999"
    assert d["agent_addr"] == _AGENT_ADDR
    assert d["generic_trap"] == 6
    assert d["specific_trap"] == 3
    assert d["timestamp"] == 777
    assert "snmp_version" not in d


def test_v2c_event_to_dict_has_no_v1_trap_keys() -> None:
    v2c = notification_event_from_message(
        SnmpMessage(
            version=1,
            community="public",
            pdu=Pdu(
                pdu_type=PduType.SNMPV2_TRAP,
                request_id=9,
                error_status=0,
                error_index=0,
                varbinds=(),
            ),
        ),
        source_address=("10.0.0.9", 40000),
        bundle=None,
    )
    d = v2c.to_dict()

    for key in ("enterprise", "agent_addr", "generic_trap", "specific_trap", "timestamp"):
        assert key not in d
    assert d["pdu_type"] == "snmpv2-trap"
    json.dumps(d)
