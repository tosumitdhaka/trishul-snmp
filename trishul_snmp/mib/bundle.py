"""Public bundle abstraction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from trishul_snmp.mib.models import MibModuleRecord, MibTypeRecord
from trishul_snmp.mib.registry import MibRegistry
from trishul_snmp.types import OidMatch


class MibBundle:
    """Loaded MIB artifact set used for translation and enrichment."""

    def __init__(self, registry: MibRegistry, *, source: Path) -> None:
        self._registry = registry
        self.source = source

    @property
    def modules(self) -> Mapping[str, MibModuleRecord]:
        return self._registry.modules

    def translate(self, target: str | Sequence[int]) -> str:
        """Translate symbolic targets to numeric OIDs and vice versa."""
        return self._registry.translate(target)

    def resolve(self, target: str) -> tuple[int, ...]:
        """Resolve MODULE::symbol[.suffix] to a numeric OID tuple."""
        return self._registry.resolve_symbolic(target)

    def lookup(self, oid: str | Sequence[int]) -> OidMatch:
        """Find the closest known object for *oid*."""
        return self._registry.lookup_oid(oid)

    def resolve_type(self, module: str, type_name: str) -> MibTypeRecord | None:
        """Resolve a local or imported textual convention."""
        return self._registry.resolve_type(module, type_name)
