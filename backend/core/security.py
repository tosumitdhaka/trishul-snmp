import os
import json
import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from core.config import settings

security = HTTPBasic()
SECRETS_FILE = os.path.join(settings.CONFIG_DIR, "secrets.json")

def get_credentials():
    """Load creds from file or return default"""
    if not os.path.exists(SECRETS_FILE):
        return {"username": "admin", "password": "admin"}
    try:
        with open(SECRETS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"username": "admin", "password": "admin"}

def save_credentials(username, password):
    os.makedirs(settings.CONFIG_DIR, exist_ok=True)
    with open(SECRETS_FILE, 'w') as f:
        json.dump({"username": username, "password": password}, f)

def validate_auth(credentials: HTTPBasicCredentials = Depends(security)):
    stored = get_credentials()
    
    # Secure comparison to prevent timing attacks
    is_user_ok = secrets.compare_digest(credentials.username, stored["username"])
    is_pass_ok = secrets.compare_digest(credentials.password, stored["password"])
    
    if not (is_user_ok and is_pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
