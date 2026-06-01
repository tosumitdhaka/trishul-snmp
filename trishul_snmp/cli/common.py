"""Shared CLI argument helpers."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.mib.loader import load_bundle
from trishul_snmp.mib.registry import parse_oid
from trishul_snmp.security.usm import AuthProtocol, PrivProtocol, UsmLocalEngine, UsmUser
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


@dataclass(frozen=True, slots=True)
class V2cCliSecurity:
    community: str


@dataclass(frozen=True, slots=True)
class V3CliSecurity:
    user: UsmUser
    context_name: bytes
    local_engine: UsmLocalEngine | None = None


CliSecurity = V2cCliSecurity | V3CliSecurity


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
    _add_security_options(parser)
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
    _add_security_options(parser)
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


def add_local_engine_options(parser: argparse.ArgumentParser, *, hidden: bool = False) -> None:
    """Add SNMPv3 local authoritative engine inputs for trap send flows."""
    parser.add_argument(
        "--local-engine-id",
        help=argparse.SUPPRESS if hidden else "SNMPv3 sender local engine-id as hex bytes",
    )
    parser.add_argument(
        "--local-engine-boots",
        type=int,
        default=None,
        help=argparse.SUPPRESS if hidden else "SNMPv3 sender local engineBoots",
    )
    parser.add_argument(
        "--local-engine-time",
        type=int,
        default=None,
        help=argparse.SUPPRESS if hidden else "SNMPv3 sender local engineTime",
    )


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


def parse_cli_security(
    args: argparse.Namespace,
    *,
    require_local_engine: bool = False,
    allow_local_engine: bool = False,
) -> CliSecurity:
    """Build validated v2c/v3 security configuration from CLI arguments."""
    if getattr(args, "snmp_version", "2c") == "3":
        return _parse_v3_cli_security(
            args,
            require_local_engine=require_local_engine,
            allow_local_engine=allow_local_engine,
        )
    return _parse_v2c_cli_security(args)


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


def _add_security_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--snmp-version",
        choices=("2c", "3"),
        default="2c",
        help="SNMP version for live operations (default: 2c)",
    )
    parser.add_argument(
        "--community",
        default=None,
        help="SNMPv2c community string (default when omitted: public)",
    )
    parser.add_argument("--username", help="SNMPv3 username")
    parser.add_argument(
        "--auth-protocol",
        choices=("none", "md5", "sha1", "sha256"),
        default="none",
        help="SNMPv3 auth protocol (default: none)",
    )
    parser.add_argument("--auth-key", help="SNMPv3 auth passphrase")
    parser.add_argument("--auth-key-env", help="Environment variable holding the SNMPv3 auth key")
    parser.add_argument(
        "--priv-protocol",
        choices=("none", "aes128"),
        default="none",
        help="SNMPv3 privacy protocol (default: none)",
    )
    parser.add_argument("--priv-key", help="SNMPv3 privacy passphrase")
    parser.add_argument("--priv-key-env", help="Environment variable holding the SNMPv3 priv key")
    parser.add_argument(
        "--context-name",
        default="",
        help="SNMPv3 contextName as UTF-8 text (default: empty)",
    )


def _parse_v2c_cli_security(args: argparse.Namespace) -> V2cCliSecurity:
    if getattr(args, "username", None):
        raise ValueError("--username is invalid with --snmp-version 2c")
    if getattr(args, "auth_protocol", "none") != "none":
        raise ValueError("--auth-protocol is invalid with --snmp-version 2c")
    if getattr(args, "auth_key", None) or getattr(args, "auth_key_env", None):
        raise ValueError("--auth-key and --auth-key-env are invalid with --snmp-version 2c")
    if getattr(args, "priv_protocol", "none") != "none":
        raise ValueError("--priv-protocol is invalid with --snmp-version 2c")
    if getattr(args, "priv_key", None) or getattr(args, "priv_key_env", None):
        raise ValueError("--priv-key and --priv-key-env are invalid with --snmp-version 2c")
    if getattr(args, "context_name", ""):
        raise ValueError("--context-name is invalid with --snmp-version 2c")
    if _local_engine_supplied(args):
        raise ValueError("--local-engine-* options are invalid with --snmp-version 2c")
    return V2cCliSecurity(community=getattr(args, "community", None) or "public")


def _parse_v3_cli_security(
    args: argparse.Namespace,
    *,
    require_local_engine: bool,
    allow_local_engine: bool,
) -> V3CliSecurity:
    if getattr(args, "community", None) is not None:
        raise ValueError("--community is invalid with --snmp-version 3")

    username = getattr(args, "username", None)
    if not username:
        raise ValueError("--username is required with --snmp-version 3")

    auth_protocol = AuthProtocol(getattr(args, "auth_protocol", "none"))
    priv_protocol = PrivProtocol(getattr(args, "priv_protocol", "none"))
    auth_key = _resolve_secret(
        args,
        inline_name="auth_key",
        env_name="auth_key_env",
        label="auth",
    )
    priv_key = _resolve_secret(
        args,
        inline_name="priv_key",
        env_name="priv_key_env",
        label="priv",
    )

    if auth_protocol is AuthProtocol.NONE:
        if auth_key is not None:
            raise ValueError(
                "--auth-key and --auth-key-env require --auth-protocol to be md5, sha1, or sha256"
            )
    elif auth_key is None:
        raise ValueError("SNMPv3 auth requires exactly one of --auth-key or --auth-key-env")

    if priv_protocol is PrivProtocol.NONE:
        if priv_key is not None:
            raise ValueError("--priv-key and --priv-key-env require --priv-protocol to be aes128")
    else:
        if auth_protocol is AuthProtocol.NONE:
            raise ValueError("--priv-protocol requires --auth-protocol to be enabled")
        if priv_key is None:
            raise ValueError("SNMPv3 privacy requires exactly one of --priv-key or --priv-key-env")

    local_engine = _parse_local_engine(
        args,
        required=require_local_engine,
        allowed=allow_local_engine,
    )
    return V3CliSecurity(
        user=UsmUser(
            username=username,
            auth_protocol=auth_protocol,
            auth_key=auth_key or b"",
            priv_protocol=priv_protocol,
            priv_key=priv_key or b"",
        ),
        context_name=getattr(args, "context_name", "").encode("utf-8"),
        local_engine=local_engine,
    )


def _resolve_secret(
    args: argparse.Namespace,
    *,
    inline_name: str,
    env_name: str,
    label: str,
) -> bytes | None:
    inline_value = getattr(args, inline_name, None)
    env_var = getattr(args, env_name, None)
    if inline_value is not None and env_var is not None:
        raise ValueError(
            f"Use only one of --{inline_name.replace('_', '-')} or --{env_name.replace('_', '-')}"
        )
    if inline_value is not None:
        return str(inline_value).encode("utf-8")
    if env_var is None:
        return None
    env_value = os.environ.get(str(env_var))
    if env_value is None:
        raise ValueError(
            f"Environment variable {env_var} is not set for SNMPv3 {label} credentials"
        )
    return env_value.encode("utf-8")


def _local_engine_supplied(args: argparse.Namespace) -> bool:
    return any(
        getattr(args, name, None) is not None
        for name in ("local_engine_id", "local_engine_boots", "local_engine_time")
    )


def _parse_local_engine(
    args: argparse.Namespace,
    *,
    required: bool,
    allowed: bool,
) -> UsmLocalEngine | None:
    supplied = _local_engine_supplied(args)
    if supplied and not allowed:
        raise ValueError("--local-engine-* options are only valid for SNMPv3 trap")
    if not supplied:
        if required:
            raise ValueError(
                "SNMPv3 trap requires --local-engine-id, "
                "--local-engine-boots, and --local-engine-time"
            )
        return None

    if getattr(args, "local_engine_id", None) is None:
        raise ValueError("SNMPv3 trap requires --local-engine-id")
    if getattr(args, "local_engine_boots", None) is None:
        raise ValueError("SNMPv3 trap requires --local-engine-boots")
    if getattr(args, "local_engine_time", None) is None:
        raise ValueError("SNMPv3 trap requires --local-engine-time")

    engine_boots = int(args.local_engine_boots)
    engine_time = int(args.local_engine_time)
    if engine_boots < 0:
        raise ValueError("--local-engine-boots cannot be negative")
    if engine_time < 0:
        raise ValueError("--local-engine-time cannot be negative")

    engine_id = parse_hex_bytes(str(args.local_engine_id))
    if not engine_id:
        raise ValueError("--local-engine-id cannot be empty")
    return UsmLocalEngine(
        engine_id=engine_id,
        engine_boots=engine_boots,
        engine_time=engine_time,
    )


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
