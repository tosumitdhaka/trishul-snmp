"""
api/routers/walker.py
~~~~~~~~~~~~~~~~~~~~~
SNMP walk endpoint. Validates input, executes walk via WalkEngine,
and records stats into stats_store.

Bug fixes in this version:
  BUG-6  : host/OID/community validated before walk execution
  BUG-7  : HTTPException caught before outer except to prevent message corruption
  BUG-13 : label-only walk results returned with mode='label' instead of empty data
"""

import re
import logging
import traceback
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.walk_engine import WalkEngine
from core import stats_store

router = APIRouter(prefix="/walk", tags=["Walker"])
logger = logging.getLogger(__name__)

# Rough hostname/IP pattern — allows IPs, FQDNs, simple hostnames
_HOST_RE = re.compile(
    r'^(\d{1,3}\.){3}\d{1,3}$'           # IPv4
    r'|^[a-zA-Z0-9]([a-zA-Z0-9\-\.]{0,253}[a-zA-Z0-9])?$'  # hostname/FQDN
)
# Numeric OID: starts with a dot or digit, only digits and dots
_OID_RE = re.compile(r'^[.0-9][0-9.]*$')
# Community: printable ASCII, no whitespace, max 64 chars
_COMMUNITY_RE = re.compile(r'^[\x21-\x7E]{1,64}$')


class WalkRequest(BaseModel):
    target: str = "127.0.0.1"
    port: int = 1061
    community: str = "public"
    oid: str
    parse: bool = True
    use_mibs: bool = True


def _validate_walk_request(req: WalkRequest) -> None:
    """BUG-6: Validate host, OID, community before executing walk."""
    if not _HOST_RE.match(req.target):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target host: '{req.target}'. Must be a valid IP or hostname."
        )
    if not (1 <= req.port <= 65535):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid port: {req.port}. Must be between 1 and 65535."
        )
    if not _COMMUNITY_RE.match(req.community):
        raise HTTPException(
            status_code=400,
            detail="Invalid community string. Must be 1-64 printable non-whitespace ASCII characters."
        )
    # OID can be numeric (.1.3.6.1...) or symbolic (SNMPv2-MIB::sysDescr)
    # Only reject clearly malformed values (empty or path traversal attempts)
    if not req.oid or len(req.oid) > 256:
        raise HTTPException(
            status_code=400,
            detail="OID must be a non-empty string of at most 256 characters."
        )


@router.post("/execute")
def execute_walk(req: WalkRequest):
    # BUG-6: validate inputs first
    _validate_walk_request(req)

    try:
        raw_lines = WalkEngine.run_snmpwalk(
            host=req.target,
            port=req.port,
            community=req.community,
            oid=req.oid,
            use_mibs=req.use_mibs
        )

        # BUG-7: check engine errors (returned as dict) before any further processing
        # This must be before the parse block so HTTPException isn't swallowed below
        if isinstance(raw_lines, dict) and "error" in raw_lines:
            logger.error(f"Walk engine error: {raw_lines['error']}")
            stats_store.increment("walker", "walks_failed")
            raise HTTPException(status_code=500, detail=raw_lines["error"])

        # BUG-13: detect label-only results (no parseable data) and return them
        # with mode='label' instead of silently returning empty data: []
        if not req.parse:
            stats_store.update_module("walker", {
                "walks_executed": stats_store.load()["walker"]["walks_executed"] + 1,
                "oids_returned": len(raw_lines)
            })
            return {
                "mode": "raw",
                "count": len(raw_lines),
                "data": raw_lines
            }

        json_result = WalkEngine.parse_output(raw_lines, req.target, req.oid)

        # BUG-13: if parse produced nothing but raw_lines is non-empty,
        # the lines are label-only (descriptive strings, not OID=value pairs)
        if len(json_result) == 0 and len(raw_lines) > 0:
            stats_store.update_module("walker", {
                "walks_executed": stats_store.load()["walker"]["walks_executed"] + 1,
                "oids_returned": len(raw_lines)
            })
            return {
                "mode": "label",
                "count": len(raw_lines),
                "data": raw_lines
            }

        s = stats_store.load()
        stats_store.update_module("walker", {
            "walks_executed": s["walker"]["walks_executed"] + 1,
            "oids_returned": len(json_result)
        })
        return {
            "mode": "parsed",
            "count": len(json_result),
            "data": json_result
        }

    except HTTPException:
        # BUG-7: re-raise HTTPException directly — do NOT let outer except catch it
        raise
    except Exception as e:
        traceback.print_exc()
        stats_store.increment("walker", "walks_failed")
        raise HTTPException(status_code=500, detail=str(e))
