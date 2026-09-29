from __future__ import annotations

import json
from pathlib import Path

import pytest

import trishul_snmp.mib.loader as mib_loader
import trishul_snmp.mib.registry as mib_registry
import trishul_snmp.mib.render as mib_render
from trishul_snmp import (
    BundleValidationError,
    IntegerValue,
    ObjectIdentifierValue,
    TranslationError,
    UnknownOidError,
    UnknownSymbolError,
    VarBind,
)
from trishul_snmp.errors import InvalidOidError
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.mib.models import MibMemberRef, MibNode
from trishul_snmp.mib.registry import MibRegistry
from trishul_snmp.types import OidMatch


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _base_module(
    *,
    module: str,
    imports: dict[str, list[str]] | None = None,
) -> dict[str, object]:
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


def _enum_tc_payload() -> dict[str, object]:
    payload = _base_module(module="ENUM-TC")
    payload["types"] = {
        "TruthValue": {
            "class": "textualconvention",
            "base_type": "Integer32",
            "status": "current",
            "constraints": {"kind": "enum", "data": [["up", 1], ["down", 2]]},
        }
    }
    return payload


def _app_payload(
    *,
    syntax: str | None = "TruthValue",
    imports: dict[str, list[str]] | None = None,
    node_constraints: dict[str, object] | None = None,
    include_local_type: bool = False,
) -> dict[str, object]:
    payload = _base_module(
        module="APP-MIB",
        imports=imports if imports is not None else {"ENUM-TC": ["TruthValue"]},
    )
    status_node: dict[str, object] = {
        "oid": "1.3.6.1.4.1.99999.1",
        "oid_path": [1, 3, 6, 1, 4, 1, 99999, 1],
        "object_type": "OBJECT-TYPE",
        "class": "objecttype",
        "nodetype": "scalar",
        "max_access": "read-only",
        "status": "current",
    }
    if syntax is not None:
        status_node["syntax"] = syntax
    if node_constraints is not None:
        status_node["constraints"] = node_constraints

    payload["objects"] = {
        "status": status_node,
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
    }
    payload["notifications"] = {
        "statusNotice": {
            "oid": "1.3.6.1.4.1.99999.10",
            "oid_path": [1, 3, 6, 1, 4, 1, 99999, 10],
            "object_type": "NOTIFICATION-TYPE",
            "class": "notificationtype",
            "status": "current",
        }
    }
    if include_local_type:
        payload["types"] = {
            "LocalFlag": {
                "class": "textualconvention",
                "base_type": "Integer32",
                "status": "current",
            }
        }
    return payload


def _bundle_from_payloads(
    *payloads: dict[str, object],
    oid_index: dict[tuple[int, ...], mib_registry._OidIndexEntry] | None = None,
) -> MibBundle:
    modules = {}
    for payload in payloads:
        module_name = str(payload["module"])
        path = Path(f"/virtual/{module_name}.json")
        module_record = mib_registry.normalize_module_payload(payload, path=path)
        modules[module_record.module] = module_record
    return MibBundle(MibRegistry(modules, oid_index=oid_index), source=Path("/virtual"))


def _match(symbol: str, *, module: str = "APP-MIB") -> OidMatch:
    base_oid = {
        "status": (1, 3, 6, 1, 4, 1, 99999, 1),
        "peerTarget": (1, 3, 6, 1, 4, 1, 99999, 2),
        "statusNotice": (1, 3, 6, 1, 4, 1, 99999, 10),
    }.get(symbol, (1, 3, 6, 1, 4, 1, 99999, 99))
    return OidMatch(oid=base_oid, module=module, symbol=symbol, matched_oid=base_oid)


def _valid_node(**overrides: object) -> dict[str, object]:
    node = {
        "oid": "1.3.6.1.4.1.99999.1",
        "oid_path": [1, 3, 6, 1, 4, 1, 99999, 1],
        "object_type": "OBJECT-TYPE",
        "class": "objecttype",
        "nodetype": "scalar",
        "syntax": "TruthValue",
        "max_access": "read-only",
        "status": "current",
    }
    node.update(overrides)
    return node


def _valid_type(**overrides: object) -> dict[str, object]:
    type_record = {
        "class": "textualconvention",
        "base_type": "Integer32",
        "display_hint": "d",
        "status": "current",
    }
    type_record.update(overrides)
    return type_record


def test_mibnode_symbolic_and_enrich_varbinds_without_bundle() -> None:
    node = MibNode(
        module="APP-MIB",
        name="status",
        oid=(1, 3, 6, 1, 4, 1, 99999, 1),
        class_name="objecttype",
        object_type="OBJECT-TYPE",
        nodetype="scalar",
        syntax="TruthValue",
        max_access="read-only",
        status="current",
        index=None,
        augments=None,
        description=None,
        members=None,
        constraints=None,
    )

    enriched = mib_render.enrich_varbinds(
        None,
        (VarBind(oid=(1, 3, 6, 1), value=IntegerValue(7)),),
    )

    assert node.symbolic == "APP-MIB::status"
    assert enriched[0].display_name is None
    assert enriched[0].display_value == "7"


def test_normalize_node_map_retains_description_and_members() -> None:
    normalized = mib_registry.normalize_node_map(
        {
            "statusNotice": {
                "oid": "1.3.6.1.4.1.99999.10",
                "oid_path": [1, 3, 6, 1, 4, 1, 99999, 10],
                "object_type": "NOTIFICATION-TYPE",
                "class": "notificationtype",
                "status": "current",
                "description": "Status changed notification.",
                "members": [
                    {"module": "APP-MIB", "object": "status"},
                    {"module": "APP-MIB", "object": "peerTarget"},
                ],
            },
        },
        module_name="APP-MIB",
        path=Path("/virtual/APP-MIB.json"),
        default_nodetype="notification",
    )

    node = normalized["statusNotice"]

    assert node.nodetype == "notification"
    assert node.description == "Status changed notification."
    assert node.members == (
        MibMemberRef(module="APP-MIB", object="status"),
        MibMemberRef(module="APP-MIB", object="peerTarget"),
    )


def test_rendering_falls_back_for_unknown_oid_lookup_and_untranslated_oid_value() -> None:
    bundle = _bundle_from_payloads(_app_payload())
    varbinds = (
        VarBind(
            oid=(1, 3, 6, 1, 4, 1, 99999, 99, 0),
            value=IntegerValue(9),
        ),
        VarBind(
            oid=(1, 3, 6, 1, 4, 1, 99999, 98, 0),
            value=ObjectIdentifierValue((1, 3, 6, 1, 4, 1, 99999, 200)),
        ),
    )

    enriched = mib_render.enrich_varbinds(bundle, varbinds)

    assert enriched[0].display_name is None
    assert enriched[0].display_value == "9"
    assert enriched[1].display_name is None
    assert enriched[1].display_value == "1.3.6.1.4.1.99999.200"


def test_render_enum_helpers_cover_missing_node_missing_type_and_invalid_constraints() -> None:
    no_syntax_bundle = _bundle_from_payloads(_app_payload(syntax=None))
    missing_type_bundle = _bundle_from_payloads(_app_payload(syntax="MissingType", imports={}))
    constrained_bundle = _bundle_from_payloads(
        _app_payload(node_constraints={"kind": "enum", "data": [["up", 1]]})
    )

    assert mib_render._resolve_node(no_syntax_bundle, _match("statusNotice")).name == "statusNotice"
    assert mib_render._resolve_node(no_syntax_bundle, _match("status", module="MISSING")) is None
    assert mib_render._resolve_enum_label(no_syntax_bundle, _match("missing"), value=1) is None
    assert mib_render._resolve_enum_label(no_syntax_bundle, _match("status"), value=1) is None
    assert mib_render._resolve_enum_label(missing_type_bundle, _match("status"), value=1) is None
    assert mib_render._resolve_enum_label(constrained_bundle, _match("status"), value=1) == "up"

    assert mib_render._enum_label_from_constraints({"kind": "range", "data": []}, value=1) is None
    assert (
        mib_render._enum_label_from_constraints(
            {"kind": "enum", "data": [["up", 1]]},
            value=2,
        )
        is None
    )


def test_parse_oid_variants_and_errors() -> None:
    assert mib_registry.parse_oid(" .1.3.6 ") == (1, 3, 6)
    assert mib_registry.parse_oid((1, 3, 6)) == (1, 3, 6)

    for value in ("", ".", "1.two", "1.-1"):
        with pytest.raises(InvalidOidError):
            mib_registry.parse_oid(value)

    for value in ((), (1, -1), (1, "x")):
        with pytest.raises(InvalidOidError):
            mib_registry.parse_oid(value)  # type: ignore[arg-type]


def test_parse_symbolic_target_and_translation_edges() -> None:
    assert mib_registry.parse_symbolic_target("APP-MIB::status.7") == ("APP-MIB", "status", (7,))

    for target in ("APP-MIB", "APP-MIB::.1", "APP-MIB::status.foo"):
        with pytest.raises(UnknownSymbolError):
            mib_registry.parse_symbolic_target(target)

    bundle = _bundle_from_payloads(
        _app_payload(
            imports={"ENUM-TC": ["TruthValue"]},
            include_local_type=True,
        )
    )

    assert bundle.resolve_type("APP-MIB", "LocalFlag") is not None
    assert bundle.resolve_type("MISSING", "LocalFlag") is None
    assert bundle.resolve_type("APP-MIB", "TruthValue") is None

    with pytest.raises(TranslationError):
        bundle.translate("   ")
    with pytest.raises(UnknownOidError):
        bundle.lookup("1.3.6.1.4.1.99999.250")


def test_normalize_imports_validation_errors(tmp_path: Path) -> None:
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_imports([], path=tmp_path / "x.json")
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_imports({1: ["name"]}, path=tmp_path / "x.json")  # type: ignore[dict-item]
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_imports({"MOD": "name"}, path=tmp_path / "x.json")


def test_normalize_node_map_validation_errors(tmp_path: Path) -> None:
    path = tmp_path / "x.json"

    with pytest.raises(BundleValidationError):
        mib_registry.normalize_node_map([], module_name="APP-MIB", path=path)
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_node_map({1: _valid_node()}, module_name="APP-MIB", path=path)  # type: ignore[dict-item]
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_node_map({"node": []}, module_name="APP-MIB", path=path)
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_node_map(
            {"node": _valid_node(index=[1])},
            module_name="APP-MIB",
            path=path,
        )
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_node_map(
            {"node": _valid_node(constraints=["bad"])},
            module_name="APP-MIB",
            path=path,
        )
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_node_map(
            {"node": _valid_node(description=1)},
            module_name="APP-MIB",
            path=path,
        )
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_node_map(
            {"node": _valid_node(members="bad")},
            module_name="APP-MIB",
            path=path,
        )
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_node_map(
            {"node": _valid_node(members=[{"module": "APP-MIB", "object": 1}])},
            module_name="APP-MIB",
            path=path,
        )


def test_normalize_type_map_validation_errors(tmp_path: Path) -> None:
    path = tmp_path / "x.json"

    with pytest.raises(BundleValidationError):
        mib_registry.normalize_type_map([], module_name="APP-MIB", path=path)
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_type_map({1: _valid_type()}, module_name="APP-MIB", path=path)  # type: ignore[dict-item]
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_type_map({"Type": []}, module_name="APP-MIB", path=path)
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_type_map(
            {"Type": _valid_type(constraints=["bad"])},
            module_name="APP-MIB",
            path=path,
        )


def test_normalize_node_oid_and_string_helpers_validation_errors(tmp_path: Path) -> None:
    path = tmp_path / "x.json"

    assert mib_registry._normalize_node_oid(None, "1.3.6.1", name="node", path=path) == (
        1,
        3,
        6,
        1,
    )

    with pytest.raises(BundleValidationError):
        mib_registry._normalize_node_oid("bad", "1.3.6.1", name="node", path=path)
    with pytest.raises(BundleValidationError):
        mib_registry._normalize_node_oid(
            [1, 3, 6, 1],
            "1.3.6.2",
            name="node",
            path=path,
        )
    with pytest.raises(BundleValidationError):
        mib_registry._normalize_node_oid(None, None, name="node", path=path)
    with pytest.raises(BundleValidationError):
        mib_registry._require_string({}, "class", name="node", path=path)
    with pytest.raises(BundleValidationError):
        mib_registry._optional_string(1, field="syntax", name="node", path=path)


def test_normalize_module_metadata_and_payload_validation_errors(tmp_path: Path) -> None:
    path = tmp_path / "x.json"

    assert mib_registry.normalize_module_metadata(None, path=path) == {}
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_module_metadata([], path=path)
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_module_metadata({1: "x"}, path=path)  # type: ignore[dict-item]
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_module_payload([], path=path)
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_module_payload({"generated_by": "trishul-smi"}, path=path)
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_module_payload({"module": "APP-MIB"}, path=path)


def test_loader_missing_path_empty_dir_and_json_reading_helpers(tmp_path: Path) -> None:
    with pytest.raises(BundleValidationError):
        mib_loader.load_bundle(tmp_path / "missing")
    with pytest.raises(BundleValidationError):
        mib_loader._discover_directory(tmp_path)
    with pytest.raises(BundleValidationError):
        mib_loader._read_json(tmp_path / "missing.json")

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not-json", encoding="utf-8")
    with pytest.raises(BundleValidationError):
        mib_loader._read_json(bad_json)

    _write_json(tmp_path / "b.json", {})
    _write_json(tmp_path / "a.json", {})
    assert [path.name for path in mib_loader._iter_bundle_files(tmp_path)] == [
        "a.json",
        "b.json",
        "bad.json",
    ]


def test_build_registry_loads_distinct_modules(tmp_path: Path) -> None:
    first = tmp_path / "A.json"
    second = tmp_path / "B.json"
    _write_json(first, _base_module(module="MIB-A"))
    _write_json(second, _base_module(module="MIB-B"))

    registry = mib_loader._build_registry((first, second), oid_index={})

    assert set(registry.modules) == {"MIB-A", "MIB-B"}


def test_build_registry_rejects_duplicate_module_names(tmp_path: Path) -> None:
    first = tmp_path / "A-IF-MIB.json"
    second = tmp_path / "B-IF-MIB.json"
    _write_json(first, _base_module(module="IF-MIB"))
    _write_json(second, _base_module(module="IF-MIB"))

    with pytest.raises(BundleValidationError) as exc_info:
        mib_loader._build_registry((first, second), oid_index={})

    message = str(exc_info.value)
    assert "IF-MIB" in message
    assert "A-IF-MIB.json" in message
    assert "B-IF-MIB.json" in message
    assert exc_info.value.path == second


def test_module_paths_from_manifest_validation_and_dedup(tmp_path: Path) -> None:
    module_path = tmp_path / "IF-MIB.json"
    _write_json(module_path, _base_module(module="IF-MIB"))

    manifest_path = tmp_path / "manifest.json"
    _write_json(manifest_path, {"modules": ["IF-MIB.json", {"file": "IF-MIB.json"}]})
    assert mib_loader._module_paths_from_manifest(tmp_path, manifest_path) == (
        module_path.resolve(),
    )

    _write_json(manifest_path, ["IF-MIB.json"])
    with pytest.raises(BundleValidationError):
        mib_loader._module_paths_from_manifest(tmp_path, manifest_path)

    _write_json(manifest_path, {"modules": []})
    with pytest.raises(BundleValidationError):
        mib_loader._module_paths_from_manifest(tmp_path, manifest_path)

    _write_json(manifest_path, {"modules": ["../outside.json"]})
    with pytest.raises(BundleValidationError):
        mib_loader._module_paths_from_manifest(tmp_path, manifest_path)

    _write_json(manifest_path, {"modules": ["MISSING.json"]})
    with pytest.raises(BundleValidationError):
        mib_loader._module_paths_from_manifest(tmp_path, manifest_path)

    _write_json(manifest_path, {"modules": [{"module": "IF-MIB"}]})
    with pytest.raises(BundleValidationError):
        mib_loader._module_paths_from_manifest(tmp_path, manifest_path)


def test_load_oid_index_validation_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    index_path = tmp_path / "oid_index.json"

    _write_json(index_path, [])
    with pytest.raises(BundleValidationError):
        mib_loader._load_oid_index(index_path)

    _write_json(index_path, {"oids": []})
    with pytest.raises(BundleValidationError):
        mib_loader._load_oid_index(index_path)

    monkeypatch.setattr(
        mib_loader,
        "_read_json",
        lambda path: {1: {"module": "APP-MIB", "object": "status"}},
    )
    with pytest.raises(BundleValidationError):
        mib_loader._load_oid_index(index_path)

    monkeypatch.setattr(mib_loader, "_read_json", lambda path: {"1.3.6": []})
    with pytest.raises(BundleValidationError):
        mib_loader._load_oid_index(index_path)

    monkeypatch.setattr(mib_loader, "_read_json", lambda path: {"1.3.6": {"module": "APP-MIB"}})
    with pytest.raises(BundleValidationError):
        mib_loader._load_oid_index(index_path)


def test_registry_accelerator_lookup_and_prefix_resolution() -> None:
    bundle = _bundle_from_payloads(
        _app_payload(),
        oid_index={
            (1, 3, 6, 1, 4, 1, 99999, 2): mib_registry._OidIndexEntry(
                module="APP-MIB",
                symbol="peerTarget",
            )
        },
    )

    exact = bundle.lookup((1, 3, 6, 1, 4, 1, 99999, 2))
    prefixed = bundle.lookup((1, 3, 6, 1, 4, 1, 99999, 2, 7))

    assert exact.symbolic == "APP-MIB::peerTarget"
    assert prefixed.symbolic == "APP-MIB::peerTarget.7"


def _enums_node(**overrides: object) -> dict[str, object]:
    node = _valid_node()
    node["enums"] = {"up": 1, "down": 2}
    node["units"] = "bits/second"
    node.update(overrides)
    return node


def test_normalize_node_enums_and_units_populated() -> None:
    normalized = mib_registry.normalize_node_map(
        {"status": _enums_node()},
        module_name="APP-MIB",
        path=Path("/virtual/APP-MIB.json"),
    )

    node = normalized["status"]

    assert node.enums == {"up": 1, "down": 2}
    assert node.units == "bits/second"


def test_normalize_node_missing_enums_and_units_default_to_none() -> None:
    normalized = mib_registry.normalize_node_map(
        {"status": _valid_node()},
        module_name="APP-MIB",
        path=Path("/virtual/APP-MIB.json"),
    )

    node = normalized["status"]

    assert node.enums is None
    assert node.units is None


def test_normalize_node_invalid_enums_and_units_errors(tmp_path: Path) -> None:
    path = tmp_path / "x.json"

    for bad_enums in ("bad", ["up"], {"up": "1"}, {"up": True}, {"up": 1, 2: 3}):
        with pytest.raises(BundleValidationError):
            mib_registry.normalize_node_map(
                {"node": _enums_node(enums=bad_enums)},
                module_name="APP-MIB",
                path=path,
            )
    with pytest.raises(BundleValidationError):
        mib_registry.normalize_node_map(
            {"node": _enums_node(units=42)},
            module_name="APP-MIB",
            path=path,
        )


def test_registry_lookup_metadata_enums_units_and_missing_nodes() -> None:
    payload = _app_payload(
        syntax="INTEGER",
        node_constraints={"kind": "enum", "data": [["up", 1], ["down", 2]]},
    )
    status_node = payload["objects"]["status"]
    assert isinstance(status_node, dict)
    status_node["enums"] = {"up": 1, "down": 2}
    status_node["units"] = "volts"
    bundle = _bundle_from_payloads(payload)

    metadata = bundle.lookup_metadata((1, 3, 6, 1, 4, 1, 99999, 1, 0))

    assert metadata is not None
    assert metadata.enums == {"up": 1, "down": 2}
    assert metadata.units == "volts"
    assert metadata.syntax == "INTEGER"

    assert bundle.lookup_metadata((1, 3, 6, 1, 4, 1, 99999, 250)) is None


def test_registry_lookup_metadata_unknown_accelerator_symbol_returns_none() -> None:
    bundle = _bundle_from_payloads(
        _app_payload(),
        oid_index={
            (1, 3, 6, 1, 4, 1): mib_registry._OidIndexEntry(
                module="APP-MIB",
                symbol="missingSymbol",
            )
        },
    )

    assert bundle.lookup_metadata((1, 3, 6, 1, 4, 1, 7)) is None


def test_registry_lookup_metadata_absent_on_legacy_bundle() -> None:
    bundle = _bundle_from_payloads(_app_payload())

    metadata = bundle.lookup_metadata((1, 3, 6, 1, 4, 1, 99999, 1, 0))

    assert metadata is not None
    assert metadata.enums is None
    assert metadata.units is None


def test_enrich_varbinds_renders_enums_units_and_bits(tmp_path: Path) -> None:
    from tests._bundle_fixtures import write_value_metadata_bundle
    from trishul_snmp import OctetStringValue

    bundle = mib_loader.load_bundle(write_value_metadata_bundle(tmp_path))

    enriched = mib_render.enrich_varbinds(
        bundle,
        (
            VarBind(oid=(1, 3, 6, 1, 4, 1, 99999, 1, 0), value=IntegerValue(2)),
            VarBind(oid=(1, 3, 6, 1, 4, 1, 99999, 2, 0), value=OctetStringValue(b"\xc0")),
            VarBind(oid=(1, 3, 6, 1, 4, 1, 99999, 3, 0), value=IntegerValue(7)),
        ),
    )

    assert enriched[0].display_value == "down(2)"
    assert enriched[0].enum_label == "down"
    assert enriched[0].units is None
    assert enriched[1].display_value == "red(0) green(1)"
    assert enriched[1].enum_label is None
    assert enriched[1].units is None
    assert enriched[2].display_value == "7"
    assert enriched[2].enum_label is None
    assert enriched[2].units == "bits/second"


def test_enrich_varbinds_unmatched_enum_and_raw_octet_strings(tmp_path: Path) -> None:
    from tests._bundle_fixtures import write_value_metadata_bundle
    from trishul_snmp import OctetStringValue

    bundle = mib_loader.load_bundle(write_value_metadata_bundle(tmp_path))

    enriched = mib_render.enrich_varbinds(
        bundle,
        (
            VarBind(oid=(1, 3, 6, 1, 4, 1, 99999, 1, 0), value=IntegerValue(99)),
            VarBind(oid=(1, 3, 6, 1, 4, 1, 99999, 2, 0), value=OctetStringValue(b"\x00")),
            VarBind(oid=(1, 3, 6, 1, 4, 1, 99999, 5, 0), value=OctetStringValue(b"hello")),
            VarBind(oid=(1, 3, 6, 1, 4, 1, 99999, 250), value=OctetStringValue(b"\x80")),
        ),
    )

    assert enriched[0].display_value == "99"
    assert enriched[0].enum_label is None
    assert enriched[1].display_value == "00"
    assert enriched[2].display_value == "hello"
    assert enriched[3].display_value == "80"


def test_enrich_varbinds_bits_via_textual_convention() -> None:
    from trishul_snmp import OctetStringValue

    tc_payload = _base_module(module="BITS-TC")
    tc_payload["types"] = {
        "PortFlags": {
            "class": "textualconvention",
            "base_type": "BITS",
            "status": "current",
            "constraints": {"kind": "bits", "data": [["red", 0], ["green", 1]]},
        }
    }
    app_payload = _base_module(
        module="APP-MIB",
        imports={"BITS-TC": ["PortFlags"]},
    )
    app_payload["objects"] = {
        "portFlags": {
            "oid": "1.3.6.1.4.1.99999.1",
            "oid_path": [1, 3, 6, 1, 4, 1, 99999, 1],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "scalar",
            "syntax": "PortFlags",
            "max_access": "read-only",
            "status": "current",
        }
    }
    bundle = _bundle_from_payloads(tc_payload, app_payload)

    enriched = mib_render.enrich_varbinds(
        bundle,
        (VarBind(oid=(1, 3, 6, 1, 4, 1, 99999, 1, 0), value=OctetStringValue(b"\x80")),),
    )

    assert enriched[0].display_value == "red(0)"


def test_bits_helpers_cover_missing_nodes_and_non_bits_objects() -> None:
    bundle = _bundle_from_payloads(_app_payload(syntax="INTEGER"))

    assert mib_render._resolve_bits_labels(bundle, _match("missing"), value=b"\x80") is None
    assert mib_render._resolve_bits_labels(bundle, _match("status"), value=b"\x80") is None
    assert mib_render._constraint_enum_map({"kind": "range", "data": []}) is None
    assert mib_render._constraint_enum_map({"kind": "enum", "data": "bad"}) is None
    assert mib_render._constraint_enum_map(None) is None
    assert mib_render._constraint_kind({"kind": 3}) is None
    assert mib_render._enum_label_from_map(None, value=1) is None


def test_bits_helpers_cover_inline_bits_and_tc_edges() -> None:
    inline_bits = _app_payload(
        syntax="BITS",
        node_constraints={"kind": "bits", "data": [["red", 0], ["green", 1]]},
    )
    inline_bundle = _bundle_from_payloads(inline_bits)
    inline_node = mib_render._resolve_node(inline_bundle, _match("status"))
    assert inline_node is not None
    assert mib_render._bits_enum_map(inline_bundle, _match("status"), inline_node) == {
        "red": 0,
        "green": 1,
    }

    bare_bits = _app_payload(syntax="BITS")
    bare_bundle = _bundle_from_payloads(bare_bits)
    bare_node = mib_render._resolve_node(bare_bundle, _match("status"))
    assert bare_node is not None
    assert mib_render._bits_enum_map(bare_bundle, _match("status"), bare_node) is None
    assert mib_render._resolve_bits_labels(bare_bundle, _match("status"), value=b"\x80") is None

    no_syntax = _bundle_from_payloads(_app_payload(syntax=None))
    no_syntax_node = mib_render._resolve_node(no_syntax, _match("status"))
    assert no_syntax_node is not None
    assert mib_render._bits_enum_map(no_syntax, _match("status"), no_syntax_node) is None
    assert mib_render._is_bits_node(no_syntax, _match("status"), no_syntax_node) is False

    tc_payload = _base_module(module="BITS-TC")
    tc_payload["types"] = {
        "PortFlags": {
            "class": "textualconvention",
            "base_type": "BITS",
            "status": "current",
            "constraints": {"kind": "bits", "data": [["red", 0]]},
        }
    }
    tc_app = _base_module(module="APP-MIB", imports={"BITS-TC": ["PortFlags"]})
    tc_app["objects"] = {
        "portFlags": {
            "oid": "1.3.6.1.4.1.99999.1",
            "oid_path": [1, 3, 6, 1, 4, 1, 99999, 1],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "scalar",
            "syntax": "PortFlags",
            "max_access": "read-only",
            "status": "current",
            "enums": {"red": 0, "green": 1},
        }
    }
    tc_bundle = _bundle_from_payloads(tc_payload, tc_app)
    tc_node = mib_render._resolve_node(tc_bundle, _match("portFlags"))
    assert tc_node is not None
    assert mib_render._is_bits_node(tc_bundle, _match("portFlags"), tc_node) is True
    assert mib_render._bits_enum_map(tc_bundle, _match("portFlags"), tc_node) == {
        "red": 0,
        "green": 1,
    }

    assert mib_render._resolve_bits_labels(
        tc_bundle,
        _match("portFlags"),
        value=b"\x80",
    ) == [("red", 0)]
