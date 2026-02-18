"""
api/routers/simulator.py
~~~~~~~~~~~~~~~~~~~~~~~~
Simulator lifecycle endpoints + custom data management.
Stats are persisted to stats.json via stats_store.

Bug fixes:
  BUG-8  : restart() now preserves saved port/community (via sim_manager fix)
  BUG-12 : single restart code path (sim_manager.restart uses start/stop)
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.sim_manager import SimulatorManager
from core.config import settings
from core import stats_store

router = APIRouter(prefix="/simulator", tags=["Simulator"])
logger = logging.getLogger(__name__)

class SimConfig(BaseModel):
    port: Optional[int] = None
    community: Optional[str] = None

# In-memory start time for run-seconds calculation.
# Resets on container restart — only used for delta calculation, not persisted.
_sim_start_time: Optional[datetime] = None


def _record_stop_stats() -> None:
    """Calculate elapsed run time and persist stop stats atomically."""
    global _sim_start_time
    s = stats_store.load()
    elapsed = 0
    if _sim_start_time:
        elapsed = int((datetime.now(timezone.utc) - _sim_start_time).total_seconds())
        _sim_start_time = None
    stats_store.update_module("simulator", {
        "stop_count": s["simulator"]["stop_count"] + 1,
        "simulator_run_seconds": s["simulator"]["simulator_run_seconds"] + elapsed
    })


@router.get("/status")
def get_status():
    status = SimulatorManager.status()
    running = status.get("running", False)
    if running and _sim_start_time:
        delta = datetime.now(timezone.utc) - _sim_start_time
        status["uptime"] = str(delta).split(".")[0]
    else:
        status["uptime"] = None
    return status


@router.post("/start")
def start_simulator(config: SimConfig = None):
    global _sim_start_time
    p = config.port if config else None
    c = config.community if config else None

    current_status = SimulatorManager.status()
    if current_status.get("running"):
        return {
            "status": "already_running",
            "message": "Simulator is already running",
            "pid": current_status.get("pid"),
            "port": current_status.get("port"),
            "community": current_status.get("community")
        }

    result = SimulatorManager.start(port=p, community=c)

    if result.get("status") == "started":
        _sim_start_time = datetime.now(timezone.utc)
        stats_store.increment("simulator", "start_count")
        return {
            "status": "started",
            "message": "Simulator started successfully",
            "pid": result.get("pid"),
            "port": result.get("port"),
            "community": result.get("community")
        }

    return result


@router.post("/stop")
def stop_simulator():
    result = SimulatorManager.stop()
    if result.get("status") == "stopped":
        _record_stop_stats()
        return {"status": "stopped", "message": "Simulator stopped successfully"}
    return result


@router.post("/restart")
def restart_simulator():
    global _sim_start_time
    # Record stop stats for the current run before restarting
    _record_stop_stats()

    import time
    time.sleep(0.5)

    # BUG-8/BUG-12: SimulatorManager.restart() now preserves port/community
    start_result = SimulatorManager.restart()

    if start_result.get("status") == "started":
        _sim_start_time = datetime.now(timezone.utc)
        stats_store.increment("simulator", "restart_count")
        return {
            "status": "restarted",
            "message": "Simulator restarted successfully",
            "pid": start_result.get("pid"),
            "port": start_result.get("port"),
            "community": start_result.get("community")
        }
    return start_result


@router.get("/data")
def get_custom_data():
    try:
        if not settings.CUSTOM_DATA_FILE.exists():
            return {}
        with open(settings.CUSTOM_DATA_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load custom data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data")
def update_custom_data(data: dict):
    try:
        os.makedirs(settings.CUSTOM_DATA_FILE.parent, exist_ok=True)
        with open(settings.CUSTOM_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)

        sim_status = SimulatorManager.status()
        if sim_status.get("running"):
            SimulatorManager.restart()
            msg = "Data saved and simulator restarted"
        else:
            msg = "Data saved (simulator is currently stopped)"

        logger.info(f"Custom data updated: {len(data)} entries")
        return {"status": "saved", "message": msg}
    except Exception as e:
        logger.error(f"Failed to save custom data: {e}")
        raise HTTPException(status_code=500, detail=str(e))
