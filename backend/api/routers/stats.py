"""
api/routers/stats.py
~~~~~~~~~~~~~~~~~~~~
Aggregated stats endpoints for all backend modules.

Endpoints:
  GET    /api/stats/           - all modules, enriched with live runtime fields
  GET    /api/stats/{module}   - single module slice (simulator|traps|walker|mibs)
  DELETE /api/stats/           - reset all stats to zero (useful for testing)

Runtime-enriched fields (NOT persisted to stats.json):
  simulator : running, pid, port, community   <- SimulatorManager.status()
  traps     : running, pid                    <- trap_manager.get_status()
  mibs      : loaded_mibs, failed_mibs,
               total_mibs                     <- mib_service.get_status()
"""

import logging
from fastapi import APIRouter, HTTPException
from core import stats_store
from services.sim_manager import SimulatorManager
from services.trap_manager import trap_manager
from services.mib_service import get_mib_service

router = APIRouter(prefix="/stats", tags=["Stats"])
logger = logging.getLogger(__name__)

VALID_MODULES = stats_store.VALID_MODULES


@router.get("/")
def get_all_stats():
    """
    Return persisted stats for all modules, enriched with live
    runtime fields from running processes.
    """
    stats = stats_store.load()

    # --- Simulator runtime enrichment ---
    try:
        sim = SimulatorManager.status()
        stats["simulator"]["running"]   = sim.get("running", False)
        stats["simulator"]["pid"]       = sim.get("pid")
        stats["simulator"]["port"]      = sim.get("port")
        stats["simulator"]["community"] = sim.get("community")
    except Exception as e:
        logger.warning(f"Could not enrich simulator stats: {e}")
        stats["simulator"]["running"] = False

    # --- Trap receiver runtime enrichment ---
    try:
        trap = trap_manager.get_status()
        stats["traps"]["running"] = trap.get("running", False)
        stats["traps"]["pid"]     = trap.get("pid")
    except Exception as e:
        logger.warning(f"Could not enrich trap stats: {e}")
        stats["traps"]["running"] = False

    # --- MIB runtime enrichment (Option A: not persisted) ---
    try:
        mib_status = get_mib_service().get_status()
        loaded = mib_status.get("loaded", 0)
        failed = mib_status.get("failed", 0)
        stats["mibs"]["loaded_mibs"] = loaded
        stats["mibs"]["failed_mibs"] = failed
        stats["mibs"]["total_mibs"]  = loaded + failed
    except Exception as e:
        logger.warning(f"Could not enrich mib stats: {e}")

    return stats


@router.get("/{module}")
def get_module_stats(module: str):
    """
    Return persisted stats for a single module.
    Valid: simulator | traps | walker | mibs
    Runtime-only fields (running, pid, loaded_mibs etc.) are NOT included here.
    Use GET /api/stats/ for the full enriched view.
    """
    if module not in VALID_MODULES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown module '{module}'. Valid: {sorted(VALID_MODULES)}"
        )
    stats = stats_store.load()
    return {module: stats.get(module, {})}


@router.delete("/")
def reset_stats():
    """Reset all stats to zero defaults."""
    stats_store.reset()
    return {"status": "reset", "message": "All stats reset to defaults"}
