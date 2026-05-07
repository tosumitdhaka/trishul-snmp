from __future__ import annotations

import json
from pathlib import Path


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
        "schema_version": "1.1",
        "producer_version": "0.4.1",
        "generated_by": "trishul-smi",
        "generated_at": "2026-05-07T12:00:00Z",
        "imports": imports or {},
        "objects": {},
        "types": {},
        "notifications": {},
        "module_metadata": {"lastupdated": None, "revisions": []},
    }


def write_scalar_instance_alias_bundle(path: Path) -> Path:
    """Write a minimal bundle where a scalar base and exact .0 alias coexist."""
    snmpv2_mib = _base_module(module="SNMPv2-MIB")
    snmpv2_mib["objects"] = {
        "system": {
            "oid": "1.3.6.1.2.1.1",
            "oid_path": [1, 3, 6, 1, 2, 1, 1],
            "object_type": "OBJECT IDENTIFIER",
            "class": "objectidentifier",
            "syntax": None,
            "max_access": None,
            "status": None,
            "index": None,
            "augments": None,
            "description": None,
        },
        "sysUpTime": {
            "oid": "1.3.6.1.2.1.1.3",
            "oid_path": [1, 3, 6, 1, 2, 1, 1, 3],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "scalar",
            "syntax": "TimeTicks",
            "max_access": "read-only",
            "status": "current",
            "index": None,
            "augments": None,
            "description": "Time since the network management subsystem was last reset.",
        },
    }

    disman_expression_mib = _base_module(
        module="DISMAN-EXPRESSION-MIB",
        imports={"SNMPv2-MIB": ["sysUpTime"]},
    )
    disman_expression_mib["objects"] = {
        "sysUpTimeInstance": {
            "oid": "1.3.6.1.2.1.1.3.0",
            "oid_path": [1, 3, 6, 1, 2, 1, 1, 3, 0],
            "object_type": "OBJECT IDENTIFIER",
            "class": "objectidentifier",
            "syntax": None,
            "max_access": None,
            "status": None,
            "index": None,
            "augments": None,
            "description": None,
        }
    }

    _write_json(path / "SNMPv2-MIB.json", snmpv2_mib)
    _write_json(path / "DISMAN-EXPRESSION-MIB.json", disman_expression_mib)
    _write_json(
        path / "manifest.json",
        {
            "schema_version": "1.1",
            "producer_version": "0.4.1",
            "generated_by": "trishul-smi",
            "generated_at": "2026-05-07T12:00:00Z",
            "modules": [
                {"module": "DISMAN-EXPRESSION-MIB", "file": "DISMAN-EXPRESSION-MIB.json"},
                {"module": "SNMPv2-MIB", "file": "SNMPv2-MIB.json"},
            ],
            "sidecars": {"oid_index": "oid_index.json"},
        },
    )
    _write_json(
        path / "oid_index.json",
        {
            "schema_version": "1.1",
            "producer_version": "0.4.1",
            "generated_by": "trishul-smi",
            "generated_at": "2026-05-07T12:00:00Z",
            "oids": {
                "1.3.6.1.2.1.1.3": {
                    "module": "SNMPv2-MIB",
                    "object": "sysUpTime",
                    "class": "objecttype",
                    "object_type": "OBJECT-TYPE",
                    "nodetype": "scalar",
                },
                "1.3.6.1.2.1.1.3.0": {
                    "module": "DISMAN-EXPRESSION-MIB",
                    "object": "sysUpTimeInstance",
                    "class": "objectidentifier",
                    "object_type": "OBJECT IDENTIFIER",
                },
            },
        },
    )
    return path
