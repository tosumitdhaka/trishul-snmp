"""Shared CLI argument helpers."""

from __future__ import annotations

import argparse
from pathlib import Path

from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.mib.loader import load_bundle


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


def load_bundle_from_args(args: argparse.Namespace) -> MibBundle | None:
    """Load the optional bundle attached to *args*."""
    bundle_path = getattr(args, "bundle", None)
    if bundle_path is None:
        return None
    return load_bundle(bundle_path)
