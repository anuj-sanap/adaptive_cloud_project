"""Validate dynamic registration, identity, timeout, recovery, and node listing."""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["NODE_OFFLINE_THRESHOLD_SEC"] = "2"
sys.path.insert(0, os.path.join(PROJECT_DIR, "src"))

from fastapi.testclient import TestClient
from central_server.api import app
from central_server.database import get_connection, init_db
from central_server.security import get_cluster_api_key
from node_agent.id_generator import get_or_create_node_id


def telemetry_payload(node_id, timestamp=None):
    return {
        "node_id": node_id,
        "hostname": f"host-{node_id[-8:]}",
        "operating_system": "test",
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        "metrics": {
            "cpu_utilization": 25.0,
            "ram_utilization": 35.0,
            "disk_utilization": 30.0,
            "network_sent_mb": 10.0,
            "network_recv_mb": 20.0,
            "process_count": 100,
        },
    }


def set_last_seen(node_id, timestamp):
    connection = get_connection()
    try:
        connection.execute("UPDATE nodes SET last_seen = ?, status = 'ONLINE' WHERE node_id = ?", (timestamp, node_id))
        connection.commit()
    finally:
        connection.close()


def run_tests():
    init_db()
    api_key = get_cluster_api_key()
    auth_headers = {"X-API-Key": api_key}
    client = TestClient(app)
    suffix_token = uuid.uuid4().hex[:8]
    node_ids = [get_or_create_node_id(f"lifecycle_{suffix_token}_{index}") for index in range(3)]
    assert len(node_ids) == len(set(node_ids)) == 3
    assert get_or_create_node_id(f"lifecycle_{suffix_token}_0") == node_ids[0]

    for index, node_id in enumerate(node_ids):
        if index < 2:
            registered = client.post("/register", json={
                "node_id": node_id,
                "hostname": f"dynamic-host-{index}",
                "operating_system": "test",
            }, headers=auth_headers)
            assert registered.status_code == 200
        telemetry = client.post("/telemetry", json=telemetry_payload(node_id), headers=auth_headers)
        assert telemetry.status_code == 200
        heartbeat = client.post("/heartbeat", json={"node_id": node_id}, headers=auth_headers)
        assert heartbeat.status_code == 200

    listed = client.get("/nodes").json()["nodes"]
    listed_by_id = {node["node_id"]: node for node in listed}
    assert all(listed_by_id[node_id]["status"] == "ONLINE" for node_id in node_ids)

    stale = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    set_last_seen(node_ids[0], stale)
    offline_listing = client.get("/nodes").json()["nodes"]
    assert {node["node_id"]: node for node in offline_listing}[node_ids[0]]["status"] == "OFFLINE"

    recovered_by_heartbeat = client.post("/heartbeat", json={"node_id": node_ids[0]}, headers=auth_headers)
    assert recovered_by_heartbeat.status_code == 200
    assert {node["node_id"]: node for node in client.get("/nodes").json()["nodes"]}[node_ids[0]]["status"] == "ONLINE"

    set_last_seen(node_ids[1], stale)
    recovered_by_telemetry = client.post("/telemetry", json=telemetry_payload(node_ids[1]), headers=auth_headers)
    assert recovered_by_telemetry.status_code == 200
    final_listing = {node["node_id"]: node for node in client.get("/nodes").json()["nodes"]}
    assert final_listing[node_ids[1]]["status"] == "ONLINE"
    assert all(node_id in final_listing for node_id in node_ids)

    print("[SUCCESS] DYNAMIC NODE TESTS PASSED")
    print("  node_ids:", ", ".join(node_ids))
    print("  lifecycle: REGISTERED -> ONLINE -> OFFLINE -> ONLINE")


if __name__ == "__main__":
    run_tests()
