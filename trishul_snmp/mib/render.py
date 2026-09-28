"""Basic post-response enrichment helpers."""

from __future__ import annotations

from collections.abc import Mapping

from trishul_snmp.errors import UnknownOidError
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.mib.models import MibNode
from trishul_snmp.types import (
    IntegerValue,
    ObjectIdentifierValue,
    OctetStringValue,
    OidMatch,
    VarBind,
)


def enrich_varbinds(bundle: MibBundle | None, varbinds: tuple[VarBind, ...]) -> tuple[VarBind, ...]:
    """Attach symbolic names and value metadata when a bundle is available."""
    if bundle is None:
        return tuple(
            VarBind(
                oid=varbind.oid,
                value=varbind.value,
                display_name=None,
                display_value=varbind.value.to_display_string(),
            )
            for varbind in varbinds
        )

    enriched: list[VarBind] = []
    for varbind in varbinds:
        try:
            match = bundle.lookup(varbind.oid)
        except UnknownOidError:
            match = None
        metadata = bundle.lookup_metadata(varbind.oid) if match is not None else None
        enum_label = (
            _resolve_enum_label(bundle, match, value=varbind.value.value)
            if isinstance(varbind.value, IntegerValue) and match is not None
            else None
        )
        enriched.append(
            VarBind(
                oid=varbind.oid,
                value=varbind.value,
                match=match,
                display_name=_render_name(bundle, match=match),
                display_value=_render_value(
                    bundle,
                    varbind,
                    match=match,
                    enum_label=enum_label,
                ),
                enum_label=enum_label,
                units=metadata.units if metadata is not None else None,
            )
        )
    return tuple(enriched)


def _render_name(bundle: MibBundle, *, match: OidMatch | None) -> str | None:
    if match is None:
        return None
    return bundle.display_symbolic_from_match(match)


def _render_value(
    bundle: MibBundle,
    varbind: VarBind,
    *,
    match: OidMatch | None,
    enum_label: str | None,
) -> str:
    if isinstance(varbind.value, ObjectIdentifierValue):
        try:
            return bundle.translate(varbind.value.value)
        except UnknownOidError:
            return varbind.value.to_display_string()

    if isinstance(varbind.value, IntegerValue) and enum_label is not None:
        return f"{enum_label}({varbind.value.value})"

    if isinstance(varbind.value, OctetStringValue) and match is not None:
        bits = _resolve_bits_labels(bundle, match, value=varbind.value.value)
        if bits:
            return " ".join(f"{label}({bit})" for label, bit in bits)

    return varbind.value.to_display_string()


def _resolve_enum_label(bundle: MibBundle, match: OidMatch, *, value: int) -> str | None:
    node = _resolve_node(bundle, match)
    if node is None:
        return None

    if node.enums is not None:
        label = _enum_label_from_map(node.enums, value=value)
        if label is not None:
            return label

    label = _enum_label_from_constraints(node.constraints, value=value)
    if label is not None:
        return label

    if node.syntax is None:
        return None
    type_record = bundle.resolve_type(match.module, node.syntax)
    if type_record is None:
        return None
    return _enum_label_from_constraints(type_record.constraints, value=value)


def _enum_label_from_map(
    enum_map: Mapping[str, int] | None,
    *,
    value: int,
) -> str | None:
    """Resolve the label for *value* from a label→number map (the enums field)."""
    if enum_map is None:
        return None
    for label, number in enum_map.items():
        if number == value:
            return label
    return None


def _resolve_bits_labels(
    bundle: MibBundle,
    match: OidMatch,
    *,
    value: bytes,
) -> list[tuple[str, int]] | None:
    """Return (label, bit) pairs for set bits when *match* owns a BITS object.

    BITS octet strings encode bit 0 as the most significant bit of the first
    byte. Returns None when the object is not a BITS object, so non-BITS
    octet strings keep their existing raw rendering.
    """
    node = _resolve_node(bundle, match)
    if node is None:
        return None
    enum_map = _bits_enum_map(bundle, match, node)
    if not enum_map:
        return None

    labels: list[tuple[str, int]] = []
    for byte_index, byte in enumerate(value):
        for bit in range(8):
            if byte & (1 << (7 - bit)):
                bit_number = byte_index * 8 + bit
                label = _enum_label_from_map(enum_map, value=bit_number)
                if label is not None:
                    labels.append((label, bit_number))
    return labels


def _bits_enum_map(
    bundle: MibBundle,
    match: OidMatch,
    node: MibNode,
) -> Mapping[str, int] | None:
    """Resolve the label→bit map for a BITS object, from the enums field or constraints."""
    if node.enums is not None and _is_bits_node(bundle, match, node):
        return node.enums
    if _constraint_kind(node.constraints) == "bits":
        return _constraint_enum_map(node.constraints)
    if node.syntax is None:
        return None
    type_record = bundle.resolve_type(match.module, node.syntax)
    if type_record is not None and _constraint_kind(type_record.constraints) == "bits":
        return _constraint_enum_map(type_record.constraints)
    return None


def _is_bits_node(bundle: MibBundle, match: OidMatch, node: MibNode) -> bool:
    if node.syntax == "BITS" or _constraint_kind(node.constraints) == "bits":
        return True
    if node.syntax is None:
        return False
    type_record = bundle.resolve_type(match.module, node.syntax)
    return type_record is not None and (
        type_record.base_type == "BITS" or _constraint_kind(type_record.constraints) == "bits"
    )


def _constraint_kind(constraints: Mapping[str, object] | None) -> str | None:
    if constraints is None:
        return None
    kind = constraints.get("kind")
    return kind if isinstance(kind, str) else None


def _constraint_enum_map(constraints: Mapping[str, object] | None) -> Mapping[str, int] | None:
    """Build a label→number map from enum/bits constraint data (older bundles)."""
    if _constraint_kind(constraints) not in ("enum", "bits"):
        return None
    data = constraints.get("data") if constraints is not None else None
    if not isinstance(data, list):
        return None

    result: dict[str, int] = {}
    for item in data:
        if (
            isinstance(item, list)
            and len(item) == 2
            and isinstance(item[0], str)
            and isinstance(item[1], int)
        ):
            result[item[0]] = item[1]
    return result or None


def _resolve_node(bundle: MibBundle, match: OidMatch) -> MibNode | None:
    module_record = bundle.modules.get(match.module)
    if module_record is None:
        return None
    return module_record.objects.get(match.symbol) or module_record.notifications.get(match.symbol)


def _enum_label_from_constraints(
    constraints: Mapping[str, object] | None,
    *,
    value: int,
) -> str | None:
    if constraints is None:
        return None

    kind = constraints.get("kind")
    data = constraints.get("data")
    if kind != "enum" or not isinstance(data, list):
        return None

    for item in data:
        if (
            isinstance(item, list)
            and len(item) == 2
            and isinstance(item[0], str)
            and isinstance(item[1], int)
            and item[1] == value
        ):
            return item[0]
    return None
