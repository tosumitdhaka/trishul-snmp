#!/usr/bin/env python3
"""Validate the tsnmp/tsmi ecosystem in an isolated virtual environment."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import venv
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = Path(__file__).resolve()
SIDE_CAR_FILENAMES = frozenset({"manifest.json", "oid_index.json"})
DEFAULT_MIBS = ("IF-MIB", "SNMPv2-MIB")


class ValidationError(RuntimeError):
    """Raised when a validation step fails."""


class SkippedStepError(RuntimeError):
    """Raised to mark an intentionally skipped validation step."""


@dataclass(slots=True)
class StepResult:
    name: str
    status: str
    detail: str
    duration_ms: float


@dataclass(slots=True)
class ValidationReport:
    work_dir: str
    tsnmp_version: str
    tsmi_version: str
    tsnmp_spec: str
    tsmi_spec: str
    steps: list[StepResult] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(step.status == "failed" for step in self.steps)


@dataclass(frozen=True, slots=True)
class CompileArtifacts:
    output_dir: Path
    module_files: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    work_dir: Path
    venv_bin_dir: Path
    tsnmp_spec: str
    tsmi_spec: str
    mibs: tuple[str, ...]
    single_module: str
    mib_dirs: tuple[Path, ...]
    online: bool
    sources: tuple[str, ...]
    cache_dir: str
    host: str
    port: int
    community: str
    timeout: float
    retries: int
    max_repetitions: int
    single_translate_target: str
    single_live_target: str
    bundle_translate_oid: str
    bundle_live_target: str
    walk_root: str
    notification_target: str
    skip_live: bool
    skip_notifications: bool
    skip_responder: bool
    report_json: Path | None


@dataclass(slots=True)
class WorkerContext:
    settings: WorkerSettings
    report: ValidationReport
    plain_dir: Path
    manifest_dir: Path
    full_dir: Path
    plain_compile: CompileArtifacts | None = None
    manifest_compile: CompileArtifacts | None = None
    full_compile: CompileArtifacts | None = None

    @property
    def tsmi_bin(self) -> Path:
        return _venv_executable(self.settings.venv_bin_dir, "tsmi")

    @property
    def tsnmp_bin(self) -> Path:
        return _venv_executable(self.settings.venv_bin_dir, "tsnmp")

    @property
    def single_module_file(self) -> Path:
        return self.plain_dir / f"{self.settings.single_module}.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create an isolated venv, install tsnmp plus a chosen tsmi build, "
            "then validate compile/runtime interoperability."
        )
    )
    parser.add_argument(
        "--tsmi-spec",
        help=(
            "pip install spec for trishul-smi, for example "
            "'trishul-smi==0.4.3', a wheel path, or a local repo path"
        ),
    )
    parser.add_argument(
        "--tsmi-version",
        help="Convenience wrapper for --tsmi-spec trishul-smi==VERSION",
    )
    parser.add_argument(
        "--tsnmp-spec",
        default=str(REPO_ROOT),
        help=(
            "pip install spec for trishul-snmp. Defaults to the current repo root. "
            "Use a wheel path or version string for release-candidate validation."
        ),
    )
    parser.add_argument(
        "--editable-tsnmp",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Install --tsnmp-spec in editable mode when it points to a local path",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="Working directory for the temporary venv and compiled artifacts",
    )
    parser.add_argument(
        "--venv-dir",
        type=Path,
        help="Override the virtualenv directory (default: <work-dir>/venv)",
    )
    parser.add_argument(
        "--keep-work-dir",
        action="store_true",
        help="Keep the working directory even after a successful run",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        help="Optional path to write the machine-readable validation report",
    )
    parser.add_argument(
        "--mib",
        dest="mibs",
        action="append",
        default=[],
        help=("MIB to compile. Repeat for multiple modules. Defaults to IF-MIB and SNMPv2-MIB."),
    )
    parser.add_argument(
        "--single-module",
        default="IF-MIB",
        help="Module file used for single-file runtime validation (default: IF-MIB)",
    )
    parser.add_argument(
        "--mib-dir",
        dest="mib_dirs",
        type=Path,
        action="append",
        default=[],
        help="Local MIB directory passed through to tsmi. Repeat for multiple.",
    )
    parser.add_argument(
        "--online",
        action="store_true",
        help="Allow tsmi to fetch missing MIBs over HTTP",
    )
    parser.add_argument(
        "--source",
        dest="sources",
        action="append",
        default=[],
        help="Custom tsmi HTTP source template. Repeat for multiple.",
    )
    parser.add_argument(
        "--cache-dir",
        default="",
        help="tsmi cache directory. Defaults to the empty string to disable cache.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Live SNMP agent host")
    parser.add_argument("--port", type=int, default=161, help="Live SNMP agent UDP port")
    parser.add_argument("--community", default="public", help="SNMPv2c community string")
    parser.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        help="Timeout in seconds for live manager and local UDP checks",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=0,
        help="Retry count for live manager checks",
    )
    parser.add_argument(
        "--max-repetitions",
        type=int,
        default=10,
        help="Max repetitions for live walk/bulkwalk checks",
    )
    parser.add_argument(
        "--single-translate-target",
        default="IF-MIB::ifDescr.1",
        help="Symbolic target validated against the standalone module JSON",
    )
    parser.add_argument(
        "--single-live-target",
        default="IF-MIB::ifNumber.0",
        help="Symbolic live GET target validated against the standalone module JSON",
    )
    parser.add_argument(
        "--bundle-translate-oid",
        default="1.3.6.1.2.1.1.3.0",
        help="Numeric OID reverse-translated through the full bundle",
    )
    parser.add_argument(
        "--bundle-live-target",
        default="SNMPv2-MIB::sysUpTime.0",
        help="Symbolic live GET target validated against the full bundle",
    )
    parser.add_argument(
        "--walk-root",
        default="IF-MIB::ifTable",
        help="Symbolic live walk root validated against the full bundle",
    )
    parser.add_argument(
        "--notification-target",
        default="IF-MIB::linkDown",
        help="Symbolic notification target used for local trap/inform validation",
    )
    parser.add_argument(
        "--skip-live",
        action="store_true",
        help="Skip live snmpd validation against --host/--port",
    )
    parser.add_argument(
        "--skip-notifications",
        action="store_true",
        help="Skip local notifier/listener/offline-decode validation",
    )
    parser.add_argument(
        "--skip-responder",
        action="store_true",
        help="Skip local responder validation",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Print the final validation report as JSON",
    )
    parser.add_argument(
        "--worker-config",
        type=Path,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.worker_config is not None:
        return _run_worker(args.worker_config, json_output=args.json_output)

    _validate_parent_args(parser, args)
    return _run_parent(args)


def _validate_parent_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.tsmi_spec and args.tsmi_version:
        parser.error("--tsmi-spec and --tsmi-version are mutually exclusive")
    if not args.mibs:
        args.mibs = list(DEFAULT_MIBS)
    if not args.mib_dirs and not args.online and not args.sources:
        parser.error("one of --mib-dir, --online, or --source is required")
    if args.timeout <= 0:
        parser.error("--timeout must be > 0")
    if args.retries < 0:
        parser.error("--retries cannot be negative")
    if args.max_repetitions <= 0:
        parser.error("--max-repetitions must be > 0")

    tsnmp_path = Path(args.tsnmp_spec).expanduser()
    if args.editable_tsnmp and not tsnmp_path.exists():
        parser.error("--editable-tsnmp requires --tsnmp-spec to point to a local path")


def _run_parent(args: argparse.Namespace) -> int:
    work_dir, created_temp = _prepare_work_dir(args.work_dir)
    keep_work_dir = args.keep_work_dir
    venv_dir = (args.venv_dir or (work_dir / "venv")).resolve()
    try:
        try:
            _create_venv(venv_dir)
            python_bin = _venv_executable(_venv_bin_dir(venv_dir), "python")
            _install_packages(
                python_bin=python_bin,
                tsnmp_spec=args.tsnmp_spec,
                editable_tsnmp=args.editable_tsnmp,
                tsmi_spec=_resolve_tsmi_spec(args),
            )

            config_path = work_dir / "worker-config.json"
            config = _build_worker_config(args, work_dir=work_dir, venv_dir=venv_dir)
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

            worker_command = [
                str(python_bin),
                str(SCRIPT_PATH),
                "--worker-config",
                str(config_path),
            ]
            if args.json_output:
                worker_command.append("--json")
            completed = subprocess.run(worker_command, text=True, check=False)
            if completed.returncode != 0:
                keep_work_dir = True
            return completed.returncode
        except Exception as exc:  # noqa: BLE001
            keep_work_dir = True
            print(f"validation bootstrap failed: {_format_exception(exc)}", file=sys.stderr)
            return 1
    finally:
        if created_temp and not keep_work_dir:
            shutil.rmtree(work_dir, ignore_errors=True)
        else:
            print(f"validation work dir: {work_dir}", file=sys.stderr)


def _prepare_work_dir(requested: Path | None) -> tuple[Path, bool]:
    if requested is not None:
        path = requested.expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path, False
    return Path(tempfile.mkdtemp(prefix="trishul-ecosystem-")).resolve(), True


def _resolve_tsmi_spec(args: argparse.Namespace) -> str:
    if args.tsmi_version:
        return f"trishul-smi=={args.tsmi_version}"
    if args.tsmi_spec:
        return args.tsmi_spec
    return "trishul-smi"


def _build_worker_config(
    args: argparse.Namespace,
    *,
    work_dir: Path,
    venv_dir: Path,
) -> dict[str, object]:
    return {
        "work_dir": str(work_dir),
        "venv_bin_dir": str(_venv_bin_dir(venv_dir)),
        "tsnmp_spec": args.tsnmp_spec,
        "tsmi_spec": _resolve_tsmi_spec(args),
        "mibs": args.mibs,
        "single_module": args.single_module,
        "mib_dirs": [str(path.expanduser().resolve()) for path in args.mib_dirs],
        "online": args.online,
        "sources": args.sources,
        "cache_dir": args.cache_dir,
        "host": args.host,
        "port": args.port,
        "community": args.community,
        "timeout": args.timeout,
        "retries": args.retries,
        "max_repetitions": args.max_repetitions,
        "single_translate_target": args.single_translate_target,
        "single_live_target": args.single_live_target,
        "bundle_translate_oid": args.bundle_translate_oid,
        "bundle_live_target": args.bundle_live_target,
        "walk_root": args.walk_root,
        "notification_target": args.notification_target,
        "skip_live": args.skip_live,
        "skip_notifications": args.skip_notifications,
        "skip_responder": args.skip_responder,
        "report_json": None if args.report_json is None else str(args.report_json.resolve()),
    }


def _create_venv(venv_dir: Path) -> None:
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    venv.EnvBuilder(with_pip=True).create(venv_dir)


def _install_packages(
    *,
    python_bin: Path,
    tsnmp_spec: str,
    editable_tsnmp: bool,
    tsmi_spec: str,
) -> None:
    pip_base = [str(python_bin), "-m", "pip", "install"]
    if editable_tsnmp:
        tsnmp_target = str(Path(tsnmp_spec).expanduser().resolve())
        _run_checked(pip_base + ["-e", tsnmp_target], cwd=REPO_ROOT)
    else:
        _run_checked(pip_base + [tsnmp_spec], cwd=REPO_ROOT)
    _run_checked(pip_base + [tsmi_spec], cwd=REPO_ROOT)


def _run_worker(config_path: Path, *, json_output: bool) -> int:
    settings = _load_worker_settings(config_path)
    report = _validate_worker(settings)

    if settings.report_json is not None:
        settings.report_json.parent.mkdir(parents=True, exist_ok=True)
        settings.report_json.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")

    if json_output:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(_render_report(report))
    return 1 if report.failed else 0


def _load_worker_settings(config_path: Path) -> WorkerSettings:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return WorkerSettings(
        work_dir=Path(payload["work_dir"]).resolve(),
        venv_bin_dir=Path(payload["venv_bin_dir"]).resolve(),
        tsnmp_spec=str(payload["tsnmp_spec"]),
        tsmi_spec=str(payload["tsmi_spec"]),
        mibs=tuple(str(value) for value in payload["mibs"]),
        single_module=str(payload["single_module"]),
        mib_dirs=tuple(Path(value).resolve() for value in payload["mib_dirs"]),
        online=bool(payload["online"]),
        sources=tuple(str(value) for value in payload["sources"]),
        cache_dir=str(payload["cache_dir"]),
        host=str(payload["host"]),
        port=int(payload["port"]),
        community=str(payload["community"]),
        timeout=float(payload["timeout"]),
        retries=int(payload["retries"]),
        max_repetitions=int(payload["max_repetitions"]),
        single_translate_target=str(payload["single_translate_target"]),
        single_live_target=str(payload["single_live_target"]),
        bundle_translate_oid=str(payload["bundle_translate_oid"]),
        bundle_live_target=str(payload["bundle_live_target"]),
        walk_root=str(payload["walk_root"]),
        notification_target=str(payload["notification_target"]),
        skip_live=bool(payload["skip_live"]),
        skip_notifications=bool(payload["skip_notifications"]),
        skip_responder=bool(payload["skip_responder"]),
        report_json=None
        if payload["report_json"] is None
        else Path(payload["report_json"]).resolve(),
    )


def _validate_worker(settings: WorkerSettings) -> ValidationReport:
    from importlib import metadata

    report = ValidationReport(
        work_dir=str(settings.work_dir),
        tsnmp_version=metadata.version("trishul-snmp"),
        tsmi_version=metadata.version("trishul-smi"),
        tsnmp_spec=settings.tsnmp_spec,
        tsmi_spec=settings.tsmi_spec,
    )
    ctx = WorkerContext(
        settings=settings,
        report=report,
        plain_dir=settings.work_dir / "compile-plain",
        manifest_dir=settings.work_dir / "compile-manifest",
        full_dir=settings.work_dir / "compile-full",
    )

    _record_step(
        ctx, "tsmi CLI version", lambda: _validate_cli_version(ctx.tsmi_bin, report.tsmi_version)
    )
    _record_step(
        ctx, "tsnmp CLI version", lambda: _validate_cli_version(ctx.tsnmp_bin, report.tsnmp_version)
    )
    _record_step(ctx, "tsmi compile plain JSON", lambda: _compile_bundle(ctx, ctx.plain_dir))
    _record_step(
        ctx,
        "tsmi compile JSON plus manifest",
        lambda: _compile_bundle(ctx, ctx.manifest_dir, emit_manifest=True),
    )
    _record_step(
        ctx,
        "tsmi compile JSON plus sidecars",
        lambda: _compile_bundle(
            ctx,
            ctx.full_dir,
            emit_manifest=True,
            emit_oid_index=True,
        ),
    )
    _record_step(ctx, "single-module JSON metadata", lambda: _validate_module_json(ctx))
    _record_step(ctx, "bundle sidecar contract", lambda: _validate_sidecars(ctx))
    _record_step(
        ctx, "standalone module runtime load", lambda: _validate_single_module_runtime(ctx)
    )
    _record_step(ctx, "full bundle runtime load", lambda: _validate_full_bundle_runtime(ctx))
    _record_step(ctx, "tsnmp CLI translate smoke", lambda: _validate_tsnmp_cli_translate(ctx))
    _record_step(ctx, "live agent validation", lambda: _validate_live_agent(ctx))
    _record_step(ctx, "notification validation", lambda: _validate_notifications(ctx))
    _record_step(ctx, "responder validation", lambda: _validate_responder(ctx))
    return report


def _record_step(ctx: WorkerContext, name: str, action: Any) -> None:
    started = time.perf_counter_ns()
    try:
        detail = str(action())
    except SkippedStepError as exc:
        status = "skipped"
        detail = str(exc)
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        detail = _format_exception(exc)
    else:
        status = "passed"
    duration_ms = (time.perf_counter_ns() - started) / 1_000_000
    ctx.report.steps.append(
        StepResult(name=name, status=status, detail=detail, duration_ms=duration_ms)
    )


def _validate_cli_version(binary: Path, expected_version: str) -> str:
    completed = _run_checked([str(binary), "version"], cwd=REPO_ROOT)
    actual = completed.stdout.strip()
    if actual != expected_version and not actual.endswith(f" {expected_version}"):
        raise ValidationError(
            f"{binary.name} version mismatch: expected {expected_version}, got {actual}"
        )
    return actual


def _compile_bundle(
    ctx: WorkerContext,
    output_dir: Path,
    *,
    emit_manifest: bool = False,
    emit_oid_index: bool = False,
) -> str:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [str(ctx.tsmi_bin), "compile", *ctx.settings.mibs, "-o", str(output_dir)]
    for mib_dir in ctx.settings.mib_dirs:
        command.extend(["-d", str(mib_dir)])
    if ctx.settings.online:
        command.append("--online")
    for source in ctx.settings.sources:
        command.extend(["--source", source])
    if emit_manifest:
        command.append("--emit-manifest")
    if emit_oid_index:
        command.append("--emit-oid-index")
    command.extend(["--cache-dir", ctx.settings.cache_dir])
    _run_checked(command, cwd=REPO_ROOT)

    module_files = tuple(
        sorted(path for path in output_dir.glob("*.json") if path.name not in SIDE_CAR_FILENAMES)
    )
    if not module_files:
        raise ValidationError(f"tsmi produced no module JSON files in {output_dir}")

    artifacts = CompileArtifacts(output_dir=output_dir, module_files=module_files)
    if output_dir == ctx.plain_dir:
        ctx.plain_compile = artifacts
    elif output_dir == ctx.manifest_dir:
        ctx.manifest_compile = artifacts
    elif output_dir == ctx.full_dir:
        ctx.full_compile = artifacts

    if emit_manifest and not (output_dir / "manifest.json").exists():
        raise ValidationError("manifest.json was requested but not emitted")
    if emit_oid_index and not (output_dir / "oid_index.json").exists():
        raise ValidationError("oid_index.json was requested but not emitted")

    return f"modules={len(module_files)} output_dir={output_dir}"


def _validate_module_json(ctx: WorkerContext) -> str:
    single_path = ctx.single_module_file
    if not single_path.exists():
        raise ValidationError(f"expected standalone module file {single_path} was not emitted")
    payload = _read_json(single_path)
    for key in ("module", "schema_version", "producer_version", "generated_by", "generated_at"):
        if not payload.get(key):
            raise ValidationError(f"{single_path.name} is missing required field {key!r}")
    if payload["module"] != ctx.settings.single_module:
        raise ValidationError(
            f"expected module {ctx.settings.single_module}, got {payload['module']!r}"
        )
    if payload["producer_version"] != ctx.report.tsmi_version:
        raise ValidationError(
            f"producer_version mismatch: expected {ctx.report.tsmi_version}, "
            f"got {payload['producer_version']!r}"
        )
    return (
        f"module={payload['module']} schema_version={payload['schema_version']} "
        f"producer_version={payload['producer_version']}"
    )


def _validate_sidecars(ctx: WorkerContext) -> str:
    manifest_path = ctx.full_dir / "manifest.json"
    oid_index_path = ctx.full_dir / "oid_index.json"
    manifest = _read_json(manifest_path)
    raw_modules = manifest.get("modules")
    if not isinstance(raw_modules, list) or not raw_modules:
        raise ValidationError("manifest.json is missing a non-empty modules list")

    module_files: list[str] = []
    for entry in raw_modules:
        if isinstance(entry, str):
            file_name = entry
        elif isinstance(entry, dict) and isinstance(entry.get("file"), str):
            file_name = entry["file"]
        else:
            raise ValidationError("manifest.json contains an invalid module entry")
        if file_name in module_files:
            raise ValidationError(
                f"manifest.json contains a duplicate module entry for {file_name}"
            )
        if not (ctx.full_dir / file_name).exists():
            raise ValidationError(f"manifest.json references a missing module file {file_name}")
        module_files.append(file_name)

    sidecars = manifest.get("sidecars")
    if sidecars is not None:
        if not isinstance(sidecars, dict):
            raise ValidationError("manifest.json sidecars field must be an object when present")
        if sidecars.get("oid_index") != "oid_index.json":
            raise ValidationError("manifest.json sidecars.oid_index must reference oid_index.json")

    oid_index = _read_json(oid_index_path)
    raw_oids = oid_index.get("oids", oid_index)
    if not isinstance(raw_oids, dict) or not raw_oids:
        raise ValidationError("oid_index.json is missing a non-empty oids map")

    return f"manifest_modules={len(module_files)} oid_index_entries={len(raw_oids)}"


def _validate_single_module_runtime(ctx: WorkerContext) -> str:
    from trishul_snmp import load_bundle

    bundle = load_bundle(ctx.single_module_file)
    translated = bundle.translate(ctx.settings.single_translate_target)
    round_trip = bundle.translate(translated)
    if round_trip != ctx.settings.single_translate_target:
        raise ValidationError(
            "standalone bundle round-trip mismatch: "
            f"expected {ctx.settings.single_translate_target}, got {round_trip}"
        )
    if len(bundle.modules) != 1:
        raise ValidationError(f"expected exactly one loaded module, got {len(bundle.modules)}")
    return f"{ctx.settings.single_translate_target} <-> {translated}"


def _validate_full_bundle_runtime(ctx: WorkerContext) -> str:
    from trishul_snmp import load_bundle

    bundle = load_bundle(ctx.full_dir)
    translated = bundle.translate(ctx.settings.bundle_translate_oid)
    if not translated.startswith("SNMPv2-MIB::sysUpTime.0"):
        raise ValidationError(
            f"unexpected bundle translation for {ctx.settings.bundle_translate_oid}: {translated}"
        )
    return f"{ctx.settings.bundle_translate_oid} -> {translated}; modules={len(bundle.modules)}"


def _validate_tsnmp_cli_translate(ctx: WorkerContext) -> str:
    completed = _run_checked(
        [
            str(ctx.tsnmp_bin),
            "translate",
            "--bundle",
            str(ctx.single_module_file),
            ctx.settings.single_translate_target,
        ],
        cwd=REPO_ROOT,
    )
    translated = completed.stdout.strip()
    if not translated or not translated[0].isdigit():
        raise ValidationError(f"unexpected tsnmp translate output: {translated!r}")
    return f"{ctx.settings.single_translate_target} -> {translated}"


def _validate_live_agent(ctx: WorkerContext) -> str:
    if ctx.settings.skip_live:
        raise SkippedStepError("disabled via --skip-live")

    from trishul_snmp import ErrorStatus, V2cManager, load_bundle

    single_bundle = load_bundle(ctx.single_module_file)
    full_bundle = load_bundle(ctx.full_dir)

    async def scenario() -> str:
        async with V2cManager(
            host=ctx.settings.host,
            port=ctx.settings.port,
            community=ctx.settings.community,
            timeout=ctx.settings.timeout,
            retries=ctx.settings.retries,
        ) as manager:
            numeric = await manager.get("1.3.6.1.2.1.1.3.0")

        async with V2cManager(
            host=ctx.settings.host,
            port=ctx.settings.port,
            community=ctx.settings.community,
            timeout=ctx.settings.timeout,
            retries=ctx.settings.retries,
            bundle=single_bundle,
        ) as manager:
            symbolic_single = await manager.get(ctx.settings.single_live_target)

        async with V2cManager(
            host=ctx.settings.host,
            port=ctx.settings.port,
            community=ctx.settings.community,
            timeout=ctx.settings.timeout,
            retries=ctx.settings.retries,
            bundle=full_bundle,
        ) as manager:
            symbolic_bundle = await manager.get(ctx.settings.bundle_live_target)
            walked = await manager.walk(
                ctx.settings.walk_root,
                max_repetitions=ctx.settings.max_repetitions,
            )
            bulk_walked = await manager.bulkwalk(
                ctx.settings.walk_root,
                max_repetitions=ctx.settings.max_repetitions,
            )

        for response in (numeric, symbolic_single, symbolic_bundle):
            if response.error_status is not ErrorStatus.NO_ERROR:
                raise ValidationError(
                    "live GET returned "
                    f"{response.error_status.label} at index {response.error_index}"
                )
            if not response.varbinds:
                raise ValidationError("live GET returned no varbinds")

        if not walked:
            raise ValidationError(f"walk {ctx.settings.walk_root} returned no varbinds")
        if not bulk_walked:
            raise ValidationError(f"bulkwalk {ctx.settings.walk_root} returned no varbinds")
        if any(varbind.display_name is None for varbind in walked[:1]):
            raise ValidationError("live walk did not enrich display names")

        return (
            f"numeric={numeric.varbinds[0].display_value} "
            f"single={symbolic_single.varbinds[0].display_name} "
            f"bundle={symbolic_bundle.varbinds[0].display_name} "
            f"walk={len(walked)} bulkwalk={len(bulk_walked)}"
        )

    detail = _run_async(scenario())

    cli_get = _run_checked(
        [
            str(ctx.tsnmp_bin),
            "get",
            "--host",
            ctx.settings.host,
            "--port",
            str(ctx.settings.port),
            "--community",
            ctx.settings.community,
            "--timeout",
            str(ctx.settings.timeout),
            "--retries",
            str(ctx.settings.retries),
            "--bundle",
            str(ctx.full_dir),
            "--json",
            ctx.settings.bundle_live_target,
        ],
        cwd=REPO_ROOT,
    )
    payload = json.loads(cli_get.stdout)
    if payload.get("error_status") != "no_error":
        raise ValidationError(f"tsnmp CLI live get failed: {payload}")
    return f"{detail}; cli_display={payload['varbinds'][0].get('display_name')}"


def _validate_notifications(ctx: WorkerContext) -> str:
    if ctx.settings.skip_notifications:
        raise SkippedStepError("disabled via --skip-notifications")

    from trishul_snmp import (
        ErrorStatus,
        V2cNotificationListener,
        V2cNotifier,
        decode_notification,
        load_bundle,
    )
    from trishul_snmp.notify.client import encode_notification_raw_varbinds
    from trishul_snmp.wire.message import SnmpMessage, encode_message
    from trishul_snmp.wire.pdu import Pdu, PduType

    bundle = load_bundle(ctx.full_dir)
    varbinds = _notification_varbinds()
    notification_oid = bundle.resolve(ctx.settings.notification_target)

    async def scenario() -> tuple[str, str]:
        async with V2cNotificationListener(
            host="127.0.0.1",
            port=0,
            communities=[ctx.settings.community],
            bundle=bundle,
        ) as listener:
            listener_port = _listener_port(listener)
            async with V2cNotifier(
                host="127.0.0.1",
                port=listener_port,
                community=ctx.settings.community,
                timeout=ctx.settings.timeout,
                retries=0,
                bundle=bundle,
            ) as notifier:
                trap_task = _run_asyncio_task(
                    notifier.send_trap(
                        ctx.settings.notification_target,
                        varbinds=varbinds,
                        uptime=55,
                    )
                )
                trap_event = await _await_with_timeout(
                    listener.receive(), timeout=max(2.0, ctx.settings.timeout * 5)
                )
                trap_request_id = await trap_task

                inform_task = _run_asyncio_task(
                    notifier.send_inform(
                        ctx.settings.notification_target,
                        varbinds=varbinds,
                        uptime=66,
                    )
                )
                inform_event = await _await_with_timeout(
                    listener.receive(), timeout=max(2.0, ctx.settings.timeout * 5)
                )
                inform_response = await _await_with_timeout(
                    inform_task, timeout=max(2.0, ctx.settings.timeout * 5)
                )

        if trap_event.request_id != trap_request_id:
            raise ValidationError("trap listener request_id did not match the sender request_id")
        _assert_notification_event(
            trap_event, expected_name=ctx.settings.notification_target, expected_uptime=55
        )
        _assert_notification_event(
            inform_event,
            expected_name=ctx.settings.notification_target,
            expected_uptime=66,
        )
        if not inform_event.is_inform:
            raise ValidationError("inform event was not marked as inform")
        if inform_response.error_status is not ErrorStatus.NO_ERROR:
            raise ValidationError(f"inform response returned {inform_response.error_status.label}")
        return trap_event.notification_name or "", inform_event.notification_name or ""

    trap_name, inform_name = _run_async(scenario())

    raw_message = encode_message(
        SnmpMessage(
            version=1,
            community=ctx.settings.community,
            pdu=Pdu(
                pdu_type=PduType.SNMPV2_TRAP,
                request_id=999,
                error_status=0,
                error_index=0,
                varbinds=encode_notification_raw_varbinds(
                    notification_oid,
                    varbinds=varbinds,
                    uptime=77,
                    bundle=bundle,
                ),
            ),
        )
    )
    offline_event = decode_notification(
        raw_message,
        bundle=bundle,
        source_address=("127.0.0.1", 49162),
    )
    _assert_notification_event(
        offline_event,
        expected_name=ctx.settings.notification_target,
        expected_uptime=77,
    )

    return (
        f"trap={trap_name} inform={inform_name} "
        f"members={len(offline_event.member_bindings)} offline_uptime={offline_event.uptime}"
    )


def _validate_responder(ctx: WorkerContext) -> str:
    if ctx.settings.skip_responder:
        raise SkippedStepError("disabled via --skip-responder")

    from trishul_snmp import (
        ErrorStatus,
        IntegerValue,
        OctetStringValue,
        TimeTicksValue,
        V2cManager,
        V2cResponder,
        load_bundle,
    )
    from trishul_snmp._runtime import response_from_pdu
    from trishul_snmp.transport.dispatcher import RequestDispatcher
    from trishul_snmp.transport.udp import UdpClient
    from trishul_snmp.wire.pdu import PduType, build_raw_varbinds

    bundle = load_bundle(ctx.full_dir)

    async def scenario() -> str:
        async with V2cResponder(
            host="127.0.0.1",
            port=0,
            communities=[ctx.settings.community],
            bundle=bundle,
        ) as responder:
            responder.set_objects(
                [
                    ("1.3.6.1.2.1.1.3.0", TimeTicksValue(12345)),
                    ("IF-MIB::ifIndex.1", IntegerValue(1)),
                    ("IF-MIB::ifIndex.2", IntegerValue(2)),
                    ("IF-MIB::ifDescr.1", OctetStringValue(b"eth0")),
                    ("IF-MIB::ifDescr.2", OctetStringValue(b"eth1")),
                ]
            )
            port = _responder_port(responder)
            serve_task = _run_asyncio_task(responder.serve(count=4))

            async with V2cManager(
                host="127.0.0.1",
                port=port,
                community=ctx.settings.community,
                timeout=ctx.settings.timeout,
                retries=0,
                bundle=bundle,
            ) as manager:
                get_response = await manager.get("IF-MIB::ifDescr.1")
                next_response = await manager.get_next(ctx.settings.walk_root)
                bulk_response = await manager.get_bulk(
                    ctx.settings.walk_root,
                    non_repeaters=0,
                    max_repetitions=3,
                )

            client = UdpClient("127.0.0.1", port)
            dispatcher = RequestDispatcher(
                client,
                community=ctx.settings.community,
                timeout=ctx.settings.timeout,
                retries=0,
            )
            await client.open()
            try:
                set_pdu = await dispatcher.send_pdu(
                    PduType.SET,
                    build_raw_varbinds(
                        (
                            (
                                bundle.resolve("IF-MIB::ifDescr.1"),
                                OctetStringValue(b"mutate"),
                            ),
                        )
                    ),
                )
            finally:
                await client.close()

            set_response = response_from_pdu(set_pdu, bundle=bundle)
            handled = await serve_task

        if get_response.error_status is not ErrorStatus.NO_ERROR:
            raise ValidationError(f"responder GET failed with {get_response.error_status.label}")
        if get_response.varbinds[0].display_value != "eth0":
            raise ValidationError(
                "responder GET returned unexpected value "
                f"{get_response.varbinds[0].display_value!r}"
            )
        if (
            not next_response.varbinds
            or next_response.varbinds[0].display_name != "IF-MIB::ifIndex.1"
        ):
            raise ValidationError("responder GETNEXT did not return IF-MIB::ifIndex.1")
        if len(bulk_response.varbinds) != 3:
            raise ValidationError(
                f"expected 3 varbinds from responder GETBULK, got {len(bulk_response.varbinds)}"
            )
        if (
            set_response.error_status is not ErrorStatus.NOT_WRITABLE
            or set_response.error_index != 1
        ):
            raise ValidationError(
                "responder SET rejection mismatch: "
                f"{set_response.error_status.label} index={set_response.error_index}"
            )
        if handled != 4:
            raise ValidationError(f"expected responder to handle 4 requests, got {handled}")

        return (
            f"get={get_response.varbinds[0].display_value} "
            f"next={next_response.varbinds[0].display_name} "
            f"bulk={len(bulk_response.varbinds)} set={set_response.error_status.label}"
        )

    return _run_async(scenario())


def _notification_varbinds() -> tuple[tuple[str, object], ...]:
    from trishul_snmp import IntegerValue

    return (
        ("IF-MIB::ifIndex.1", IntegerValue(1)),
        ("IF-MIB::ifAdminStatus.1", IntegerValue(1)),
        ("IF-MIB::ifOperStatus.1", IntegerValue(2)),
    )


def _assert_notification_event(event: Any, *, expected_name: str, expected_uptime: int) -> None:
    if event.notification_name != expected_name:
        raise ValidationError(
            f"notification name mismatch: expected {expected_name}, got {event.notification_name!r}"
        )
    if event.notification_description is None or not event.notification_description.strip():
        raise ValidationError("notification description was not retained")
    if event.uptime != expected_uptime:
        raise ValidationError(
            f"notification uptime mismatch: expected {expected_uptime}, got {event.uptime!r}"
        )
    if not event.member_bindings:
        raise ValidationError("notification member bindings were not retained")
    if event.member_bindings[0].varbind is None:
        raise ValidationError("first notification member binding was not paired with a varbind")


def _listener_port(listener: Any) -> int:
    local_address = listener.local_address
    if local_address is None:
        raise ValidationError("notification listener did not expose a local address")
    return int(local_address[1])


def _responder_port(responder: Any) -> int:
    local_address = responder.local_address
    if local_address is None:
        raise ValidationError("responder did not expose a local address")
    return int(local_address[1])


def _run_async(coro: Any) -> Any:
    import asyncio

    return asyncio.run(coro)


async def _await_with_timeout(awaitable: Any, *, timeout: float) -> Any:
    import asyncio

    return await asyncio.wait_for(awaitable, timeout=timeout)


def _run_asyncio_task(coro: Any) -> Any:
    import asyncio

    return asyncio.create_task(coro)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _render_report(report: ValidationReport) -> str:
    lines = [
        "Ecosystem validation",
        f"work_dir: {report.work_dir}",
        f"trishul-snmp: {report.tsnmp_version} ({report.tsnmp_spec})",
        f"trishul-smi: {report.tsmi_version} ({report.tsmi_spec})",
        "",
    ]
    for step in report.steps:
        marker = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}[step.status]
        lines.append(f"[{marker}] {step.name} ({step.duration_ms:.1f} ms)")
        lines.append(f"      {step.detail}")
    return "\n".join(lines)


def _format_exception(exc: Exception) -> str:
    if isinstance(exc, subprocess.CalledProcessError):
        return _format_command_failure(exc)
    return f"{type(exc).__name__}: {exc}"


def _format_command_failure(exc: subprocess.CalledProcessError) -> str:
    stdout = exc.stdout.strip() if isinstance(exc.stdout, str) else ""
    stderr = exc.stderr.strip() if isinstance(exc.stderr, str) else ""
    detail = f"command failed with exit code {exc.returncode}: {' '.join(exc.cmd)}"
    if stdout:
        detail += f"; stdout={stdout!r}"
    if stderr:
        detail += f"; stderr={stderr!r}"
    return detail


def _run_checked(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
        env=_subprocess_env(),
    )


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def _venv_bin_dir(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts" if os.name == "nt" else "bin")


def _venv_executable(bin_dir: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return bin_dir / f"{name}{suffix}"


if __name__ == "__main__":
    raise SystemExit(main())
