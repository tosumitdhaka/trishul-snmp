from __future__ import annotations

import json
from pathlib import Path

from trishul_snmp import load_bundle
from trishul_snmp.mib.models import MibNode


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


def _multi_module_bundle(tmp_path: Path):
    mib_a = _base_module(module="MIB-A")
    mib_a["objects"] = {
        "sysDescr": {
            "oid": "1.3.6.1.2.1.1.1",
            "oid_path": [1, 3, 6, 1, 2, 1, 1, 1],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "scalar",
            "syntax": "DisplayString",
            "max_access": "read-only",
            "status": "current",
            "description": "The system description.",
        },
        "ifIndex": {
            "oid": "1.3.6.1.2.1.2.2.1.1",
            "oid_path": [1, 3, 6, 1, 2, 1, 2, 2, 1, 1],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "column",
            "syntax": "Integer32",
            "max_access": "read-only",
            "status": "current",
            "description": "Interface index column.",
        },
    }
    mib_a["notifications"] = {
        "linkDown": {
            "oid": "1.3.6.1.6.3.1.1.5.3",
            "oid_path": [1, 3, 6, 1, 6, 3, 1, 1, 5, 3],
            "object_type": "NOTIFICATION-TYPE",
            "class": "notificationtype",
            "status": "current",
            "description": "A link down notification.",
        }
    }

    mib_b = _base_module(module="MIB-B")
    mib_b["objects"] = {
        "sysUpTime": {
            "oid": "1.3.6.1.2.1.1.3",
            "oid_path": [1, 3, 6, 1, 2, 1, 1, 3],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "scalar",
            "syntax": "TimeTicks",
            "max_access": "read-only",
            "status": "current",
            "description": "System uptime ticks.",
        }
    }
    mib_b["notifications"] = {
        "linkUp": {
            "oid": "1.3.6.1.6.3.1.1.5.4",
            "oid_path": [1, 3, 6, 1, 6, 3, 1, 1, 5, 4],
            "object_type": "NOTIFICATION-TYPE",
            "class": "notificationtype",
            "status": "current",
            "description": "A link up event.",
        }
    }

    _write_json(tmp_path / "MIB-A.json", mib_a)
    _write_json(tmp_path / "MIB-B.json", mib_b)
    return load_bundle(tmp_path)


# --- iter_objects ---


def test_iter_objects_returns_all_objects(tmp_path: Path) -> None:
    bundle = _multi_module_bundle(tmp_path)
    nodes = list(bundle.iter_objects())
    names = {n.name for n in nodes}
    assert names == {"sysDescr", "ifIndex", "sysUpTime"}
    assert all(isinstance(n, MibNode) for n in nodes)


def test_iter_objects_filters_by_module(tmp_path: Path) -> None:
    bundle = _multi_module_bundle(tmp_path)
    nodes = list(bundle.iter_objects(module="MIB-A"))
    assert {n.name for n in nodes} == {"sysDescr", "ifIndex"}


def test_iter_objects_filters_by_type_filter(tmp_path: Path) -> None:
    bundle = _multi_module_bundle(tmp_path)
    nodes = list(bundle.iter_objects(type_filter="OBJECT-TYPE"))
    assert all(n.object_type == "OBJECT-TYPE" for n in nodes)
    assert len(nodes) == 3


def test_iter_objects_module_and_type_filter_combined(tmp_path: Path) -> None:
    bundle = _multi_module_bundle(tmp_path)
    nodes = list(bundle.iter_objects(module="MIB-B", type_filter="OBJECT-TYPE"))
    assert [n.name for n in nodes] == ["sysUpTime"]


def test_iter_objects_empty_for_unknown_module(tmp_path: Path) -> None:
    bundle = _multi_module_bundle(tmp_path)
    assert list(bundle.iter_objects(module="NO-SUCH-MIB")) == []


# --- iter_notifications ---


def test_iter_notifications_returns_all_notifications(tmp_path: Path) -> None:
    bundle = _multi_module_bundle(tmp_path)
    nodes = list(bundle.iter_notifications())
    assert {n.name for n in nodes} == {"linkDown", "linkUp"}


def test_iter_notifications_filters_by_module(tmp_path: Path) -> None:
    bundle = _multi_module_bundle(tmp_path)
    nodes = list(bundle.iter_notifications(module="MIB-A"))
    assert [n.name for n in nodes] == ["linkDown"]


def test_iter_notifications_empty_for_unknown_module(tmp_path: Path) -> None:
    bundle = _multi_module_bundle(tmp_path)
    assert list(bundle.iter_notifications(module="NO-SUCH-MIB")) == []


# --- search ---


def test_search_matches_name_substring(tmp_path: Path) -> None:
    bundle = _multi_module_bundle(tmp_path)
    results = bundle.search("sys")
    names = {n.name for n in results}
    assert "sysDescr" in names
    assert "sysUpTime" in names


def test_search_matches_description_substring(tmp_path: Path) -> None:
    bundle = _multi_module_bundle(tmp_path)
    results = bundle.search("uptime")
    assert any(n.name == "sysUpTime" for n in results)


def test_search_is_case_insensitive(tmp_path: Path) -> None:
    bundle = _multi_module_bundle(tmp_path)
    lower = {n.name for n in bundle.search("link")}
    upper = {n.name for n in bundle.search("LINK")}
    assert lower == upper
    assert "linkDown" in lower
    assert "linkUp" in lower


def test_search_filters_by_module(tmp_path: Path) -> None:
    bundle = _multi_module_bundle(tmp_path)
    results = bundle.search("sys", module="MIB-B")
    assert [n.name for n in results] == ["sysUpTime"]


def test_search_type_filter_objects_only(tmp_path: Path) -> None:
    bundle = _multi_module_bundle(tmp_path)
    results = bundle.search("link", type_filter="OBJECT-TYPE")
    assert results == []


def test_search_type_filter_notifications_only(tmp_path: Path) -> None:
    bundle = _multi_module_bundle(tmp_path)
    results = bundle.search("link", type_filter="NOTIFICATION-TYPE")
    assert {n.name for n in results} == {"linkDown", "linkUp"}


def test_search_respects_limit(tmp_path: Path) -> None:
    bundle = _multi_module_bundle(tmp_path)
    results = bundle.search("", limit=2)
    assert len(results) <= 2


def test_search_returns_empty_for_no_match(tmp_path: Path) -> None:
    bundle = _multi_module_bundle(tmp_path)
    assert bundle.search("zzznomatch") == []
