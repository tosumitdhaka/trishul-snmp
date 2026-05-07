"""Bundle loading entry points."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from trishul_snmp.errors import BundleValidationError
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.mib.models import MibModuleRecord
from trishul_snmp.mib.registry import (
    MibRegistry,
    _OidIndexEntry,
    normalize_module_payload,
    parse_oid,
)
from trishul_snmp.types import OID

_SIDECAR_FILENAMES = {"manifest.json", "oid_index.json"}


@dataclass(frozen=True, slots=True)
class _LoadedDirectory:
    module_paths: tuple[Path, ...]
    oid_index: dict[OID, _OidIndexEntry]


def load_bundle(path: str | Path) -> MibBundle:
    """Load a bundle from a module JSON file or a directory of module JSON files."""
    source = Path(path).expanduser()
    if source.is_file():
        module_record = _load_module_json(source)
        registry = MibRegistry({module_record.module: module_record})
        return MibBundle(registry, source=source)

    if source.is_dir():
        loaded = _discover_directory(source)
        modules = [_load_module_json(module_path) for module_path in loaded.module_paths]
        registry = MibRegistry(
            {module.module: module for module in modules},
            oid_index=loaded.oid_index,
        )
        return MibBundle(registry, source=source)

    raise BundleValidationError("Bundle path does not exist", path=source)


def _load_module_json(path: Path) -> MibModuleRecord:
    payload = _read_json(path)
    return normalize_module_payload(payload, path=path)


def _discover_directory(path: Path) -> _LoadedDirectory:
    manifest_path = path / "manifest.json"
    module_paths: tuple[Path, ...]
    if manifest_path.exists():
        module_paths = _module_paths_from_manifest(path, manifest_path)
    else:
        module_paths = tuple(
            sorted(
                candidate
                for candidate in path.glob("*.json")
                if candidate.name not in _SIDECAR_FILENAMES
            )
        )

    if not module_paths:
        raise BundleValidationError(
            "No module JSON files were found in bundle directory",
            path=path,
        )

    oid_index_path = path / "oid_index.json"
    oid_index = _load_oid_index(oid_index_path) if oid_index_path.exists() else {}
    return _LoadedDirectory(module_paths=module_paths, oid_index=oid_index)


def _module_paths_from_manifest(bundle_dir: Path, manifest_path: Path) -> tuple[Path, ...]:
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise BundleValidationError("Manifest must be a JSON object", path=manifest_path)

    raw_modules = manifest.get("modules")
    if not isinstance(raw_modules, list) or not raw_modules:
        raise BundleValidationError(
            "Manifest is missing a valid 'modules' list",
            path=manifest_path,
        )

    module_paths: list[Path] = []
    seen_files: set[Path] = set()
    for entry in raw_modules:
        file_name = _manifest_module_filename(entry, manifest_path=manifest_path)
        module_path = (bundle_dir / file_name).resolve()
        if bundle_dir.resolve() not in module_path.parents:
            raise BundleValidationError(
                "Manifest module file must stay within the bundle directory",
                path=manifest_path,
            )
        if module_path in seen_files:
            continue
        if not module_path.exists():
            raise BundleValidationError(
                f"Manifest references a missing module file {file_name!r}",
                path=manifest_path,
            )
        seen_files.add(module_path)
        module_paths.append(module_path)
    return tuple(module_paths)


def _manifest_module_filename(entry: object, *, manifest_path: Path) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        file_name = entry.get("file")
        if isinstance(file_name, str) and file_name:
            return file_name
    raise BundleValidationError(
        "Manifest modules must be strings or objects containing a 'file' field",
        path=manifest_path,
    )


def _load_oid_index(path: Path) -> dict[OID, _OidIndexEntry]:
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise BundleValidationError("OID index must be a JSON object", path=path)

    if "oids" in payload:
        raw_index = payload["oids"]
    else:
        raw_index = payload

    if not isinstance(raw_index, dict):
        raise BundleValidationError("OID index entries must be a JSON object", path=path)

    normalized: dict[OID, _OidIndexEntry] = {}
    for raw_oid, entry in raw_index.items():
        if not isinstance(raw_oid, str):
            raise BundleValidationError("OID index keys must be dotted-string OIDs", path=path)
        if not isinstance(entry, dict):
            raise BundleValidationError("OID index entries must be JSON objects", path=path)
        module = entry.get("module")
        symbol = entry.get("object") or entry.get("symbol")
        if not isinstance(module, str) or not isinstance(symbol, str):
            raise BundleValidationError(
                "OID index entries must contain string 'module' and 'object' fields",
                path=path,
            )
        normalized[parse_oid(raw_oid)] = _OidIndexEntry(module=module, symbol=symbol)
    return normalized


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BundleValidationError("Missing bundle artifact", path=path) from exc
    except json.JSONDecodeError as exc:
        raise BundleValidationError(f"Invalid JSON: {exc.msg}", path=path) from exc


def _iter_bundle_files(path: Path) -> Iterable[Path]:
    return sorted(candidate for candidate in path.glob("*.json"))
