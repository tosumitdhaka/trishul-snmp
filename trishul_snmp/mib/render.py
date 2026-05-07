"""Basic post-response enrichment helpers."""

from __future__ import annotations

from collections.abc import Mapping

from trishul_snmp.errors import UnknownOidError
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.mib.models import MibNode
from trishul_snmp.types import IntegerValue, ObjectIdentifierValue, OidMatch, VarBind


def enrich_varbinds(bundle: MibBundle | None, varbinds: tuple[VarBind, ...]) -> tuple[VarBind, ...]:
    """Attach symbolic names when a bundle is available."""
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
        enriched.append(
            VarBind(
                oid=varbind.oid,
                value=varbind.value,
                match=match,
                display_name=_render_name(bundle, match=match),
                display_value=_render_value(bundle, varbind, match=match),
            )
        )
    return tuple(enriched)


def _render_name(bundle: MibBundle, *, match: OidMatch | None) -> str | None:
    if match is None:
        return None
    return bundle.display_symbolic_from_match(match)


def _render_value(bundle: MibBundle, varbind: VarBind, *, match: OidMatch | None) -> str:
    if isinstance(varbind.value, ObjectIdentifierValue):
        try:
            return bundle.translate(varbind.value.value)
        except UnknownOidError:
            return varbind.value.to_display_string()

    if isinstance(varbind.value, IntegerValue) and match is not None:
        enum_label = _resolve_enum_label(bundle, match, value=varbind.value.value)
        if enum_label is not None:
            return f"{enum_label}({varbind.value.value})"

    return varbind.value.to_display_string()


def _resolve_enum_label(bundle: MibBundle, match: OidMatch, *, value: int) -> str | None:
    node = _resolve_node(bundle, match)
    if node is None:
        return None

    label = _enum_label_from_constraints(node.constraints, value=value)
    if label is not None:
        return label

    if node.syntax is None:
        return None
    type_record = bundle.resolve_type(match.module, node.syntax)
    if type_record is None:
        return None
    return _enum_label_from_constraints(type_record.constraints, value=value)


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
