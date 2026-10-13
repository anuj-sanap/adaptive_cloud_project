"""Verify per-agent credentials, node ownership, location metadata, and heartbeat status."""

import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

TEST_DIR = tempfile.mkdtemp(prefix="adaptive-agent-identity-")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
os.environ["TELEMETRY_DB_PATH"] = os.path.join(TEST_DIR, "telemetry.db")
os.environ["SERVER_API_KEY"] = "identity-test-admin-key"
os.environ["DISABLE_AUTH"] = "false"
os.environ["NODE_OFFLINE_THRESHOLD_SEC"] = "5"

from fastapi.testclient import TestClient
from central_server.api import app
from central_server.database import get_connection, get_all_nodes, init_db
from node_agent.metrics import collect_node_telemetry


def run_tests():
    init_db()
    client = TestClient(app)
    admin_headers = {"X-API-Key": os.environ["SERVER_API_KEY"]}
    assert client.get("/nodes").json()["total_nodes"] == 0

    run_id = uuid.uuid4().hex[:10]
    node_ids = [f"identity-alpha-{run_id}", f"identity-beta-{run_id}"]
    locations = ["North Office", "Remote Studio"]
    credentials = []

    for node_id, location in zip(node_ids, locations):
        response = client.post("/agents/provision", headers=admin_headers, json={
            "node_id": node_id,
            "hostname": f"host-{node_id}",
            "operating_system": "Test OS",
            "hardware_info": {"cpu_count_logical": 4},
            "location_label": location,
        })
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["node_id"] == node_id
        assert data["credential_storage"] == "hash_only"
        assert "agent_api_key" in data
        credentials.append(data["agent_api_key"])

    duplicate = client.post("/agents/provision", headers=admin_headers, json={
        "node_id": node_ids[0], "hostname": "duplicate", "location_label": locations[0],
    })
    assert duplicate.status_code == 409

    for node_id, credential, location in zip(node_ids, credentials, locations):
        headers = {"X-API-Key": credential}
        telemetry = collect_node_telemetry(node_id)
        telemetry["location_label"] = location
        response = client.post("/telemetry", headers=headers, json=telemetry)
        assert response.status_code == 200, response.text
        heartbeat = client.post("/heartbeat", headers=headers, json={"node_id": node_id})
        assert heartbeat.status_code == 200, heartbeat.text

    alpha_headers = {"X-API-Key": credentials[0]}
    spoofed_telemetry = client.post("/telemetry", headers=alpha_headers, json={
        "node_id": node_ids[1], "metrics": {"cpu_utilization": 99.0},
    })
    assert spoofed_telemetry.status_code == 403
    spoofed_heartbeat = client.post("/heartbeat", headers=alpha_headers, json={"node_id": node_ids[1]})
    assert spoofed_heartbeat.status_code == 403

    nodes = {node["node_id"]: node for node in client.get("/nodes").json()["nodes"]}
    assert set(nodes) == set(node_ids)
    assert [nodes[node_id]["location_label"] for node_id in node_ids] == locations
    for node_id in node_ids:
        latest = nodes[node_id]["latest_telemetry"]
        assert latest["node_id"] == node_id
        assert latest["timestamp"]
        assert latest["cpu_utilization"] is not None
        assert nodes[node_id]["last_heartbeat"]

    # Old buffered telemetry cannot keep a node online; a heartbeat can.
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE nodes SET last_heartbeat = ?, last_seen = ? WHERE node_id = ?",
            (stale_time, datetime.now(timezone.utc).isoformat(), node_ids[0]),
        )
        conn.commit()
    nodes = {node["node_id"]: node for node in client.get("/nodes").json()["nodes"]}
    assert nodes[node_ids[0]]["status"] == "OFFLINE"
    recovered = client.post("/heartbeat", headers=alpha_headers, json={"node_id": node_ids[0]})
    assert recovered.status_code == 200
    nodes = {node["node_id"]: node for node in client.get("/nodes").json()["nodes"]}
    assert nodes[node_ids[0]]["status"] == "ONLINE"

    # Reopening the schema preserves both node records and their telemetry.
    init_db()
    persisted = {node["node_id"]: node for node in get_all_nodes()}
    assert set(node_ids).issubset(persisted)
    assert all(persisted[node_id]["latest_telemetry"] for node_id in node_ids)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT node_id, token_hash FROM node_agent_credentials ORDER BY node_id"
        ).fetchall()
        assert len(rows) == 2
        assert all(row["token_hash"] not in credentials for row in rows)

    client.close()
    print("PASS: independent agent credentials, anti-spoofing, real telemetry, locations, heartbeat timeout, and SQLite persistence")


if __name__ == "__main__":
    run_tests()
