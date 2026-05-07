from __future__ import annotations

from trishul_snmp.types import (
    Counter32Value,
    Counter64Value,
    Gauge32Value,
    IpAddressValue,
    NoSuchInstanceValue,
    NoSuchObjectValue,
    NullValue,
    OctetStringValue,
    OpaqueValue,
    TimeTicksValue,
)


def test_octet_string_display_falls_back_for_empty_invalid_and_nonprintable_values() -> None:
    assert OctetStringValue(b"").to_display_string() == ""
    assert OctetStringValue(b"\xff").to_display_string() == "ff"
    assert OctetStringValue(b"line\nbreak").to_display_string() == "6c696e650a627265616b"


def test_scalar_value_display_helpers() -> None:
    assert NullValue().to_display_string() == "null"
    assert IpAddressValue("192.0.2.1").to_display_string() == "192.0.2.1"
    assert Counter32Value(7).to_display_string() == "7"
    assert Gauge32Value(8).to_display_string() == "8"
    assert TimeTicksValue(9).to_display_string() == "9"
    assert OpaqueValue(b"\x01\xab").to_display_string() == "01ab"
    assert Counter64Value(10).to_display_string() == "10"
    assert NoSuchObjectValue().to_display_string() == "noSuchObject"
    assert NoSuchInstanceValue().to_display_string() == "noSuchInstance"
