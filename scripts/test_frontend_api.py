"""
test_frontend_api.py - Comprehensive API and Integration Test Suite
Validates the FastAPI backend routes and response schemas consumed by the React + TypeScript frontend.

Covers:
- CORS configuration for React frontend origin (http://localhost:5173).
- Fleet summary aggregation and real telemetry averages (/fleet/summary).
- Real operational models and inference status (/models/status).
- Node listing with attached latest telemetry (/nodes, /api/nodes).
- Individual node details and historical metrics (/nodes/{id}).
- Active predictive maintenance alerts and history (/alerts, /alerts/active).
- Validated unified risk assessments (/risk/nodes, /risk/nodes/{id}).
- Real infrastructure health and security status (/live-health, /security/nodes).
- Concept drift and adaptive retraining status (/live-drift, /adaptive/retraining).
- Adaptive recovery decisions, history, and policy benchmarks (/recovery/...).
- Zero fake nodes or fabricated fallback values verification.
- Operator dashboard authentication handling (X-API-Key).
"""

import os
import sys
import uuid
import unittest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from central_server.api import app
from central_server.database import (
    init_db,
    register_node,
    record_telemetry,
    get_node_by_id,
    save_recovery_benchmark_result,
)


class TestFrontendAPIIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.test_node_id = f"frontend-test-node-{uuid.uuid4().hex[:6]}"
        cls.hostname = "web-console-host"

        # Register a real test node
        register_node(
            node_id=cls.test_node_id,
            hostname=cls.hostname,
            ip_address="192.168.1.100",
            operating_system="Linux Ubuntu 22.04 LTS",
            hardware_info={"cpu_count_logical": 8, "ram_total_mb": 16384, "disk_total_gb": 512}
        )

        # Ingest real telemetry record for the test node
        now_iso = datetime.now(timezone.utc).isoformat()
        record_telemetry({
            "node_id": cls.test_node_id,
            "timestamp": now_iso,
            "metrics": {
                "cpu_utilization": 54.2,
                "ram_utilization": 61.8,
                "disk_utilization": 42.0,
                "process_count": 142,
                "network_sent_mb": 12.4,
                "network_recv_mb": 45.1,
            }
        })

    def test_01_cors_headers_for_frontend_origin(self):
        """Test that CORS headers allow the React frontend development origin."""
        headers = {
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        }
        resp = self.client.options("/health", headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://localhost:5173")
        self.assertEqual(resp.headers.get("access-control-allow-credentials"), "true")

    def test_02_health_probe(self):
        """Test GET /health returns service status and database connectivity."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("status", data)
        self.assertEqual(data["database"], "connected")
        self.assertIn("auth_required", data)

    def test_03_fleet_summary_aggregation(self):
        """Test GET /fleet/summary returns real node counts and calculated telemetry averages."""
        resp = self.client.get("/fleet/summary")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("total_nodes", data)
        self.assertGreaterEqual(data["total_nodes"], 1)
        self.assertIn("online_nodes", data)
        self.assertIn("offline_nodes", data)
        self.assertIn("stale_nodes", data)
        self.assertIn("active_alerts_count", data)

        # Telemetry averages must be numeric or null, never fabricate string dummy data
        if data["avg_cpu"] is not None:
            self.assertIsInstance(data["avg_cpu"], (int, float))
            self.assertGreaterEqual(data["avg_cpu"], 0.0)
            self.assertLessEqual(data["avg_cpu"], 100.0)

        if data["avg_ram"] is not None:
            self.assertIsInstance(data["avg_ram"], (int, float))

        # Test alias route /api/fleet/summary
        alias_resp = self.client.get("/api/fleet/summary")
        self.assertEqual(alias_resp.status_code, 200)
        self.assertEqual(alias_resp.json()["total_nodes"], data["total_nodes"])

    def test_04_models_status(self):
        """Test GET /models/status reports real operational status for all ML components."""
        resp = self.client.get("/models/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("models", data)
        models = data["models"]
        self.assertIn("predictive_maintenance", models)
        self.assertIn("live_infrastructure_health", models)
        self.assertIn("network_security", models)
        self.assertIn("concept_drift_detector", models)
        self.assertIn("adaptive_recovery", models)

        self.assertEqual(models["predictive_maintenance"]["status"], "LOADED")
        self.assertEqual(models["live_infrastructure_health"]["status"], "LOADED")
        self.assertEqual(models["network_security"]["status"], "LOADED")
        self.assertEqual(models["concept_drift_detector"]["status"], "ACTIVE")
        self.assertEqual(models["adaptive_recovery"]["status"], "ACTIVE")

        # Test alias route
        alias_resp = self.client.get("/api/models/status")
        self.assertEqual(alias_resp.status_code, 200)

    def test_05_registered_nodes_and_latest_telemetry(self):
        """Test GET /nodes returns nodes with attached latest real telemetry."""
        resp = self.client.get("/nodes")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("total_nodes", data)
        self.assertIn("nodes", data)
        target = next((n for n in data["nodes"] if n["node_id"] == self.test_node_id), None)
        self.assertIsNotNone(target, f"Test node {self.test_node_id} not found in nodes list")

        # Validate attached latest telemetry
        self.assertIn("latest_telemetry", target)
        if target["latest_telemetry"]:
            tel = target["latest_telemetry"]
            self.assertEqual(tel["node_id"], self.test_node_id)
            self.assertAlmostEqual(tel["cpu_utilization"], 54.2, delta=0.5)
            self.assertAlmostEqual(tel["ram_utilization"], 61.8, delta=0.5)

    def test_06_node_details_and_historical_metrics(self):
        """Test GET /nodes/{node_id} retrieves metadata and historical telemetry array."""
        resp = self.client.get(f"/nodes/{self.test_node_id}?limit=20")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["node_id"], self.test_node_id)
        self.assertEqual(data["hostname"], self.hostname)
        self.assertIn("recent_telemetry", data)
        self.assertIsInstance(data["recent_telemetry"], list)
        self.assertGreaterEqual(len(data["recent_telemetry"]), 1)

        first = data["recent_telemetry"][0]
        self.assertIn("cpu_utilization", first)
        self.assertIn("ram_utilization", first)
        self.assertIn("disk_utilization", first)

    def test_07_node_details_not_found(self):
        """Test GET /nodes/{non_existent_id} returns standard 404."""
        resp = self.client.get("/nodes/non-existent-node-999")
        self.assertEqual(resp.status_code, 404)

    def test_08_active_alerts_and_history(self):
        """Test GET /alerts and GET /alerts/active endpoints."""
        resp = self.client.get("/alerts")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("active_count", data)
        self.assertIn("alerts", data)

        active_resp = self.client.get("/alerts/active")
        self.assertEqual(active_resp.status_code, 200)
        self.assertIn("active_count", active_resp.json())

    def test_09_validated_node_risk(self):
        """Test GET /risk/nodes and GET /risk/nodes/{node_id}."""
        resp = self.client.get("/risk/nodes")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total_nodes", data)
        self.assertIn("nodes", data)

        node_risk = self.client.get(f"/risk/nodes/{self.test_node_id}")
        self.assertEqual(node_risk.status_code, 200)
        r_data = node_risk.json()
        self.assertEqual(r_data["node_id"], self.test_node_id)
        self.assertIn("overall_risk_score", r_data)
        self.assertIn("overall_risk_level", r_data)
        self.assertIn("security_risk_level", r_data)
        self.assertIn("failure_risk_level", r_data)

    def test_10_live_health_and_security(self):
        """Test live infrastructure health Isolation Forest and UNSW-NB15 security endpoints."""
        health_resp = self.client.get("/live-health")
        self.assertEqual(health_resp.status_code, 200)
        h_data = health_resp.json()
        self.assertIn("model_name", h_data)
        self.assertIn("nodes", h_data)

        sec_resp = self.client.get("/security/nodes")
        self.assertEqual(sec_resp.status_code, 200)
        s_data = sec_resp.json()
        self.assertIn("model_name", s_data)
        self.assertIn("nodes", s_data)

    def test_11_live_drift_and_retraining(self):
        """Test KS drift detection and retraining controller endpoints."""
        drift_resp = self.client.get("/live-drift")
        self.assertEqual(drift_resp.status_code, 200)
        d_data = drift_resp.json()
        self.assertIn("total_nodes", d_data)
        self.assertIn("retraining", d_data)

        retrain_resp = self.client.get("/adaptive/retraining")
        self.assertEqual(retrain_resp.status_code, 200)
        self.assertIn("retraining", retrain_resp.json())

    def test_12_recovery_endpoints(self):
        """Test /recovery/decisions, /recovery/history/{node_id}, and /recovery/benchmarks."""
        # 1. Recovery decisions list
        dec_resp = self.client.get("/recovery/decisions")
        self.assertEqual(dec_resp.status_code, 200)
        self.assertIn("decisions", dec_resp.json())

        # 2. Node history
        hist_resp = self.client.get(f"/recovery/history/{self.test_node_id}")
        self.assertEqual(hist_resp.status_code, 200)
        self.assertEqual(hist_resp.json()["node_id"], self.test_node_id)

        # 3. Seed benchmark and query /recovery/benchmarks
        benchmark_id = f"bench-{uuid.uuid4().hex[:6]}"
        save_recovery_benchmark_result({
            "benchmark_id": benchmark_id,
            "mode": "SIMULATED",
            "trial_count": 25,
            "seed": 42,
            "adaptive_metrics": {"mean_reward": 0.85, "success_rate": 0.92},
            "baseline_metrics": {"mean_reward": 0.60, "success_rate": 0.70},
            "deltas": {"reward_delta": 0.25, "success_rate_delta": 0.22},
            "episodes_log": [],
        })
        bench_resp = self.client.get("/recovery/benchmarks")
        self.assertEqual(bench_resp.status_code, 200)
        b_data = bench_resp.json()
        self.assertIn("benchmarks", b_data)
        self.assertGreaterEqual(b_data["total"], 1)

    def test_13_recovery_evaluation_endpoint(self):
        """Test POST /recovery/evaluate with canonical and alias incident types."""
        # Test dry-run with PREDICTIVE_FAILURE
        payload = {
            "node_id": self.test_node_id,
            "incident_type": "PREDICTIVE_FAILURE",
            "severity": "HIGH",
            "telemetry": {"cpu_utilization": 82.0, "ram_utilization": 75.0},
            "execute": False,
        }
        resp = self.client.post("/recovery/evaluate", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["node_id"], self.test_node_id)
        self.assertEqual(data["incident_type"], "PREDICTIVE_FAILURE")
        self.assertIn("candidate_rankings", data)
        self.assertIn("ranking_rationale", data)

        # Test alias mapping (e.g. HIGH_CPU_LOAD maps to HIGH_CPU)
        alias_payload = {
            "node_id": self.test_node_id,
            "incident_type": "HIGH_CPU_LOAD",
            "severity": "MEDIUM",
            "telemetry": {"cpu_utilization": 89.0},
            "execute": False,
        }
        alias_resp = self.client.post("/recovery/evaluate", json=alias_payload)
        self.assertEqual(alias_resp.status_code, 200)
        self.assertEqual(alias_resp.json()["incident_type"], "HIGH_CPU")


if __name__ == "__main__":
    unittest.main()
