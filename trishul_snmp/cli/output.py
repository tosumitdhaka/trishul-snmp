"""CLI output formatting helpers."""

from __future__ import annotations

import json

from trishul_snmp.notify.events import NotificationEvent, NotificationMemberBinding
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


def render_request_id(request_id: int, *, json_output: bool) -> str:
    """Render a request identifier for trap-style CLI commands."""
    if json_output:
        return json.dumps({"request_id": request_id}, indent=2)
    return f"request_id={request_id}"


def render_notification_event(
    event: NotificationEvent,
    *,
    json_output: bool,
    numeric: bool,
    compact: bool = False,
) -> str:
    """Render a decoded notification event."""
    if json_output:
        if compact:
            return json.dumps(_notification_payload(event), separators=(",", ":"))
        return json.dumps(_notification_payload(event), indent=2)

    header = [f"type={event.pdu_type}", f"request_id={event.request_id}"]
    if event.community is not None:
        header.append(f"community={event.community}")
    elif event.username is not None:
        header.append(f"user={event.username}")
        if event.security_level is not None:
            header.append(f"level={event.security_level}")
    if event.source_address is not None:
        header.append(f"source={event.source_host}:{event.source_port}")

    lines = [" ".join(header)]
    detail_line = _notification_detail_line(event, numeric=numeric)
    if detail_line is not None:
        lines.append(detail_line)
    if event.notification_description is not None:
        lines.append(event.notification_description)
    lines.extend(_render_varbind_text(varbind, numeric=numeric) for varbind in event.varbinds)
    return "\n".join(lines)


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


def _notification_payload(event: NotificationEvent) -> dict[str, object]:
    payload: dict[str, object] = {
        "request_id": event.request_id,
        "community": event.community,
        "pdu_type": event.pdu_type,
        "varbinds": [_varbind_payload(varbind) for varbind in event.varbinds],
        "member_bindings": [_member_binding_payload(binding) for binding in event.member_bindings],
    }
    if event.source_address is not None:
        payload["source_address"] = {
            "host": event.source_host,
            "port": event.source_port,
        }
    if event.notification_oid is not None:
        payload["notification_oid"] = ".".join(str(arc) for arc in event.notification_oid)
    if event.notification_name is not None:
        payload["notification_name"] = event.notification_name
    if event.notification_description is not None:
        payload["notification_description"] = event.notification_description
    if event.uptime is not None:
        payload["uptime"] = event.uptime
    if event.snmp_version is not None:
        payload["snmp_version"] = event.snmp_version
    if event.username is not None:
        payload["username"] = event.username
    if event.security_level is not None:
        payload["security_level"] = event.security_level
    if event.context_engine_id is not None:
        payload["context_engine_id"] = event.context_engine_id.hex()
    if event.context_name is not None:
        payload["context_name"] = event.context_name.hex()
    if event.authoritative_engine_id is not None:
        payload["authoritative_engine_id"] = event.authoritative_engine_id.hex()
    if event.authoritative_engine_boots is not None:
        payload["authoritative_engine_boots"] = event.authoritative_engine_boots
    if event.authoritative_engine_time is not None:
        payload["authoritative_engine_time"] = event.authoritative_engine_time
    return payload


def _member_binding_payload(binding: NotificationMemberBinding) -> dict[str, object]:
    return {
        "member": binding.symbolic,
        "varbind": None if binding.varbind is None else _varbind_payload(binding.varbind),
    }


def _notification_detail_line(event: NotificationEvent, *, numeric: bool) -> str | None:
    notification = _notification_label(event, numeric=numeric)
    details: list[str] = []
    if notification is not None:
        details.append(f"notification={notification}")
    if event.uptime is not None:
        details.append(f"uptime={event.uptime}")
    if not details:
        return None
    return " ".join(details)


def _notification_label(event: NotificationEvent, *, numeric: bool) -> str | None:
    if numeric:
        if event.notification_oid is None:
            return None
        return ".".join(str(arc) for arc in event.notification_oid)

    if event.notification_name is not None:
        return event.notification_name
    if event.notification_oid is None:
        return None
    return ".".join(str(arc) for arc in event.notification_oid)
