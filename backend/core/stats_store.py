"""
core/stats_store.py
~~~~~~~~~~~~~~~~~~~
Lightweight, file-backed stats store shared by all backend modules.

All modules (simulator, traps, walker, mibs) write events here via
increment(), set_field(), or update_module(). The /api/stats router
reads from here to serve dashboard-facing stats.

File location: data/configs/stats.json  (volume-mounted, persists across restarts)

Thread safety:
  - API process: _lock (threading.Lock) guards all reads + writes.
  - Worker subprocesses (snmp_simulator, trap_receiver): they write directly
    to the JSON file using atomic rename (tempfile + os.replace) via
    worker_increment() / worker_set_field() to avoid partial-write corruption.
"""

import json
import os
import tempfile
from copy import deepcopy
from threading import Lock
from typing import Any
from core.config import settings

_lock = Lock()

# ---------------------------------------------------------------------------
# Schema — all keys that every module tracks.
# New keys added here will automatically appear in existing stats.json files
# on the next load() call (merge-with-defaults logic).
# ---------------------------------------------------------------------------

DEFAULT_STATS: dict[str, dict] = {
    "simulator": {
        "start_count": 0,
        "stop_count": 0,
        "restart_count": 0,
        "oids_loaded": 0,
        "snmp_requests_served": 0,
        "last_started": None,
        "last_stopped": None,
    },
    "traps": {
        "receiver_start_count": 0,
        "receiver_stop_count": 0,
        "traps_received_total": 0,
        "traps_cleared_count": 0,
        "last_trap_source": None,
        "last_trap_time": None,
    },
    "walker": {
        "walks_executed": 0,
        "walks_failed": 0,
        "last_walk_target": None,
        "last_walk_oid": None,
        "last_walk_time": None,
    },
    "mibs": {
        "reload_count": 0,
        "upload_count": 0,
        "delete_count": 0,
        "last_reload_time": None,
    },
}

VALID_MODULES = set(DEFAULT_STATS.keys())


# ---------------------------------------------------------------------------
# Internal helpers  (call only while _lock is held)
# ---------------------------------------------------------------------------

def _load_unsafe() -> dict:
    """Load stats.json and merge with DEFAULT_STATS. No lock acquired."""
    if not settings.STATS_FILE.exists():
        return deepcopy(DEFAULT_STATS)
    try:
        with open(settings.STATS_FILE, "r") as f:
            on_disk = json.load(f)
        merged = deepcopy(DEFAULT_STATS)
        for module, values in on_disk.items():
            if module in merged and isinstance(values, dict):
                merged[module].update(values)
        return merged
    except Exception:
        return deepcopy(DEFAULT_STATS)


def _save_unsafe(stats: dict) -> None:
    """Write stats atomically via tempfile + os.replace. No lock acquired."""
    stats_path = settings.STATS_FILE
    os.makedirs(stats_path.parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=stats_path.parent, prefix="stats_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(stats, f, indent=2, default=str)
        os.replace(tmp_path, stats_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Public API  (used by routers + services inside the API process)
# ---------------------------------------------------------------------------

def load() -> dict:
    """Return a full copy of current stats merged with defaults."""
    with _lock:
        return _load_unsafe()


def save(stats: dict) -> None:
    """Overwrite entire stats file. Prefer update_module() for partial updates."""
    with _lock:
        _save_unsafe(stats)


def increment(module: str, key: str, by: int = 1) -> None:
    """Atomically increment a single integer counter."""
    with _lock:
        stats = _load_unsafe()
        stats.setdefault(module, {})
        stats[module][key] = stats[module].get(key, 0) + by
        _save_unsafe(stats)


def set_field(module: str, key: str, value: Any) -> None:
    """Atomically set a single field."""
    with _lock:
        stats = _load_unsafe()
        stats.setdefault(module, {})
        stats[module][key] = value
        _save_unsafe(stats)


def update_module(module: str, updates: dict) -> None:
    """
    Atomically apply multiple field updates for one module in a single
    read-modify-write cycle. Preferred over multiple set_field() calls
    when updating counter + timestamp together.
    """
    with _lock:
        stats = _load_unsafe()
        stats.setdefault(module, {})
        stats[module].update(updates)
        _save_unsafe(stats)


def reset() -> None:
    """Reset all stats to zero defaults."""
    with _lock:
        _save_unsafe(deepcopy(DEFAULT_STATS))


# ---------------------------------------------------------------------------
# Worker-safe helpers  (used by subprocess workers: snmp_simulator, trap_receiver)
# ---------------------------------------------------------------------------
# Workers run as separate processes and cannot share the in-process _lock.
# They use the same atomic-rename pattern directly to avoid partial writes.
# The API process lock only protects within the API process; cross-process
# safety relies on os.replace() being atomic on POSIX (Linux/macOS).

def worker_increment(stats_file: str, module: str, key: str, by: int = 1) -> None:
    """Increment a counter from a worker subprocess. Uses atomic rename."""
    try:
        if os.path.exists(stats_file):
            with open(stats_file, "r") as f:
                stats = json.load(f)
        else:
            stats = deepcopy(DEFAULT_STATS)

        stats.setdefault(module, {})
        stats[module][key] = stats[module].get(key, 0) + by

        parent = os.path.dirname(stats_file) or "."
        fd, tmp = tempfile.mkstemp(dir=parent, prefix="stats_", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(stats, f, indent=2, default=str)
        os.replace(tmp, stats_file)
    except Exception:
        pass  # never crash a worker over stats


def worker_set_field(stats_file: str, module: str, key: str, value: Any) -> None:
    """Set a field from a worker subprocess. Uses atomic rename."""
    try:
        if os.path.exists(stats_file):
            with open(stats_file, "r") as f:
                stats = json.load(f)
        else:
            stats = deepcopy(DEFAULT_STATS)

        stats.setdefault(module, {})
        stats[module][key] = value

        parent = os.path.dirname(stats_file) or "."
        fd, tmp = tempfile.mkstemp(dir=parent, prefix="stats_", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(stats, f, indent=2, default=str)
        os.replace(tmp, stats_file)
    except Exception:
        pass
