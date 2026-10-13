"""
config.py - Configuration settings for the Live Node Monitoring Agent.
Supports environment variables and sensible defaults.
"""

import os

# ─────────────────────────────────────────────────────────────────────────────
# Central Server Base URL  (no trailing slash)
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_SERVER_BASE_URL = "http://localhost:8000"

# Check for a local server_url.txt or server_ip.txt in agent directory
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_URL_FILE = os.path.join(_AGENT_DIR, "server_url.txt")
_IP_FILE = os.path.join(_AGENT_DIR, "server_ip.txt")

if os.path.exists(_URL_FILE):
    try:
        with open(_URL_FILE, "r", encoding="utf-8") as _f:
            _raw = _f.read().strip()
            if _raw:
                if not _raw.startswith("http://") and not _raw.startswith("https://"):
                    _raw = f"http://{_raw}:8000" if ":" not in _raw else f"http://{_raw}"
                DEFAULT_SERVER_BASE_URL = _raw
    except Exception:
        pass
elif os.path.exists(_IP_FILE):
    try:
        with open(_IP_FILE, "r", encoding="utf-8") as _f:
            _raw = _f.read().strip()
            if _raw:
                DEFAULT_SERVER_BASE_URL = f"http://{_raw}:8000" if ":" not in _raw else f"http://{_raw}"
    except Exception:
        pass

SERVER_BASE_URL = os.getenv("NODE_SERVER_URL", DEFAULT_SERVER_BASE_URL).rstrip("/")

# Derived endpoint URLs  (do not override these manually)
REGISTER_URL        = f"{SERVER_BASE_URL}/register"
TELEMETRY_URL       = f"{SERVER_BASE_URL}/telemetry"
BATCH_TELEMETRY_URL = f"{SERVER_BASE_URL}/telemetry/batch"
HEARTBEAT_URL       = f"{SERVER_BASE_URL}/heartbeat"

# ─────────────────────────────────────────────────────────────────────────────
# Authentication (Cluster API Key)
# ─────────────────────────────────────────────────────────────────────────────
# 1. Environment variable
DEFAULT_NODE_API_KEY = os.getenv("NODE_API_KEY") or os.getenv("ADAPTIVE_CLOUD_API_KEY", "")

# 2. Local api_key.txt file in the agent directory. It must contain this
#    specific node's provisioned credential, never the server admin key.
_KEY_FILE = os.path.join(_AGENT_DIR, "api_key.txt")

if not DEFAULT_NODE_API_KEY:
    if os.path.exists(_KEY_FILE):
        try:
            with open(_KEY_FILE, "r", encoding="utf-8") as _kf:
                _raw_k = _kf.read().strip()
                if _raw_k:
                    DEFAULT_NODE_API_KEY = _raw_k
        except Exception:
            pass
NODE_API_KEY = DEFAULT_NODE_API_KEY
NODE_LOCATION_LABEL = os.getenv("NODE_LOCATION_LABEL", "").strip()

# ─────────────────────────────────────────────────────────────────────────────
# Timing
# ─────────────────────────────────────────────────────────────────────────────
# How often to send a telemetry snapshot (seconds)
DEFAULT_TELEMETRY_INTERVAL = 5
TELEMETRY_INTERVAL_SEC = int(os.getenv("NODE_TELEMETRY_INTERVAL", str(DEFAULT_TELEMETRY_INTERVAL)))

# How often to send a heartbeat (seconds) — independent of telemetry
DEFAULT_HEARTBEAT_INTERVAL = 15
HEARTBEAT_INTERVAL_SEC = int(os.getenv("NODE_HEARTBEAT_INTERVAL", str(DEFAULT_HEARTBEAT_INTERVAL)))

# ─────────────────────────────────────────────────────────────────────────────
# HTTP / Network / Resilience behaviour
# ─────────────────────────────────────────────────────────────────────────────
HTTP_TIMEOUT_SEC = float(os.getenv("NODE_HTTP_TIMEOUT", "10.0"))

# Base back-off between retries (doubles up to MAX_RETRY_WAIT_SEC)
RETRY_BASE_WAIT_SEC = 2
MAX_RETRY_WAIT_SEC  = 60

# SSL verification toggle for HTTPS endpoints (disable only for local self-signed dev)
NODE_SSL_VERIFY = os.getenv("NODE_SSL_VERIFY", "true").lower() in ("true", "1", "yes")

# Maximum offline snapshots buffered in memory during network disconnects
OFFLINE_BUFFER_MAX_SIZE = int(os.getenv("NODE_BUFFER_MAX", "120"))

# Disable transmission entirely (telemetry printed to stdout only)
ENABLE_HTTP_POST = os.getenv("NODE_ENABLE_POST", "True").lower() in ("true", "1", "yes")
