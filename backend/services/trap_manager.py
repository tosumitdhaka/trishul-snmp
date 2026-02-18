"""
services/trap_manager.py
~~~~~~~~~~~~~~~~~~~~~~~~
Manages the trap_receiver subprocess lifecycle.

Bug fixes:
  BUG-9  : get_status() now uses self._port instead of hardcoded 1162
  BUG-10 : clear_traps() uses context manager (no file handle leak)
"""

import os
import sys
import json
import logging
import subprocess
from datetime import datetime, timezone
from typing import Optional
from core.config import settings
from core import stats_store

logger = logging.getLogger(__name__)


class TrapManager:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.log_file  = str(settings.TRAPS_FILE)
        self.mib_path  = str(settings.MIB_DIR)
        self.resolve_mibs = True
        self._port: int = settings.TRAP_PORT
        self._community: str = settings.COMMUNITY
        self._start_time: Optional[datetime] = None

        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

    def start(self, port: int = None, community: str = None, resolve_mibs: bool = True):
        if self.process and self.process.poll() is None:
            return {"status": "already_running", "pid": self.process.pid}

        if port is not None:
            self._port = port
        if community is not None:
            self._community = community
        self.resolve_mibs = resolve_mibs

        cmd = [
            sys.executable, "workers/trap_receiver.py",
            "--port",         str(self._port),
            "--community",    self._community,
            "--mib-path",     self.mib_path,
            "--output",       self.log_file,
            "--resolve-mibs", "true" if resolve_mibs else "false",
        ]

        self.process = subprocess.Popen(
            cmd,
            cwd=str(settings.BASE_DIR),
            stdout=sys.stdout,
            stderr=sys.stderr
        )

        self._start_time = datetime.now(timezone.utc)
        stats_store.increment("traps", "receiver_start_count")
        logger.info(f"Trap receiver started: pid={self.process.pid} port={self._port}")
        return {"status": "started", "pid": self.process.pid, "port": self._port, "resolve_mibs": resolve_mibs}

    def stop(self):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()

            self.process = None

            # BUG-9 fix + run-seconds tracking
            elapsed = 0
            if self._start_time:
                elapsed = int((datetime.now(timezone.utc) - self._start_time).total_seconds())
                self._start_time = None

            s = stats_store.load()
            stats_store.update_module("traps", {
                "receiver_stop_count":  s["traps"]["receiver_stop_count"] + 1,
                "receiver_run_seconds": s["traps"]["receiver_run_seconds"] + elapsed,
            })
            return {"status": "stopped"}
        return {"status": "not_running"}

    def get_status(self):
        running = self.process is not None and self.process.poll() is None
        return {
            "running":      running,
            "pid":          self.process.pid if running else None,
            "port":         self._port,           # BUG-9: use stored port, not hardcoded 1162
            "resolve_mibs": self.resolve_mibs if running else None,
        }

    def get_traps(self, limit: int = 50):
        data = []
        if not os.path.exists(self.log_file):
            return []
        try:
            with open(self.log_file, 'r') as f:   # BUG-10: already a context manager
                lines = f.readlines()
            for line in reversed(lines[-limit:]):
                if line.strip():
                    try:
                        data.append(json.loads(line))
                    except Exception:
                        pass
        except Exception:
            pass
        return data

    def clear_traps(self):
        # BUG-10: use context manager — no file handle leak
        with open(self.log_file, 'w'):
            pass
        stats_store.increment("traps", "traps_cleared_count")


trap_manager = TrapManager()
