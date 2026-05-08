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
