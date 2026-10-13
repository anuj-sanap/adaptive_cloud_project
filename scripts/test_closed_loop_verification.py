"""
test_closed_loop_verification.py - Closed-Loop Recovery Verification Test Suite.

Tests:
  1. Successful recovery verification (criteria met within window -> SUCCESS -> engine updated).
  2. Failed recovery verification (criteria unmet within window -> FAILURE -> escalation -> score degraded).
  3. Timeout recovery verification (timeout exceeded -> FAILURE -> duration recorded).
  4. Unavailable telemetry marked INCONCLUSIVE separately from SUCCESS and FAILURE.
  5. Inconclusive outcomes DO NOT update adaptive decision engine history scores.
  6. Database audit log records criteria, verification status, and verification details.
"""

import os
import sys
import uuid
import unittest
import time
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
    get_action_history,
    get_recovery_decisions,
    get_active_maintenance_alerts,
)
from recovery.models import (
    Incident,
    IncidentType,
    SeverityLevel,
    VerificationStatus,
    RecoveryCriteria,
    VerificationResult,
    DecisionResult,
)
from recovery.verifier import ClosedLoopVerifier
from recovery.decision_engine import (
    AdaptiveRecoveryDecisionEngine,
    DEFAULT_ACTION_CATALOG,
)


class TestClosedLoopVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.verifier = ClosedLoopVerifier(default_timeout_sec=0.3, poll_interval_sec=0.05)
        cls.engine = AdaptiveRecoveryDecisionEngine(
            verifier=cls.verifier,
            default_verification_timeout_sec=0.3,
        )

    def setUp(self):
        self.node_id = f"test-verify-node-{uuid.uuid4().hex[:8]}"
        register_node(self.node_id, "verify-host", "127.0.0.1", "Windows", {})

    def test_01_successful_recovery_verification(self):
        """
        Criteria defined before action, fresh telemetry meets targets within window:
        Status is SUCCESS, actual duration is recorded, and adaptive scoring history is updated.
        """
        # Baseline incident: High CPU at 89%
        incident = Incident(
            node_id=self.node_id,
            incident_type=IncidentType.HIGH_CPU,
            severity=SeverityLevel.MEDIUM,
            telemetry={"cpu_utilization": 89.0, "ram_utilization": 55.0},
        )

        # Fresh telemetry simulating successful workload throttle: CPU drops to 64.0% (<= 75% target)
        fresh_telemetry = {"cpu_utilization": 64.0, "ram_utilization": 54.0}

        # Evaluate and recover with fresh telemetry provider
        decision = self.engine.evaluate_and_recover(
            incident=incident,
            auto_execute=True,
            verification_timeout_sec=0.5,
            telemetry_provider=fresh_telemetry,
        )

        # 1. Verify criteria were defined before action
        self.assertIsNotNone(decision.recovery_criteria)
        self.assertEqual(decision.recovery_criteria.incident_type, "HIGH_CPU")
        self.assertTrue(len(decision.recovery_criteria.criteria) > 0)
        cpu_crit = decision.recovery_criteria.criteria[0]
        self.assertEqual(cpu_crit.metric_name, "cpu_utilization")
        self.assertEqual(cpu_crit.baseline_value, 89.0)
        self.assertEqual(cpu_crit.target_threshold, 75.0)

        # 2. Verify post-action verification result
        self.assertIsNotNone(decision.verification_result)
        self.assertEqual(decision.verification_status, "SUCCESS")
        self.assertEqual(decision.verification_result.status, VerificationStatus.SUCCESS)
        self.assertTrue(decision.verification_result.is_verified)
        self.assertFalse(decision.verification_result.timeout_exceeded)
        self.assertFalse(decision.verification_result.telemetry_unavailable)
        self.assertGreater(decision.verification_result.verification_duration_sec, 0.0)

        # 3. Check criteria evaluations list
        evals = decision.verification_result.criteria_evaluations
        self.assertTrue(len(evals) > 0)
        self.assertTrue(evals[0]["met"])
        self.assertEqual(evals[0]["observed"], 64.0)

        # 4. Verify adaptive decision engine was updated in persistent history
        hist = get_action_history(self.node_id, "HIGH_CPU", decision.selected_action.action_id)
        self.assertIsNotNone(hist)
        self.assertEqual(hist["trials"], 1)
        self.assertEqual(hist["successes"], 1)
        self.assertEqual(hist["last_outcome"], "SUCCESS")

    def test_02_failed_recovery_verification_and_escalation(self):
        """
        Fresh telemetry fails recovery criteria:
        Status is FAILURE, duration is recorded, engine learns failure, and alert is escalated.
        """
        # Baseline incident: High Memory at 94%
        incident = Incident(
            node_id=self.node_id,
            incident_type=IncidentType.HIGH_MEMORY,
            severity=SeverityLevel.MEDIUM,
            telemetry={"ram_utilization": 94.0, "cpu_utilization": 50.0},
        )

        # Fresh telemetry simulating stubborn memory leak: RAM remains at 91.5% (> 78.0% target)
        unmet_telemetry = {"ram_utilization": 91.5, "cpu_utilization": 50.0}

        decision = self.engine.evaluate_and_recover(
            incident=incident,
            auto_execute=True,
            verification_timeout_sec=0.15,
            telemetry_provider=unmet_telemetry,
        )

        # 1. Verification status must be FAILURE
        self.assertEqual(decision.verification_status, "FAILURE")
        self.assertEqual(decision.verification_result.status, VerificationStatus.FAILURE)
        self.assertTrue(decision.verification_result.is_verified)
        self.assertTrue(decision.verification_result.timeout_exceeded)
        self.assertFalse(decision.verification_result.telemetry_unavailable)

        # 2. Escalation must be triggered
        self.assertTrue(decision.escalated)
        self.assertIn("Closed-loop verification failed", decision.escalation_reason)

        # 3. Adaptive scoring history must record the failure trial
        hist = get_action_history(self.node_id, "HIGH_MEMORY", decision.selected_action.action_id)
        self.assertIsNotNone(hist)
        self.assertEqual(hist["trials"], 1)
        self.assertEqual(hist["successes"], 0)
        self.assertEqual(hist["last_outcome"], "FAILURE")

        # 4. Maintenance alert was created
        alerts = get_active_maintenance_alerts()
        node_alerts = [a for a in alerts if a["node_id"] == self.node_id]
        self.assertTrue(len(node_alerts) > 0)
        self.assertEqual(node_alerts[0]["risk_level"], "CRITICAL")

    def test_03_timeout_recovery_verification(self):
        """
        Verification time window expires before telemetry improves:
        Recorded recovery duration matches time window elapsed and marked FAILURE.
        """
        incident = Incident(
            node_id=self.node_id,
            incident_type=IncidentType.HIGH_DISK,
            severity=SeverityLevel.LOW,
            telemetry={"disk_utilization": 92.0},
        )

        t_start = time.perf_counter()
        # Telemetry remains pegged at 91.0% (target is <= 85.0%)
        decision = self.engine.evaluate_and_recover(
            incident=incident,
            auto_execute=True,
            verification_timeout_sec=0.20,
            telemetry_provider={"disk_utilization": 91.0},
        )
        elapsed = time.perf_counter() - t_start

        self.assertEqual(decision.verification_status, "FAILURE")
        self.assertTrue(decision.verification_result.timeout_exceeded)
        self.assertGreaterEqual(elapsed, 0.18)
        self.assertGreaterEqual(decision.verification_result.verification_duration_sec, 0.15)

    def test_04_unavailable_telemetry_marked_inconclusive(self):
        """
        Telemetry is completely unavailable (collector returns None/empty):
        Outcome is marked INCONCLUSIVE separately from SUCCESS or FAILURE.
        """
        incident = Incident(
            node_id=self.node_id,
            incident_type=IncidentType.HIGH_CPU,
            severity=SeverityLevel.MEDIUM,
            telemetry={"cpu_utilization": 85.0},
        )

        # Simulate unresponsive node agent: collector returns None
        decision = self.engine.evaluate_and_recover(
            incident=incident,
            auto_execute=True,
            verification_timeout_sec=0.15,
            telemetry_provider=lambda: None,
        )

        # 1. Must be marked INCONCLUSIVE, not SUCCESS and not FAILURE
        self.assertEqual(decision.verification_status, "INCONCLUSIVE")
        self.assertEqual(decision.verification_result.status, VerificationStatus.INCONCLUSIVE)
        self.assertFalse(decision.verification_result.is_verified)
        self.assertTrue(decision.verification_result.telemetry_unavailable)
        self.assertTrue(decision.verification_result.timeout_exceeded)
        self.assertIn("inconclusive", decision.verification_result.details.lower())

    def test_05_adaptive_engine_not_updated_on_inconclusive(self):
        """
        CRITICAL TEST: Inconclusive outcomes MUST NOT update adaptive scoring weights.
        Trials and successes in recovery_action_history remain completely untouched.
        """
        target_action = "THROTTLE_PROCESS_WORKLOAD"
        inc_type = "HIGH_CPU"

        # Check history before trial
        before_hist = get_action_history(self.node_id, inc_type, target_action)
        before_trials = before_hist["trials"] if before_hist else 0
        before_successes = before_hist["successes"] if before_hist else 0

        incident = Incident(
            node_id=self.node_id,
            incident_type=IncidentType.HIGH_CPU,
            severity=SeverityLevel.MEDIUM,
            telemetry={"cpu_utilization": 87.0},
        )

        # Execute with unavailable telemetry
        decision = self.engine.evaluate_and_recover(
            incident=incident,
            auto_execute=True,
            verification_timeout_sec=0.10,
            telemetry_provider=lambda: None,
        )

        self.assertEqual(decision.verification_status, "INCONCLUSIVE")

        # Check history after trial: MUST BE UNCHANGED
        after_hist = get_action_history(self.node_id, inc_type, target_action)
        after_trials = after_hist["trials"] if after_hist else 0
        after_successes = after_hist["successes"] if after_hist else 0

        self.assertEqual(
            after_trials,
            before_trials,
            "Adaptive engine trials were incorrectly incremented on an inconclusive outcome!",
        )
        self.assertEqual(
            after_successes,
            before_successes,
            "Adaptive engine successes were incorrectly modified on an inconclusive outcome!",
        )

    def test_06_database_audit_log_stores_criteria_and_verification_details(self):
        """
        Verifies SQLite recovery_decisions table stores criteria JSON,
        verification status, and verification details JSON.
        """
        incident = Incident(
            node_id=self.node_id,
            incident_type=IncidentType.HIGH_MEMORY,
            severity=SeverityLevel.LOW,
            telemetry={"ram_utilization": 85.0},
        )

        decision = self.engine.evaluate_and_recover(
            incident=incident,
            auto_execute=True,
            verification_timeout_sec=0.2,
            telemetry_provider={"ram_utilization": 72.0},
        )

        decisions = get_recovery_decisions(node_id=self.node_id, limit=5)
        self.assertTrue(len(decisions) > 0)
        target_dec = next((d for d in decisions if d["decision_id"] == decision.decision_id), None)
        self.assertIsNotNone(target_dec)

        # Check parsed fields
        self.assertEqual(target_dec["verification_status"], "SUCCESS")
        self.assertTrue(isinstance(target_dec["recovery_criteria"], dict))
        self.assertEqual(target_dec["recovery_criteria"].get("incident_type"), "HIGH_MEMORY")
        self.assertTrue(isinstance(target_dec["verification_details"], dict))
        self.assertEqual(target_dec["verification_details"].get("status"), "SUCCESS")
        self.assertGreater(target_dec["execution_duration_sec"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
