"""
test_telemetry_api.py - Direct functional test for Central Telemetry REST API.
Tests /register, /telemetry, /nodes, /nodes/{node_id}, and /heartbeat using FastAPI TestClient.
"""

import sys
import os
import json

# Add src to path
SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from fastapi.testclient import TestClient
from central_server.api import app
from central_server.database import init_db, get_db_path
from central_server.security import get_cluster_api_key

client = TestClient(app)

def run_tests():
    print("=" * 65)
    print("[TEST SUITE] RUNNING CENTRAL TELEMETRY REST API TEST SUITE")
    print("=" * 65)

    # Initialize DB
    init_db()
    api_key = get_cluster_api_key()
    auth_headers = {"X-API-Key": api_key}

    # 0. Test Authentication Rejection
    print("\n[TEST 0/6] Testing Authentication Enforcement (401 on missing key) ...")
    unauth_resp = client.post("/register", json={"node_id": "unauth_node"})
    assert unauth_resp.status_code == 401
    print("  [OK] Unauthenticated request correctly rejected with 401 Unauthorized")

    # 1. Test POST /register with Auth
    print("\n[TEST 1/6] Testing POST /register with Valid API Key ...")
    reg_payload = {
        "node_id": "test_node_alpha",
        "hostname": "alpha-server-01",
        "ip_address": "192.168.1.50",
        "operating_system": "Linux Ubuntu 22.04",
        "hardware_info": {"cpu_cores": 8, "ram_gb": 16}
    }
    response = client.post("/register", json=reg_payload, headers=auth_headers)
    print(f"  Response Status: {response.status_code}")
    print(f"  Response Body  : {response.json()}")
    assert response.status_code == 200
    assert response.json()["node_id"] == "test_node_alpha"
    assert response.json()["status"] == "ONLINE"
    print("  [OK] POST /register PASSED")

    # 2. Test POST /telemetry
    print("\n[TEST 2/6] Testing POST /telemetry ...")
    telemetry_payload = {
        "node_id": "test_node_alpha",
        "hostname": "alpha-server-01",
        "operating_system": "Linux Ubuntu 22.04",
        "timestamp": "2026-09-19T14:15:00+00:00",
        "metrics": {
            "cpu_utilization": 24.5,
            "ram_utilization": 55.2,
            "disk_utilization": 42.1,
            "network_sent_mb": 105.4,
            "network_recv_mb": 420.8,
            "disk_read_mb": 12.3,
            "disk_write_mb": 45.6,
            "cpu_temperature_c": 48.5,
            "process_count": 180
        }
    }
    response = client.post("/telemetry", json=telemetry_payload, headers=auth_headers)
    print(f"  Response Status: {response.status_code}")
    print(f"  Response Body  : {response.json()}")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    print("  [OK] POST /telemetry PASSED")

    # 2b. Test Auto-Registration via POST /telemetry
    print("\n[TEST 2b] Testing Auto-Registration via POST /telemetry ...")
    auto_node_payload = {
        "node_id": "test_node_beta_auto",
        "hostname": "beta-auto-host",
        "operating_system": "Windows 11",
        "timestamp": "2026-09-19T14:15:05+00:00",
        "metrics": {
            "cpu_utilization": 88.9,
            "ram_utilization": 91.0,
            "disk_utilization": 80.0,
            "network_sent_mb": 5.0,
            "network_recv_mb": 10.0,
            "disk_read_mb": 1.0,
            "disk_write_mb": 2.0,
            "process_count": 95
        }
    }
    response = client.post("/telemetry", json=auto_node_payload, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["node_id"] == "test_node_beta_auto"
    print("  [OK] Auto-Registration via POST /telemetry PASSED")

    # 3. Test POST /telemetry/batch (Buffered historical metrics)
    print("\n[TEST 3/6] Testing POST /telemetry/batch (Offline Buffering Recovery) ...")
    batch_payload = {
        "node_id": "test_node_alpha",
        "snapshots": [
            {
                "timestamp": "2026-09-19T14:15:10+00:00",
                "metrics": {"cpu_utilization": 30.0, "ram_utilization": 50.0, "disk_utilization": 40.0}
            },
            {
                "timestamp": "2026-09-19T14:15:15+00:00",
                "metrics": {"cpu_utilization": 35.0, "ram_utilization": 52.0, "disk_utilization": 40.0}
            }
        ]
    }
    batch_resp = client.post("/telemetry/batch", json=batch_payload, headers=auth_headers)
    assert batch_resp.status_code == 200
    assert batch_resp.json()["inserted_count"] == 2
    print("  [OK] POST /telemetry/batch PASSED")

    # 4. Test GET /nodes
    print("\n[TEST 4/6] Testing GET /nodes ...")
    response = client.get("/nodes")
    print(f"  Response Status: {response.status_code}")
    print(f"  Response Body  : {json.dumps(response.json(), indent=2)}")
    assert response.status_code == 200
    nodes_data = response.json()
    assert nodes_data["total_nodes"] >= 2
    node_ids = [n["node_id"] for n in nodes_data["nodes"]]
    assert "test_node_alpha" in node_ids
    assert "test_node_beta_auto" in node_ids
    print("  [OK] GET /nodes PASSED")

    # 5. Test GET /nodes/{node_id}
    print("\n[TEST 5/6] Testing GET /nodes/test_node_alpha ...")
    response = client.get("/nodes/test_node_alpha")
    print(f"  Response Status: {response.status_code}")
    node_detail = response.json()
    print(f"  Node Hostname  : {node_detail['hostname']}")
    print(f"  Status         : {node_detail['status']}")
    print(f"  Telemetry Count: {len(node_detail['recent_telemetry'])}")
    assert response.status_code == 200
    assert node_detail["node_id"] == "test_node_alpha"
    assert len(node_detail["recent_telemetry"]) > 0
    print("  [OK] GET /nodes/{node_id} PASSED")

    # 6. Test POST /heartbeat
    print("\n[TEST 6/6] Testing POST /heartbeat ...")
    response = client.post("/heartbeat", json={"node_id": "test_node_alpha"}, headers=auth_headers)
    print(f"  Response Status: {response.status_code}")
    print(f"  Response Body  : {response.json()}")
    assert response.status_code == 200
    assert response.json()["status"] == "acknowledged"
    print("  [OK] POST /heartbeat PASSED")

    print("\n" + "=" * 65)
    print("[SUCCESS] ALL CENTRAL TELEMETRY REST API TESTS PASSED SUCCESSFULLY!")
    print("=" * 65)

if __name__ == "__main__":
    run_tests()
