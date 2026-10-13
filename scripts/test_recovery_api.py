"""
test_recovery_api.py - Test FastAPI endpoints for Adaptive Recovery Decision Engine.
Verifies /recovery/evaluate, /recovery/decisions, and /recovery/history/{node_id}.
"""

import os
import sys
import uuid
import unittest
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from central_server.api import app
from central_server.database import register_node, init_db


class TestRecoveryAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.node_id = f"api-test-node-{uuid.uuid4().hex[:6]}"
        register_node(self.node_id, "api-node", "127.0.0.1", "Windows", {})

    def test_01_evaluate_and_execute_endpoint(self):
        """Test POST /recovery/evaluate triggers ranking, safe execution, and returns decision."""
        payload = {
            "node_id": self.node_id,
            "incident_type": "HIGH_CPU",
            "severity": "MEDIUM",
            "telemetry": {"cpu_utilization": 88.5, "ram_utilization": 45.0},
            "fresh_telemetry": {"cpu_utilization": 64.0, "ram_utilization": 44.0},
            "verification_timeout_sec": 0.2,
            "execute": True,
        }
        resp = self.client.post("/recovery/evaluate", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("decision_id", data)
        self.assertEqual(data["node_id"], self.node_id)
        self.assertEqual(data["incident_type"], "HIGH_CPU")
        self.assertEqual(data["severity"], "MEDIUM")
        self.assertEqual(data["selected_action"], "THROTTLE_PROCESS_WORKLOAD")
        self.assertIn("ranking_rationale", data)
        self.assertIn("candidate_rankings", data)
        self.assertTrue(len(data["candidate_rankings"]) > 0)
        self.assertIn("execution_result", data)
        self.assertTrue(data["execution_result"]["success"])

    def test_02_evaluate_dry_run_endpoint(self):
        """Test POST /recovery/evaluate with execute=False scores candidates without executing."""
        payload = {
            "node_id": self.node_id,
            "incident_type": "HIGH_MEMORY",
            "severity": "LOW",
            "telemetry": {"ram_utilization": 72.0},
            "execute": False,
        }
        resp = self.client.post("/recovery/evaluate", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("decision_id", data)
        self.assertEqual(data["selected_action"], "CLEAR_MEMORY_CACHE")
        self.assertEqual(data["execution_status"], "PENDING")
        self.assertIsNone(data["execution_result"])

    def test_03_get_recovery_decisions_audit_log(self):
        """Test GET /recovery/decisions retrieves audit log of past evaluations."""
        # Run an evaluation first
        self.client.post("/recovery/evaluate", json={
            "node_id": self.node_id,
            "incident_type": "HIGH_DISK",
            "severity": "LOW",
            "telemetry": {"disk_utilization": 90.0},
            "execute": True,
        })

        resp = self.client.get(f"/recovery/decisions?node_id={self.node_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("decisions", data)
        self.assertGreaterEqual(len(data["decisions"]), 1)
        latest = data["decisions"][0]
        self.assertEqual(latest["node_id"], self.node_id)
        self.assertEqual(latest["selected_action"], "CLEAN_TEMP_STORAGE")

    def test_04_get_recovery_history_endpoint(self):
        """Test GET /recovery/history/{node_id} retrieves node-specific learned scores."""
        # Execute action to generate history
        self.client.post("/recovery/evaluate", json={
            "node_id": self.node_id,
            "incident_type": "HIGH_CPU",
            "severity": "MEDIUM",
            "telemetry": {"cpu_utilization": 85.0},
            "fresh_telemetry": {"cpu_utilization": 60.0},
            "verification_timeout_sec": 0.2,
            "execute": True,
        })

        resp = self.client.get(f"/recovery/history/{self.node_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["node_id"], self.node_id)
        self.assertIn("history", data)
        self.assertGreaterEqual(len(data["history"]), 1)
        action_item = data["history"][0]
        self.assertIn("trials", action_item)
        self.assertIn("successes", action_item)
        self.assertIn("success_rate", action_item)

    def test_05_get_recovery_incidents_endpoint(self):
        """Test GET /recovery/incidents returns actual cluster incidents and risk assessments."""
        resp = self.client.get(f"/recovery/incidents?node_id={self.node_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total", data)
        self.assertIn("incidents", data)
        self.assertGreaterEqual(data["total"], 1)
        inc = data["incidents"][0]
        self.assertEqual(inc["node_id"], self.node_id)
        self.assertIn("incident_id", inc)
        self.assertIn("incident_type", inc)
        self.assertIn("risk_assessment", inc)
        self.assertIn("supporting_evidence", inc)

    def test_06_disruptive_action_requires_authorization(self):
        """Test that potentially disruptive action requires explicit operator approval."""
        # Request PREDICTIVE_FAILURE with HIGH severity (which ranks DRAIN_AND_FAILOVER or SANDBOX)
        payload = {
            "node_id": self.node_id,
            "incident_type": "PREDICTIVE_FAILURE",
            "severity": "CRITICAL",
            "telemetry": {"cpu_utilization": 95.0, "ram_utilization": 92.0},
            "execute": True,
            "approved": False,  # Not approved by operator!
        }
        resp = self.client.post("/recovery/evaluate", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        if data.get("is_disruptive"):
            self.assertTrue(data.get("requires_authorization"))
            self.assertEqual(data.get("lifecycle_status"), "PROPOSED")
            self.assertIn("AUTHORIZATION REQUIRED", data.get("ranking_rationale"))

    def test_07_approve_and_execute_recovery(self):
        """Test POST /recovery/approve-and-execute grants operator authorization and executes."""
        payload = {
            "node_id": self.node_id,
            "incident_type": "HIGH_CPU",
            "severity": "MEDIUM",
            "telemetry": {"cpu_utilization": 86.0},
            "fresh_telemetry": {"cpu_utilization": 62.0},
            "verification_timeout_sec": 0.2,
        }
        resp = self.client.post("/recovery/approve-and-execute", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("is_approved"))
        self.assertIn(data.get("lifecycle_status"), ["SUCCESSFUL", "FAILED", "EXECUTING", "INCONCLUSIVE"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
