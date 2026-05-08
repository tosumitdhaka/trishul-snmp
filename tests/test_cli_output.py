from __future__ import annotations

import json

from trishul_snmp.cli.output import (
    render_notification_event,
    render_request_id,
    render_response,
    render_walk,
)
from trishul_snmp.mib.models import MibMemberRef
from trishul_snmp.notify.events import NotificationEvent, NotificationMemberBinding
from trishul_snmp.types import ErrorStatus, IntegerValue, Response, VarBind


def _varbind(
    oid: tuple[int, ...],
    *,
    display_name: str | None = None,
    display_value: str | None = None,
) -> VarBind:
    return VarBind(
        oid=oid,
        value=IntegerValue(7),
        display_name=display_name,
        display_value=display_value,
    )


def test_render_response_includes_error_status_line() -> None:
    response = Response(
        request_id=99,
        error_status=ErrorStatus.GEN_ERR,
        error_index=2,
        varbinds=(_varbind((1, 3, 6, 1, 2, 1, 1, 3, 0), display_name="SNMPv2-MIB::sysUpTime.0"),),
    )

    rendered = render_response(response, json_output=False, numeric=False)

    assert rendered.splitlines() == [
        "error_status=gen_err error_index=2",
        "SNMPv2-MIB::sysUpTime.0 = 7",
    ]


def test_render_walk_json_output() -> None:
    rendered = render_walk(
        (_varbind((1, 3, 6, 1, 2, 1, 2, 2, 1, 1), display_name="IF-MIB::ifIndex.1"),),
        json_output=True,
        numeric=False,
    )

    payload = json.loads(rendered)
    assert payload == {
        "varbinds": [
            {
                "oid": "1.3.6.1.2.1.2.2.1.1",
                "value_type": "integer",
                "display_name": "IF-MIB::ifIndex.1",
                "display_value": "7",
            }
        ]
    }


def test_render_request_id_json_output() -> None:
    rendered = render_request_id(17, json_output=True)

    assert json.loads(rendered) == {"request_id": 17}


def test_render_notification_event_text_and_json() -> None:
    event = NotificationEvent(
        request_id=9,
        community="public",
        source_address=("127.0.0.1", 40162),
        pdu_type="snmpv2-trap",
        varbinds=(
            _varbind(
                (1, 3, 6, 1, 4, 1, 99999, 1, 0),
                display_name="APP-MIB::status.0",
                display_value="7",
            ),
        ),
        notification_oid=(1, 3, 6, 1, 4, 1, 99999, 10),
        notification_name="APP-MIB::statusNotice",
        notification_description="Status changed.",
        uptime=55,
        member_bindings=(
            NotificationMemberBinding(
                member=MibMemberRef(module="APP-MIB", object="status"),
                varbind=_varbind(
                    (1, 3, 6, 1, 4, 1, 99999, 1, 0),
                    display_name="APP-MIB::status.0",
                    display_value="7",
                ),
            ),
        ),
    )

    rendered_text = render_notification_event(event, json_output=False, numeric=False)
    rendered_json = render_notification_event(event, json_output=True, numeric=False)

    assert rendered_text.splitlines() == [
        "type=snmpv2-trap request_id=9 community=public source=127.0.0.1:40162",
        "notification=APP-MIB::statusNotice uptime=55",
        "Status changed.",
        "APP-MIB::status.0 = 7",
    ]

    assert json.loads(rendered_json) == {
        "request_id": 9,
        "community": "public",
        "pdu_type": "snmpv2-trap",
        "source_address": {"host": "127.0.0.1", "port": 40162},
        "notification_oid": "1.3.6.1.4.1.99999.10",
        "notification_name": "APP-MIB::statusNotice",
        "notification_description": "Status changed.",
        "uptime": 55,
        "member_bindings": [
            {
                "member": "APP-MIB::status",
                "varbind": {
                    "oid": "1.3.6.1.4.1.99999.1.0",
                    "value_type": "integer",
                    "display_name": "APP-MIB::status.0",
                    "display_value": "7",
                },
            }
        ],
        "varbinds": [
            {
                "oid": "1.3.6.1.4.1.99999.1.0",
                "value_type": "integer",
                "display_name": "APP-MIB::status.0",
                "display_value": "7",
            }
        ],
    }


def test_render_notification_event_handles_compact_json_and_fallback_labels() -> None:
    event = NotificationEvent(
        request_id=4,
        community="public",
        source_address=None,
        pdu_type="inform-request",
        varbinds=(),
        notification_oid=(1, 3, 6, 1, 4, 1, 99999, 10),
        notification_name=None,
        notification_description=None,
        uptime=None,
        member_bindings=(
            NotificationMemberBinding(
                member=MibMemberRef(module="APP-MIB", object="status"),
                varbind=None,
            ),
        ),
    )

    rendered_text = render_notification_event(event, json_output=False, numeric=False)
    rendered_compact = render_notification_event(
        event,
        json_output=True,
        numeric=False,
        compact=True,
    )

    assert rendered_text.splitlines() == [
        "type=inform-request request_id=4 community=public",
        "notification=1.3.6.1.4.1.99999.10",
    ]
    assert "\n" not in rendered_compact
    assert json.loads(rendered_compact)["member_bindings"] == [
        {"member": "APP-MIB::status", "varbind": None}
    ]


def test_render_notification_event_omits_detail_line_when_no_notification_or_uptime() -> None:
    event = NotificationEvent(
        request_id=5,
        community="public",
        source_address=None,
        pdu_type="snmpv2-trap",
        varbinds=(),
    )

    rendered_numeric = render_notification_event(event, json_output=False, numeric=True)
    rendered_symbolic = render_notification_event(event, json_output=False, numeric=False)

    assert rendered_numeric == "type=snmpv2-trap request_id=5 community=public"
    assert rendered_symbolic == "type=snmpv2-trap request_id=5 community=public"
