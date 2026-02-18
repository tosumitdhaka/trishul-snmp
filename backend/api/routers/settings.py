import secrets
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from core.security import save_credentials, validate_auth, login_user, logout_user, get_stored_credentials, _verify_password

router = APIRouter(prefix="/settings", tags=["Settings"])


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
    _username: str = Depends(validate_auth)   # BUG-11 fix: validate_auth returns username;
                                               # we read the raw token from the header directly
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

    # Verify current password — uses _verify_password to handle
    # both legacy plaintext and hashed formats
    if not _verify_password(creds.current_password, stored["password"]):
        raise HTTPException(status_code=403, detail="Current password incorrect")

    # Save new credentials — always writes hashed
    save_credentials(creds.username, creds.password)
    return {"status": "updated", "message": "Credentials updated. Please log in again."}
