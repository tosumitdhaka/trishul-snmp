"""Registry and translation helpers for loaded MIB artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from trishul_snmp.errors import (
    BundleValidationError,
    InvalidOidError,
    TranslationError,
    UnknownOidError,
    UnknownSymbolError,
)
from trishul_snmp.mib.models import MibMemberRef, MibModuleRecord, MibNode, MibTypeRecord
from trishul_snmp.types import OID, OidMatch

_SUPPORTED_PRODUCER = "trishul-smi"


def oid_to_string(oid: OID) -> str:
    return ".".join(str(arc) for arc in oid)


def parse_oid(value: str | Sequence[int]) -> OID:
    """Normalize dotted string or numeric sequence to an OID tuple."""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise InvalidOidError("OID cannot be empty")
        text = text.lstrip(".")
        if not text:
            raise InvalidOidError("OID cannot be empty")
        parts = text.split(".")
        try:
            oid = tuple(int(part) for part in parts)
        except ValueError as exc:
            raise InvalidOidError(f"OID contains a non-numeric arc: {value}") from exc
        if any(arc < 0 for arc in oid):
            raise InvalidOidError(f"OID contains a negative arc: {value}")
        return oid

    oid = tuple(value)
    if not oid:
        raise InvalidOidError("OID cannot be empty")
    if any(not isinstance(arc, int) or arc < 0 for arc in oid):
        raise InvalidOidError(f"OID contains a non-integer or negative arc: {value}")
    return oid


def is_numeric_oid_text(value: str) -> bool:
    """Return True when *value* is a dotted numeric OID."""
    text = value.strip().lstrip(".")
    return bool(text) and all(part.isdigit() for part in text.split("."))


def parse_symbolic_target(target: str) -> tuple[str, str, OID]:
    """Split MODULE::symbol[.suffix] into module, symbol, and numeric suffix."""
    module, sep, remainder = target.partition("::")
    if not sep or not module or not remainder:
        raise UnknownSymbolError(f"Symbolic target must use MODULE::symbol form: {target}")

    if "." not in remainder:
        return module, remainder, ()

    symbol, suffix = remainder.split(".", 1)
    if not symbol:
        raise UnknownSymbolError(f"Symbolic target is missing an object name: {target}")
    if not suffix or not is_numeric_oid_text(suffix):
        raise UnknownSymbolError(
            f"Only numeric instance suffixes are supported in symbolic targets: {target}"
        )
    return module, symbol, parse_oid(suffix)


@dataclass(frozen=True, slots=True)
class _OidIndexEntry:
    module: str
    symbol: str


class MibRegistry:
    """In-memory indexes over loaded MIB modules."""

    def __init__(
        self,
        modules: Mapping[str, MibModuleRecord],
        *,
        oid_index: Mapping[OID, _OidIndexEntry] | None = None,
    ) -> None:
        self._modules = dict(modules)
        self._symbol_index: dict[tuple[str, str], MibNode] = {}
        self._exact_oid_index: dict[OID, MibNode] = {}
        self._type_index: dict[tuple[str, str], MibTypeRecord] = {}
        self._oid_index = dict(oid_index or {})

        for module in self._modules.values():
            for node in module.iter_nodes():
                self._symbol_index[(module.module, node.name)] = node
                self._exact_oid_index[node.oid] = node
            for type_record in module.types.values():
                self._type_index[(module.module, type_record.name)] = type_record

    @property
    def modules(self) -> Mapping[str, MibModuleRecord]:
        return self._modules

    def resolve_symbolic(self, target: str) -> OID:
        """Resolve MODULE::symbol[.suffix] to a numeric OID."""
        module, symbol, suffix = parse_symbolic_target(target)
        node = self._symbol_index.get((module, symbol))
        if node is None:
            raise UnknownSymbolError(f"Unknown symbolic target: {target}")
        return node.oid + suffix

    def lookup_oid(self, value: str | Sequence[int]) -> OidMatch:
        """Find the closest known object for *value*."""
        oid = parse_oid(value)
        node = self._lookup_exact_from_accelerator(oid)
        if node is None:
            node = self._exact_oid_index.get(oid)
        if node is not None:
            return OidMatch(
                oid=oid,
                module=node.module,
                symbol=node.name,
                matched_oid=node.oid,
                class_name=node.class_name,
                object_type=node.object_type,
                nodetype=node.nodetype,
            )

        for prefix_len in range(len(oid) - 1, 0, -1):
            prefix = oid[:prefix_len]
            node = self._lookup_exact_from_accelerator(prefix)
            if node is None:
                node = self._exact_oid_index.get(prefix)
            if node is not None:
                return OidMatch(
                    oid=oid,
                    module=node.module,
                    symbol=node.name,
                    matched_oid=node.oid,
                    suffix=oid[prefix_len:],
                    class_name=node.class_name,
                    object_type=node.object_type,
                    nodetype=node.nodetype,
                )

        raise UnknownOidError(f"Unknown numeric OID: {oid_to_string(oid)}")

    def translate(self, target: str | Sequence[int]) -> str:
        """Translate symbolic targets to numeric OIDs and vice versa."""
        if isinstance(target, str) and not target.strip():
            raise TranslationError("Translation target cannot be empty")

        if isinstance(target, str) and not is_numeric_oid_text(target) and "::" in target:
            return oid_to_string(self.resolve_symbolic(target))

        return self.display_symbolic(target)

    def display_symbolic(self, value: str | Sequence[int]) -> str:
        """Render a numeric OID using user-facing symbolic display policy."""
        match = self.lookup_oid(value)
        return self.display_symbolic_from_match(match)

    def display_symbolic_from_match(self, match: OidMatch) -> str:
        """Render *match* using user-facing symbolic display policy."""
        return self._display_match(match).symbolic

    def resolve_type(self, module: str, type_name: str) -> MibTypeRecord | None:
        """Return a type record from the local module or imported modules."""
        direct = self._type_index.get((module, type_name))
        if direct is not None:
            return direct

        module_record = self._modules.get(module)
        if module_record is None:
            return None

        for imported_module, names in module_record.imports.items():
            if type_name in names:
                return self._type_index.get((imported_module, type_name))
        return None

    def resolve_node(self, module: str, symbol: str) -> MibNode | None:
        """Return an object or notification node by exact module/symbol."""
        return self._symbol_index.get((module, symbol))

    def _lookup_exact_from_accelerator(self, oid: OID) -> MibNode | None:
        entry = self._oid_index.get(oid)
        if entry is None:
            return None
        return self._symbol_index.get((entry.module, entry.symbol))

    def _display_match(self, match: OidMatch) -> OidMatch:
        if (
            match.suffix
            or match.object_type != "OBJECT IDENTIFIER"
            or not match.oid
            or match.oid[-1] != 0
        ):
            return match

        parent = self._exact_oid_index.get(match.oid[:-1])
        if parent is None or parent.object_type != "OBJECT-TYPE" or parent.nodetype != "scalar":
            return match

        return OidMatch(
            oid=match.oid,
            module=parent.module,
            symbol=parent.name,
            matched_oid=parent.oid,
            suffix=(0,),
            class_name=parent.class_name,
            object_type=parent.object_type,
            nodetype=parent.nodetype,
        )


def validate_module_record(module: MibModuleRecord, *, path: Path) -> None:
    """Validate a normalized module record."""
    if module.generated_by != _SUPPORTED_PRODUCER:
        raise BundleValidationError(
            f"Unsupported JSON producer {module.generated_by!r}",
            path=path,
        )


def normalize_imports(raw_imports: object, *, path: Path) -> Mapping[str, tuple[str, ...]]:
    if not isinstance(raw_imports, dict):
        raise BundleValidationError("Module imports must be an object", path=path)

    normalized: dict[str, tuple[str, ...]] = {}
    for module, names in raw_imports.items():
        if not isinstance(module, str):
            raise BundleValidationError("Import module names must be strings", path=path)
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            raise BundleValidationError(
                f"Imported symbols for {module!r} must be a list of strings",
                path=path,
            )
        normalized[module] = tuple(names)
    return normalized


def normalize_node_map(
    raw_nodes: object,
    *,
    module_name: str,
    path: Path,
    default_nodetype: str | None = None,
) -> Mapping[str, MibNode]:
    if not isinstance(raw_nodes, dict):
        raise BundleValidationError("Node collections must be objects", path=path)

    normalized: dict[str, MibNode] = {}
    for name, raw_node in raw_nodes.items():
        if not isinstance(name, str):
            raise BundleValidationError("Node names must be strings", path=path)
        if not isinstance(raw_node, dict):
            raise BundleValidationError(f"Node {name!r} must be an object", path=path)

        oid_path = raw_node.get("oid_path")
        oid_value = raw_node.get("oid")
        oid = _normalize_node_oid(oid_path, oid_value, name=name, path=path)
        object_type = _require_string(raw_node, "object_type", name=name, path=path)
        class_name = _require_string(raw_node, "class", name=name, path=path)
        nodetype_raw = raw_node.get("nodetype")
        nodetype = nodetype_raw if isinstance(nodetype_raw, str) else default_nodetype
        index_raw = raw_node.get("index")
        if index_raw is not None:
            if not isinstance(index_raw, list) or not all(
                isinstance(item, str) for item in index_raw
            ):
                raise BundleValidationError(f"Node {name!r} has invalid index metadata", path=path)
            index = tuple(index_raw)
        else:
            index = None

        constraints = raw_node.get("constraints")
        if constraints is not None and not isinstance(constraints, dict):
            raise BundleValidationError(f"Node {name!r} constraints must be an object", path=path)

        normalized[name] = MibNode(
            module=module_name,
            name=name,
            oid=oid,
            class_name=class_name,
            object_type=object_type,
            nodetype=nodetype,
            syntax=_optional_string(raw_node.get("syntax"), field="syntax", name=name, path=path),
            max_access=_optional_string(
                raw_node.get("max_access"), field="max_access", name=name, path=path
            ),
            status=_optional_string(raw_node.get("status"), field="status", name=name, path=path),
            index=index,
            augments=_optional_string(
                raw_node.get("augments"),
                field="augments",
                name=name,
                path=path,
            ),
            description=_optional_string(
                raw_node.get("description"),
                field="description",
                name=name,
                path=path,
            ),
            members=_normalize_member_refs(raw_node.get("members"), name=name, path=path),
            constraints=constraints,
        )
    return normalized


def normalize_type_map(
    raw_types: object,
    *,
    module_name: str,
    path: Path,
) -> Mapping[str, MibTypeRecord]:
    if not isinstance(raw_types, dict):
        raise BundleValidationError("Type collections must be objects", path=path)

    normalized: dict[str, MibTypeRecord] = {}
    for name, raw_type in raw_types.items():
        if not isinstance(name, str):
            raise BundleValidationError("Type names must be strings", path=path)
        if not isinstance(raw_type, dict):
            raise BundleValidationError(f"Type {name!r} must be an object", path=path)

        constraints = raw_type.get("constraints")
        if constraints is not None and not isinstance(constraints, dict):
            raise BundleValidationError(f"Type {name!r} constraints must be an object", path=path)

        normalized[name] = MibTypeRecord(
            module=module_name,
            name=name,
            class_name=_require_string(raw_type, "class", name=name, path=path),
            base_type=_optional_string(
                raw_type.get("base_type"), field="base_type", name=name, path=path
            ),
            display_hint=_optional_string(
                raw_type.get("display_hint"), field="display_hint", name=name, path=path
            ),
            status=_optional_string(raw_type.get("status"), field="status", name=name, path=path),
            constraints=constraints,
        )
    return normalized


def _normalize_node_oid(
    oid_path: object,
    oid_value: object,
    *,
    name: str,
    path: Path,
) -> OID:
    if oid_path is not None:
        if not isinstance(oid_path, list) or not all(
            isinstance(arc, int) and arc >= 0 for arc in oid_path
        ):
            raise BundleValidationError(f"Node {name!r} has an invalid oid_path", path=path)
        oid = tuple(oid_path)
        if oid_value is not None and isinstance(oid_value, str) and parse_oid(oid_value) != oid:
            raise BundleValidationError(
                f"Node {name!r} has inconsistent oid and oid_path values",
                path=path,
            )
        return oid

    if isinstance(oid_value, str):
        return parse_oid(oid_value)

    raise BundleValidationError(f"Node {name!r} is missing both oid_path and oid", path=path)


def _require_string(raw_data: Mapping[str, object], field: str, *, name: str, path: Path) -> str:
    value = raw_data.get(field)
    if not isinstance(value, str) or not value:
        raise BundleValidationError(
            f"Node {name!r} is missing required string field {field!r}",
            path=path,
        )
    return value


def _optional_string(value: object, *, field: str, name: str, path: Path) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise BundleValidationError(f"Node {name!r} field {field!r} must be a string", path=path)
    return value


def _normalize_member_refs(
    raw_members: object,
    *,
    name: str,
    path: Path,
) -> tuple[MibMemberRef, ...] | None:
    if raw_members is None:
        return None
    if not isinstance(raw_members, list):
        raise BundleValidationError(f"Node {name!r} field 'members' must be a list", path=path)

    normalized: list[MibMemberRef] = []
    for raw_member in raw_members:
        if not isinstance(raw_member, dict):
            raise BundleValidationError(
                f"Node {name!r} members must be objects containing 'module' and 'object'",
                path=path,
            )
        module = raw_member.get("module")
        object_name = raw_member.get("object")
        if (
            not isinstance(module, str)
            or not module
            or not isinstance(object_name, str)
            or not object_name
        ):
            raise BundleValidationError(
                f"Node {name!r} members must contain string 'module' and 'object' fields",
                path=path,
            )
        normalized.append(MibMemberRef(module=module, object=object_name))
    return tuple(normalized)


def normalize_module_metadata(raw_metadata: object, *, path: Path) -> Mapping[str, object]:
    if raw_metadata is None:
        return {}
    if not isinstance(raw_metadata, dict):
        raise BundleValidationError("Module metadata must be an object", path=path)
    if not all(isinstance(key, str) for key in raw_metadata):
        raise BundleValidationError("Module metadata keys must be strings", path=path)
    return dict(raw_metadata)


def normalize_module_payload(payload: object, *, path: Path) -> MibModuleRecord:
    """Validate and normalize a raw module payload."""
    if not isinstance(payload, dict):
        raise BundleValidationError("Module JSON must be an object", path=path)

    module_name = payload.get("module")
    generated_by = payload.get("generated_by")
    if not isinstance(module_name, str) or not module_name:
        raise BundleValidationError("Module JSON is missing a valid 'module' field", path=path)
    if not isinstance(generated_by, str) or not generated_by:
        raise BundleValidationError(
            "Module JSON is missing a valid 'generated_by' field",
            path=path,
        )

    module_record = MibModuleRecord(
        module=module_name,
        language=payload.get("language") if isinstance(payload.get("language"), str) else None,
        generated_by=generated_by,
        generated_at=(
            payload.get("generated_at") if isinstance(payload.get("generated_at"), str) else None
        ),
        schema_version=payload.get("schema_version")
        if isinstance(payload.get("schema_version"), str)
        else None,
        producer_version=payload.get("producer_version")
        if isinstance(payload.get("producer_version"), str)
        else None,
        imports=normalize_imports(payload.get("imports", {}), path=path),
        objects=normalize_node_map(payload.get("objects", {}), module_name=module_name, path=path),
        notifications=normalize_node_map(
            payload.get("notifications", {}),
            module_name=module_name,
            path=path,
            default_nodetype="notification",
        ),
        types=normalize_type_map(payload.get("types", {}), module_name=module_name, path=path),
        module_metadata=normalize_module_metadata(payload.get("module_metadata"), path=path),
    )
    validate_module_record(module_record, path=path)
    return module_record
