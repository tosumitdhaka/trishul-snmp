from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from trishul_snmp import (
    IntegerValue,
    NotificationEvent,
    NotificationMemberBinding,
    ObjectIdentifierValue,
    __version__,
)
from trishul_snmp.cli.main import _handle_translate, main, run
from trishul_snmp.mib.models import MibMemberRef
from trishul_snmp.types import ErrorStatus, OctetStringValue, Response, VarBind


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


def _if_mib_payload() -> dict[object, object]:
    payload = _base_module(module="IF-MIB")
    payload["objects"] = {
        "ifTable": {
            "oid": "1.3.6.1.2.1.2.2",
            "oid_path": [1, 3, 6, 1, 2, 1, 2, 2],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "table",
            "syntax": "SEQUENCE OF IfEntry",
            "max_access": "not-accessible",
            "status": "current",
        },
        "ifDescr": {
            "oid": "1.3.6.1.2.1.2.2.1.2",
            "oid_path": [1, 3, 6, 1, 2, 1, 2, 2, 1, 2],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "column",
            "syntax": "DisplayString",
            "max_access": "read-only",
            "status": "current",
        },
    }
    return payload


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


class FakeManager:
    created: list[FakeManager] = []

    def __init__(
        self,
        *,
        host: str,
        community: str,
        port: int = 161,
        timeout: float = 2.0,
        retries: int = 1,
        bundle=None,
    ) -> None:
        self.host = host
        self.community = community
        self.port = port
        self.timeout = timeout
        self.retries = retries
        self.bundle = bundle
        self.calls: list[tuple[str, object]] = []
        type(self).created.append(self)

    async def __aenter__(self) -> FakeManager:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, *targets: str) -> Response:
        self.calls.append(("get", targets))
        return _response("1.3.6.1.2.1.2.2.1.2.1", display_name="IF-MIB::ifDescr.1")

    async def get_next(self, *targets: str) -> Response:
        self.calls.append(("get_next", targets))
        return _response("1.3.6.1.2.1.2.2.1.2.2", display_name="IF-MIB::ifDescr.2")

    async def get_bulk(
        self,
        *targets: str,
        non_repeaters: int = 0,
        max_repetitions: int = 10,
    ) -> Response:
        self.calls.append(
            (
                "get_bulk",
                {
                    "targets": targets,
                    "non_repeaters": non_repeaters,
                    "max_repetitions": max_repetitions,
                },
            )
        )
        return _response("1.3.6.1.2.1.2.2.1.2.1", display_name="IF-MIB::ifDescr.1")

    async def walk(
        self,
        root: str,
        *,
        bulk: bool = True,
        max_repetitions: int = 10,
    ) -> tuple[VarBind, ...]:
        self.calls.append(
            (
                "walk",
                {
                    "root": root,
                    "bulk": bulk,
                    "max_repetitions": max_repetitions,
                },
            )
        )
        return (
            _varbind("1.3.6.1.2.1.2.2.1.2.1", "IF-MIB::ifDescr.1", "eth0"),
            _varbind("1.3.6.1.2.1.2.2.1.2.2", "IF-MIB::ifDescr.2", "eth1"),
        )

    async def bulkwalk(
        self,
        root: str,
        *,
        max_repetitions: int = 10,
    ) -> tuple[VarBind, ...]:
        self.calls.append(
            (
                "bulkwalk",
                {
                    "root": root,
                    "max_repetitions": max_repetitions,
                },
            )
        )
        return await self.walk(root, bulk=True, max_repetitions=max_repetitions)


class FakeV3Manager(FakeManager):
    created: list[FakeV3Manager] = []

    def __init__(
        self,
        *,
        host: str,
        user,
        port: int = 161,
        timeout: float = 2.0,
        retries: int = 1,
        bundle=None,
        context_name: bytes = b"",
    ) -> None:
        self.host = host
        self.user = user
        self.context_name = context_name
        self.port = port
        self.timeout = timeout
        self.retries = retries
        self.bundle = bundle
        self.calls: list[tuple[str, object]] = []
        type(self).created.append(self)


class FakeNotifier:
    created: list[FakeNotifier] = []

    def __init__(
        self,
        *,
        host: str,
        community: str,
        port: int = 162,
        timeout: float = 2.0,
        retries: int = 1,
        bundle=None,
    ) -> None:
        self.host = host
        self.community = community
        self.port = port
        self.timeout = timeout
        self.retries = retries
        self.bundle = bundle
        self.calls: list[tuple[str, object]] = []
        type(self).created.append(self)

    async def __aenter__(self) -> FakeNotifier:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def send_trap(self, notification: str, *, varbinds=(), uptime: int = 0) -> int:
        self.calls.append(
            (
                "send_trap",
                {
                    "notification": notification,
                    "varbinds": tuple(varbinds),
                    "uptime": uptime,
                },
            )
        )
        return 77

    async def send_inform(self, notification: str, *, varbinds=(), uptime: int = 0) -> Response:
        self.calls.append(
            (
                "send_inform",
                {
                    "notification": notification,
                    "varbinds": tuple(varbinds),
                    "uptime": uptime,
                },
            )
        )
        return Response(
            request_id=11,
            error_status=ErrorStatus.NO_ERROR,
            error_index=0,
            varbinds=(_varbind("1.3.6.1.2.1.2.2.1.1.7", "NOTIF-MIB::ifIndex.7", "7"),),
        )


class FakeV3Notifier(FakeNotifier):
    created: list[FakeV3Notifier] = []

    def __init__(
        self,
        *,
        host: str,
        user,
        port: int = 162,
        timeout: float = 2.0,
        retries: int = 1,
        bundle=None,
        context_name: bytes = b"",
        local_engine=None,
    ) -> None:
        self.host = host
        self.user = user
        self.context_name = context_name
        self.local_engine = local_engine
        self.port = port
        self.timeout = timeout
        self.retries = retries
        self.bundle = bundle
        self.calls: list[tuple[str, object]] = []
        type(self).created.append(self)


class FakeListener:
    created: list[FakeListener] = []
    queued_events: list[NotificationEvent] = []

    def __init__(
        self,
        *,
        host: str = "0.0.0.0",
        port: int = 162,
        communities=None,
        bundle=None,
    ) -> None:
        self.host = host
        self.port = port
        self.communities = communities
        self.bundle = bundle
        type(self).created.append(self)

    async def __aenter__(self) -> FakeListener:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def receive(self) -> NotificationEvent:
        return type(self).queued_events.pop(0)


class FakeV3Listener:
    created: list[FakeV3Listener] = []
    queued_events: list[NotificationEvent] = []

    def __init__(
        self,
        *,
        host: str = "0.0.0.0",
        port: int = 162,
        user=None,
        local_engine=None,
        bundle=None,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.local_engine = local_engine
        self.bundle = bundle
        type(self).created.append(self)

    async def __aenter__(self) -> FakeV3Listener:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def receive(self) -> NotificationEvent:
        return type(self).queued_events.pop(0)


def _response(oid: str, *, display_name: str) -> Response:
    return Response(
        request_id=1,
        error_status=ErrorStatus.NO_ERROR,
        error_index=0,
        varbinds=(_varbind(oid, display_name, "eth0"),),
    )


def _varbind(oid: str, display_name: str, value: str) -> VarBind:
    return VarBind(
        oid=tuple(int(part) for part in oid.split(".")),
        value=OctetStringValue(value.encode("utf-8")),
        display_name=display_name,
        display_value=value,
    )


def _notification_event() -> NotificationEvent:
    varbind = _varbind("1.3.6.1.2.1.2.2.1.1.7", "NOTIF-MIB::ifIndex.7", "7")
    return NotificationEvent(
        request_id=12,
        community="public",
        source_address=("127.0.0.1", 49162),
        pdu_type="snmpv2-trap",
        varbinds=(varbind,),
        notification_oid=(1, 3, 6, 1, 6, 3, 1, 1, 5, 3),
        notification_name="NOTIF-MIB::linkDown",
        notification_description="A linkDown notification.",
        uptime=55,
        member_bindings=(
            NotificationMemberBinding(
                member=MibMemberRef(module="NOTIF-MIB", object="ifIndex"),
                varbind=varbind,
            ),
        ),
    )


def _v3_notification_event() -> NotificationEvent:
    return NotificationEvent(
        request_id=13,
        community=None,
        source_address=("127.0.0.1", 49163),
        pdu_type="inform-request",
        varbinds=(),
        snmp_version="3",
        username="alice",
        security_level="authNoPriv",
        context_engine_id=bytes.fromhex("8000010203"),
        context_name=b"alerts",
        authoritative_engine_id=bytes.fromhex("8000010203"),
        authoritative_engine_boots=7,
        authoritative_engine_time=99,
    )


def test_cli_version(capsys) -> None:
    exit_code = main(["version"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == __version__


def test_cli_translate_with_single_module_bundle(tmp_path: Path, capsys) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())

    exit_code = main(
        [
            "translate",
            "--bundle",
            str(tmp_path / "IF-MIB.json"),
            "IF-MIB::ifDescr.7",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "1.3.6.1.2.1.2.2.1.2.7"


def test_cli_get_renders_text_and_uses_bundle(monkeypatch, tmp_path: Path, capsys) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())
    FakeManager.created.clear()
    monkeypatch.setattr("trishul_snmp.cli.main.V2cManager", FakeManager)

    exit_code = main(
        [
            "get",
            "--host",
            "127.0.0.1",
            "--bundle",
            str(tmp_path / "IF-MIB.json"),
            "IF-MIB::ifDescr.1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "IF-MIB::ifDescr.1 = eth0"
    assert FakeManager.created[0].bundle is not None
    assert FakeManager.created[0].calls == [("get", ("IF-MIB::ifDescr.1",))]


def test_cli_get_v3_uses_v3manager(monkeypatch, tmp_path: Path, capsys) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())
    FakeV3Manager.created.clear()
    monkeypatch.setattr("trishul_snmp.cli.main.V3Manager", FakeV3Manager)

    exit_code = main(
        [
            "get",
            "--host",
            "127.0.0.1",
            "--snmp-version",
            "3",
            "--username",
            "alice",
            "--context-name",
            "alerts",
            "--bundle",
            str(tmp_path / "IF-MIB.json"),
            "IF-MIB::ifDescr.1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "IF-MIB::ifDescr.1 = eth0"
    assert FakeV3Manager.created[0].user.username == "alice"
    assert FakeV3Manager.created[0].context_name == b"alerts"
    assert FakeV3Manager.created[0].calls == [("get", ("IF-MIB::ifDescr.1",))]


def test_cli_getbulk_json_output(monkeypatch, capsys) -> None:
    FakeManager.created.clear()
    monkeypatch.setattr("trishul_snmp.cli.main.V2cManager", FakeManager)

    exit_code = main(
        [
            "getbulk",
            "--host",
            "127.0.0.1",
            "--json",
            "--non-repeaters",
            "1",
            "--max-repetitions",
            "4",
            "1.3.6.1.2.1.2.2",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["error_status"] == "no_error"
    assert payload["varbinds"][0]["display_name"] == "IF-MIB::ifDescr.1"
    assert FakeManager.created[0].calls == [
        (
            "get_bulk",
            {
                "targets": ("1.3.6.1.2.1.2.2",),
                "non_repeaters": 1,
                "max_repetitions": 4,
            },
        )
    ]


def test_cli_walk_and_bulkwalk_flags(monkeypatch, capsys) -> None:
    FakeManager.created.clear()
    monkeypatch.setattr("trishul_snmp.cli.main.V2cManager", FakeManager)

    walk_exit = main(
        [
            "walk",
            "--host",
            "127.0.0.1",
            "--no-bulk",
            "1.3.6.1.2.1.2.2",
        ]
    )
    walk_output = capsys.readouterr().out.strip().splitlines()

    bulk_exit = main(
        [
            "bulkwalk",
            "--host",
            "127.0.0.1",
            "--max-repetitions",
            "6",
            "1.3.6.1.2.1.2.2",
        ]
    )
    capsys.readouterr()

    assert walk_exit == 0
    assert bulk_exit == 0
    assert walk_output == [
        "IF-MIB::ifDescr.1 = eth0",
        "IF-MIB::ifDescr.2 = eth1",
    ]
    assert FakeManager.created[0].calls == [
        (
            "walk",
            {
                "root": "1.3.6.1.2.1.2.2",
                "bulk": False,
                "max_repetitions": 10,
            },
        )
    ]
    assert FakeManager.created[1].calls == [
        (
            "bulkwalk",
            {
                "root": "1.3.6.1.2.1.2.2",
                "max_repetitions": 6,
            },
        ),
        (
            "walk",
            {
                "root": "1.3.6.1.2.1.2.2",
                "bulk": True,
                "max_repetitions": 6,
            },
        ),
    ]


def test_cli_getnext_uses_manager_get_next(monkeypatch, capsys) -> None:
    FakeManager.created.clear()
    monkeypatch.setattr("trishul_snmp.cli.main.V2cManager", FakeManager)

    exit_code = main(
        [
            "getnext",
            "--host",
            "127.0.0.1",
            "1.3.6.1.2.1.2.2",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "IF-MIB::ifDescr.2 = eth0"
    assert FakeManager.created[0].calls == [("get_next", ("1.3.6.1.2.1.2.2",))]


def test_cli_trap_parses_typed_varbinds(monkeypatch, tmp_path: Path, capsys) -> None:
    _write_json(tmp_path / "NOTIF-MIB.json", _notification_payload())
    FakeNotifier.created.clear()
    monkeypatch.setattr("trishul_snmp.cli.main.V2cNotifier", FakeNotifier)

    exit_code = main(
        [
            "trap",
            "--host",
            "127.0.0.1",
            "--bundle",
            str(tmp_path / "NOTIF-MIB.json"),
            "--uptime",
            "55",
            "--varbind",
            "1.3.6.1.6.3.1.1.4.1.0=oid:NOTIF-MIB::linkDown",
            "--varbind",
            "NOTIF-MIB::ifIndex.7=int:7",
            "NOTIF-MIB::linkDown",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == "request_id=77"
    assert FakeNotifier.created[0].calls == [
        (
            "send_trap",
            {
                "notification": "NOTIF-MIB::linkDown",
                "varbinds": (
                    (
                        "1.3.6.1.6.3.1.1.4.1.0",
                        ObjectIdentifierValue((1, 3, 6, 1, 6, 3, 1, 1, 5, 3)),
                    ),
                    (
                        "NOTIF-MIB::ifIndex.7",
                        IntegerValue(7),
                    ),
                ),
                "uptime": 55,
            },
        )
    ]


def test_cli_trap_v3_routes_to_v3notifier(monkeypatch, capsys) -> None:
    FakeV3Notifier.created.clear()
    monkeypatch.setattr("trishul_snmp.cli.main.V3Notifier", FakeV3Notifier)

    exit_code = main(
        [
            "trap",
            "--host",
            "127.0.0.1",
            "--snmp-version",
            "3",
            "--username",
            "alice",
            "--local-engine-id",
            "80:00:01:02:03",
            "--local-engine-boots",
            "7",
            "--local-engine-time",
            "99",
            "1.3.6.1.6.3.1.1.5.3",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "request_id=77"
    assert FakeV3Notifier.created[0].user.username == "alice"
    assert FakeV3Notifier.created[0].local_engine is not None
    assert FakeV3Notifier.created[0].local_engine.engine_id == bytes.fromhex("8000010203")
    assert FakeV3Notifier.created[0].local_engine.engine_boots == 7
    assert FakeV3Notifier.created[0].local_engine.engine_time == 99
    assert FakeV3Notifier.created[0].calls == [
        (
            "send_trap",
            {
                "notification": "1.3.6.1.6.3.1.1.5.3",
                "varbinds": (),
                "uptime": 0,
            },
        )
    ]


def test_cli_inform_renders_response(monkeypatch, capsys) -> None:
    FakeNotifier.created.clear()
    monkeypatch.setattr("trishul_snmp.cli.main.V2cNotifier", FakeNotifier)

    exit_code = main(
        [
            "inform",
            "--host",
            "127.0.0.1",
            "--varbind",
            "1.3.6.1.2.1.2.2.1.1.7=int:7",
            "1.3.6.1.6.3.1.1.5.3",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == "NOTIF-MIB::ifIndex.7 = 7"
    assert FakeNotifier.created[0].calls == [
        (
            "send_inform",
            {
                "notification": "1.3.6.1.6.3.1.1.5.3",
                "varbinds": (("1.3.6.1.2.1.2.2.1.1.7", IntegerValue(7)),),
                "uptime": 0,
            },
        )
    ]


def test_cli_inform_v3_routes_to_v3notifier(monkeypatch, capsys) -> None:
    FakeV3Notifier.created.clear()
    monkeypatch.setattr("trishul_snmp.cli.main.V3Notifier", FakeV3Notifier)

    exit_code = main(
        [
            "inform",
            "--host",
            "127.0.0.1",
            "--snmp-version",
            "3",
            "--username",
            "alice",
            "--context-name",
            "alerts",
            "1.3.6.1.6.3.1.1.5.3",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "NOTIF-MIB::ifIndex.7 = 7"
    assert FakeV3Notifier.created[0].user.username == "alice"
    assert FakeV3Notifier.created[0].context_name == b"alerts"
    assert FakeV3Notifier.created[0].local_engine is None
    assert FakeV3Notifier.created[0].calls == [
        (
            "send_inform",
            {
                "notification": "1.3.6.1.6.3.1.1.5.3",
                "varbinds": (),
                "uptime": 0,
            },
        )
    ]


def test_cli_listen_receives_configured_count(monkeypatch, capsys) -> None:
    FakeListener.created.clear()
    FakeListener.queued_events = [_notification_event()]
    monkeypatch.setattr("trishul_snmp.cli.main.V2cNotificationListener", FakeListener)

    exit_code = main(
        [
            "listen",
            "--host",
            "127.0.0.1",
            "--community",
            "public",
            "--count",
            "1",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "notification=NOTIF-MIB::linkDown uptime=55" in captured.out
    assert "NOTIF-MIB::ifIndex.7 = 7" in captured.out
    assert FakeListener.created[0].host == "127.0.0.1"
    assert FakeListener.created[0].communities == ["public"]


def test_cli_listen_v3_uses_v3_listener(monkeypatch, capsys) -> None:
    FakeV3Listener.created.clear()
    FakeV3Listener.queued_events = [_v3_notification_event()]
    monkeypatch.setattr("trishul_snmp.cli.main.V3NotificationListener", FakeV3Listener)

    exit_code = main(
        [
            "listen",
            "--host",
            "127.0.0.1",
            "--snmp-version",
            "3",
            "--username",
            "alice",
            "--local-engine-id",
            "80:00:01:02:03",
            "--local-engine-boots",
            "7",
            "--local-engine-time",
            "99",
            "--count",
            "1",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "user=alice level=authNoPriv" in captured.out
    assert FakeV3Listener.created[0].host == "127.0.0.1"
    assert FakeV3Listener.created[0].user.username == "alice"
    assert FakeV3Listener.created[0].local_engine is not None
    assert FakeV3Listener.created[0].local_engine.engine_id == bytes.fromhex("8000010203")


def test_cli_decode_notification_accepts_hex_input(monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_decode_notification(data: bytes, *, bundle=None, user=None):
        seen["data"] = data
        seen["bundle"] = bundle
        seen["user"] = user
        return _notification_event()

    monkeypatch.setattr("trishul_snmp.cli.main.decode_notification", fake_decode_notification)

    exit_code = main(
        [
            "decode-notification",
            "--hex",
            "30 01",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert seen["data"] == b"\x30\x01"
    assert seen["bundle"] is None
    assert seen["user"] is None
    assert "notification=NOTIF-MIB::linkDown uptime=55" in captured.out


def test_cli_decode_notification_v3_passes_user(monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_decode_notification(data: bytes, *, bundle=None, user=None):
        seen["data"] = data
        seen["bundle"] = bundle
        seen["user"] = user
        return _v3_notification_event()

    monkeypatch.setattr("trishul_snmp.cli.main.decode_notification", fake_decode_notification)

    exit_code = main(
        [
            "decode-notification",
            "--snmp-version",
            "3",
            "--username",
            "alice",
            "--auth-protocol",
            "md5",
            "--auth-key",
            "secret",
            "--hex",
            "30 01",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert seen["data"] == b"\x30\x01"
    assert seen["bundle"] is None
    assert seen["user"] is not None
    assert seen["user"].username == "alice"
    assert "user=alice level=authNoPriv" in captured.out


def test_cli_listen_rejects_negative_count(capsys) -> None:
    exit_code = main(
        [
            "listen",
            "--count",
            "-1",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.err.strip() == "tsnmp: --count cannot be negative"


def test_cli_main_renders_handler_value_errors(monkeypatch, capsys) -> None:
    class ExplodingManager(FakeManager):
        async def get(self, *targets: str) -> Response:
            del targets
            raise ValueError("boom")

    monkeypatch.setattr("trishul_snmp.cli.main.V2cManager", ExplodingManager)

    exit_code = main(
        [
            "get",
            "--host",
            "127.0.0.1",
            "1.3.6.1.2.1.2.2",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err.strip() == "tsnmp: boom"


def test_cli_main_renders_v3_validation_errors(capsys) -> None:
    exit_code = main(
        [
            "get",
            "--host",
            "127.0.0.1",
            "--snmp-version",
            "3",
            "--community",
            "public",
            "--username",
            "alice",
            "1.3.6.1.2.1.2.2",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err.strip() == "tsnmp: --community is invalid with --snmp-version 3"


def test_cli_main_renders_v3_import_errors(monkeypatch, capsys) -> None:
    class ExplodingV3Manager(FakeV3Manager):
        async def __aenter__(self) -> FakeV3Manager:
            raise ImportError("pip install trishul-snmp[v3]")

    monkeypatch.setattr("trishul_snmp.cli.main.V3Manager", ExplodingV3Manager)

    exit_code = main(
        [
            "get",
            "--host",
            "127.0.0.1",
            "--snmp-version",
            "3",
            "--username",
            "alice",
            "--auth-protocol",
            "md5",
            "--auth-key",
            "secret",
            "1.3.6.1.2.1.2.2",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err.strip() == "tsnmp: pip install trishul-snmp[v3]"


def test_cli_run_exits_with_main_status(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["tsnmp", "version"])

    with pytest.raises(SystemExit) as exc_info:
        run()

    assert exc_info.value.code == 0


def test_handle_translate_requires_bundle() -> None:
    with pytest.raises(ValueError, match="translate requires --bundle"):
        _handle_translate(argparse.Namespace(bundle=None, target="IF-MIB::ifDescr.1"))
