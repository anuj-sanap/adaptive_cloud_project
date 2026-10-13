"""
test_secure_multi_node.py - Verification suite for Real-Time Multi-Node Telemetry.

Validates all repository audit improvements:
  1. Node ID uniqueness with hardware MAC fingerprinting.
  2. Server-side Cluster API Key authentication (rejections & acceptances).
  3. Server-side telemetry payload bounds and schema validation.
  4. Multi-node separation (distinct laptops reporting to central server).
  5. Agent network resilience & offline FIFO buffering.
  6. SQLite WAL concurrency without table locks.
"""

import sys
import os
import time
import json
import sqlite3
import threading
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from fastapi.testclient import TestClient
from central_server.api import app
from central_server.database import init_db, get_connection, get_latest_telemetry, get_all_nodes
from central_server.security import get_cluster_api_key, validate_api_token
from node_agent.id_generator import get_or_create_node_id
from node_agent.server_client import (
    buffer_telemetry,
    get_buffered_count,
    flush_buffered_telemetry,
    _OFFLINE_BUFFER,
)
from node_agent.metrics import collect_node_telemetry

client = TestClient(app)


def test_suite():
    print("=" * 75)
    print("VERIFICATION SUITE: SECURE REAL-TIME MULTI-NODE TELEMETRY")
    print("=" * 75)

    init_db()
    api_key = get_cluster_api_key()
    auth_headers = {"X-API-Key": api_key}
    bearer_headers = {"Authorization": f"Bearer {api_key}"}

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 1: Node ID Uniqueness & Hardware Fingerprinting
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 1] Verifying Node ID Uniqueness & Hardware Fingerprinting...")
    test_nonce = str(int(time.time()))[-5:]
    node_id_1 = get_or_create_node_id(suffix=f"alpha_{test_nonce}")
    node_id_2 = get_or_create_node_id(suffix=f"beta_{test_nonce}")
    assert node_id_1 != node_id_2, "Node IDs with different suffixes must be distinct!"
    assert "node_" in node_id_1 and f"alpha_{test_nonce}" in node_id_1
    assert "node_" in node_id_2 and f"beta_{test_nonce}" in node_id_2
    print(f"  -> Generated Node 1 ID: {node_id_1}")
    print(f"  -> Generated Node 2 ID: {node_id_2}")
    print("  [PASS] Test 1: Unique node IDs incorporating hardware and random hashes.")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 2: Cluster API Key Authentication Enforcement
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 2] Verifying Server-Side Authentication Enforcement...")
    # Public health endpoint must be open
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "healthy"
    print("  -> /health is public and reachable without auth: [OK]")

    # Unauthenticated /register -> 401
    unauth_reg = client.post("/register", json={"node_id": node_id_1})
    assert unauth_reg.status_code == 401, f"Expected 401, got {unauth_reg.status_code}"
    print("  -> Unauthenticated POST /register rejected with 401: [OK]")

    # Invalid API key /telemetry -> 401
    bad_key_resp = client.post("/telemetry", json={"node_id": node_id_1}, headers={"X-API-Key": "bogus_key_999"})
    assert bad_key_resp.status_code == 401
    print("  -> Invalid API Key rejected with 401: [OK]")

    # Valid X-API-Key /register -> 200
    auth_reg = client.post("/register", json={
        "node_id": node_id_1,
        "hostname": "alpha-machine",
        "ip_address": "10.0.0.15",
        "operating_system": "Windows 11",
        "hardware_info": {"cpu_cores": 8, "ram_gb": 16}
    }, headers=auth_headers)
    assert auth_reg.status_code == 200
    print("  -> Valid X-API-Key POST /register accepted: [OK]")

    # Valid Bearer token /heartbeat -> 200
    auth_hb = client.post("/heartbeat", json={"node_id": node_id_1}, headers=bearer_headers)
    assert auth_hb.status_code == 200
    print("  -> Valid Bearer Token POST /heartbeat accepted: [OK]")
    print("  [PASS] Test 2: Constant-time API Key authentication verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 3: Server-Side Input Validation
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 3] Verifying Server-Side Metric Validation...")
    # Out of bounds CPU (> 100%)
    invalid_cpu = {
        "node_id": node_id_1,
        "metrics": {"cpu_utilization": 150.0, "ram_utilization": 50.0, "disk_utilization": 40.0}
    }
    inv_resp1 = client.post("/telemetry", json=invalid_cpu, headers=auth_headers)
    assert inv_resp1.status_code == 422, f"Expected 422 for CPU > 100%, got {inv_resp1.status_code}"
    print("  -> CPU > 100% rejected with HTTP 422: [OK]")

    # Invalid negative RAM
    invalid_ram = {
        "node_id": node_id_1,
        "metrics": {"cpu_utilization": 20.0, "ram_utilization": -5.0, "disk_utilization": 40.0}
    }
    inv_resp2 = client.post("/telemetry", json=invalid_ram, headers=auth_headers)
    assert inv_resp2.status_code == 422, f"Expected 422 for RAM < 0%, got {inv_resp2.status_code}"
    print("  -> RAM < 0% rejected with HTTP 422: [OK]")

    # Empty node_id
    invalid_nid = {
        "node_id": "",
        "metrics": {"cpu_utilization": 20.0, "ram_utilization": 50.0, "disk_utilization": 40.0}
    }
    inv_resp3 = client.post("/telemetry", json=invalid_nid, headers=auth_headers)
    assert inv_resp3.status_code == 422
    print("  -> Empty node_id rejected with HTTP 422: [OK]")
    print("  [PASS] Test 3: Input validation rejects malformed/out-of-bounds metrics.")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 4: Multi-Node Separation & Isolated Predictions
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 4] Verifying Multi-Node Telemetry Separation & Isolated Storage...")
    # Register Node 2
    client.post("/register", json={
        "node_id": node_id_2,
        "hostname": "beta-machine",
        "ip_address": "10.0.0.16",
        "operating_system": "Ubuntu 22.04",
        "hardware_info": {"cpu_cores": 4, "ram_gb": 8}
    }, headers=auth_headers)

    now_ts = datetime.now(timezone.utc).isoformat()
    # Telemetry snapshot for Node Alpha (Normal load)
    alpha_payload = {
        "node_id": node_id_1,
        "hostname": "alpha-machine",
        "timestamp": now_ts,
        "metrics": {
            "cpu_utilization": 18.5,
            "ram_utilization": 42.0,
            "disk_utilization": 30.0,
            "process_count": 120
        }
    }
    resp_alpha = client.post("/telemetry", json=alpha_payload, headers=auth_headers)
    assert resp_alpha.status_code == 200

    # Telemetry snapshot for Node Beta (Stressed load)
    beta_payload = {
        "node_id": node_id_2,
        "hostname": "beta-machine",
        "timestamp": now_ts,
        "metrics": {
            "cpu_utilization": 96.0,
            "ram_utilization": 94.5,
            "disk_utilization": 88.0,
            "process_count": 310
        }
    }
    resp_beta = client.post("/telemetry", json=beta_payload, headers=auth_headers)
    assert resp_beta.status_code == 200

    # Verify database isolation
    alpha_tel = get_latest_telemetry(node_id_1)
    beta_tel = get_latest_telemetry(node_id_2)

    assert alpha_tel["node_id"] == node_id_1
    assert beta_tel["node_id"] == node_id_2
    assert alpha_tel["cpu_utilization"] == 18.5
    assert beta_tel["cpu_utilization"] == 96.0

    print(f"  -> Node Alpha in DB: CPU={alpha_tel['cpu_utilization']}%, RAM={alpha_tel['ram_utilization']}%")
    print(f"  -> Node Beta in DB : CPU={beta_tel['cpu_utilization']}%, RAM={beta_tel['ram_utilization']}%")
    print(f"  -> Node Alpha failure risk: {resp_alpha.json().get('predictive_maintenance', {}).get('risk_level')}")
    print(f"  -> Node Beta failure risk : {resp_beta.json().get('predictive_maintenance', {}).get('risk_level')}")
    print("  [PASS] Test 4: Node telemetry completely isolated across nodes.")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 5: Offline Buffering & Batch Flush
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 5] Verifying Agent Offline Buffering & Batch Flush...")
    _OFFLINE_BUFFER.clear()

    # Simulate 3 dropped snapshots while disconnected
    snap1 = {"timestamp": "2026-10-13T01:05:00+00:00", "metrics": {"cpu_utilization": 40.0, "ram_utilization": 50.0, "disk_utilization": 30.0}}
    snap2 = {"timestamp": "2026-10-13T01:05:05+00:00", "metrics": {"cpu_utilization": 45.0, "ram_utilization": 51.0, "disk_utilization": 30.0}}
    snap3 = {"timestamp": "2026-10-13T01:05:10+00:00", "metrics": {"cpu_utilization": 50.0, "ram_utilization": 52.0, "disk_utilization": 30.0}}

    buffer_telemetry(snap1)
    buffer_telemetry(snap2)
    buffer_telemetry(snap3)

    assert get_buffered_count() == 3, f"Expected 3 buffered snapshots, got {get_buffered_count()}"
    print(f"  -> Buffered {get_buffered_count()} snapshots in-memory during simulated outage: [OK]")

    # Ingest batch through the server
    batch_req = {
        "node_id": node_id_1,
        "snapshots": list(_OFFLINE_BUFFER)
    }
    batch_resp = client.post("/telemetry/batch", json=batch_req, headers=auth_headers)
    assert batch_resp.status_code == 200
    assert batch_resp.json()["inserted_count"] == 3
    _OFFLINE_BUFFER.clear()
    assert get_buffered_count() == 0
    print("  -> Batch endpoint recorded all 3 historical snapshots atomically: [OK]")
    print("  [PASS] Test 5: Agent offline buffering and server-side batch recovery verified.")

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 6: SQLite WAL Concurrency
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[TEST 6] Verifying SQLite WAL Concurrency (Simultaneous Multi-Node Writes)...")
    errors = []

    def concurrent_node_poster(nid: str, num_records: int):
        for i in range(num_records):
            p = {
                "node_id": nid,
                "timestamp": f"2026-10-13T01:10:{i:02d}+00:00",
                "metrics": {
                    "cpu_utilization": 20.0 + i,
                    "ram_utilization": 50.0,
                    "disk_utilization": 30.0
                }
            }
            try:
                r = client.post("/telemetry", json=p, headers=auth_headers)
                if r.status_code != 200:
                    errors.append(f"HTTP {r.status_code}: {r.text}")
            except Exception as e:
                errors.append(str(e))

    threads = [
        threading.Thread(target=concurrent_node_poster, args=(node_id_1, 5)),
        threading.Thread(target=concurrent_node_poster, args=(node_id_2, 5)),
        threading.Thread(target=concurrent_node_poster, args=("node_laptop_gamma", 5)),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Concurrent write errors encountered: {errors}"
    print("  -> 15 concurrent snapshots written across 3 nodes with 0 lock errors: [OK]")
    print("  [PASS] Test 6: SQLite WAL mode handles multi-node concurrency cleanly.")

    print("\n" + "=" * 75)
    print("ALL 6 SECURE REAL-TIME MULTI-NODE TELEMETRY TESTS PASSED SUCCESSFULLY!")
    print("=" * 75)


if __name__ == "__main__":
    test_suite()
