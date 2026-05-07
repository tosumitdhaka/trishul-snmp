from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from trishul_snmp.cli.main import _handle_translate, main, run
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


def test_cli_version(capsys) -> None:
    exit_code = main(["version"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "0.1.0"


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


def test_cli_run_exits_with_main_status(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["tsnmp", "version"])

    with pytest.raises(SystemExit) as exc_info:
        run()

    assert exc_info.value.code == 0


def test_handle_translate_requires_bundle() -> None:
    with pytest.raises(ValueError, match="translate requires --bundle"):
        _handle_translate(argparse.Namespace(bundle=None, target="IF-MIB::ifDescr.1"))
