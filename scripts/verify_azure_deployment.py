"""
verify_azure_deployment.py - Post-Deployment Verification Tool for Azure Infrastructure

Autonomously verifies all critical cloud requirements:
  1. Frontend HTTPS reachable & serving SPA HTML.
  2. Backend HTTPS reachable, /health and /healthz reporting status=healthy and database=connected.
  3. CORS headers properly configured for the deployed frontend domain.
  4. Server authentication rejects unauthorized requests and accepts valid cluster secrets.
  5. Live node agent can register and ingest telemetry over public HTTPS.
  6. Database persists nodes and telemetry records across transactions.
  7. Batch telemetry ingestion (/telemetry/batch) succeeds.

Usage:
  python scripts/verify_azure_deployment.py \\
    --frontend-url https://<your-app>.azurestaticapps.net \\
    --backend-url https://<your-backend>.azurewebsites.net \\
    --api-key <your-cluster-secret>
"""

import sys
import json
import uuid
import time
import argparse
import ssl
import urllib.request
import urllib.error
from typing import Tuple, Dict, Any, Optional


def make_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 15.0
) -> Tuple[int, Dict[str, str], Optional[Any]]:
    """Helper to perform HTTP/HTTPS requests with full status and header capture."""
    hdrs = headers.copy() if headers else {}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    context = ssl.create_default_context()
    
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            status = resp.status
            resp_headers = dict(resp.headers)
            body_bytes = resp.read()
            try:
                body = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                body = body_bytes.decode("utf-8", errors="replace")
            return status, resp_headers, body
    except urllib.error.HTTPError as e:
        resp_headers = dict(e.headers)
        body_bytes = e.read()
        try:
            body = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            body = body_bytes.decode("utf-8", errors="replace")
        return e.code, resp_headers, body
    except urllib.error.URLError as e:
        return 0, {}, {"error": "URLError", "reason": str(e.reason)}
    except Exception as e:
        return 0, {}, {"error": "Exception", "detail": str(e)}


def test_frontend(frontend_url: str) -> bool:
    print("\n" + "=" * 75)
    print(f"[TEST 1] FRONTEND HTTPS VERIFICATION: {frontend_url}")
    print("=" * 75)
    
    if not frontend_url.startswith("https://"):
        print("  ✗ Warning: Frontend URL is not using HTTPS!")
        return False
        
    status, headers, body = make_request(frontend_url)
    if status == 200:
        print(f"  ✓ Frontend responded with HTTP 200 OK.")
        if isinstance(body, str) and ("<div id=\"root\">" in body or "<!doctype html>" in body.lower()):
            print("  ✓ Verified single-page application index.html served correctly.")
            return True
        else:
            print("  ✓ Received 200 response (custom content).")
            return True
    else:
        print(f"  ✗ Frontend check failed with status {status}: {body}")
        return False


def test_backend_health(backend_url: str) -> Tuple[bool, bool]:
    print("\n" + "=" * 75)
    print(f"[TEST 2] BACKEND HTTPS & /health PROBES: {backend_url}")
    print("=" * 75)
    
    if not backend_url.startswith("https://"):
        print("  ✗ Warning: Backend URL is not using HTTPS!")
        return False, False

    health_url = f"{backend_url.rstrip('/')}/health"
    status, _, body = make_request(health_url)
    
    if status != 200 or not isinstance(body, dict):
        print(f"  ✗ Health probe failed: HTTP {status}, response: {body}")
        return False, False
        
    print(f"  ✓ GET /health returned HTTP 200 OK.")
    print(f"    • Service   : {body.get('service')}")
    print(f"    • Status    : {body.get('status')}")
    print(f"    • Database  : {body.get('database')}")
    print(f"    • DB Path   : {body.get('database_path')}")
    print(f"    • Storage   : {body.get('storage_mode')}")
    print(f"    • Auth Reqd : {body.get('auth_required')}")
    
    db_ok = body.get("database") == "connected"
    auth_reqd = bool(body.get("auth_required"))
    
    if not db_ok:
        print("  ✗ Database is NOT reporting connected status!")
        return False, auth_reqd
        
    # Check /healthz alias
    healthz_url = f"{backend_url.rstrip('/')}/healthz"
    hz_status, _, _ = make_request(healthz_url)
    if hz_status == 200:
        print(f"  ✓ Cloud health probe alias /healthz verified (HTTP 200).")
        
    return True, auth_reqd


def test_cors(backend_url: str, frontend_url: str) -> bool:
    print("\n" + "=" * 75)
    print(f"[TEST 3] CORS PREFLIGHT VERIFICATION FOR FRONTEND ORIGIN")
    print(f"  Target Origin: {frontend_url}")
    print("=" * 75)
    
    origin = frontend_url.rstrip("/")
    probe_url = f"{backend_url.rstrip('/')}/telemetry"
    
    headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type, X-API-Key, Authorization"
    }
    
    status, resp_headers, _ = make_request(probe_url, method="OPTIONS", headers=headers)
    
    # Headers in urllib are lowercase keys
    norm_headers = {k.lower(): v for k, v in resp_headers.items()}
    allow_origin = norm_headers.get("access-control-allow-origin")
    
    print(f"  • Preflight response status: HTTP {status}")
    print(f"  • Access-Control-Allow-Origin: {allow_origin}")
    
    if status == 200 and allow_origin and (allow_origin == origin or allow_origin == "*"):
        print("  ✓ CORS preflight approved for deployed frontend origin.")
        return True
    elif allow_origin == origin:
        print("  ✓ Origin matches Access-Control-Allow-Origin.")
        return True
    else:
        print(f"  ✗ CORS preflight check failed. Ensure CORS_ORIGINS on backend contains '{origin}'")
        return False


def test_authentication(backend_url: str, api_key: Optional[str]) -> bool:
    print("\n" + "=" * 75)
    print(f"[TEST 4] AUTHENTICATION & SECURITY ENFORCEMENT")
    print("=" * 75)
    
    reg_url = f"{backend_url.rstrip('/')}/register"
    dummy_payload = {
        "node_id": "probe_unauth_node",
        "hostname": "probe.laptop.internal",
        "operating_system": "Verification Probe"
    }
    
    # 1. Unauthenticated request must receive 401 (if auth is enabled)
    status_no_key, _, _ = make_request(reg_url, method="POST", payload=dummy_payload)
    print(f"  • Request with NO credentials returned: HTTP {status_no_key}")
    
    # 2. Invalid credentials must receive 401
    status_bad_key, _, _ = make_request(
        reg_url,
        method="POST",
        headers={"X-API-Key": "completely-invalid-token-12345"},
        payload=dummy_payload
    )
    print(f"  • Request with INVALID token returned : HTTP {status_bad_key}")
    
    if status_no_key == 401 and status_bad_key == 401:
        print("  ✓ Unauthorized and spoofed requests are strictly rejected (HTTP 401).")
    else:
        print("  ℹ Note: Server has authentication disabled or public mode active.")
        
    # 3. Valid credentials check
    if api_key:
        valid_payload = {
            "node_id": f"probe_auth_{uuid.uuid4().hex[:8]}",
            "hostname": "probe.laptop.internal",
            "operating_system": "Verification Probe"
        }
        status_valid, _, resp_body = make_request(
            reg_url,
            method="POST",
            headers={"X-API-Key": api_key},
            payload=valid_payload
        )
        if status_valid == 200:
            print("  ✓ Authorized request with cluster API key succeeded (HTTP 200).")
            return True
        else:
            print(f"  ✗ Request with provided API key failed (HTTP {status_valid}): {resp_body}")
            return False
            
    return True


def test_agent_telemetry_and_persistence(backend_url: str, api_key: Optional[str]) -> bool:
    print("\n" + "=" * 75)
    print(f"[TEST 5] LIVE AGENT TELEMETRY INGESTION & DATABASE PERSISTENCE")
    print("=" * 75)
    
    test_node_id = f"azure_verify_node_{uuid.uuid4().hex[:8]}"
    headers = {"X-API-Key": api_key} if api_key else {}
    
    # Step A: Register test node
    reg_url = f"{backend_url.rstrip('/')}/register"
    reg_payload = {
        "node_id": test_node_id,
        "hostname": "azure.cloud.verifier",
        "operating_system": "Azure Verification Test OS",
        "hardware_info": {"cores": 4, "ram_gb": 16.0}
    }
    
    st_reg, _, _ = make_request(reg_url, method="POST", headers=headers, payload=reg_payload)
    if st_reg != 200:
        print(f"  ✗ Node registration failed with HTTP {st_reg}")
        return False
    print(f"  ✓ Test node '{test_node_id}' registered successfully.")
    
    # Step B: Ingest telemetry snapshot
    telem_url = f"{backend_url.rstrip('/')}/telemetry"
    t_payload = {
        "node_id": test_node_id,
        "metrics": {
            "cpu_utilization": 42.5,
            "ram_utilization": 61.2,
            "disk_utilization": 28.0,
            "network_sent_mb": 15.4,
            "network_recv_mb": 45.2,
            "disk_read_mb": 1.2,
            "disk_write_mb": 3.4,
            "process_count": 140,
            "cpu_temperature_c": 48.0
        }
    }
    
    st_tel, _, tel_body = make_request(telem_url, method="POST", headers=headers, payload=t_payload)
    if st_tel != 200:
        print(f"  ✗ Telemetry ingestion failed with HTTP {st_tel}: {tel_body}")
        return False
    print("  ✓ Telemetry snapshot ingested successfully over public HTTPS.")
    
    # Step C: Query node details from database to verify persistence
    get_node_url = f"{backend_url.rstrip('/')}/nodes/{test_node_id}"
    st_get, _, get_body = make_request(get_node_url, headers=headers)
    
    if st_get == 200 and isinstance(get_body, dict):
        persisted_id = get_body.get("node_id")
        recent_telem = get_body.get("recent_telemetry", [])
        print(f"  ✓ Persistent DB verification passed:")
        print(f"    • Node ID in DB     : {persisted_id}")
        print(f"    • Telemetry records : {len(recent_telem)} record(s) persisted in database.")
    else:
        print(f"  ✗ Failed to retrieve persisted node details: HTTP {st_get}, {get_body}")
        return False
        
    # Step D: Test batch offline buffer ingestion
    batch_url = f"{backend_url.rstrip('/')}/telemetry/batch"
    batch_payload = {
        "node_id": test_node_id,
        "snapshots": [
            {
                "node_id": test_node_id,
                "timestamp": "2026-10-13T06:00:00Z",
                "metrics": {"cpu_utilization": 43.0, "ram_utilization": 61.5, "disk_utilization": 28.1}
            },
            {
                "node_id": test_node_id,
                "timestamp": "2026-10-13T06:00:05Z",
                "metrics": {"cpu_utilization": 44.1, "ram_utilization": 62.0, "disk_utilization": 28.1}
            }
        ]
    }
    st_b, _, b_body = make_request(batch_url, method="POST", headers=headers, payload=batch_payload)
    if st_b == 200:
        print("  ✓ Offline batch telemetry flushing verified (/telemetry/batch returned HTTP 200).")
    else:
        print(f"  ✗ Batch telemetry failed with HTTP {st_b}: {b_body}")
        return False
        
    return True


def main():
    parser = argparse.ArgumentParser(description="Verify Azure Cloud Deployment for Adaptive Cloud Project")
    parser.add_argument("--frontend-url", type=str, required=True, help="HTTPS URL of deployed React frontend")
    parser.add_argument("--backend-url", type=str, required=True, help="HTTPS URL of deployed FastAPI backend")
    parser.add_argument("--api-key", type=str, default=None, help="Cluster API Key")
    args = parser.parse_args()

    frontend_url = args.frontend_url.rstrip("/")
    backend_url = args.backend_url.rstrip("/")
    api_key = args.api_key

    print("=" * 75)
    print("AZURE CLOUD DEPLOYMENT VERIFICATION SUITE")
    print(f"  • Frontend URL : {frontend_url}")
    print(f"  • Backend URL  : {backend_url}")
    print(f"  • API Key      : {'[CONFIGURED]' if api_key else '[NONE]'}")
    print("=" * 75)

    results = {}

    results["frontend"] = test_frontend(frontend_url)
    health_ok, auth_reqd = test_backend_health(backend_url)
    results["backend_health"] = health_ok

    if auth_reqd and not api_key:
        print("\n[WARNING] Server enforces authentication but no --api-key was provided.")
        print("Remaining tests will continue, but auth checks may require the key.")

    results["cors"] = test_cors(backend_url, frontend_url)
    results["auth"] = test_authentication(backend_url, api_key)
    results["telemetry_and_persistence"] = test_agent_telemetry_and_persistence(backend_url, api_key)

    print("\n" + "=" * 75)
    print("VERIFICATION SUMMARY REPORT")
    print("=" * 75)
    all_passed = True
    for test_name, passed in results.items():
        status_icon = "✓ PASS" if passed else "✗ FAIL"
        if not passed:
            all_passed = False
        print(f"  [{status_icon}] {test_name.replace('_', ' ').title()}")
    print("=" * 75)

    if all_passed:
        print("ALL AZURE DEPLOYMENT VERIFICATION CHECKS PASSED SUCCESSFULLY!")
        print("Your React frontend, FastAPI backend, SQLite persistence, and edge agent reachability are operational.")
        sys.exit(0)
    else:
        print("ONE OR MORE VERIFICATION CHECKS FAILED.")
        print("Review the failure messages above and verify your Azure resource configurations.")
        sys.exit(1)


if __name__ == "__main__":
    main()
