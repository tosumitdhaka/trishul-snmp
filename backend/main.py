import os
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.security import validate_auth
from core.log_config import setup_logging   # BUG-14: renamed from core.logging to avoid shadowing stdlib
from api.routers import simulator, walker, settings, traps, mibs, browser
from core.config import meta

setup_logging()

app = FastAPI(title=meta.NAME, version=meta.VERSION)

# ---------------------------------------------------------------------------
# CORS  (BUG-16)
# ---------------------------------------------------------------------------
# Use explicit origins instead of wildcard "*" — required when
# allow_credentials=True (browsers reject wildcard + credentials per spec).
# Set ALLOWED_ORIGINS in .env as a comma-separated list.
# Default: http://localhost:8080 (Nginx dev proxy)
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8080").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/meta")
def get_app_metadata():
    return {
        "name": meta.NAME,
        "version": meta.VERSION,
        "author": meta.AUTHOR,
        "description": meta.DESCRIPTION
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": meta.NAME,
        "version": meta.VERSION
    }


# ---------------------------------------------------------------------------
# Routers
# NOTE: files.py router is intentionally NOT registered here — it is
# deprecated and will be removed in Phase 3 (see issue #12).
# Canonical MIB file endpoints: /api/mibs/*
# Canonical data endpoints:     /api/simulator/*
# ---------------------------------------------------------------------------
app.include_router(simulator.router, prefix="/api", dependencies=[Depends(validate_auth)])
app.include_router(walker.router,    prefix="/api", dependencies=[Depends(validate_auth)])
app.include_router(traps.router,     prefix="/api", dependencies=[Depends(validate_auth)])
app.include_router(browser.router,   prefix="/api", dependencies=[Depends(validate_auth)])
app.include_router(mibs.router,      prefix="/api", dependencies=[Depends(validate_auth)])
app.include_router(settings.router,  prefix="/api")  # public: login endpoint lives here


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
