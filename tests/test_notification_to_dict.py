from __future__ import annotations

import json
from pathlib import Path

from trishul_snmp import IntegerValue, ObjectIdentifierValue, TimeTicksValue, load_bundle
from trishul_snmp.notify.events import decode_notification, notification_event_from_message
from trishul_snmp.security.usm import AuthProtocol, UsmLocalEngine, UsmModel, UsmUser
from trishul_snmp.wire.message import SnmpMessage
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind


def _write_json(path: Path, payload: dict[object, object]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _base_module(*, module: str) -> dict[object, object]:
    return {
        "module": module,
        "language": "SMIv2",
        "generated_by": "trishul-smi",
        "generated_at": "2026-05-06T12:00:00Z",
        "imports": {},
        "objects": {},
        "types": {},
        "notifications": {},
        "module_metadata": {"lastupdated": None, "revisions": []},
    }


def _notification_payload() -> dict[object, object]:
    payload = _base_module(module="NOTIF-MIB")
    payload["objects"] = {
        "ifIndex": {
            "oid": "1.3.6.1.2.1.2.2.1.1",
            "oid_path": [1, 3, 6, 1, 2, 1, 2, 2, 1, 1],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "column",
            "syntax": "Integer32",
            "max_access": "read-only",
            "status": "current",
        }
    }
    payload["notifications"] = {
        "linkDown": {
            "oid": "1.3.6.1.6.3.1.1.5.3",
            "oid_path": [1, 3, 6, 1, 6, 3, 1, 1, 5, 3],
            "object_type": "NOTIFICATION-TYPE",
            "class": "notificationtype",
            "status": "current",
            "description": "A linkDown notification.",
            "members": [{"module": "NOTIF-MIB", "object": "ifIndex"}],
        }
    }
    return payload


def _make_trap_message() -> SnmpMessage:
    return SnmpMessage(
        version=1,
        community="public",
        pdu=Pdu(
            pdu_type=PduType.SNMPV2_TRAP,
            request_id=42,
            error_status=0,
            error_index=0,
            varbinds=(
                RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=TimeTicksValue(123)),
                RawVarBind(
                    oid=(1, 3, 6, 1, 6, 3, 1, 1, 4, 1, 0),
                    value=ObjectIdentifierValue((1, 3, 6, 1, 6, 3, 1, 1, 5, 3)),
                ),
                RawVarBind(oid=(1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 7), value=IntegerValue(7)),
            ),
        ),
    )


def test_to_dict_is_json_serializable_without_bundle() -> None:
    message = _make_trap_message()
    event = notification_event_from_message(
        message,
        source_address=("10.0.0.1", 12345),
        bundle=None,
    )
    d = event.to_dict()

    # Must round-trip through JSON without error
    json.dumps(d)

    assert d["request_id"] == 42
    assert d["community"] == "public"
    assert d["source_host"] == "10.0.0.1"
    assert d["source_port"] == 12345
    assert d["pdu_type"] == "snmpv2-trap"
    assert d["notification_oid"] == "1.3.6.1.6.3.1.1.5.3"
    assert d["notification_name"] is None
    assert d["uptime"] == 123
    assert len(d["varbinds"]) == 3
    assert d["member_bindings"] == []


def test_to_dict_includes_notification_metadata_with_bundle(tmp_path: Path) -> None:
    _write_json(tmp_path / "NOTIF-MIB.json", _notification_payload())
    bundle = load_bundle(tmp_path / "NOTIF-MIB.json")

    message = _make_trap_message()
    event = notification_event_from_message(
        message,
        source_address=("192.168.1.1", 161),
        bundle=bundle,
    )
    d = event.to_dict()

    json.dumps(d)

    assert d["notification_oid"] == "1.3.6.1.6.3.1.1.5.3"
    assert d["notification_name"] == "NOTIF-MIB::linkDown"
    assert d["notification_description"] == "A linkDown notification."
    assert d["uptime"] == 123

    assert len(d["member_bindings"]) == 1
    mb = d["member_bindings"][0]
    assert mb["symbolic"] == "NOTIF-MIB::ifIndex"
    assert mb["oid"] == "1.3.6.1.2.1.2.2.1.1.7"
    assert mb["value_type"] == "integer"
    assert mb["value"] == "7"


def test_to_dict_varbind_fields(tmp_path: Path) -> None:
    _write_json(tmp_path / "NOTIF-MIB.json", _notification_payload())
    bundle = load_bundle(tmp_path / "NOTIF-MIB.json")

    message = _make_trap_message()
    event = notification_event_from_message(
        message,
        source_address=None,
        bundle=bundle,
    )
    d = event.to_dict()

    assert d["source_host"] is None
    assert d["source_port"] is None

    uptime_vb = d["varbinds"][0]
    assert uptime_vb["oid"] == "1.3.6.1.2.1.1.3.0"
    assert uptime_vb["value_type"] == "timeticks"
    assert uptime_vb["value"] == "123"


def test_to_dict_with_no_source_address() -> None:
    message = SnmpMessage(
        version=1,
        community="mgmt",
        pdu=Pdu(
            pdu_type=PduType.SNMPV2_TRAP,
            request_id=1,
            error_status=0,
            error_index=0,
            varbinds=(),
        ),
    )
    event = notification_event_from_message(message, source_address=None, bundle=None)
    d = event.to_dict()

    assert d["source_host"] is None
    assert d["source_port"] is None
    assert d["varbinds"] == []
    assert d["member_bindings"] == []
    json.dumps(d)


def test_to_dict_v3_fields_are_json_safe() -> None:
    user = UsmUser(username="notify", auth_protocol=AuthProtocol.NONE)
    engine = UsmLocalEngine(
        engine_id=b"\x80\x00\x01\x02\x03" + b"\x44" * 12,
        engine_boots=9,
        engine_time=321,
    )
    model = UsmModel(user=user, context_name=b"alerts", local_engine=engine)
    raw = model.wrap_pdu(
        Pdu(
            pdu_type=PduType.SNMPV2_TRAP,
            request_id=77,
            error_status=0,
            error_index=0,
            varbinds=(),
        )
    )

    d = decode_notification(raw, user=user, source_address=("10.0.0.2", 40162)).to_dict()

    json.dumps(d)
    assert d["community"] is None
    assert d["snmp_version"] == "3"
    assert d["username"] == "notify"
    assert d["security_level"] == "noAuthNoPriv"
    assert d["context_engine_id"] == engine.engine_id.hex()
    assert d["context_name"] == b"alerts".hex()
    assert d["authoritative_engine_id"] == engine.engine_id.hex()
    assert d["authoritative_engine_boots"] == 9
    assert d["authoritative_engine_time"] == 321
