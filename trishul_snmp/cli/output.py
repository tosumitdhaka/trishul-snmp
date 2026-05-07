"""CLI output formatting helpers."""

from __future__ import annotations

import json

from trishul_snmp.types import ErrorStatus, Response, VarBind


def render_translation(result: str) -> str:
    """Render a translated OID or symbol."""
    return result


def render_response(response: Response, *, json_output: bool, numeric: bool) -> str:
    """Render an SNMP response for CLI output."""
    if json_output:
        return json.dumps(_response_payload(response), indent=2)

    lines: list[str] = []
    if response.error_status is not ErrorStatus.NO_ERROR:
        lines.append(
            f"error_status={response.error_status.label} error_index={response.error_index}"
        )
    lines.extend(_render_varbind_text(varbind, numeric=numeric) for varbind in response.varbinds)
    return "\n".join(lines)


def render_walk(varbinds: tuple[VarBind, ...], *, json_output: bool, numeric: bool) -> str:
    """Render walked varbinds for CLI output."""
    if json_output:
        payload = {"varbinds": [_varbind_payload(varbind) for varbind in varbinds]}
        return json.dumps(payload, indent=2)
    return "\n".join(_render_varbind_text(varbind, numeric=numeric) for varbind in varbinds)


def _render_varbind_text(varbind: VarBind, *, numeric: bool) -> str:
    name = varbind.oid_str if numeric or varbind.display_name is None else varbind.display_name
    value = varbind.display_value or varbind.value.to_display_string()
    return f"{name} = {value}"


def _response_payload(response: Response) -> dict[str, object]:
    return {
        "request_id": response.request_id,
        "error_status": response.error_status.label,
        "error_status_code": int(response.error_status),
        "error_index": response.error_index,
        "varbinds": [_varbind_payload(varbind) for varbind in response.varbinds],
    }


def _varbind_payload(varbind: VarBind) -> dict[str, object]:
    payload: dict[str, object] = {
        "oid": varbind.oid_str,
        "value_type": varbind.value_type,
        "display_value": varbind.display_value or varbind.value.to_display_string(),
    }
    if varbind.display_name is not None:
        payload["display_name"] = varbind.display_name
    return payload
