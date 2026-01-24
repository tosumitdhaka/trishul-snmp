from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.walk_engine import WalkEngine
from core.config import settings

router = APIRouter(prefix="/walk", tags=["Walker"])

class WalkRequest(BaseModel):
    target: str = "127.0.0.1"
    port: int = 1061
    community: str = "public"
    oid: str
    parse: bool = True
    use_mibs: bool = True

@router.post("/execute")
def execute_walk(req: WalkRequest):
    # Pass use_mibs to engine
    raw_lines = WalkEngine.run_snmpwalk(
        req.target, req.port, req.community, req.oid, req.use_mibs
    )
    
    if isinstance(raw_lines, dict) and "error" in raw_lines:
        raise HTTPException(status_code=500, detail=raw_lines["error"])
        
    if not req.parse:
        return {
            "mode": "raw",
            "count": len(raw_lines),
            "data": raw_lines
        }

    # 3. Parse
    json_result = WalkEngine.parse_output(raw_lines, req.target, req.oid)
    
    return {
        "mode": "parsed",
        "count": len(json_result),
        "data": json_result
    }
