"""Helpers for manager request and response shaping."""

from __future__ import annotations

from trishul_snmp._runtime import normalize_targets as normalize_targets
from trishul_snmp._runtime import response_from_pdu as response_from_pdu
from trishul_snmp.types import OID
from trishul_snmp.wire.pdu import RawVarBind, build_null_varbinds

__all__ = ["normalize_targets", "build_request_varbinds", "response_from_pdu"]


def build_request_varbinds(oids: tuple[OID, ...]) -> tuple[RawVarBind, ...]:
    """Build request varbinds using NULL placeholders."""
    return build_null_varbinds(oids)
