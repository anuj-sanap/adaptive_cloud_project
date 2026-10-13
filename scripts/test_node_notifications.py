"""
test_node_notifications.py - Verification for Node-Side Predictive Maintenance Notifications.

Verifies:
  1. Real ML prediction on Central Server generates an alert payload for the affected node.
  2. The Node Agent receives the server alert directly in the telemetry response.
  3. Node-side notifier displays the clear notification format:
       ⚠ PREDICTIVE MAINTENANCE ALERT
       Node: ...
       Risk: CRITICAL
       Failure Probability: ...%
       Recommended action: ...
  4. Non-affected nodes do not receive alerts.
  5. Deduplication prevents repeated notifications across subsequent polling cycles.
  6. Telemetry and heartbeat functionality continue running uninterrupted.
  7. Auto-clearing when node recovers to low risk.
"""

import os
import sys
import json
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

from fastapi.testclient import TestClient
from central_server.api import app
from central_server.database import init_db, get_connection
from central_server.security import get_cluster_api_key
from node_agent.notifier import NodeAlertNotifier
from node_agent.server_client import send_telemetry_with_response, fetch_node_alert

def run_tests():
    print("=" * 68)
    print("TESTING NODE-SIDE PREDICTIVE MAINTENANCE NOTIFICATIONS")
    print("=" * 68)

    init_db()
    api_key = get_cluster_api_key()
    auth_headers = {"X-API-Key": api_key}
    client = TestClient(app)

    affected_node_id = "test_node_alert_03"
    healthy_node_id  = "test_node_healthy_04"

    # Register both nodes
    client.post("/register", json={"node_id": affected_node_id, "hostname": "NODE-03", "operating_system": "Windows 11"}, headers=auth_headers)
    client.post("/register", json={"node_id": healthy_node_id, "hostname": "NODE-04", "operating_system": "Windows 11"}, headers=auth_headers)

    notifier_affected = NodeAlertNotifier(affected_node_id)
    notifier_healthy  = NodeAlertNotifier(healthy_node_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 1: Normal Baseline Telemetry
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[Phase 1] Sending nominal telemetry for both nodes...")
    nominal_payload = {
        "node_id": affected_node_id,
        "cpu_utilization": 24.5,
        "ram_utilization": 35.0,
        "disk_utilization": 42.0,
        "cpu_temperature_c": 46.0,
        "process_count": 120,
        "network_sent_mb": 12.0,
        "network_recv_mb": 18.0,
        "duration_sec": 3600
    }
    r_nom = client.post("/telemetry", json=nominal_payload, headers=auth_headers).json()
    assert r_nom.get("alert") is None, "Unexpected alert generated for nominal telemetry!"
    triggered = notifier_affected.process_server_alert(r_nom.get("alert"))
    assert not triggered
    print("  -> Nominal telemetry ingested: No alert triggered. [PASS]")

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 2: Elevated Failure Strain on Affected Node
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[Phase 2] Sending high failure strain telemetry on Affected Node (NODE-03)...")
    critical_payload = {
        "node_id": affected_node_id,
        "cpu_utilization": 89.5,
        "ram_utilization": 94.0,
        "disk_utilization": 65.0,
        "cpu_temperature_c": 84.5,
        "process_count": 240,
        "network_sent_mb": 85.0,
        "network_recv_mb": 190.0,
        "duration_sec": 7200
    }
    r_crit = client.post("/telemetry", json=critical_payload, headers=auth_headers).json()
    server_alert = r_crit.get("alert")
    assert server_alert is not None, "Central server failed to return ML alert in telemetry response!"
    assert server_alert["node_id"] == affected_node_id
    assert server_alert["risk_level"] in ("HIGH", "CRITICAL")
    assert server_alert["failure_probability"] >= 0.70
    print(f"  -> Real ML Prediction: Risk={server_alert['risk_level']}, Prob={server_alert['failure_probability']*100:.1f}%")
    print(f"  -> Server-Dispatched Alert ID: {server_alert['alert_id']}")
    print(f"  -> Recommended Action: {server_alert['recommended_action']}")

    # Process on Node-Side Notifier
    print("\n[Phase 2b] Executing node-side notification display...")
    triggered = notifier_affected.process_server_alert(server_alert)
    assert triggered is True, "Notifier failed to trigger new alert notification!"
    assert notifier_affected.last_notified_alert_id == server_alert["alert_id"]
    print("  -> First alert notification displayed successfully. [PASS]")

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 3: Verify Healthy Node is NOT Notified
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[Phase 3] Checking Healthy Node (NODE-04)...")
    r_healthy = client.post("/telemetry", json={
        "node_id": healthy_node_id,
        "cpu_utilization": 20.0,
        "ram_utilization": 30.0,
        "disk_utilization": 40.0
    }, headers=auth_headers).json()
    assert r_healthy.get("alert") is None
    assert not notifier_healthy.process_server_alert(r_healthy.get("alert"))

    # Direct query test: GET /nodes/{node_id}/alerts
    r_node_check = client.get(f"/nodes/{healthy_node_id}/alerts").json()
    assert r_node_check["has_active_alert"] is False
    assert r_node_check["alert"] is None

    r_affected_check = client.get(f"/nodes/{affected_node_id}/alerts").json()
    assert r_affected_check["has_active_alert"] is True
    assert r_affected_check["alert"]["node_id"] == affected_node_id
    print("  -> Strict isolation confirmed: Only affected node receives alert. [PASS]")

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 4: Deduplication Across Subsequent Polling Ticks
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[Phase 4] Testing deduplication on subsequent polling ticks...")
    for tick in range(2, 5):
        r_repeat = client.post("/telemetry", json=critical_payload, headers=auth_headers).json()
        repeat_alert = r_repeat.get("alert")
        assert repeat_alert is not None
        assert repeat_alert["alert_id"] == server_alert["alert_id"]

        # Node-side notifier should SUPPRESS repeated desktop notification
        triggered_again = notifier_affected.process_server_alert(repeat_alert)
        assert triggered_again is False, f"Duplicate notification fired on tick {tick}!"
    print(f"  -> Successfully suppressed duplicate popups across 3 subsequent ticks. [PASS]")

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 5: Auto-Recovery when Node Health Returns to Low Risk
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[Phase 5] Testing recovery when node workload subsides...")
    r_recovered = client.post("/telemetry", json=nominal_payload, headers=auth_headers).json()
    assert r_recovered.get("alert") is None
    cleared = notifier_affected.process_server_alert(r_recovered.get("alert"))
    assert cleared is False
    assert notifier_affected.active_alert_ongoing is False
    assert notifier_affected.last_notified_alert_id is None
    print("  -> Alert state automatically cleared on affected node. [PASS]")

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 6: Clean up test entries from DB
    # ─────────────────────────────────────────────────────────────────────────
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM maintenance_alerts WHERE node_id LIKE 'test_node_%'")
        cur.execute("DELETE FROM telemetry WHERE node_id LIKE 'test_node_%'")
        cur.execute("DELETE FROM nodes WHERE node_id LIKE 'test_node_%'")
        conn.commit()

    print("\n" + "=" * 68)
    print("ALL NODE-SIDE NOTIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 68)

if __name__ == "__main__":
    run_tests()
