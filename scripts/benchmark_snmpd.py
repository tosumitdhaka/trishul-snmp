#!/usr/bin/env python3
"""Benchmark tsnmp against a live SNMP agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import subprocess
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from trishul_snmp import MibBundle, Response, V2cManager, VarBind, load_bundle

AsyncOperation = Callable[[], Awaitable[object]]


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    name: str
    iterations: int
    warmup_iterations: int
    result_size: int | None
    min_ms: float
    median_ms: float
    mean_ms: float
    p95_ms: float
    max_ms: float
    stdev_ms: float


@dataclass(frozen=True, slots=True)
class BenchmarkSuite:
    name: str
    bundle: MibBundle | None
    bundle_path: Path | None
    uptime_target: str
    system_root: str


@dataclass(frozen=True, slots=True)
class PreviewVarBind:
    oid: str
    value_type: str
    display_name: str | None
    display_value: str


@dataclass(frozen=True, slots=True)
class PreviewSample:
    suite: str
    operation: str
    target: str
    total_varbinds: int
    shown_varbinds: tuple[PreviewVarBind, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark tsnmp raw and enriched paths against a live SNMP agent"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Target SNMP agent host")
    parser.add_argument("--port", type=int, default=161, help="Target SNMP agent UDP port")
    parser.add_argument("--community", default="public", help="SNMPv2c community string")
    parser.add_argument("--timeout", type=float, default=0.5, help="Request timeout in seconds")
    parser.add_argument("--retries", type=int, default=0, help="Retry count per request")
    parser.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="Measured iterations per hot benchmark (default: 100)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=10,
        help="Warmup iterations per benchmark (default: 10)",
    )
    parser.add_argument(
        "--cold-iterations",
        type=int,
        default=20,
        help="Measured iterations for cold open/get/close benchmark (default: 20)",
    )
    parser.add_argument(
        "--max-repetitions",
        type=int,
        default=6,
        help="GETBULK / BULKWALK max repetitions (default: 6)",
    )
    parser.add_argument(
        "--system-root",
        default="1.3.6.1.2.1.1",
        help="Numeric subtree root used for raw and enriched-numeric bulk and walk benchmarks",
    )
    parser.add_argument(
        "--uptime-oid",
        default="1.3.6.1.2.1.1.3.0",
        help="Numeric sysUpTime OID used for raw and enriched-numeric GET benchmark",
    )
    parser.add_argument(
        "--bundle",
        type=Path,
        help="Compiled module JSON file or bundle directory used for enrichment benchmarks",
    )
    parser.add_argument(
        "--symbolic-system-root",
        default="SNMPv2-MIB::system",
        help="Symbolic subtree root used for enriched-symbolic bulk and walk benchmarks",
    )
    parser.add_argument(
        "--symbolic-uptime-target",
        default="SNMPv2-MIB::sysUpTime.0",
        help="Symbolic sysUpTime target used for enriched-symbolic GET benchmark",
    )
    parser.add_argument(
        "--preview-limit",
        type=int,
        default=5,
        help="Show up to N varbinds from raw/enriched preview samples (default: 5, 0 disables)",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit JSON instead of a plain-text report",
    )
    parser.add_argument(
        "--include-cli",
        action="store_true",
        help="Also benchmark tsnmp CLI process startup and command execution",
    )
    parser.add_argument(
        "--tsnmp-bin",
        default=str(Path(".venv/bin/tsnmp")),
        help="Path to the tsnmp CLI binary for CLI benchmarks",
    )
    return parser


def _percentile(sorted_samples: list[float], fraction: float) -> float:
    if not sorted_samples:
        raise ValueError("Cannot compute percentile for empty samples")
    index = max(0, min(len(sorted_samples) - 1, math.ceil(len(sorted_samples) * fraction) - 1))
    return sorted_samples[index]


def _result_size(result: object) -> int | None:
    try:
        varbinds = result.varbinds  # type: ignore[attr-defined]
    except AttributeError:
        varbinds = None
    if varbinds is not None:
        try:
            return len(varbinds)
        except TypeError:
            return None
    if isinstance(result, tuple):
        return len(result)
    return None


def _summarize(
    name: str,
    samples_ms: list[float],
    *,
    iterations: int,
    warmup_iterations: int,
    result_size: int | None,
) -> BenchmarkSummary:
    ordered = sorted(samples_ms)
    return BenchmarkSummary(
        name=name,
        iterations=iterations,
        warmup_iterations=warmup_iterations,
        result_size=result_size,
        min_ms=min(ordered),
        median_ms=statistics.median(ordered),
        mean_ms=statistics.fmean(ordered),
        p95_ms=_percentile(ordered, 0.95),
        max_ms=max(ordered),
        stdev_ms=statistics.stdev(ordered) if len(ordered) > 1 else 0.0,
    )


async def _measure_async(
    name: str,
    operation: AsyncOperation,
    *,
    iterations: int,
    warmup_iterations: int,
) -> BenchmarkSummary:
    for _ in range(warmup_iterations):
        await operation()

    samples_ms: list[float] = []
    result_size: int | None = None
    for _ in range(iterations):
        start = time.perf_counter_ns()
        result = await operation()
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        samples_ms.append(elapsed_ms)
        if result_size is None:
            result_size = _result_size(result)

    return _summarize(
        name,
        samples_ms,
        iterations=iterations,
        warmup_iterations=warmup_iterations,
        result_size=result_size,
    )


def _measure_cli(
    name: str,
    command: list[str],
    *,
    iterations: int,
    warmup_iterations: int,
) -> BenchmarkSummary:
    result_size: int | None = None
    for _ in range(warmup_iterations):
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        if result_size is None:
            result_size = _cli_result_size(completed.stdout)

    samples_ms: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        samples_ms.append(elapsed_ms)
        if result_size is None:
            result_size = _cli_result_size(completed.stdout)

    return _summarize(
        name,
        samples_ms,
        iterations=iterations,
        warmup_iterations=warmup_iterations,
        result_size=result_size,
    )


def _cli_result_size(stdout: str) -> int | None:
    payload = json.loads(stdout)
    varbinds = payload.get("varbinds")
    if isinstance(varbinds, list):
        return len(varbinds)
    return None


def _build_suites(args: argparse.Namespace) -> list[BenchmarkSuite]:
    suites = [
        BenchmarkSuite(
            name="raw",
            bundle=None,
            bundle_path=None,
            uptime_target=args.uptime_oid,
            system_root=args.system_root,
        )
    ]
    if args.bundle is None:
        return suites

    bundle_path = args.bundle.expanduser()
    bundle = load_bundle(bundle_path)
    suites.extend(
        [
            BenchmarkSuite(
                name="enriched_numeric",
                bundle=bundle,
                bundle_path=bundle_path,
                uptime_target=args.uptime_oid,
                system_root=args.system_root,
            ),
            BenchmarkSuite(
                name="enriched_symbolic",
                bundle=bundle,
                bundle_path=bundle_path,
                uptime_target=args.symbolic_uptime_target,
                system_root=args.symbolic_system_root,
            ),
        ]
    )
    return suites


def _varbinds_from_result(result: Response | tuple[VarBind, ...]) -> tuple[VarBind, ...]:
    if isinstance(result, Response):
        return result.varbinds
    return result


def _preview_varbind(varbind: VarBind) -> PreviewVarBind:
    return PreviewVarBind(
        oid=varbind.oid_str,
        value_type=varbind.value_type,
        display_name=varbind.display_name,
        display_value=varbind.display_value or varbind.value.to_display_string(),
    )


def _build_preview(
    suite: BenchmarkSuite,
    *,
    operation: str,
    target: str,
    result: Response | tuple[VarBind, ...],
    limit: int,
) -> PreviewSample:
    varbinds = _varbinds_from_result(result)
    shown = tuple(_preview_varbind(varbind) for varbind in varbinds[:limit])
    return PreviewSample(
        suite=suite.name,
        operation=operation,
        target=target,
        total_varbinds=len(varbinds),
        shown_varbinds=shown,
    )


async def _run_api_suite(
    args: argparse.Namespace,
    suite: BenchmarkSuite,
) -> tuple[list[BenchmarkSummary], list[PreviewSample]]:
    results: list[BenchmarkSummary] = []
    previews: list[PreviewSample] = []

    async with V2cManager(
        host=args.host,
        port=args.port,
        community=args.community,
        timeout=args.timeout,
        retries=args.retries,
        bundle=suite.bundle,
    ) as manager:

        async def op_get() -> object:
            return await manager.get(suite.uptime_target)

        async def op_get_next() -> object:
            return await manager.get_next(suite.uptime_target)

        async def op_get_bulk() -> object:
            return await manager.get_bulk(suite.system_root, max_repetitions=args.max_repetitions)

        async def op_walk_next() -> object:
            return await manager.walk(
                suite.system_root,
                bulk=False,
                max_repetitions=args.max_repetitions,
            )

        async def op_bulkwalk() -> object:
            return await manager.bulkwalk(suite.system_root, max_repetitions=args.max_repetitions)

        operations = [
            ("api_get_hot", op_get),
            ("api_get_next_hot", op_get_next),
            ("api_get_bulk_hot", op_get_bulk),
            ("api_walk_hot", op_walk_next),
            ("api_bulkwalk_hot", op_bulkwalk),
        ]
        for operation_name, operation in operations:
            results.append(
                await _measure_async(
                    f"{suite.name}_{operation_name}",
                    operation,
                    iterations=args.iterations,
                    warmup_iterations=args.warmup,
                )
            )

        if args.preview_limit > 0:
            previews.append(
                _build_preview(
                    suite,
                    operation="api_get",
                    target=suite.uptime_target,
                    result=await manager.get(suite.uptime_target),
                    limit=args.preview_limit,
                )
            )
            previews.append(
                _build_preview(
                    suite,
                    operation="api_bulkwalk",
                    target=suite.system_root,
                    result=await manager.bulkwalk(
                        suite.system_root,
                        max_repetitions=args.max_repetitions,
                    ),
                    limit=args.preview_limit,
                )
            )

    async def op_cold_get() -> object:
        async with V2cManager(
            host=args.host,
            port=args.port,
            community=args.community,
            timeout=args.timeout,
            retries=args.retries,
            bundle=suite.bundle,
        ) as manager:
            return await manager.get(suite.uptime_target)

    results.append(
        await _measure_async(
            f"{suite.name}_api_get_cold",
            op_cold_get,
            iterations=args.cold_iterations,
            warmup_iterations=max(1, min(args.warmup, args.cold_iterations)),
        )
    )
    return results, previews


async def run_api_benchmarks(
    args: argparse.Namespace,
    suites: list[BenchmarkSuite],
) -> tuple[list[BenchmarkSummary], list[PreviewSample]]:
    results: list[BenchmarkSummary] = []
    previews: list[PreviewSample] = []
    for suite in suites:
        suite_results, suite_previews = await _run_api_suite(args, suite)
        results.extend(suite_results)
        previews.extend(suite_previews)
    return results, previews


def run_cli_benchmarks(
    args: argparse.Namespace,
    suites: list[BenchmarkSuite],
) -> list[BenchmarkSummary]:
    common = [
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--community",
        args.community,
        "--timeout",
        str(args.timeout),
        "--retries",
        str(args.retries),
    ]
    iterations = max(5, min(20, args.cold_iterations))
    warmup_iterations = max(1, min(3, args.warmup))

    results: list[BenchmarkSummary] = []
    for suite in suites:
        bundle_args = []
        if suite.bundle_path is not None:
            bundle_args = ["--bundle", str(suite.bundle_path)]

        commands = [
            (
                f"{suite.name}_cli_get",
                [args.tsnmp_bin, "get", *common, *bundle_args, "--json", suite.uptime_target],
            ),
            (
                f"{suite.name}_cli_bulkwalk",
                [
                    args.tsnmp_bin,
                    "bulkwalk",
                    *common,
                    *bundle_args,
                    "--json",
                    "--max-repetitions",
                    str(args.max_repetitions),
                    suite.system_root,
                ],
            ),
        ]

        for name, command in commands:
            results.append(
                _measure_cli(
                    name,
                    command,
                    iterations=iterations,
                    warmup_iterations=warmup_iterations,
                )
            )
    return results


def _format_summaries(summaries: list[BenchmarkSummary]) -> str:
    headers = [
        "name",
        "iter",
        "warm",
        "result",
        "min_ms",
        "median_ms",
        "mean_ms",
        "p95_ms",
        "max_ms",
        "stdev_ms",
    ]
    rows = [
        [
            summary.name,
            str(summary.iterations),
            str(summary.warmup_iterations),
            "-" if summary.result_size is None else str(summary.result_size),
            f"{summary.min_ms:.3f}",
            f"{summary.median_ms:.3f}",
            f"{summary.mean_ms:.3f}",
            f"{summary.p95_ms:.3f}",
            f"{summary.max_ms:.3f}",
            f"{summary.stdev_ms:.3f}",
        ]
        for summary in summaries
    ]

    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def format_row(values: list[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(values))

    lines = [format_row(headers), format_row(["-" * width for width in widths])]
    lines.extend(format_row(row) for row in rows)
    return "\n".join(lines)


def _format_previews(previews: list[PreviewSample]) -> str:
    lines = ["preview", "-------"]
    for preview in previews:
        shown_count = len(preview.shown_varbinds)
        lines.append(
            f"{preview.suite}:{preview.operation} target={preview.target} "
            f"shown={shown_count}/{preview.total_varbinds}"
        )
        for varbind in preview.shown_varbinds:
            display_name = varbind.display_name if varbind.display_name is not None else "-"
            lines.append(
                f"  oid={varbind.oid} name={display_name} "
                f"type={varbind.value_type} value={varbind.display_value}"
            )
    return "\n".join(lines)


async def main_async(args: argparse.Namespace) -> int:
    suites = _build_suites(args)
    summaries, previews = await run_api_benchmarks(args, suites)
    if args.include_cli:
        summaries.extend(run_cli_benchmarks(args, suites))

    if args.json_output:
        payload = {
            "summaries": [asdict(summary) for summary in summaries],
            "previews": [asdict(preview) for preview in previews],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(_format_summaries(summaries))
        if previews:
            print()
            print(_format_previews(previews))
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
