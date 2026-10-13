"""
server_client.py - Resilient HTTP/HTTPS client for the Central Telemetry REST API.

Handles:
  - Node registration (POST /register) with exponential back-off
  - Telemetry ingestion (POST /telemetry)
  - Batch ingestion of offline-buffered telemetry (POST /telemetry/batch)
  - Heartbeat check-ins (POST /heartbeat)
  - API Key authentication (X-API-Key and Authorization: Bearer headers)
  - HTTPS / SSL support with configurable certificate validation
  - In-memory offline buffering during temporary network disconnections
  - Transparent error recovery without crashing the calling process
"""

from __future__ import annotations

import json
import time
import socket
import os
import sys
import ssl
import platform
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, Tuple, List

_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _AGENT_DIR not in sys.path:
    sys.path.insert(0, _AGENT_DIR)

try:
    from node_agent.config import (
        REGISTER_URL,
        TELEMETRY_URL,
        BATCH_TELEMETRY_URL,
        HEARTBEAT_URL,
        HTTP_TIMEOUT_SEC,
        RETRY_BASE_WAIT_SEC,
        MAX_RETRY_WAIT_SEC,
        NODE_API_KEY,
        NODE_LOCATION_LABEL,
        NODE_SSL_VERIFY,
        OFFLINE_BUFFER_MAX_SIZE,
    )
except ImportError:
    from config import (
        REGISTER_URL,
        TELEMETRY_URL,
        BATCH_TELEMETRY_URL,
        HEARTBEAT_URL,
        HTTP_TIMEOUT_SEC,
        RETRY_BASE_WAIT_SEC,
        MAX_RETRY_WAIT_SEC,
        NODE_API_KEY,
        NODE_LOCATION_LABEL,
        NODE_SSL_VERIFY,
        OFFLINE_BUFFER_MAX_SIZE,
    )

# In-memory buffer for telemetry records during temporary network drops
_OFFLINE_BUFFER: List[Dict[str, Any]] = []


# ─────────────────────────────────────────────────────────────────────────────
# Low-level HTTP/HTTPS helper
# ─────────────────────────────────────────────────────────────────────────────

def _build_ssl_context(url: str) -> Optional[ssl.SSLContext]:
    """Builds appropriate SSL context for HTTPS URLs."""
    if not url.startswith("https://"):
        return None
    context = ssl.create_default_context()
    if not NODE_SSL_VERIFY:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def _post_json(
    url: str,
    payload: dict,
    timeout: float = HTTP_TIMEOUT_SEC,
    api_key: Optional[str] = None
) -> Tuple[bool, Optional[dict]]:
    """
    POST a JSON payload to *url* over HTTP or HTTPS.
    Includes API Key authentication headers if configured.
    Returns (True, response_dict) on success.
    Returns (False, error_dict) on network/HTTP error without raising unhandled exceptions.
    """
    effective_key = api_key if api_key is not None else NODE_API_KEY
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "LiveNodeAgent/2.0",
    }
    if effective_key:
        headers["X-API-Key"] = effective_key
        headers["Authorization"] = f"Bearer {effective_key}"

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        context = _build_ssl_context(url)

        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return True, body

    except urllib.error.HTTPError as e:
        error_msg = str(e.reason)
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            if isinstance(err_body, dict) and "detail" in err_body:
                error_msg = err_body["detail"]
        except Exception:
            pass

        if e.code == 401:
            print(f"[CLIENT AUTH ERROR] {url} -> HTTP 401 Unauthorized: {error_msg}")
            print("  Check that NODE_API_KEY is the credential provisioned for this specific node.")
        elif e.code == 422:
            print(f"[CLIENT VALIDATION ERROR] {url} -> HTTP 422 Unprocessable Entity: {error_msg}")
        else:
            print(f"[CLIENT HTTP ERROR] {url} -> HTTP {e.code}: {e.reason} ({error_msg})")
        return False, {"http_code": e.code, "error": error_msg}

    except urllib.error.URLError as e:
        print(f"[CLIENT CONN WARN] Cannot reach server at {url}: {e.reason}")
        return False, {"error": "unreachable", "reason": str(e.reason)}

    except socket.timeout:
        print(f"[CLIENT TIMEOUT WARN] Request to {url} timed out after {timeout}s")
        return False, {"error": "timeout"}

    except Exception as e:
        print(f"[CLIENT ERROR] Unexpected network error posting to {url}: {e}")
        return False, {"error": "unexpected", "detail": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Offline Buffering for Network Resilience
# ─────────────────────────────────────────────────────────────────────────────

def buffer_telemetry(payload: Dict[str, Any]) -> int:
    """
    Appends a telemetry record to the in-memory offline buffer.
    Maintains FIFO limit so memory remains bounded during prolonged outages.
    """
    global _OFFLINE_BUFFER
    if len(_OFFLINE_BUFFER) >= OFFLINE_BUFFER_MAX_SIZE:
        _OFFLINE_BUFFER.pop(0)  # Evict oldest record
    _OFFLINE_BUFFER.append(payload)
    return len(_OFFLINE_BUFFER)


def get_buffered_count() -> int:
    """Returns number of buffered telemetry records awaiting transmission."""
    return len(_OFFLINE_BUFFER)


def flush_buffered_telemetry(node_id: str) -> bool:
    """
    Transmits all offline-buffered telemetry snapshots to the Central Server
    via POST /telemetry/batch. Clears buffer upon server acknowledgement.
    """
    global _OFFLINE_BUFFER
    if not _OFFLINE_BUFFER:
        return True

    count = len(_OFFLINE_BUFFER)
    batch_payload = {
        "node_id": node_id,
        "snapshots": list(_OFFLINE_BUFFER)
    }

    ok, resp = _post_json(BATCH_TELEMETRY_URL, batch_payload)
    if ok:
        print(f"  [FLUSH BUFFER] Successfully retransmitted {count} buffered snapshot(s) -> [OK]")
        _OFFLINE_BUFFER.clear()
        return True

    print(f"  [FLUSH BUFFER] Server could not accept batch flush (still holding {count} records in queue)")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────────────────────────────────────

def _build_register_payload(node_id: str) -> dict:
    hostname = socket.gethostname()
    import psutil
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\" if platform.system() == "Windows" else "/")
    return {
        "node_id": node_id,
        "hostname": hostname,
        "operating_system": f"{platform.system()} {platform.release()} ({platform.architecture()[0]})",
        "location_label": NODE_LOCATION_LABEL or None,
        "hardware_info": {
            "cpu_count_logical": psutil.cpu_count(logical=True),
            "cpu_count_physical": psutil.cpu_count(logical=False),
            "ram_total_mb": round(vm.total / (1024 ** 2), 2),
            "disk_total_gb": round(disk.total / (1024 ** 3), 2),
        },
    }


def register_with_retry(node_id: str, max_attempts: Optional[int] = None) -> bool:
    """
    Attempts to register the node with the central server.
    Retries with exponential back-off until accepted or max_attempts is reached.
    """
    payload = _build_register_payload(node_id)
    wait_sec = RETRY_BASE_WAIT_SEC
    attempt = 0

    while True:
        attempt += 1
        ok, resp = _post_json(REGISTER_URL, payload)
        if ok:
            print(f"[REGISTER] Node '{node_id}' registered with central server. (attempt {attempt})")
            return True

        # Check if error was 401 Unauthorized
        if isinstance(resp, dict) and resp.get("http_code") == 401:
            print("\n" + "!" * 68)
            print("[AUTHENTICATION ERROR] Central server requires a valid API key!")
            print("Set your key via:")
            print("  set NODE_API_KEY=<key>  (Command Prompt)")
            print("  $env:NODE_API_KEY=\"<key>\"  (PowerShell)")
            print("  Or run: python collector.py --api-key <key>")
            print("!" * 68 + "\n")

        if attempt == 2 and ("localhost" in REGISTER_URL or "127.0.0.1" in REGISTER_URL):
            print("\n" + "!" * 68)
            print("[CONNECTION TIP] The node agent is attempting to connect to 'localhost:8000'.")
            print("If this node is running on a SEPARATE LAPTOP / MACHINE, 'localhost' will NOT")
            print("reach the Central Server! Run collector with your Central Server's IP or Domain:")
            print("    python collector.py --server-url http://<CENTRAL_SERVER_IP>:8000")
            print("Or create a 'server_url.txt' file in this folder containing that address.")
            print("!" * 68 + "\n")

        if max_attempts and attempt >= max_attempts:
            print(f"[REGISTER] Reached maximum attempts ({max_attempts}). Aborting registration.")
            return False

        print(f"[REGISTER] Server unavailable at {REGISTER_URL}. Retrying in {wait_sec}s (attempt {attempt}) ...")
        time.sleep(wait_sec)
        wait_sec = min(wait_sec * 2, MAX_RETRY_WAIT_SEC)


# ─────────────────────────────────────────────────────────────────────────────
# Telemetry Transmission
# ─────────────────────────────────────────────────────────────────────────────

def send_telemetry_with_response(payload: dict) -> Tuple[bool, Optional[dict]]:
    """
    Sends one telemetry snapshot.
    Returns (ok, response_body) where response_body includes real ML predictions
    and any active predictive maintenance alert for this node.
    """
    return _post_json(TELEMETRY_URL, payload)


def send_telemetry(payload: dict) -> bool:
    """
    Sends one telemetry snapshot. Returns True on success, False otherwise.
    Does NOT crash on network error.
    """
    ok, _ = _post_json(TELEMETRY_URL, payload)
    return ok


def fetch_node_alert(node_id: str) -> Optional[dict]:
    """Queries Central Server directly for active alerts on this node."""
    try:
        from node_agent.config import SERVER_BASE_URL, HTTP_TIMEOUT_SEC, NODE_API_KEY
    except ImportError:
        from config import SERVER_BASE_URL, HTTP_TIMEOUT_SEC, NODE_API_KEY

    url = f"{SERVER_BASE_URL}/nodes/{node_id}/alerts"
    headers = {"User-Agent": "LiveNodeAgent/2.0"}
    if NODE_API_KEY:
        headers["X-API-Key"] = NODE_API_KEY
        headers["Authorization"] = f"Bearer {NODE_API_KEY}"

    try:
        context = _build_ssl_context(url)
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC, context=context) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("has_active_alert"):
                return data.get("alert")
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Heartbeat
# ─────────────────────────────────────────────────────────────────────────────

def send_heartbeat(node_id: str) -> bool:
    """
    Sends a lightweight heartbeat. Returns True on success.
    Does NOT raise exceptions on network drops.
    """
    ok, _ = _post_json(HEARTBEAT_URL, {"node_id": node_id})
    return ok
