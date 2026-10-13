"""
Unit & Integration Test Suite for Recovery Decision Lab (Dashboard Tab 5)
========================================================================
Validates data flow, scenario configurations, ML risk evaluations,
adaptive decision scoring, baseline rule comparison, and verified outcome history.
"""

import sys
import os
import unittest
from datetime import datetime, timezone

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from app.dashboard import (
    DEMO_SCENARIOS,
    STATIC_BASELINE_RULES,
    get_fixed_rule_selection,
    _evaluate_node_ml_risks,
)
from central_server.database import (
    init_db,
    get_all_nodes,
    record_action_outcome,
    get_action_history,
    get_comparable_fleet_action_history,
    get_all_action_history_for_node,
)
from recovery.decision_engine import (
    AdaptiveRecoveryDecisionEngine,
    DEFAULT_ACTION_CATALOG,
)
from recovery.models import (
    Incident,
    IncidentType,
    SeverityLevel,
    VerificationStatus,
    RecoveryCriteria,
    VerificationResult,
)


class TestRecoveryDecisionLabDataFlow(unittest.TestCase):
    """Test suite for the Recovery Decision Lab data flow and components."""

    @classmethod
    def setUpClass(cls):
        init_db()

    def test_01_demo_scenarios_schema(self):
        """Verify all DEMO_SCENARIOS have required schema fields and valid actions."""
        required_keys = ["name", "is_simulated", "description", "incident_type", "severity"]
        for key, sc in DEMO_SCENARIOS.items():
            for rk in required_keys:
                self.assertIn(rk, sc, f"Scenario '{key}' missing required key '{rk}'")
            self.assertIsInstance(sc["is_simulated"], bool)
            self.assertIn(sc["incident_type"], [e.value for e in IncidentType])
            self.assertIn(sc["severity"], ["LOW", "MEDIUM", "HIGH", "CRITICAL"])

    def test_02_fixed_rule_baseline(self):
        """Verify fixed-rule baseline returns deterministic rule-based decisions."""
        # CPU incident
        cpu_res = get_fixed_rule_selection("HIGH_CPU", "CRITICAL")
        self.assertEqual(cpu_res["action_id"], "THROTTLE_PROCESS_WORKLOAD")
        self.assertEqual(cpu_res["policy_type"], "Static Fixed-Rule Baseline")
        self.assertIn("Static heuristic rule", cpu_res["rationale"])

        # Memory incident
        mem_res = get_fixed_rule_selection("HIGH_MEMORY", "HIGH")
        self.assertEqual(mem_res["action_id"], "CLEAR_MEMORY_CACHE")

        # Disk incident
        disk_res = get_fixed_rule_selection("HIGH_DISK", "MEDIUM")
        self.assertEqual(disk_res["action_id"], "CLEAN_TEMP_STORAGE")

        # Unknown incident defaults safely to ROUTINE_OBSERVATION
        unk_res = get_fixed_rule_selection("NONEXISTENT_INCIDENT", "LOW")
        self.assertEqual(unk_res["action_id"], "ROUTINE_OBSERVATION")

    def test_03_evaluate_node_ml_risks(self):
        """Verify _evaluate_node_ml_risks integrates predictive, anomaly, security, and fused models."""
        sample_metrics = {
            "cpu_utilization": 88.5,
            "ram_utilization": 92.0,
            "disk_utilization": 65.0,
            "process_count": 310,
        }
        res = _evaluate_node_ml_risks(sample_metrics, "node_india_01")
        self.assertIn("maintenance", res)
        self.assertIn("infrastructure", res)
        self.assertIn("security", res)
        self.assertIn("integrated", res)

        # Risk value assertions
        self.assertTrue(0.0 <= res["maintenance"]["failure_prob"] <= 1.0)
        self.assertTrue(0.0 <= res["infrastructure"]["anomaly_prob"] <= 1.0)
        self.assertTrue(0.0 <= res["integrated"]["overall_score"] <= 1.0)
        self.assertIn(res["integrated"]["risk_level"], ["LOW", "MEDIUM", "HIGH", "CRITICAL"])

    def test_04_adaptive_engine_cold_start_vs_evidence(self):
        """Verify decision engine distinguishes Catalog Prior from Learned Evidence."""
        test_node = f"test_lab_node_{datetime.now().strftime('%M%S')}"

        # 1. Cold start: node has 0 trials
        history_before = get_all_action_history_for_node(test_node)
        self.assertEqual(len(history_before), 0)

        engine = AdaptiveRecoveryDecisionEngine(share_fleet_evidence=False)
        inc = Incident(
            node_id=test_node,
            incident_type=IncidentType.HIGH_CPU,
            severity=SeverityLevel.MEDIUM,
            telemetry={"cpu_utilization": 92.0, "ram_utilization": 55.0, "disk_utilization": 40.0},
        )
        dec = engine.evaluate_and_recover(
            incident=inc,
            auto_execute=True,
            verification_timeout_sec=5.0,
            telemetry_provider={"cpu_utilization": 60.0, "ram_utilization": 55.0, "disk_utilization": 40.0},
        )

        self.assertIsNotNone(dec.selected_action)
        self.assertEqual(dec.verification_status, "SUCCESS")

        # 2. Database should now contain 1 verified trial for this action
        history_after = get_action_history(test_node, "HIGH_CPU", dec.selected_action.action_id)
        self.assertIsNotNone(history_after)
        self.assertEqual(history_after["trials"], 1)
        self.assertEqual(history_after["successes"], 1)
        self.assertEqual(history_after["last_outcome"], "SUCCESS")

    def test_05_scenario_execution_and_closed_loop_verification(self):
        """Execute Scenario 1 (Transient Compute Spike) and assert SUCCESS."""
        scenario = DEMO_SCENARIOS["1_TRANSIENT_CPU"]
        node_id = "test_scenario_node_1"

        engine = AdaptiveRecoveryDecisionEngine(share_fleet_evidence=False)
        inc = Incident(
            node_id=node_id,
            incident_type=IncidentType(scenario["incident_type"]),
            severity=SeverityLevel[scenario["severity"]],
            telemetry=scenario["baseline_telemetry"],
        )

        dec = engine.evaluate_and_recover(
            incident=inc,
            auto_execute=True,
            verification_timeout_sec=5.0,
            telemetry_provider=scenario["fresh_telemetry"],
        )

        self.assertIsNotNone(dec.selected_action)
        self.assertEqual(dec.selected_action.action_id, "THROTTLE_PROCESS_WORKLOAD")
        self.assertEqual(dec.verification_status, "SUCCESS")
        self.assertIsNotNone(dec.verification_result)
        self.assertTrue(dec.verification_result.verification_duration_sec >= 0.0)
        self.assertEqual(dec.verification_result.status, VerificationStatus.SUCCESS)

    def test_06_inconclusive_scenario_data_flow(self):
        """Verify Scenario 4 (Telemetry Dropout) yields INCONCLUSIVE without corrupting score."""
        scenario = DEMO_SCENARIOS["4_TELEMETRY_DROPOUT"]
        node_id = "test_dropout_node"

        engine = AdaptiveRecoveryDecisionEngine(share_fleet_evidence=False)
        inc = Incident(
            node_id=node_id,
            incident_type=IncidentType(scenario["incident_type"]),
            severity=SeverityLevel[scenario["severity"]],
            telemetry=scenario["baseline_telemetry"],
        )

        # fresh_telemetry is None -> simulate agent dropout
        dec = engine.evaluate_and_recover(
            incident=inc,
            auto_execute=True,
            verification_timeout_sec=2.0,
            telemetry_provider=None,
        )

        self.assertEqual(dec.verification_status, "INCONCLUSIVE")
        self.assertIsNotNone(dec.verification_result)
        self.assertEqual(dec.verification_result.status, VerificationStatus.INCONCLUSIVE)
        self.assertTrue(dec.verification_result.telemetry_unavailable)

        # Trials in action history must NOT be incremented for inconclusive verification
        history = get_action_history(node_id, "HIGH_CPU", dec.selected_action.action_id)
        self.assertIsNone(history)


if __name__ == "__main__":
    unittest.main(verbosity=2)
