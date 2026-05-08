"""Responder data sources."""

from __future__ import annotations

from bisect import bisect_right, insort
from collections.abc import Callable, Iterable, Sequence
from typing import Protocol, TypeAlias

from trishul_snmp._runtime import normalize_targets
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.types import OID, SnmpValueType

ObjectInput: TypeAlias = tuple[str | Sequence[int], SnmpValueType]
NextLookupResult: TypeAlias = tuple[OID, SnmpValueType] | None
ExactLookup: TypeAlias = Callable[[OID], SnmpValueType | None]
NextLookup: TypeAlias = Callable[[OID], NextLookupResult]


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
        self._values: dict[OID, SnmpValueType] = {}
        self._sorted_oids: list[OID] = []
        self.set_objects(objects)

    def lookup_exact(self, oid: OID) -> SnmpValueType | None:
        """Return the exact value for *oid* when present."""
        return self._values.get(oid)

    def lookup_next(self, oid: OID) -> NextLookupResult:
        """Return the next lexicographic OID/value pair after *oid*."""
        index = bisect_right(self._sorted_oids, oid)
        if index >= len(self._sorted_oids):
            return None
        next_oid = self._sorted_oids[index]
        return next_oid, self._values[next_oid]

    def set_object(self, target: str | Sequence[int], value: SnmpValueType) -> OID:
        """Insert or replace an object value and return its normalized OID."""
        oid = self._normalize_target(target)
        if oid not in self._values:
            insort(self._sorted_oids, oid)
        self._values[oid] = value
        return oid

    def set_objects(self, objects: Iterable[ObjectInput]) -> tuple[OID, ...]:
        """Insert or replace multiple object values."""
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

    def _normalize_target(self, target: str | Sequence[int]) -> OID:
        return normalize_targets((target,), bundle=self._bundle)[0]


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
