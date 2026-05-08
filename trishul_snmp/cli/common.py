"""Shared CLI argument helpers."""

from __future__ import annotations

import argparse
from pathlib import Path

from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.mib.loader import load_bundle
from trishul_snmp.mib.registry import parse_oid
from trishul_snmp.types import (
    Counter32Value,
    Counter64Value,
    Gauge32Value,
    IntegerValue,
    IpAddressValue,
    NullValue,
    ObjectIdentifierValue,
    OctetStringValue,
    OpaqueValue,
    SnmpValueType,
    TimeTicksValue,
)


def add_bundle_option(parser: argparse.ArgumentParser, *, required: bool = False) -> None:
    """Add the standard bundle option to *parser*."""
    parser.add_argument(
        "--bundle",
        type=Path,
        required=required,
        help="Compiled module JSON file or bundle directory for symbolic translation",
    )


def add_live_options(parser: argparse.ArgumentParser) -> None:
    """Add common options for live manager commands."""
    parser.add_argument("--host", required=True, help="Target agent hostname or IP address")
    parser.add_argument("--port", type=int, default=161, help="Target UDP port (default: 161)")
    parser.add_argument(
        "--community",
        default="public",
        help="SNMPv2c community string (default: public)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="Request timeout in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help="Retry count per request (default: 1)",
    )
    add_bundle_option(parser, required=False)
    parser.add_argument(
        "--numeric",
        action="store_true",
        help="Render numeric OIDs in text output even when a bundle is loaded",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output",
    )


def add_notifier_options(parser: argparse.ArgumentParser) -> None:
    """Add common options for outbound notification commands."""
    parser.add_argument("--host", required=True, help="Target notification receiver hostname or IP")
    parser.add_argument("--port", type=int, default=162, help="Target UDP port (default: 162)")
    parser.add_argument(
        "--community",
        default="public",
        help="SNMPv2c community string (default: public)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="Request timeout in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help="Retry count per request (default: 1)",
    )
    add_bundle_option(parser, required=False)


def add_listener_options(parser: argparse.ArgumentParser) -> None:
    """Add common options for inbound notification listener commands."""
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Listener bind hostname or IP address (default: 0.0.0.0)",
    )
    parser.add_argument("--port", type=int, default=162, help="Listener UDP port (default: 162)")
    parser.add_argument(
        "--community",
        dest="communities",
        action="append",
        default=None,
        help="Allowed SNMPv2c community string; repeat to allow multiple values",
    )
    add_bundle_option(parser, required=False)
    parser.add_argument(
        "--numeric",
        action="store_true",
        help="Render numeric OIDs in text output even when a bundle is loaded",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit one JSON object per received notification",
    )


def load_bundle_from_args(args: argparse.Namespace) -> MibBundle | None:
    """Load the optional bundle attached to *args*."""
    bundle_path = getattr(args, "bundle", None)
    if bundle_path is None:
        return None
    return load_bundle(bundle_path)


def parse_notification_varbinds(
    values: list[str] | None,
    *,
    bundle: MibBundle | None,
) -> tuple[tuple[str, SnmpValueType], ...]:
    """Parse repeated CLI notification varbind specifications."""
    if not values:
        return ()
    return tuple(parse_notification_varbind(value, bundle=bundle) for value in values)


def parse_notification_varbind(
    value: str,
    *,
    bundle: MibBundle | None,
) -> tuple[str, SnmpValueType]:
    """Parse a single ``OID=TYPE:VALUE`` CLI varbind specification."""
    oid_text, sep, value_spec = value.partition("=")
    oid_target = oid_text.strip()
    if not sep or not oid_target:
        raise ValueError(f"Varbind must use OID=TYPE:VALUE form: {value}")
    return oid_target, parse_snmp_value(value_spec.strip(), bundle=bundle)


def parse_snmp_value(value: str, *, bundle: MibBundle | None) -> SnmpValueType:
    """Parse a typed CLI value specification."""
    type_name, sep, raw_value = value.partition(":")
    normalized_type = type_name.strip().lower()
    if not normalized_type:
        raise ValueError(f"Value type cannot be empty: {value}")

    if normalized_type == "null":
        if sep and raw_value.strip():
            raise ValueError("null values must not include a payload")
        return NullValue()

    if not sep:
        raise ValueError(f"Value must use TYPE:VALUE form: {value}")

    if normalized_type in {"int", "integer"}:
        return IntegerValue(_parse_int(raw_value, field="integer"))
    if normalized_type in {"str", "string"}:
        return OctetStringValue(raw_value.encode("utf-8"))
    if normalized_type == "hex":
        return OctetStringValue(parse_hex_bytes(raw_value))
    if normalized_type == "oid":
        return ObjectIdentifierValue(resolve_oid_target(raw_value.strip(), bundle=bundle))
    if normalized_type in {"ip", "ip-address"}:
        return IpAddressValue(raw_value.strip())
    if normalized_type == "counter32":
        return Counter32Value(_parse_non_negative_int(raw_value, field="counter32"))
    if normalized_type == "gauge32":
        return Gauge32Value(_parse_non_negative_int(raw_value, field="gauge32"))
    if normalized_type == "timeticks":
        return TimeTicksValue(_parse_non_negative_int(raw_value, field="timeticks"))
    if normalized_type == "opaque":
        return OpaqueValue(parse_hex_bytes(raw_value))
    if normalized_type == "counter64":
        return Counter64Value(_parse_non_negative_int(raw_value, field="counter64"))

    raise ValueError(f"Unsupported value type: {type_name.strip()}")


def resolve_oid_target(target: str, *, bundle: MibBundle | None) -> tuple[int, ...]:
    """Resolve a numeric or symbolic OID target for CLI inputs."""
    if "::" in target:
        if bundle is None:
            raise ValueError(f"Symbolic OID requires --bundle: {target}")
        return bundle.resolve(target)
    return parse_oid(target)


def parse_hex_bytes(value: str) -> bytes:
    """Parse raw hex bytes while tolerating common separators."""
    normalized = (
        value.strip()
        .removeprefix("0x")
        .replace(" ", "")
        .replace("\n", "")
        .replace("\t", "")
        .replace(":", "")
        .replace("-", "")
    )
    if len(normalized) % 2 != 0:
        raise ValueError(f"Hex payload must contain an even number of digits: {value}")
    try:
        return bytes.fromhex(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid hex payload: {value}") from exc


def _parse_int(value: str, *, field: str) -> int:
    try:
        return int(value.strip(), 10)
    except ValueError as exc:
        raise ValueError(f"Invalid {field} value: {value}") from exc


def _parse_non_negative_int(value: str, *, field: str) -> int:
    parsed = _parse_int(value, field=field)
    if parsed < 0:
        raise ValueError(f"{field} cannot be negative: {value}")
    return parsed
