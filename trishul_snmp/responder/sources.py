"""Responder data sources."""

from __future__ import annotations

from bisect import bisect_right, insort
from collections.abc import Callable, Iterable, Sequence
from typing import Protocol, TypeAlias

from trishul_snmp._runtime import normalize_targets
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.responder.rules import CounterRule, RandomNumericRule, SimulationRule, UptimeRule
from trishul_snmp.types import (
    OID,
    Counter64Value,
    IntegerValue,
    IpAddressValue,
    OctetStringValue,
    SnmpValueType,
)

ObjectValue: TypeAlias = SnmpValueType | SimulationRule
ObjectInput: TypeAlias = tuple[str | Sequence[int], ObjectValue]
NextLookupResult: TypeAlias = tuple[OID, SnmpValueType] | None
ExactLookup: TypeAlias = Callable[[OID], SnmpValueType | None]
NextLookup: TypeAlias = Callable[[OID], NextLookupResult]

_COUNTER32_SYNTAXES = frozenset({"Counter32", "ZeroBasedCounter32"})
_COUNTER64_SYNTAXES = frozenset({"Counter64", "ZeroBasedCounter64", "CounterBasedGauge64"})
_GAUGE_SYNTAXES = frozenset({"Gauge32", "Unsigned32"})
_TIMETICKS_SYNTAXES = frozenset({"TimeTicks", "TimeStamp", "TimeInterval"})
_IP_SYNTAXES = frozenset({"IpAddress"})


class ResponderSource(Protocol):
    """Protocol for read-only responder lookup sources."""

    def lookup_exact(self, oid: OID) -> SnmpValueType | None:
        """Return the exact value for *oid*, or ``None`` when missing."""

    def lookup_next(self, oid: OID) -> NextLookupResult:
        """Return the next lexicographic OID/value pair after *oid*."""


class InMemoryObjectSource:
    """Mutable in-memory object source for responder and simulator use."""

    def __init__(
        self,
        *,
        bundle: MibBundle | None = None,
        objects: Iterable[ObjectInput] = (),
    ) -> None:
        self._bundle = bundle
        self._values: dict[OID, ObjectValue] = {}
        self._sorted_oids: list[OID] = []
        self.set_objects(objects)

    def lookup_exact(self, oid: OID) -> SnmpValueType | None:
        """Return the exact value for *oid* when present."""
        stored = self._values.get(oid)
        if stored is None:
            return None
        if isinstance(stored, SimulationRule):
            return stored.get_value()
        return stored

    def lookup_next(self, oid: OID) -> NextLookupResult:
        """Return the next lexicographic OID/value pair after *oid*."""
        index = bisect_right(self._sorted_oids, oid)
        if index >= len(self._sorted_oids):
            return None
        next_oid = self._sorted_oids[index]
        stored = self._values[next_oid]
        value = stored.get_value() if isinstance(stored, SimulationRule) else stored
        return next_oid, value

    def set_object(self, target: str | Sequence[int], value: ObjectValue) -> OID:
        """Insert or replace an object value or rule and return its normalized OID."""
        oid = self._normalize_target(target)
        if oid not in self._values:
            insort(self._sorted_oids, oid)
        self._values[oid] = value
        return oid

    def set_objects(self, objects: Iterable[ObjectInput]) -> tuple[OID, ...]:
        """Insert or replace multiple object values or rules."""
        return tuple(self.set_object(target, value) for target, value in objects)

    def delete_object(self, target: str | Sequence[int]) -> bool:
        """Delete an object value when present."""
        oid = self._normalize_target(target)
        if oid not in self._values:
            return False
        del self._values[oid]
        self._sorted_oids.remove(oid)
        return True

    def clear(self) -> None:
        """Remove all stored objects."""
        self._values.clear()
        self._sorted_oids.clear()

    @property
    def oids(self) -> tuple[OID, ...]:
        """Return stored OIDs in lexicographic order."""
        return tuple(self._sorted_oids)

    @classmethod
    def from_bundle(
        cls,
        bundle: MibBundle,
        *,
        max_instances: int = 2,
        include_deprecated: bool = False,
    ) -> InMemoryObjectSource:
        """Generate a populated source from bundle objects with sensible default values."""
        source = cls(bundle=bundle)
        for node in bundle.iter_objects():
            if node.max_access == "not-accessible":
                continue
            if node.status == "obsolete":
                continue
            if not include_deprecated and node.status == "deprecated":
                continue
            if node.nodetype == "scalar":
                source.set_object(node.oid + (0,), _default_value(node.syntax, instance=0))
            elif node.nodetype == "column":
                for i in range(1, max_instances + 1):
                    source.set_object(node.oid + (i,), _default_value(node.syntax, instance=i))
        return source

    def _normalize_target(self, target: str | Sequence[int]) -> OID:
        return normalize_targets((target,), bundle=self._bundle)[0]


def _default_value(syntax: str | None, *, instance: int) -> ObjectValue:
    if syntax is None:
        return OctetStringValue(b"")
    base = syntax.split("(")[0].strip()
    if base in _COUNTER32_SYNTAXES:
        return CounterRule()
    if base in _COUNTER64_SYNTAXES:
        return CounterRule(value_type=Counter64Value)
    if base in _GAUGE_SYNTAXES:
        return RandomNumericRule(min=0, max=1000)
    if base in _TIMETICKS_SYNTAXES:
        return UptimeRule()
    if base in _IP_SYNTAXES:
        return IpAddressValue("0.0.0.0")
    if base in {
        "Integer32",
        "Integer",
        "InterfaceIndex",
        "TruthValue",
        "RowStatus",
        "StorageType",
        "ColumnStatus",
    }:
        return IntegerValue(instance)
    return OctetStringValue(b"")


class CallbackObjectSource:
    """Callback-backed responder source for dynamic simulation."""

    def __init__(
        self,
        *,
        exact_lookup: ExactLookup,
        next_lookup: NextLookup,
    ) -> None:
        self._exact_lookup = exact_lookup
        self._next_lookup = next_lookup

    def lookup_exact(self, oid: OID) -> SnmpValueType | None:
        """Delegate exact lookup to the configured callback."""
        return self._exact_lookup(oid)

    def lookup_next(self, oid: OID) -> NextLookupResult:
        """Delegate next lookup to the configured callback."""
        return self._next_lookup(oid)
