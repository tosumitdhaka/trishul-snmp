from __future__ import annotations

import json
import time
from pathlib import Path

from trishul_snmp import (
    Counter32Value,
    Counter64Value,
    CounterRule,
    Gauge32Value,
    InMemoryObjectSource,
    IntegerValue,
    OctetStringValue,
    RandomNumericRule,
    SimulationRule,
    TimestampRule,
    TimeTicksValue,
    UptimeRule,
    load_bundle,
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


def _sys_mib_payload() -> dict[object, object]:
    payload = _base_module(module="RFC1213-MIB")
    payload["objects"] = {
        "sysDescr": {
            "oid": "1.3.6.1.2.1.1.1",
            "oid_path": [1, 3, 6, 1, 2, 1, 1, 1],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "scalar",
            "syntax": "DisplayString",
            "max_access": "read-only",
            "status": "current",
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
        },
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
        "ifIndex": {
            "oid": "1.3.6.1.2.1.2.2.1.1",
            "oid_path": [1, 3, 6, 1, 2, 1, 2, 2, 1, 1],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "column",
            "syntax": "Integer32",
            "max_access": "read-only",
            "status": "current",
        },
        "ifInOctets": {
            "oid": "1.3.6.1.2.1.2.2.1.10",
            "oid_path": [1, 3, 6, 1, 2, 1, 2, 2, 1, 10],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "column",
            "syntax": "Counter32",
            "max_access": "read-only",
            "status": "current",
        },
    }
    return payload


# --- CounterRule ---


def test_counter_rule_increments_on_each_get() -> None:
    rule = CounterRule(start=10, increment=5)
    assert rule.get_value() == Counter32Value(10)
    assert rule.get_value() == Counter32Value(15)
    assert rule.get_value() == Counter32Value(20)


def test_counter_rule_defaults() -> None:
    rule = CounterRule()
    assert rule.get_value() == Counter32Value(0)
    assert rule.get_value() == Counter32Value(1)


def test_counter_rule_custom_value_type() -> None:
    rule = CounterRule(start=0, increment=100, value_type=Counter64Value)
    assert rule.get_value() == Counter64Value(0)
    assert rule.get_value() == Counter64Value(100)


# --- RandomNumericRule ---


def test_random_numeric_rule_stays_in_range() -> None:
    rule = RandomNumericRule(min=10, max=20)
    for _ in range(50):
        v = rule.get_value()
        assert isinstance(v, Gauge32Value)
        assert 10 <= v.value <= 20


def test_random_numeric_rule_custom_type() -> None:
    rule = RandomNumericRule(min=0, max=0, value_type=IntegerValue)
    assert rule.get_value() == IntegerValue(0)


# --- UptimeRule ---


def test_uptime_rule_increases_over_time() -> None:
    rule = UptimeRule()
    v1 = rule.get_value()
    assert isinstance(v1, TimeTicksValue)
    time.sleep(0.02)
    v2 = rule.get_value()
    assert v2.value >= v1.value


def test_uptime_rule_starts_near_zero() -> None:
    rule = UptimeRule()
    v = rule.get_value()
    assert isinstance(v, TimeTicksValue)
    assert v.value < 100  # < 1 second in centiseconds


# --- TimestampRule ---


def test_timestamp_rule_returns_current_epoch() -> None:
    before = int(time.time())
    rule = TimestampRule()
    v = rule.get_value()
    after = int(time.time())
    assert isinstance(v, IntegerValue)
    assert before <= v.value <= after


def test_timestamp_rule_custom_type() -> None:
    rule = TimestampRule(value_type=Counter32Value)
    v = rule.get_value()
    assert isinstance(v, Counter32Value)


# --- SimulationRule protocol ---


def test_simulation_rule_protocol_check() -> None:
    assert isinstance(CounterRule(), SimulationRule)
    assert isinstance(RandomNumericRule(min=0, max=1), SimulationRule)
    assert isinstance(UptimeRule(), SimulationRule)
    assert isinstance(TimestampRule(), SimulationRule)
    assert not isinstance(IntegerValue(1), SimulationRule)
    assert not isinstance(42, SimulationRule)


# --- InMemoryObjectSource with rules ---


def test_in_memory_source_with_counter_rule() -> None:
    source = InMemoryObjectSource()
    rule = CounterRule(start=0, increment=10)
    source.set_object("1.3.6.1.2.1.1.3.0", rule)

    v1 = source.lookup_exact((1, 3, 6, 1, 2, 1, 1, 3, 0))
    v2 = source.lookup_exact((1, 3, 6, 1, 2, 1, 1, 3, 0))
    assert v1 == Counter32Value(0)
    assert v2 == Counter32Value(10)


def test_in_memory_source_lookup_next_with_rule() -> None:
    source = InMemoryObjectSource()
    source.set_object("1.3.6.1.2.1.1.3.0", CounterRule(start=7))
    source.set_object("1.3.6.1.2.1.1.4.0", IntegerValue(99))

    result = source.lookup_next((1, 3, 6, 1, 2, 1, 1, 2))
    assert result is not None
    oid, value = result
    assert oid == (1, 3, 6, 1, 2, 1, 1, 3, 0)
    assert value == Counter32Value(7)


def test_in_memory_source_mixes_rules_and_static_values() -> None:
    source = InMemoryObjectSource()
    source.set_object("1.3.6.1.2.1.1.1.0", OctetStringValue(b"router"))
    source.set_object("1.3.6.1.2.1.1.3.0", UptimeRule())

    static = source.lookup_exact((1, 3, 6, 1, 2, 1, 1, 1, 0))
    dynamic = source.lookup_exact((1, 3, 6, 1, 2, 1, 1, 3, 0))
    assert static == OctetStringValue(b"router")
    assert isinstance(dynamic, TimeTicksValue)


# --- from_bundle ---


def test_from_bundle_generates_scalar_and_column_instances(tmp_path: Path) -> None:
    _write_json(tmp_path / "RFC1213-MIB.json", _sys_mib_payload())
    bundle = load_bundle(tmp_path / "RFC1213-MIB.json")

    source = InMemoryObjectSource.from_bundle(bundle, max_instances=2)

    # Static types stay static
    assert source.lookup_exact((1, 3, 6, 1, 2, 1, 1, 1, 0)) == OctetStringValue(b"")
    assert source.lookup_exact((1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 1)) == IntegerValue(1)
    assert source.lookup_exact((1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 2)) == IntegerValue(2)

    # TimeTicks scalar → UptimeRule: value is a TimeTicksValue and changes over time
    v1 = source.lookup_exact((1, 3, 6, 1, 2, 1, 1, 3, 0))
    assert isinstance(v1, TimeTicksValue)
    time.sleep(0.02)
    v2 = source.lookup_exact((1, 3, 6, 1, 2, 1, 1, 3, 0))
    assert isinstance(v2, TimeTicksValue)
    assert v2.value >= v1.value

    # Counter32 column → CounterRule: value increments on each poll
    c1 = source.lookup_exact((1, 3, 6, 1, 2, 1, 2, 2, 1, 10, 1))
    c2 = source.lookup_exact((1, 3, 6, 1, 2, 1, 2, 2, 1, 10, 1))
    assert isinstance(c1, Counter32Value)
    assert isinstance(c2, Counter32Value)
    assert c2.value > c1.value

    # Not-accessible table row must be absent
    assert source.lookup_exact((1, 3, 6, 1, 2, 1, 2, 2)) is None
    assert source.lookup_exact((1, 3, 6, 1, 2, 1, 2, 2, 1)) is None


def test_from_bundle_respects_max_instances(tmp_path: Path) -> None:
    _write_json(tmp_path / "RFC1213-MIB.json", _sys_mib_payload())
    bundle = load_bundle(tmp_path / "RFC1213-MIB.json")

    source = InMemoryObjectSource.from_bundle(bundle, max_instances=1)
    assert source.lookup_exact((1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 1)) == IntegerValue(1)
    assert source.lookup_exact((1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 2)) is None


def test_from_bundle_skips_deprecated_by_default(tmp_path: Path) -> None:
    payload = _base_module(module="DEP-MIB")
    payload["objects"] = {
        "oldObj": {
            "oid": "1.3.6.1.2.1.99.1",
            "oid_path": [1, 3, 6, 1, 2, 1, 99, 1],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "scalar",
            "syntax": "Integer32",
            "max_access": "read-only",
            "status": "deprecated",
        },
        "newObj": {
            "oid": "1.3.6.1.2.1.99.2",
            "oid_path": [1, 3, 6, 1, 2, 1, 99, 2],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "scalar",
            "syntax": "Integer32",
            "max_access": "read-only",
            "status": "current",
        },
    }
    _write_json(tmp_path / "DEP-MIB.json", payload)
    bundle = load_bundle(tmp_path / "DEP-MIB.json")

    source_default = InMemoryObjectSource.from_bundle(bundle)
    assert source_default.lookup_exact((1, 3, 6, 1, 2, 1, 99, 1, 0)) is None
    assert source_default.lookup_exact((1, 3, 6, 1, 2, 1, 99, 2, 0)) == IntegerValue(0)

    source_with_dep = InMemoryObjectSource.from_bundle(bundle, include_deprecated=True)
    assert source_with_dep.lookup_exact((1, 3, 6, 1, 2, 1, 99, 1, 0)) == IntegerValue(0)
