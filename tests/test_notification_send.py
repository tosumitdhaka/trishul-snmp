from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from trishul_snmp import (
    ErrorStatus,
    IntegerValue,
    ObjectIdentifierValue,
    RequestTimeoutError,
    TimeTicksValue,
    V2cNotifier,
    load_bundle,
)
from trishul_snmp.notify.client import (
    build_notification_raw_varbinds,
    encode_notification_raw_varbinds,
)
from trishul_snmp.security.community import CommunityModel
from trishul_snmp.transport.dispatcher import RequestDispatcher
from trishul_snmp.wire.message import SnmpMessage, decode_message, encode_message
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
            "members": [{"module": "NOTIF-MIB", "object": "ifIndex"}],
        }
    }
    return payload


class FakeUdpClient:
    def __init__(self, replies: list[bytes | Exception]) -> None:
        self._replies = list(replies)
        self.sent: list[bytes] = []

    async def send(self, data: bytes) -> None:
        self.sent.append(data)

    async def receive(self, timeout: float) -> bytes:
        del timeout
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _inform_response_bytes(*, request_id: int, community: str = "public") -> bytes:
    return encode_message(
        SnmpMessage(
            version=1,
            community=community,
            pdu=Pdu(
                pdu_type=PduType.RESPONSE,
                request_id=request_id,
                error_status=0,
                error_index=0,
                varbinds=(
                    RawVarBind(
                        oid=(1, 3, 6, 1, 2, 1, 1, 3, 0),
                        value=TimeTicksValue(55),
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


def _build_notifier(
    *,
    bundle_path: Path | None = None,
    replies: list[bytes | Exception] | None = None,
):
    bundle = load_bundle(bundle_path) if bundle_path is not None else None
    notifier = V2cNotifier(host="127.0.0.1", port=162, community="public", bundle=bundle, retries=0)
    fake_client = FakeUdpClient(replies or [])
    notifier._session._client = fake_client  # type: ignore[attr-defined]
    notifier._session._dispatcher = RequestDispatcher(  # type: ignore[attr-defined]
        fake_client,
        security=CommunityModel("public"),
        timeout=0.2,
        retries=0,
    )
    return notifier, fake_client


def test_notification_varbind_builder_adds_standard_bindings() -> None:
    varbinds = build_notification_raw_varbinds(
        (1, 3, 6, 1, 6, 3, 1, 1, 5, 3),
        varbinds=[("1.3.6.1.2.1.2.2.1.1.7", IntegerValue(7))],
        uptime=123,
    )

    assert varbinds[0][0] == (1, 3, 6, 1, 2, 1, 1, 3, 0)
    assert varbinds[1][0] == (1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0)
    assert isinstance(varbinds[0][1], TimeTicksValue)
    assert isinstance(varbinds[1][1], ObjectIdentifierValue)
    assert varbinds[2] == ((1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 7), IntegerValue(7))


def test_notification_varbind_builder_preserves_explicit_standard_overrides() -> None:
    varbinds = build_notification_raw_varbinds(
        (1, 3, 6, 1, 6, 3, 1, 1, 5, 3),
        varbinds=[
            ("1.3.6.1.2.1.1.3.0", TimeTicksValue(44)),
            ("1.3.6.1.6.3.1.1.4.1.0", ObjectIdentifierValue((1, 3, 6, 1, 4, 1, 99999, 1))),
        ],
        uptime=123,
    )

    assert varbinds[0] == ((1, 3, 6, 1, 2, 1, 1, 3, 0), TimeTicksValue(44))
    assert varbinds[1] == (
        (1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0),
        ObjectIdentifierValue((1, 3, 6, 1, 4, 1, 99999, 1)),
    )


def test_v2c_notifier_send_trap_encodes_notification_pdu_and_varbinds() -> None:
    notifier, fake_client = _build_notifier()

    async def scenario() -> int:
        return await notifier.send_trap(
            "1.3.6.1.6.3.1.1.5.3",
            varbinds=[("1.3.6.1.2.1.2.2.1.1.7", IntegerValue(7))],
            uptime=123,
        )

    request_id = asyncio.run(scenario())
    message = decode_message(fake_client.sent[0])

    assert request_id == 1
    assert message.pdu.pdu_type is PduType.SNMPV2_TRAP
    assert message.pdu.request_id == 1
    assert message.pdu.varbinds[0].oid == (1, 3, 6, 1, 2, 1, 1, 3, 0)
    assert message.pdu.varbinds[0].value == TimeTicksValue(123)
    assert message.pdu.varbinds[1].oid == (1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0)
    assert message.pdu.varbinds[2].oid == (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 7)


def test_v2c_notifier_send_trap_supports_symbolic_targets_with_bundle(tmp_path: Path) -> None:
    _write_json(tmp_path / "NOTIF-MIB.json", _notification_payload())
    notifier, fake_client = _build_notifier(bundle_path=tmp_path / "NOTIF-MIB.json")

    async def scenario() -> int:
        return await notifier.send_trap(
            "NOTIF-MIB::linkDown",
            varbinds=[("NOTIF-MIB::ifIndex.7", IntegerValue(7))],
            uptime=55,
        )

    request_id = asyncio.run(scenario())
    message = decode_message(fake_client.sent[0])

    assert request_id == 1
    assert message.pdu.pdu_type is PduType.SNMPV2_TRAP
    assert message.pdu.varbinds[1].value == ObjectIdentifierValue((1, 3, 6, 1, 6, 3, 1, 1, 5, 3))
    assert message.pdu.varbinds[2].oid == (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 7)
    assert message.pdu.varbinds[2].value == IntegerValue(7)


def test_v2c_notifier_send_inform_returns_response() -> None:
    notifier, _ = _build_notifier(replies=[_inform_response_bytes(request_id=1)])

    async def scenario():
        return await notifier.send_inform(
            "1.3.6.1.6.3.1.1.5.3",
            varbinds=[("1.3.6.1.2.1.2.2.1.1.7", IntegerValue(7))],
            uptime=55,
        )

    response = asyncio.run(scenario())

    assert response.error_status is ErrorStatus.NO_ERROR
    assert response.request_id == 1
    assert response.varbinds[0].oid == (1, 3, 6, 1, 2, 1, 1, 3, 0)
    assert response.varbinds[2].value == IntegerValue(7)


def test_v2c_notifier_send_inform_raises_on_timeout() -> None:
    notifier, _ = _build_notifier(replies=[RequestTimeoutError("timed out")])

    async def scenario() -> None:
        await notifier.send_inform("1.3.6.1.6.3.1.1.5.3")

    with pytest.raises(RequestTimeoutError, match="timed out"):
        asyncio.run(scenario())


def test_encode_notification_raw_varbinds_builds_low_level_varbinds() -> None:
    raw_varbinds = encode_notification_raw_varbinds(
        (1, 3, 6, 1, 6, 3, 1, 1, 5, 3),
        varbinds=[("1.3.6.1.2.1.2.2.1.1.7", IntegerValue(7))],
        uptime=9,
    )

    assert raw_varbinds[0] == RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=TimeTicksValue(9))
    assert raw_varbinds[2] == RawVarBind(
        oid=(1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 7),
        value=IntegerValue(7),
    )
