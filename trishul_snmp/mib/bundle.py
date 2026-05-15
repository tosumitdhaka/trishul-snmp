"""Public bundle abstraction."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

from trishul_snmp.mib.models import MibModuleRecord, MibNode, MibTypeRecord
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

    def display_symbolic(self, target: str | Sequence[int]) -> str:
        """Render a numeric OID using user-facing symbolic display policy."""
        return self._registry.display_symbolic(target)

    def display_symbolic_from_match(self, match: OidMatch) -> str:
        """Render a resolved OID match using user-facing symbolic display policy."""
        return self._registry.display_symbolic_from_match(match)

    def resolve(self, target: str) -> tuple[int, ...]:
        """Resolve MODULE::symbol[.suffix] to a numeric OID tuple."""
        return self._registry.resolve_symbolic(target)

    def lookup(self, oid: str | Sequence[int]) -> OidMatch:
        """Find the closest known object for *oid*."""
        return self._registry.lookup_oid(oid)

    def resolve_type(self, module: str, type_name: str) -> MibTypeRecord | None:
        """Resolve a local or imported textual convention."""
        return self._registry.resolve_type(module, type_name)

    def resolve_node(self, module: str, symbol: str) -> MibNode | None:
        """Resolve an exact object or notification record."""
        return self._registry.resolve_node(module, symbol)

    def iter_objects(
        self,
        *,
        module: str | None = None,
        type_filter: str | None = None,
    ) -> Iterator[MibNode]:
        """Iterate over object nodes, optionally filtered by module and object_type."""
        for mod_name, mod_record in self._registry.modules.items():
            if module is not None and mod_name != module:
                continue
            for node in mod_record.objects.values():
                if type_filter is not None and node.object_type != type_filter:
                    continue
                yield node

    def iter_notifications(
        self,
        *,
        module: str | None = None,
    ) -> Iterator[MibNode]:
        """Iterate over notification nodes, optionally filtered by module."""
        for mod_name, mod_record in self._registry.modules.items():
            if module is not None and mod_name != module:
                continue
            yield from mod_record.notifications.values()

    def search(
        self,
        query: str,
        *,
        module: str | None = None,
        type_filter: str | None = None,
        limit: int = 100,
    ) -> list[MibNode]:
        """Case-insensitive substring search over node names and descriptions."""
        needle = query.lower()
        results: list[MibNode] = []
        for mod_name, mod_record in self._registry.modules.items():
            if module is not None and mod_name != module:
                continue
            candidates: list[MibNode] = []
            if type_filter != "NOTIFICATION-TYPE":
                candidates.extend(mod_record.objects.values())
            if type_filter != "OBJECT-TYPE":
                candidates.extend(mod_record.notifications.values())
            for node in candidates:
                if type_filter is not None and node.object_type != type_filter:
                    continue
                name_match = needle in node.name.lower()
                desc_match = node.description is not None and needle in node.description.lower()
                if name_match or desc_match:
                    results.append(node)
                    if len(results) >= limit:
                        return results
        return results
