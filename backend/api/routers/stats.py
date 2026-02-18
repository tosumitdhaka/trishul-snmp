"""
api/routers/stats.py
~~~~~~~~~~~~~~~~~~~~
Aggregated stats endpoints for all backend modules.

Endpoints:
  GET    /api/stats/           — all modules, enriched with live runtime fields
  GET    /api/stats/{module}   — single module slice (simulator|traps|walker|mibs)
  DELETE /api/stats/           — reset all stats to zero (useful for testing)
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
    runtime fields from running processes (pid, port, running state).
    """
    stats = stats_store.load()

    # --- Simulator runtime enrichment ---
    try:
        sim = SimulatorManager.status()
        stats["simulator"]["running"] = sim.get("running", False)
        stats["simulator"]["pid"]     = sim.get("pid")
        stats["simulator"]["port"]    = sim.get("port")
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

    # --- MIB runtime enrichment ---
    try:
        mib_status = get_mib_service().get_status()
        stats["mibs"]["loaded"] = mib_status.get("loaded", 0)
        stats["mibs"]["failed"] = mib_status.get("failed", 0)
    except Exception as e:
        logger.warning(f"Could not enrich mib stats: {e}")

    return stats


@router.get("/{module}")
def get_module_stats(module: str):
    """
    Return stats for a single module.
    Valid modules: simulator, traps, walker, mibs
    """
    if module not in VALID_MODULES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown module '{module}'. Valid modules: {sorted(VALID_MODULES)}"
        )
    stats = stats_store.load()
    return {module: stats.get(module, {})}


@router.delete("/")
def reset_stats():
    """Reset all stats to zero defaults. Useful for testing / clean slate."""
    stats_store.reset()
    return {"status": "reset", "message": "All stats reset to defaults"}
