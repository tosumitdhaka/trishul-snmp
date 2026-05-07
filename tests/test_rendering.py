from __future__ import annotations

import json
from pathlib import Path

from trishul_snmp import IntegerValue, ObjectIdentifierValue, VarBind, load_bundle
from trishul_snmp.mib.render import enrich_varbinds


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


def _test_tc_payload() -> dict[object, object]:
    payload = _base_module(module="TEST-TC")
    payload["types"] = {
        "TruthValue": {
            "class": "textualconvention",
            "base_type": "Integer32",
            "display_hint": "d",
            "status": "current",
            "constraints": {"kind": "enum", "data": [["up", 1], ["down", 2]]},
        }
    }
    return payload


def _test_app_payload() -> dict[object, object]:
    payload = _base_module(module="TEST-APP-MIB", imports={"TEST-TC": ["TruthValue"]})
    payload["objects"] = {
        "adminStatus": {
            "oid": "1.3.6.1.4.1.99999.1",
            "oid_path": [1, 3, 6, 1, 4, 1, 99999, 1],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "scalar",
            "syntax": "TruthValue",
            "max_access": "read-only",
            "status": "current",
        },
        "peerTarget": {
            "oid": "1.3.6.1.4.1.99999.2",
            "oid_path": [1, 3, 6, 1, 4, 1, 99999, 2],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "scalar",
            "syntax": "OBJECT IDENTIFIER",
            "max_access": "read-only",
            "status": "current",
        },
        "peerReference": {
            "oid": "1.3.6.1.4.1.99999.3",
            "oid_path": [1, 3, 6, 1, 4, 1, 99999, 3],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "scalar",
            "syntax": "OBJECT IDENTIFIER",
            "max_access": "read-only",
            "status": "current",
        },
    }
    return payload


def test_bundle_enrichment_renders_imported_enum_labels(tmp_path: Path) -> None:
    _write_json(tmp_path / "TEST-TC.json", _test_tc_payload())
    _write_json(tmp_path / "TEST-APP-MIB.json", _test_app_payload())
    bundle = load_bundle(tmp_path)

    varbinds = (
        VarBind(
            oid=(1, 3, 6, 1, 4, 1, 99999, 1, 0),
            value=IntegerValue(1),
        ),
    )

    enriched = enrich_varbinds(bundle, varbinds)

    assert enriched[0].display_name == "TEST-APP-MIB::adminStatus.0"
    assert enriched[0].display_value == "up(1)"


def test_bundle_enrichment_translates_object_identifier_values(tmp_path: Path) -> None:
    _write_json(tmp_path / "TEST-TC.json", _test_tc_payload())
    _write_json(tmp_path / "TEST-APP-MIB.json", _test_app_payload())
    bundle = load_bundle(tmp_path)

    varbinds = (
        VarBind(
            oid=(1, 3, 6, 1, 4, 1, 99999, 3, 0),
            value=ObjectIdentifierValue((1, 3, 6, 1, 4, 1, 99999, 2)),
        ),
    )

    enriched = enrich_varbinds(bundle, varbinds)

    assert enriched[0].display_name == "TEST-APP-MIB::peerReference.0"
    assert enriched[0].display_value == "TEST-APP-MIB::peerTarget"
