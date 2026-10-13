"""
security.py - Server-Side Authentication & Access Control for Central Telemetry Server.

Features:
  - Validates API tokens supplied in 'X-API-Key' or 'Authorization: Bearer <token>' headers.
  - Compares tokens using constant-time string comparison (hmac.compare_digest) to prevent timing attacks.
  - Automatically loads key from SERVER_API_KEY environment variable or data/.api_key.
  - Supports generating a secure persistent token on first run if none is explicitly provided.
  - Never exposes secrets in version-controlled source code.
"""

from __future__ import annotations

import os
import hmac
import hashlib
import secrets
from typing import Optional
from fastapi import Request, HTTPException, status

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA_DIR = os.path.join(_BASE_DIR, "data")

def get_api_key_file() -> str:
    if os.getenv("SERVER_API_KEY_FILE"):
        return os.getenv("SERVER_API_KEY_FILE")
    if os.getenv("TELEMETRY_DB_PATH"):
        return os.path.join(os.path.dirname(os.getenv("TELEMETRY_DB_PATH")), ".api_key")
    if os.getenv("WEBSITE_SITE_NAME"):
        return "/home/data/.api_key"
    return os.path.join(_DATA_DIR, ".api_key")

_API_KEY_FILE = get_api_key_file()

_CACHED_KEY: Optional[str] = None


def get_cluster_api_key() -> Optional[str]:
    """
    Retrieves the authoritative cluster API key.
    
    Order of precedence:
      1. SERVER_API_KEY environment variable.
      2. ADAPTIVE_CLOUD_API_KEY environment variable.
      3. data/.api_key file.
      4. Auto-generate persistent random token in data/.api_key (if auth is enabled).
    """
    global _CACHED_KEY
    if _CACHED_KEY is not None:
        return _CACHED_KEY

    # Check for explicit auth disablement (useful for local offline testing)
    if os.getenv("DISABLE_AUTH", "false").lower() in ("true", "1", "yes"):
        return None

    # 1. Environment variable
    env_key = os.getenv("SERVER_API_KEY") or os.getenv("ADAPTIVE_CLOUD_API_KEY")
    if env_key and env_key.strip():
        _CACHED_KEY = env_key.strip()
        return _CACHED_KEY

    # 2. Local file in data/.api_key
    if os.path.exists(_API_KEY_FILE):
        try:
            with open(_API_KEY_FILE, "r", encoding="utf-8") as f:
                saved = f.read().strip()
                if saved:
                    _CACHED_KEY = saved
                    return _CACHED_KEY
        except Exception as e:
            print(f"[SECURITY WARN] Could not read {_API_KEY_FILE}: {e}")

    # 3. Generate a secure random token on first startup
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        new_key = secrets.token_hex(24)
        with open(_API_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(new_key + "\n")
        _CACHED_KEY = new_key
        print("=" * 65)
        print("[SECURITY NOTICE] A new Cluster API Key was generated:")
        print(f"  Key location : {_API_KEY_FILE}")
        print("  To connect remote node agents, configure on each laptop:")
        print("    set NODE_API_KEY=<your_key>  (Command Prompt)")
        print("    $env:NODE_API_KEY=\"<your_key>\"  (PowerShell)")
        print("    Or place it in: src/node_agent/api_key.txt")
        print("=" * 65)
        return _CACHED_KEY
    except Exception as e:
        print(f"[SECURITY WARN] Could not persist API key to {_API_KEY_FILE}: {e}")
        return None


def is_auth_enabled() -> bool:
    """Returns True if the server enforces authentication on agent endpoints."""
    return get_cluster_api_key() is not None


def extract_token_from_request(request: Request) -> Optional[str]:
    """
    Extracts authentication token from incoming request headers.
    Supports:
      - 'X-API-Key: <token>'
      - 'Authorization: Bearer <token>'
      - 'Authorization: <token>'
    """
    # 1. Direct header
    x_key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    if x_key:
        return x_key.strip()

    # 2. Authorization header
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth_header:
        parts = auth_header.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return auth_header.strip()

    return None


def validate_api_token(token: Optional[str]) -> bool:
    """
    Validates token using constant-time string comparison.
    Returns True if authentication is disabled or if token matches expected key.
    """
    expected = get_cluster_api_key()
    if expected is None:
        return True  # Auth is disabled

    if not token:
        return False

    return hmac.compare_digest(token.strip(), expected.strip())


def get_agent_node_id(token: Optional[str]) -> Optional[str]:
    """Resolve a high-entropy agent token to its single registered node identity."""
    if not token:
        return None
    from central_server.database import get_agent_node_id as lookup_agent_node_id

    token_hash = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
    return lookup_agent_node_id(token_hash)


async def require_api_key(request: Request) -> None:
    """
    FastAPI dependency that enforces API key authentication.
    Raises HTTPException(401) on missing or invalid key.
    """
    if not is_auth_enabled():
        return

    token = extract_token_from_request(request)
    if not validate_api_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Unauthorized: Invalid or missing API key. "
                "Provide a valid 'X-API-Key' or 'Authorization: Bearer <token>' header."
            ),
            headers={"WWW-Authenticate": "Bearer"}
        )
