"""Thin CLI over the trishul-snmp Python API."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from typing import TypeAlias, cast

from trishul_snmp import V2cManager, __version__
from trishul_snmp.cli.common import add_bundle_option, add_live_options, load_bundle_from_args
from trishul_snmp.cli.output import render_response, render_translation, render_walk
from trishul_snmp.errors import TsnmpError
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.types import ErrorStatus, Response

HandlerResult: TypeAlias = int | Coroutine[object, object, int]
Handler: TypeAlias = Callable[[argparse.Namespace], HandlerResult]
ResponseOperation: TypeAlias = Callable[[V2cManager, argparse.Namespace], Awaitable[Response]]


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="tsnmp",
        description="Modern SNMP manager runtime CLI with optional compiled-JSON MIB enrichment",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    translate = subparsers.add_parser(
        "translate",
        help="Translate numeric OIDs and symbolic names using a compiled bundle",
    )
    add_bundle_option(translate, required=True)
    translate.add_argument("target", help="Numeric OID or MODULE::symbol target")
    translate.set_defaults(handler=_handle_translate)

    get = subparsers.add_parser("get", help="Perform an SNMP GET request")
    add_live_options(get)
    get.add_argument("targets", nargs="+", help="Numeric OIDs or MODULE::symbol targets")
    get.set_defaults(handler=_handle_get)

    get_next = subparsers.add_parser("getnext", help="Perform an SNMP GETNEXT request")
    add_live_options(get_next)
    get_next.add_argument("targets", nargs="+", help="Numeric OIDs or MODULE::symbol targets")
    get_next.set_defaults(handler=_handle_get_next)

    get_bulk = subparsers.add_parser("getbulk", help="Perform an SNMP GETBULK request")
    add_live_options(get_bulk)
    get_bulk.add_argument("targets", nargs="+", help="Numeric OIDs or MODULE::symbol targets")
    get_bulk.add_argument(
        "--non-repeaters",
        type=int,
        default=0,
        help="Number of non-repeaters (default: 0)",
    )
    get_bulk.add_argument(
        "--max-repetitions",
        type=int,
        default=10,
        help="Maximum repetitions per repeating target (default: 10)",
    )
    get_bulk.set_defaults(handler=_handle_get_bulk)

    walk = subparsers.add_parser("walk", help="Walk an SNMP subtree")
    add_live_options(walk)
    walk.add_argument("root", help="Numeric OID or MODULE::symbol subtree root")
    walk.add_argument(
        "--max-repetitions",
        type=int,
        default=10,
        help="Maximum repetitions for bulk walk steps (default: 10)",
    )
    walk.add_argument(
        "--no-bulk",
        action="store_false",
        dest="bulk",
        help="Use GETNEXT rather than GETBULK during the walk",
    )
    walk.set_defaults(handler=_handle_walk, bulk=True)

    bulk_walk = subparsers.add_parser("bulkwalk", help="Walk an SNMP subtree using GETBULK")
    add_live_options(bulk_walk)
    bulk_walk.add_argument("root", help="Numeric OID or MODULE::symbol subtree root")
    bulk_walk.add_argument(
        "--max-repetitions",
        type=int,
        default=10,
        help="Maximum repetitions per bulk request (default: 10)",
    )
    bulk_walk.set_defaults(handler=_handle_bulk_walk)

    version = subparsers.add_parser("version", help="Print the installed version")
    version.set_defaults(handler=_handle_version)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    handler = cast(Handler, args.handler)

    try:
        result = handler(args)
        if isinstance(result, int):
            return result
        return asyncio.run(result)
    except (TsnmpError, ValueError) as exc:
        print(f"tsnmp: {exc}", file=sys.stderr)
        return 1


def run() -> None:
    """Console script entry point."""
    raise SystemExit(main())


def _handle_version(_: argparse.Namespace) -> int:
    print(__version__)
    return 0


def _handle_translate(args: argparse.Namespace) -> int:
    bundle = load_bundle_from_args(args)
    if bundle is None:
        raise ValueError("translate requires --bundle")
    print(render_translation(bundle.translate(args.target)))
    return 0


async def _handle_get(args: argparse.Namespace) -> int:
    return await _run_response_command(args, _perform_get)


async def _handle_get_next(args: argparse.Namespace) -> int:
    return await _run_response_command(args, _perform_get_next)


async def _handle_get_bulk(args: argparse.Namespace) -> int:
    return await _run_response_command(args, _perform_get_bulk)


async def _handle_walk(args: argparse.Namespace) -> int:
    bundle = load_bundle_from_args(args)
    async with _manager_from_args(args, bundle=bundle) as manager:
        varbinds = await manager.walk(
            args.root,
            bulk=args.bulk,
            max_repetitions=args.max_repetitions,
        )
    print(render_walk(varbinds, json_output=args.json_output, numeric=args.numeric))
    return 0


async def _handle_bulk_walk(args: argparse.Namespace) -> int:
    bundle = load_bundle_from_args(args)
    async with _manager_from_args(args, bundle=bundle) as manager:
        varbinds = await manager.bulkwalk(
            args.root,
            max_repetitions=args.max_repetitions,
        )
    print(render_walk(varbinds, json_output=args.json_output, numeric=args.numeric))
    return 0


async def _run_response_command(args: argparse.Namespace, operation: ResponseOperation) -> int:
    bundle = load_bundle_from_args(args)
    async with _manager_from_args(args, bundle=bundle) as manager:
        response = await operation(manager, args)
    print(render_response(response, json_output=args.json_output, numeric=args.numeric))
    return 0 if response.error_status is ErrorStatus.NO_ERROR else 1


def _manager_from_args(args: argparse.Namespace, *, bundle: MibBundle | None) -> V2cManager:
    return V2cManager(
        host=args.host,
        port=args.port,
        community=args.community,
        timeout=args.timeout,
        retries=args.retries,
        bundle=bundle,
    )


async def _perform_get(manager: V2cManager, args: argparse.Namespace) -> Response:
    return await manager.get(*args.targets)


async def _perform_get_next(manager: V2cManager, args: argparse.Namespace) -> Response:
    return await manager.get_next(*args.targets)


async def _perform_get_bulk(manager: V2cManager, args: argparse.Namespace) -> Response:
    return await manager.get_bulk(
        *args.targets,
        non_repeaters=args.non_repeaters,
        max_repetitions=args.max_repetitions,
    )
