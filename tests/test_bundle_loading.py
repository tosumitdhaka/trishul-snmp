from __future__ import annotations

import json
from pathlib import Path

import pytest

from trishul_snmp import BundleValidationError, UnknownSymbolError, load_bundle


def _write_json(path: Path, payload: dict[object, object]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _base_module(
    *,
    module: str,
    imports: dict[str, list[str]] | None = None,
) -> dict[object, object]:
    return {
        "module": module,
        "language": "SMIv2",
        "generated_by": "trishul-smi",
        "generated_at": "2026-05-06T12:00:00Z",
        "imports": imports or {},
        "objects": {},
        "types": {},
        "notifications": {},
        "module_metadata": {"lastupdated": None, "revisions": []},
    }


def _if_mib_payload(*, include_imports: bool = True) -> dict[object, object]:
    payload = _base_module(
        module="IF-MIB",
        imports={"SNMPv2-TC": ["DisplayString"]} if include_imports else {},
    )
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
            "index": ["ifIndex"],
        },
        "ifIndex": {
            "oid": "1.3.6.1.2.1.2.2.1.1",
            "oid_path": [1, 3, 6, 1, 2, 1, 2, 2, 1, 1],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "column",
            "syntax": "InterfaceIndex",
            "max_access": "read-only",
            "status": "current",
        },
    }
    payload["types"] = {
        "InterfaceIndex": {
            "class": "textualconvention",
            "base_type": "Integer32",
            "display_hint": "d",
            "status": "current",
        }
    }
    return payload


def _snmpv2_tc_payload() -> dict[object, object]:
    payload = _base_module(module="SNMPv2-TC")
    payload["types"] = {
        "DisplayString": {
            "class": "textualconvention",
            "base_type": "OctetString",
            "display_hint": "255a",
            "status": "current",
        }
    }
    return payload


def test_load_bundle_from_single_module_json_file(tmp_path: Path) -> None:
    module_path = tmp_path / "IF-MIB.json"
    _write_json(module_path, _if_mib_payload())

    bundle = load_bundle(module_path)

    assert bundle.translate("IF-MIB::ifDescr") == "1.3.6.1.2.1.2.2.1.2"
    assert bundle.translate("IF-MIB::ifDescr.1") == "1.3.6.1.2.1.2.2.1.2.1"
    assert bundle.translate("1.3.6.1.2.1.2.2.1.2.1") == "IF-MIB::ifDescr.1"

    match = bundle.lookup("1.3.6.1.2.1.2.2.1.1.7")
    assert match.symbolic == "IF-MIB::ifIndex.7"


def test_load_bundle_retains_description_and_members_metadata(tmp_path: Path) -> None:
    payload = _if_mib_payload()
    payload["objects"]["ifDescr"]["description"] = "A textual description of the interface."
    payload["notifications"] = {
        "linkDown": {
            "oid": "1.3.6.1.6.3.1.1.5.3",
            "oid_path": [1, 3, 6, 1, 6, 3, 1, 1, 5, 3],
            "object_type": "NOTIFICATION-TYPE",
            "class": "notificationtype",
            "status": "current",
            "description": "The agent has detected that the ifOperStatus object is down.",
            "members": [
                {"module": "IF-MIB", "object": "ifIndex"},
                {"module": "IF-MIB", "object": "ifDescr"},
            ],
        }
    }
    module_path = tmp_path / "IF-MIB.json"
    _write_json(module_path, payload)

    bundle = load_bundle(module_path)
    if_descr = bundle.modules["IF-MIB"].objects["ifDescr"]
    link_down = bundle.modules["IF-MIB"].notifications["linkDown"]

    assert if_descr.description == "A textual description of the interface."
    assert link_down.description == "The agent has detected that the ifOperStatus object is down."
    assert [member.symbolic for member in link_down.members or ()] == [
        "IF-MIB::ifIndex",
        "IF-MIB::ifDescr",
    ]


def test_directory_bundle_uses_manifest_inventory(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())
    _write_json(tmp_path / "SNMPv2-TC.json", _snmpv2_tc_payload())
    (tmp_path / "IGNORED.json").write_text("{not-valid-json", encoding="utf-8")
    _write_json(
        tmp_path / "manifest.json",
        {
            "schema_version": "1",
            "producer_version": "0.4.0",
            "generated_by": "trishul-smi",
            "generated_at": "2026-05-06T12:00:00Z",
            "modules": [
                {"module": "IF-MIB", "file": "IF-MIB.json"},
                {"module": "SNMPv2-TC", "file": "SNMPv2-TC.json"},
            ],
            "artifacts": {"oid_index": "oid_index.json"},
        },
    )
    _write_json(
        tmp_path / "oid_index.json",
        {
            "schema_version": "1",
            "producer_version": "0.4.0",
            "generated_by": "trishul-smi",
            "generated_at": "2026-05-06T12:00:00Z",
            "oids": {
                "1.3.6.1.2.1.2.2.1.2": {
                    "module": "IF-MIB",
                    "object": "ifDescr",
                    "class": "objecttype",
                }
            },
        },
    )

    bundle = load_bundle(tmp_path)

    assert set(bundle.modules) == {"IF-MIB", "SNMPv2-TC"}
    assert bundle.translate("1.3.6.1.2.1.2.2.1.2.5") == "IF-MIB::ifDescr.5"
    assert bundle.resolve_type("IF-MIB", "DisplayString") is not None


def test_directory_bundle_without_manifest_ignores_sidecars(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())
    _write_json(
        tmp_path / "oid_index.json",
        {
            "1.3.6.1.2.1.2.2.1.2": {
                "module": "IF-MIB",
                "object": "ifDescr",
                "class": "objecttype",
            }
        },
    )

    bundle = load_bundle(tmp_path)

    assert set(bundle.modules) == {"IF-MIB"}
    assert bundle.translate("1.3.6.1.2.1.2.2.1.2.9") == "IF-MIB::ifDescr.9"


def test_missing_dependency_modules_do_not_block_load(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())

    bundle = load_bundle(tmp_path / "IF-MIB.json")

    assert bundle.translate("IF-MIB::ifTable") == "1.3.6.1.2.1.2.2"
    assert bundle.resolve_type("IF-MIB", "DisplayString") is None


def test_invalid_generated_by_fails_validation(tmp_path: Path) -> None:
    payload = _if_mib_payload()
    payload["generated_by"] = "someone-else"
    _write_json(tmp_path / "IF-MIB.json", payload)

    with pytest.raises(BundleValidationError):
        load_bundle(tmp_path / "IF-MIB.json")


def test_unknown_symbol_raises_error(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload(include_imports=False))
    bundle = load_bundle(tmp_path / "IF-MIB.json")

    with pytest.raises(UnknownSymbolError):
        bundle.resolve("IF-MIB::doesNotExist")


@pytest.mark.parametrize("schema_version", ["1.1", "1", "1.0"])
def test_schema_version_at_or_below_maximum_is_accepted(
    tmp_path: Path, schema_version: str
) -> None:
    payload = _if_mib_payload()
    payload["schema_version"] = schema_version
    _write_json(tmp_path / "IF-MIB.json", payload)

    bundle = load_bundle(tmp_path / "IF-MIB.json")

    assert bundle.modules["IF-MIB"].schema_version == schema_version


def test_missing_schema_version_is_accepted(tmp_path: Path) -> None:
    payload = _if_mib_payload()
    assert "schema_version" not in payload
    _write_json(tmp_path / "IF-MIB.json", payload)

    bundle = load_bundle(tmp_path / "IF-MIB.json")

    assert bundle.modules["IF-MIB"].schema_version is None


@pytest.mark.parametrize("schema_version", ["1.2", "2.0"])
def test_newer_schema_version_is_rejected(tmp_path: Path, schema_version: str) -> None:
    payload = _if_mib_payload()
    payload["schema_version"] = schema_version
    payload["producer_version"] = "9.9.9"
    _write_json(tmp_path / "IF-MIB.json", payload)

    with pytest.raises(BundleValidationError) as exc_info:
        load_bundle(tmp_path / "IF-MIB.json")

    message = str(exc_info.value)
    assert schema_version in message
    assert "1.1" in message
    assert "trishul-smi" in message
    assert "9.9.9" in message


@pytest.mark.parametrize("schema_version", ["abc", "", "1.1.0-beta", 2, 1.5])
def test_malformed_schema_version_is_rejected(tmp_path: Path, schema_version: object) -> None:
    payload = _if_mib_payload()
    payload["schema_version"] = schema_version
    _write_json(tmp_path / "IF-MIB.json", payload)

    with pytest.raises(BundleValidationError):
        load_bundle(tmp_path / "IF-MIB.json")


def test_directory_bundle_rejects_newer_manifest_schema_version(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())
    _write_json(
        tmp_path / "manifest.json",
        {
            "schema_version": "2.0",
            "producer_version": "9.9.9",
            "generated_by": "trishul-smi",
            "generated_at": "2026-05-06T12:00:00Z",
            "modules": [{"module": "IF-MIB", "file": "IF-MIB.json"}],
        },
    )

    with pytest.raises(BundleValidationError) as exc_info:
        load_bundle(tmp_path)

    message = str(exc_info.value)
    assert "2.0" in message
    assert "1.1" in message
    assert "9.9.9" in message
