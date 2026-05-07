"""Helpers for manager request and response shaping."""

from __future__ import annotations

from collections.abc import Sequence

from trishul_snmp.errors import UnknownSymbolError
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.mib.registry import is_numeric_oid_text, parse_oid
from trishul_snmp.mib.render import enrich_varbinds
from trishul_snmp.types import OID, NullValue, Response, VarBind
from trishul_snmp.wire.pdu import Pdu, RawVarBind, response_error_status


def normalize_targets(
    targets: tuple[str | Sequence[int], ...],
    *,
    bundle: MibBundle | None,
) -> tuple[OID, ...]:
    """Normalize symbolic or numeric targets to numeric OIDs."""
    if not targets:
        raise ValueError("At least one target is required")

    normalized: list[OID] = []
    for target in targets:
        if isinstance(target, str):
            stripped = target.strip()
            if "::" in stripped:
                if bundle is None:
                    raise UnknownSymbolError(f"Symbolic target requires a loaded bundle: {target}")
                normalized.append(bundle.resolve(stripped))
                continue
            if is_numeric_oid_text(stripped):
                normalized.append(parse_oid(stripped))
                continue
            raise UnknownSymbolError(f"Unrecognized target format: {target}")
        normalized.append(parse_oid(target))
    return tuple(normalized)


def build_request_varbinds(oids: tuple[OID, ...]) -> tuple[RawVarBind, ...]:
    """Build request varbinds using NULL placeholders."""
    return tuple(RawVarBind(oid=oid, value=NullValue()) for oid in oids)


def response_from_pdu(pdu: Pdu, *, bundle: MibBundle | None) -> Response:
    """Convert a low-level PDU to the public Response model."""
    varbinds = tuple(VarBind(oid=vb.oid, value=vb.value) for vb in pdu.varbinds)
    enriched = enrich_varbinds(bundle, varbinds)
    return Response(
        request_id=pdu.request_id,
        error_status=response_error_status(pdu.error_status),
        error_index=pdu.error_index,
        varbinds=enriched,
    )
