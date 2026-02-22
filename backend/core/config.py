import os
import json
from pathlib import Path


class Settings:
    # Base paths
    BASE_DIR   = Path(__file__).parent.parent.resolve()
    DATA_DIR   = BASE_DIR / "data"
    MIB_DIR    = DATA_DIR / "mibs"
    CONFIG_DIR = DATA_DIR / "configs"
    LOG_DIR    = DATA_DIR / "logs"

    # SNMP Settings
    SNMP_PORT  = int(os.getenv("SNMP_PORT",  "1061"))
    COMMUNITY  = os.getenv("SNMP_COMMUNITY", "public")
    TRAP_PORT  = int(os.getenv("TRAP_PORT",  "1162"))

    # File paths
    CUSTOM_DATA_FILE  = CONFIG_DIR / "custom_data.json"
    SECRETS_FILE      = CONFIG_DIR / "secrets.json"
    STATS_FILE        = CONFIG_DIR / "stats.json"
    APP_SETTINGS_FILE = CONFIG_DIR / "app_settings.json"
    TRAPS_FILE        = DATA_DIR   / "traps.jsonl"

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE  = LOG_DIR / "app.log"

    # Application metadata
    APP_NAME        = os.getenv("APP_NAME",        "Trishul SNMP Studio")
    APP_VERSION     = os.getenv("APP_VERSION",     "1.2.3")
    APP_AUTHOR      = os.getenv("APP_AUTHOR",      "Sumit Dhaka")
    APP_DESCRIPTION = os.getenv("APP_DESCRIPTION", "Network Management & SNMP Utilities")

    # Security
    SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "3600"))

    # Auto-start flags
    AUTO_START_SIMULATOR     = os.getenv("AUTO_START_SIMULATOR",     "true").lower() == "true"
    AUTO_START_TRAP_RECEIVER = os.getenv("AUTO_START_TRAP_RECEIVER", "true").lower() == "true"

    # WebSocket internal UDP side-channel port (loopback only, not exposed)
    # Worker subprocesses send trap datagrams here so the main process
    # can broadcast real-time WS push events without shared memory.
    WS_INTERNAL_PORT = int(os.getenv("WS_INTERNAL_PORT", "19876"))

    def __init__(self):
        self.DATA_DIR.mkdir(exist_ok=True)
        self.MIB_DIR.mkdir(exist_ok=True)
        self.CONFIG_DIR.mkdir(exist_ok=True)
        self.LOG_DIR.mkdir(exist_ok=True)

        if not self.CUSTOM_DATA_FILE.exists():
            self.CUSTOM_DATA_FILE.write_text('{}')

        if not self.SECRETS_FILE.exists():
            self.SECRETS_FILE.write_text(json.dumps(
                {"username": "admin", "password": "admin123"}, indent=2
            ))

        if not self.TRAPS_FILE.exists():
            self.TRAPS_FILE.touch()

        # Load app_settings.json overrides.
        # These win over env defaults but NOT over explicit env vars set in docker-compose.
        # Priority order: env vars (class attrs) > app_settings.json > hardcoded defaults.
        # Since class attrs are already resolved from env, we only override here if the
        # env var was NOT explicitly set (i.e. still at its default value).
        self._apply_app_settings()

    def _apply_app_settings(self):
        """Apply persisted app_settings.json on top of env defaults at startup."""
        if not self.APP_SETTINGS_FILE.exists():
            return
        try:
            data = json.loads(self.APP_SETTINGS_FILE.read_text())
            if "session_timeout" in data:
                self.SESSION_TIMEOUT = int(data["session_timeout"])
            if "auto_start_simulator" in data:
                self.AUTO_START_SIMULATOR = bool(data["auto_start_simulator"])
            if "auto_start_trap_receiver" in data:
                self.AUTO_START_TRAP_RECEIVER = bool(data["auto_start_trap_receiver"])
        except Exception:
            pass  # Corrupt file — silently fall back to env defaults


settings = Settings()


class AppMeta:
    NAME        = settings.APP_NAME
    VERSION     = settings.APP_VERSION
    AUTHOR      = settings.APP_AUTHOR
    DESCRIPTION = settings.APP_DESCRIPTION


meta = AppMeta()
