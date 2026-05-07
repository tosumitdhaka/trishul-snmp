"""Normalized internal MIB models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from trishul_snmp.types import OID


@dataclass(frozen=True, slots=True)
class MibNode:
    """Normalized object or notification record."""

    module: str
    name: str
    oid: OID
    class_name: str
    object_type: str
    nodetype: str | None
    syntax: str | None
    max_access: str | None
    status: str | None
    index: tuple[str, ...] | None
    augments: str | None
    constraints: Mapping[str, Any] | None

    @property
    def symbolic(self) -> str:
        return f"{self.module}::{self.name}"


@dataclass(frozen=True, slots=True)
class MibTypeRecord:
    """Normalized textual-convention record."""

    module: str
    name: str
    class_name: str
    base_type: str | None
    display_hint: str | None
    status: str | None
    constraints: Mapping[str, Any] | None


@dataclass(frozen=True, slots=True)
class MibModuleRecord:
    """Normalized module payload."""

    module: str
    language: str | None
    generated_by: str
    generated_at: str | None
    schema_version: str | None
    producer_version: str | None
    imports: Mapping[str, tuple[str, ...]]
    objects: Mapping[str, MibNode]
    notifications: Mapping[str, MibNode]
    types: Mapping[str, MibTypeRecord]
    module_metadata: Mapping[str, Any]

    def iter_nodes(self) -> tuple[MibNode, ...]:
        return tuple(self.objects.values()) + tuple(self.notifications.values())
