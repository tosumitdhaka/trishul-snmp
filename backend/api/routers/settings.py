import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from core.security import save_credentials, validate_auth, login_user, logout_user, get_stored_credentials, _verify_password
from core.config import settings

router = APIRouter(prefix="/settings", tags=["Settings"])


# ---------------------------------------------------------------------------
# Auth models & endpoints (unchanged)
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class AuthUpdate(BaseModel):
    current_password: str
    username: str
    password: str


@router.post("/login")
def login(creds: LoginRequest):
    """Public endpoint — issues a session token on valid credentials."""
    token = login_user(creds.username, creds.password)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": token, "username": creds.username}


@router.post("/logout")
def logout(
    x_auth_token: str = Header(None),
    _username: str = Depends(validate_auth)
):
    """Invalidate the current session token."""
    logout_user(x_auth_token)
    return {"status": "logged_out"}


@router.get("/check")
def check_auth_status(username: str = Depends(validate_auth)):
    return {"status": "authenticated", "user": username}


@router.post("/auth", dependencies=[Depends(validate_auth)])
def update_auth(creds: AuthUpdate):
    """Change username and/or password. Requires current password verification."""
    stored = get_stored_credentials()
    if not _verify_password(creds.current_password, stored["password"]):
        raise HTTPException(status_code=403, detail="Current password incorrect")
    save_credentials(creds.username, creds.password)
    return {"status": "updated", "message": "Credentials updated. Please log in again."}


# ---------------------------------------------------------------------------
# App Settings — persisted to data/configs/app_settings.json
# ---------------------------------------------------------------------------

# Schema / defaults — single source of truth
DEFAULT_APP_SETTINGS: dict = {
    "auto_start_simulator":     True,
    "auto_start_trap_receiver": True,
    "session_timeout":          3600,
}


class AppSettingsUpdate(BaseModel):
    auto_start_simulator:     Optional[bool] = None
    auto_start_trap_receiver: Optional[bool] = None
    session_timeout:          Optional[int]  = Field(None, ge=60, le=86400)


def _load_app_settings() -> dict:
    """Return current app_settings.json merged with defaults."""
    data = {**DEFAULT_APP_SETTINGS}
    if settings.APP_SETTINGS_FILE.exists():
        try:
            saved = json.loads(settings.APP_SETTINGS_FILE.read_text())
            # Only accept known keys to guard against stale/corrupt data
            data.update({k: v for k, v in saved.items() if k in DEFAULT_APP_SETTINGS})
        except Exception:
            pass
    return data


def _save_app_settings(data: dict) -> None:
    settings.APP_SETTINGS_FILE.write_text(json.dumps(data, indent=2))


@router.get("/app", dependencies=[Depends(validate_auth)])
def get_app_settings():
    """Return current application behaviour settings."""
    return _load_app_settings()


@router.post("/app", dependencies=[Depends(validate_auth)])
def update_app_settings(body: AppSettingsUpdate):
    """
    Persist application behaviour settings.
    Changes are written to app_settings.json and applied on next container restart.
    """
    current = _load_app_settings()
    if body.auto_start_simulator is not None:
        current["auto_start_simulator"] = body.auto_start_simulator
    if body.auto_start_trap_receiver is not None:
        current["auto_start_trap_receiver"] = body.auto_start_trap_receiver
    if body.session_timeout is not None:
        current["session_timeout"] = body.session_timeout
    _save_app_settings(current)
    return {"status": "saved", "restart_required": True, "settings": current}
