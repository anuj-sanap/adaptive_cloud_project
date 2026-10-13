"""
test_adaptive_recovery_engine.py - Comprehensive Verification Test Suite
Tests the Adaptive Recovery Decision Engine, Multi-Factor Scoring,
Safe Execution, Outcome Verification, Node-Isolated Score Adaptation,
and Automatic Escalation.
"""

import os
import sys
import uuid
import unittest
from datetime import datetime, timezone

# Ensure project root in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from central_server.database import (
    init_db,
    register_node,
    record_telemetry,
    get_action_history,
    get_all_action_history_for_node,
    get_recovery_decisions,
)
from recovery.models import (
    Incident,
    IncidentType,
    SeverityLevel,
    RecoveryActionDefinition,
    ActionCandidateScore,
    DecisionResult,
    ExecutionResult,
)
from recovery.recovery_controller import RecoveryController
from recovery.decision_engine import (
    AdaptiveRecoveryDecisionEngine,
    DEFAULT_ACTION_CATALOG,
    get_decision_engine,
)


class TestAdaptiveRecoveryDecisionEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.engine = AdaptiveRecoveryDecisionEngine()
        cls.controller = RecoveryController()

    def setUp(self):
        self.node_id_1 = f"test-node-alpha-{uuid.uuid4().hex[:6]}"
        self.node_id_2 = f"test-node-beta-{uuid.uuid4().hex[:6]}"
        register_node(self.node_id_1, "alpha-host", "192.168.1.50", "Windows", {})
        register_node(self.node_id_2, "beta-host", "192.168.1.51", "Linux", {})

    def test_01_candidate_ranking_and_authorization_filtering(self):
        """Test candidate actions are ranked and filtered by severity authorization."""
        # 1. Low severity incident - actions requiring MEDIUM or HIGH must be filtered as unauthorized
        incident_low = Incident(
            node_id=self.node_id_1,
            incident_type=IncidentType.HIGH_CPU,
            severity=SeverityLevel.LOW,
            telemetry={"cpu_utilization": 65.0, "ram_utilization": 50.0},
        )
        decision_low = self.engine.evaluate_actions(incident_low)
        self.assertIsNotNone(decision_low.candidate_rankings)
        self.assertTrue(len(decision_low.candidate_rankings) > 0)

        # THROTTLE_PROCESS_WORKLOAD requires MEDIUM severity, so at LOW severity it must be unauthorized
        throttle_cand = next((c for c in decision_low.candidate_rankings if c.action_id == "THROTTLE_PROCESS_WORKLOAD"), None)
        if throttle_cand:
            self.assertFalse(throttle_cand.is_authorized)
            self.assertEqual(throttle_cand.score, -1.0)
            self.assertIn("Unauthorized", throttle_cand.rationale)

        # 2. Medium severity incident - THROTTLE_PROCESS_WORKLOAD should now be authorized
        incident_med = Incident(
            node_id=self.node_id_1,
            incident_type=IncidentType.HIGH_CPU,
            severity=SeverityLevel.MEDIUM,
            telemetry={"cpu_utilization": 88.0, "ram_utilization": 55.0},
        )
        decision_med = self.engine.evaluate_actions(incident_med)
        throttle_cand_med = next((c for c in decision_med.candidate_rankings if c.action_id == "THROTTLE_PROCESS_WORKLOAD"), None)
        self.assertIsNotNone(throttle_cand_med)
        self.assertTrue(throttle_cand_med.is_authorized)
        self.assertGreater(throttle_cand_med.score, 0.0)
        self.assertEqual(decision_med.selected_action.action_id, "THROTTLE_PROCESS_WORKLOAD")

    def test_02_safe_controller_execution_and_objective_measurement(self):
        """Test execution delegates safely to RecoveryController without arbitrary command risk."""
        incident = Incident(
            node_id=self.node_id_1,
            incident_type=IncidentType.HIGH_MEMORY,
            severity=SeverityLevel.MEDIUM,
            telemetry={"ram_utilization": 91.0, "cpu_utilization": 45.0},
        )
        # Execute CLEAR_MEMORY_CACHE
        action_def = DEFAULT_ACTION_CATALOG["CLEAR_MEMORY_CACHE"]
        cand = self.engine._score_candidate(self.node_id_1, incident.incident_type, incident.severity, action_def)

        exec_res = self.controller.execute_action(self.node_id_1, cand, incident.telemetry)
        self.assertTrue(exec_res.success)
        self.assertEqual(exec_res.status, "SUCCESS")
        self.assertGreater(exec_res.duration_sec, 0.0)
        self.assertTrue(exec_res.outcome_verified)
        self.assertIn("ram_utilization", exec_res.metrics_before)
        self.assertIn("ram_utilization", exec_res.metrics_after)
        # Verify RAM utilization stabilized
        ram_before = exec_res.metrics_before.get("ram_utilization")
        ram_after = exec_res.metrics_after.get("ram_utilization")
        self.assertLess(ram_after, ram_before)

    def test_03_outcome_adapts_stored_score_and_influences_subsequent_decision(self):
        """
        CRITICAL TEST: Proves that a measured outcome changes the stored score
        and alters subsequent recovery decisions for comparable incidents on that node.
        """
        inc_type = IncidentType.HIGH_CPU
        sev = SeverityLevel.MEDIUM
        incident = Incident(
            node_id=self.node_id_1,
            incident_type=inc_type,
            severity=sev,
            telemetry={"cpu_utilization": 89.0, "ram_utilization": 52.0},
        )

        # 1. Initial Evaluation: THROTTLE_PROCESS_WORKLOAD should be ranked #1
        initial_decision = self.engine.evaluate_actions(incident)
        initial_top_action = initial_decision.selected_action
        self.assertEqual(initial_top_action.action_id, "THROTTLE_PROCESS_WORKLOAD")
        initial_throttle_score = initial_top_action.score

        # Find the runner-up action
        runner_up = initial_decision.candidate_rankings[1]
        self.assertTrue(runner_up.is_authorized)
        self.assertLess(runner_up.score, initial_throttle_score)

        # 2. Simulate failed recovery outcomes for THROTTLE_PROCESS_WORKLOAD on this node
        # Record 4 consecutive failures
        for _ in range(4):
            self.engine.record_outcome(
                node_id=self.node_id_1,
                incident_type=inc_type,
                action_id="THROTTLE_PROCESS_WORKLOAD",
                success=False,
                recovery_time_sec=12.0,
                cost=0.70,
            )

        # Verify that stored history in database reflects the failures
        stored_hist = get_action_history(self.node_id_1, inc_type.value, "THROTTLE_PROCESS_WORKLOAD")
        self.assertIsNotNone(stored_hist)
        self.assertEqual(stored_hist["trials"], 4)
        self.assertEqual(stored_hist["successes"], 0)
        self.assertEqual(stored_hist["success_rate"], 0.0)

        # 3. Subsequent Evaluation: Evaluate identical incident on node 1 again
        subsequent_decision = self.engine.evaluate_actions(incident)
        subsequent_top_action = subsequent_decision.selected_action

        # The degraded action must NOT be #1 anymore!
        self.assertNotEqual(subsequent_top_action.action_id, "THROTTLE_PROCESS_WORKLOAD")

        # The subsequent score for THROTTLE_PROCESS_WORKLOAD must be significantly lower than initial
        subsequent_throttle_cand = next(
            c for c in subsequent_decision.candidate_rankings if c.action_id == "THROTTLE_PROCESS_WORKLOAD"
        )
        self.assertLess(subsequent_throttle_cand.score, initial_throttle_score)

        # The runner-up has now been promoted to #1 based on learned empirical evidence
        self.assertEqual(subsequent_top_action.action_id, runner_up.action_id)
        self.assertIn("Outranked", subsequent_decision.rationale)

    def test_04_node_specific_learning_isolation(self):
        """
        Tests that node-specific learning remains isolated by default:
        Failures on Node 1 do not penalize or degrade Node 2's independent policy.
        """
        inc_type = IncidentType.HIGH_CPU
        sev = SeverityLevel.MEDIUM

        # Node 1 already experienced failures in previous test (or record failures now)
        for _ in range(3):
            self.engine.record_outcome(
                node_id=self.node_id_1,
                incident_type=inc_type,
                action_id="THROTTLE_PROCESS_WORKLOAD",
                success=False,
                recovery_time_sec=10.0,
                cost=0.60,
            )

        # Node 2 has no recorded trials for THROTTLE_PROCESS_WORKLOAD
        node2_hist = get_action_history(self.node_id_2, inc_type.value, "THROTTLE_PROCESS_WORKLOAD")
        self.assertIsNone(node2_hist)

        # Evaluate Node 2: Node 2 still has THROTTLE_PROCESS_WORKLOAD as top candidate
        incident_node2 = Incident(
            node_id=self.node_id_2,
            incident_type=inc_type,
            severity=sev,
            telemetry={"cpu_utilization": 90.0, "ram_utilization": 50.0},
        )
        decision_node2 = self.engine.evaluate_actions(incident_node2)
        self.assertEqual(decision_node2.selected_action.action_id, "THROTTLE_PROCESS_WORKLOAD")
        self.assertGreater(decision_node2.selected_action.score, 0.30)

        # Compare Node 1 vs Node 2 score for THROTTLE_PROCESS_WORKLOAD:
        cand_node1 = next(c for c in self.engine.evaluate_actions(Incident(self.node_id_1, inc_type, sev, {})).candidate_rankings if c.action_id == "THROTTLE_PROCESS_WORKLOAD")
        cand_node2 = next(c for c in decision_node2.candidate_rankings if c.action_id == "THROTTLE_PROCESS_WORKLOAD")
        self.assertLess(cand_node1.score, cand_node2.score)

    def test_05_escalation_when_no_safe_action_available_or_execution_fails(self):
        """Test escalation to administrator alert when actions fail or are unavailable."""
        incident = Incident(
            node_id=self.node_id_1,
            incident_type=IncidentType.SECURITY_ANOMALY,
            severity=SeverityLevel.LOW,
            telemetry={"attack_cat": "Exploits"},
        )
        # If all candidates fail or require higher severity, engine escalates
        # Here CONTROLLED_SANDBOX_ISOLATION requires HIGH severity
        sandbox_def = DEFAULT_ACTION_CATALOG["CONTROLLED_SANDBOX_ISOLATION"]
        self.assertEqual(sandbox_def.min_authorized_severity, "HIGH")

        # Now test execution failure causing escalation
        # Create a mock controller that fails
        class FailingController(RecoveryController):
            def execute_action(self, *args, **kwargs):
                action_id = kwargs.get("action_id") or (args[0] if args else "TEST_ACTION")
                return ExecutionResult(
                    action_id=str(action_id),
                    status="FAILED",
                    success=False,
                    outcome_verified=False,
                    duration_sec=3.0,
                    details="Hardware bus timeout during remediation.",
                )

        failing_engine = AdaptiveRecoveryDecisionEngine(controller=FailingController())
        exec_incident = Incident(
            node_id=self.node_id_1,
            incident_type=IncidentType.HIGH_DISK,
            severity=SeverityLevel.MEDIUM,
            telemetry={"disk_utilization": 95.0},
        )
        decision = failing_engine.evaluate_and_execute(exec_incident)
        self.assertTrue(decision.is_escalated)
        self.assertEqual(decision.escalation_reason, "Action execution failed to resolve incident")
        self.assertIn("Hardware bus timeout", str(decision.execution_result.details))

    def test_06_database_audit_trail_and_retrieval(self):
        """Test that decisions, rationales, and candidate scores are logged in database."""
        incident = Incident(
            node_id=self.node_id_1,
            incident_type=IncidentType.HIGH_MEMORY,
            severity=SeverityLevel.MEDIUM,
            telemetry={"ram_utilization": 88.0},
        )
        decision = self.engine.evaluate_and_execute(incident)
        self.assertIsNotNone(decision.decision_id)

        # Retrieve logged decisions
        decisions = get_recovery_decisions(node_id=self.node_id_1, limit=10)
        self.assertTrue(len(decisions) > 0)
        latest = decisions[0]
        self.assertEqual(latest["decision_id"], decision.decision_id)
        self.assertEqual(latest["node_id"], self.node_id_1)
        self.assertEqual(latest["incident_type"], "HIGH_MEMORY")
        self.assertIn("candidate_scores", latest)
        cand_action_ids = [c["action_id"] for c in latest["candidate_scores"]]
        self.assertIn("CLEAR_MEMORY_CACHE", cand_action_ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
