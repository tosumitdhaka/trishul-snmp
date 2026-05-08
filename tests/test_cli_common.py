from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from trishul_snmp.cli.common import (
    load_bundle_from_args,
    parse_hex_bytes,
    parse_notification_varbind,
    parse_notification_varbinds,
    parse_snmp_value,
    resolve_oid_target,
)
from trishul_snmp.types import (
    Counter32Value,
    Counter64Value,
    Gauge32Value,
    IntegerValue,
    IpAddressValue,
    NullValue,
    ObjectIdentifierValue,
    OctetStringValue,
    OpaqueValue,
    TimeTicksValue,
)


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
        "ifDescr": {
            "oid": "1.3.6.1.2.1.2.2.1.2",
            "oid_path": [1, 3, 6, 1, 2, 1, 2, 2, 1, 2],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "column",
            "syntax": "DisplayString",
            "max_access": "read-only",
            "status": "current",
        }
    }
    return payload


def test_load_bundle_from_args_handles_missing_and_present_bundle(tmp_path: Path) -> None:
    assert load_bundle_from_args(argparse.Namespace(bundle=None)) is None

    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())
    bundle = load_bundle_from_args(argparse.Namespace(bundle=tmp_path / "IF-MIB.json"))

    assert bundle is not None
    assert bundle.resolve("IF-MIB::ifDescr.7") == (1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 7)


def test_parse_notification_varbinds_empty_returns_empty_tuple() -> None:
    assert parse_notification_varbinds(None, bundle=None) == ()
    assert parse_notification_varbinds([], bundle=None) == ()


def test_parse_notification_varbind_rejects_invalid_shape() -> None:
    with pytest.raises(ValueError, match="OID=TYPE:VALUE"):
        parse_notification_varbind("IF-MIB::ifDescr.1", bundle=None)
    with pytest.raises(ValueError, match="OID=TYPE:VALUE"):
        parse_notification_varbind("=int:1", bundle=None)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("null", NullValue()),
        ("integer:-7", IntegerValue(-7)),
        ("string:eth0", OctetStringValue(b"eth0")),
        ("hex:61:62-63 64", OctetStringValue(b"abcd")),
        ("ip-address:192.0.2.1", IpAddressValue("192.0.2.1")),
        ("counter32:7", Counter32Value(7)),
        ("gauge32:8", Gauge32Value(8)),
        ("timeticks:9", TimeTicksValue(9)),
        ("opaque:aa bb", OpaqueValue(bytes.fromhex("aabb"))),
        ("counter64:10", Counter64Value(10)),
        ("oid:1.3.6.1.2.1", ObjectIdentifierValue((1, 3, 6, 1, 2, 1))),
    ],
)
def test_parse_snmp_value_supports_expected_types(value: str, expected) -> None:
    assert parse_snmp_value(value, bundle=None) == expected


def test_parse_snmp_value_supports_symbolic_oid_with_bundle(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())
    bundle = load_bundle_from_args(argparse.Namespace(bundle=tmp_path / "IF-MIB.json"))

    parsed = parse_snmp_value("oid:IF-MIB::ifDescr.7", bundle=bundle)

    assert parsed == ObjectIdentifierValue((1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 7))


def test_parse_notification_varbinds_parses_multiple_values(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())
    bundle = load_bundle_from_args(argparse.Namespace(bundle=tmp_path / "IF-MIB.json"))

    parsed = parse_notification_varbinds(
        [
            "IF-MIB::ifDescr.1=string:eth0",
            "1.3.6.1.2.1.2.2.1.2.2=oid:IF-MIB::ifDescr.7",
        ],
        bundle=bundle,
    )

    assert parsed == (
        ("IF-MIB::ifDescr.1", OctetStringValue(b"eth0")),
        (
            "1.3.6.1.2.1.2.2.1.2.2",
            ObjectIdentifierValue((1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 7)),
        ),
    )


def test_parse_snmp_value_rejects_invalid_forms(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())
    bundle = load_bundle_from_args(argparse.Namespace(bundle=tmp_path / "IF-MIB.json"))

    with pytest.raises(ValueError, match="Value type cannot be empty"):
        parse_snmp_value(":7", bundle=None)
    with pytest.raises(ValueError, match="null values must not include a payload"):
        parse_snmp_value("null:1", bundle=None)
    with pytest.raises(ValueError, match="TYPE:VALUE"):
        parse_snmp_value("integer", bundle=None)
    with pytest.raises(ValueError, match="Unsupported value type"):
        parse_snmp_value("unknown:1", bundle=None)
    with pytest.raises(ValueError, match="Symbolic OID requires --bundle"):
        resolve_oid_target("IF-MIB::ifDescr.1", bundle=None)
    with pytest.raises(ValueError, match="Invalid integer value"):
        parse_snmp_value("integer:nope", bundle=None)
    with pytest.raises(ValueError, match="counter32 cannot be negative"):
        parse_snmp_value("counter32:-1", bundle=None)
    with pytest.raises(ValueError, match="Invalid hex payload"):
        parse_snmp_value("opaque:zz", bundle=None)
    with pytest.raises(ValueError, match="Symbolic OID requires --bundle"):
        parse_snmp_value("oid:IF-MIB::ifDescr.1", bundle=None)

    assert resolve_oid_target("IF-MIB::ifDescr.3", bundle=bundle) == (
        1,
        3,
        6,
        1,
        2,
        1,
        2,
        2,
        1,
        2,
        3,
    )


def test_parse_hex_bytes_rejects_odd_and_invalid_payloads() -> None:
    with pytest.raises(ValueError, match="even number of digits"):
        parse_hex_bytes("abc")
    with pytest.raises(ValueError, match="Invalid hex payload"):
        parse_hex_bytes("zz")
