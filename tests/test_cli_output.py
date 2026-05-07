from __future__ import annotations

import json

from trishul_snmp.cli.output import render_response, render_walk
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
