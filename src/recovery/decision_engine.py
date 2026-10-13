"""
decision_engine.py - Adaptive Recovery Decision Engine.

Ranks, selects, executes, measures, and adapts safe recovery actions
for node incidents based on historical verified outcomes.
"""

from __future__ import annotations

import os
import sys
import uuid
import json
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

# Ensure project paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from recovery.models import (
    Incident,
    RecoveryActionDefinition,
    ActionCandidateScore,
    DecisionResult,
    ExecutionResult,
    ActionIdRef,
    VerificationStatus,
    RecoveryCriteria,
    VerificationResult,
)
from recovery.verifier import ClosedLoopVerifier
from recovery.recovery_controller import RecoveryController
from central_server.database import (
    get_action_history,
    record_action_outcome,
    save_recovery_decision,
    update_recovery_decision_outcome,
    get_comparable_fleet_action_history,
    save_maintenance_alert,
)


# ─────────────────────────────────────────────────────────────────────────────
# Default Action Catalog
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_ACTION_CATALOG: Dict[str, RecoveryActionDefinition] = {
    "CLEAR_MEMORY_CACHE": RecoveryActionDefinition(
        action_id="CLEAR_MEMORY_CACHE",
        name="Trim Memory Footprint & Clear Buffers",
        description="Flush standby memory buffers and trigger process working-set trimming.",
        applicable_incident_types=["HIGH_MEMORY", "COMPOUND_RESOURCE_PRESSURE", "PREDICTIVE_FAILURE", "MEMORY_STRESS"],
        base_effectiveness_prior=0.85,
        expected_duration_sec=1.5,
        resource_impact_cost=0.20,
        invasiveness_risk=0.15,
        min_authorized_severity="LOW",
    ),
    "THROTTLE_PROCESS_WORKLOAD": RecoveryActionDefinition(
        action_id="THROTTLE_PROCESS_WORKLOAD",
        name="Throttle Process Workload",
        description="Throttle background worker thread priority and task processing rate.",
        applicable_incident_types=["HIGH_CPU", "COMPOUND_RESOURCE_PRESSURE", "PREDICTIVE_FAILURE", "CPU_STRESS"],
        base_effectiveness_prior=0.82,
        expected_duration_sec=2.5,
        resource_impact_cost=0.35,
        invasiveness_risk=0.20,
        min_authorized_severity="MEDIUM",
    ),
    "CLEAN_TEMP_STORAGE": RecoveryActionDefinition(
        action_id="CLEAN_TEMP_STORAGE",
        name="Clean Temporary Files & Rotate Logs",
        description="Prune application scratch cache files and rotate debug logs.",
        applicable_incident_types=["HIGH_DISK", "PREDICTIVE_FAILURE", "DISK_STRESS"],
        base_effectiveness_prior=0.80,
        expected_duration_sec=3.0,
        resource_impact_cost=0.15,
        invasiveness_risk=0.10,
        min_authorized_severity="LOW",
    ),
    "SCHEDULE_NODE_DIAGNOSTIC": RecoveryActionDefinition(
        action_id="SCHEDULE_NODE_DIAGNOSTIC",
        name="Low-Impact Diagnostic Sweep",
        description="Run non-intrusive component integrity verification and sensor probe.",
        applicable_incident_types=["HIGH_CPU", "HIGH_MEMORY", "HIGH_DISK", "PREDICTIVE_FAILURE", "SECURITY_ANOMALY"],
        base_effectiveness_prior=0.60,
        expected_duration_sec=4.0,
        resource_impact_cost=0.10,
        invasiveness_risk=0.05,
        min_authorized_severity="LOW",
    ),
    "CONTROLLED_SANDBOX_ISOLATION": RecoveryActionDefinition(
        action_id="CONTROLLED_SANDBOX_ISOLATION",
        name="Controlled Network Sandbox Isolation",
        description="Quarantine suspicious network connections and isolate node in test environment.",
        applicable_incident_types=["SECURITY_ANOMALY", "PREDICTIVE_FAILURE"],
        base_effectiveness_prior=0.75,
        expected_duration_sec=3.5,
        resource_impact_cost=0.60,
        invasiveness_risk=0.50,
        min_authorized_severity="HIGH",
        requires_confirmation=True,
    ),
    "DRAIN_AND_FAILOVER": RecoveryActionDefinition(
        action_id="DRAIN_AND_FAILOVER",
        name="Drain Workload & Standby Failover",
        description="Gracefully drain active tasks and failover node duties to standby replica.",
        applicable_incident_types=["PREDICTIVE_FAILURE", "COMPOUND_RESOURCE_PRESSURE", "HIGH_CPU", "HIGH_MEMORY"],
        base_effectiveness_prior=0.90,
        expected_duration_sec=8.0,
        resource_impact_cost=0.85,
        invasiveness_risk=0.70,
        min_authorized_severity="HIGH",
        requires_confirmation=True,
    ),
    "ROUTINE_OBSERVATION": RecoveryActionDefinition(
        action_id="ROUTINE_OBSERVATION",
        name="Routine Observation",
        description="Retain standard telemetry surveillance without active intervention.",
        applicable_incident_types=["HIGH_CPU", "HIGH_MEMORY", "HIGH_DISK", "PREDICTIVE_FAILURE", "SECURITY_ANOMALY", "COMPOUND_RESOURCE_PRESSURE", "GENERIC_WARNING"],
        base_effectiveness_prior=0.45,
        expected_duration_sec=1.0,
        resource_impact_cost=0.05,
        invasiveness_risk=0.00,
        min_authorized_severity="LOW",
    ),
    "ESCALATE_TO_ADMIN": RecoveryActionDefinition(
        action_id="ESCALATE_TO_ADMIN",
        name="Escalate to System Administrator",
        description="Generate high-priority operational alert requiring manual human intervention.",
        applicable_incident_types=["HIGH_CPU", "HIGH_MEMORY", "HIGH_DISK", "PREDICTIVE_FAILURE", "SECURITY_ANOMALY", "COMPOUND_RESOURCE_PRESSURE", "GENERIC_WARNING"],
        base_effectiveness_prior=0.95,
        expected_duration_sec=0.5,
        resource_impact_cost=0.90,
        invasiveness_risk=0.10,
        min_authorized_severity="HIGH",
    ),
}

SEVERITY_ORDER = {
    "LOW": 0,
    "MEDIUM": 1,
    "HIGH": 2,
    "CRITICAL": 3,
}


class AdaptiveRecoveryDecisionEngine:
    """
    Adaptive Recovery Decision Engine.
    Uses an explainable Bayesian scoring algorithm that learns node-specific action effectiveness.
    """

    def __init__(
        self,
        controller: Optional[RecoveryController] = None,
        catalog: Optional[Dict[str, RecoveryActionDefinition]] = None,
        verifier: Optional[ClosedLoopVerifier] = None,
        weights: Optional[Dict[str, float]] = None,
        share_fleet_evidence: bool = False,
        default_verification_timeout_sec: float = 8.0,
    ):
        self.controller = controller or RecoveryController()
        self.catalog = catalog or DEFAULT_ACTION_CATALOG
        self.verifier = verifier or ClosedLoopVerifier()
        self.share_fleet_evidence = share_fleet_evidence
        self.default_verification_timeout_sec = default_verification_timeout_sec
        # Scoring weights: w_success + w_time + w_cost + w_risk
        self.weights = weights or {
            "w_success": 0.55,
            "w_time": 0.15,
            "w_cost": 0.15,
            "w_risk": 0.15,
        }

    def evaluate_and_recover(
        self,
        incident: Incident,
        auto_execute: bool = True,
        context: Optional[Dict[str, Any]] = None,
        verification_timeout_sec: Optional[float] = None,
        telemetry_provider: Optional[Any] = None,
    ) -> DecisionResult:
        """
        Main entrypoint:
          1. Evaluates and scores applicable actions.
          2. Selects the safest, highest-ranking authorized action.
          3. Defines measurable recovery criteria before action execution.
          4. Persists the decision with baseline metrics and criteria.
          5. Executes through the RecoveryController.
          6. Collects fresh telemetry and verifies criteria within the time window.
          7. Updates the adaptive decision engine ONLY from verified outcomes (SUCCESS or FAILURE).
          8. Marks inconclusive results separately from success or failure.
          9. Escalates if verification fails or is inconclusive.
        """
        ctx = context or {}
        v_timeout = (
            verification_timeout_sec
            if verification_timeout_sec is not None
            else ctx.get("verification_timeout_sec", self.default_verification_timeout_sec)
        )
        v_provider = telemetry_provider if telemetry_provider is not None else ctx.get("telemetry_provider")
        if v_provider is None and "fresh_telemetry" in ctx:
            v_provider = ctx["fresh_telemetry"]

        # 1. Filter applicable candidate actions
        applicable_actions = self._get_applicable_actions(incident.incident_type)
        if not applicable_actions:
            # Fallback to routine observation or escalate
            applicable_actions = [self.catalog["ROUTINE_OBSERVATION"], self.catalog["ESCALATE_TO_ADMIN"]]

        # 2. Score and rank candidate actions
        candidate_scores: List[ActionCandidateScore] = []
        for action in applicable_actions:
            score_data = self._score_action(action, incident)
            candidate_scores.append(score_data)

        # Sort descending by score
        candidate_scores.sort(key=lambda s: s.score, reverse=True)

        # 3. Select the highest-ranking AUTHORIZED and SAFE action
        selected_candidate = None
        for cand in candidate_scores:
            if cand.is_authorized:
                selected_candidate = cand
                break

        # If no action is authorized, force escalation
        if not selected_candidate or (selected_candidate.action_id == "ROUTINE_OBSERVATION" and incident.severity in ("HIGH", "CRITICAL")):
            escalate_action = self.catalog["ESCALATE_TO_ADMIN"]
            selected_candidate = ActionCandidateScore(
                action_id=escalate_action.action_id,
                name=escalate_action.name,
                score=0.99,
                historical_success_rate=1.0,
                trials=0,
                successes=0,
                resource_cost=escalate_action.resource_impact_cost,
                recovery_time_sec=escalate_action.expected_duration_sec,
                risk_penalty=0.0,
                is_authorized=True,
                rationale="Forced administrative escalation: No safe automated recovery action available for this high-severity incident.",
            )

        # 4. Formulate explainable ranking rationale
        ranking_rationale = self._formulate_rationale(selected_candidate, candidate_scores, incident)

        # 5. Define measurable recovery criteria before action execution
        criteria = self.verifier.define_criteria(
            incident=incident,
            action_id=selected_candidate.action_id,
            timeout_sec=v_timeout,
            custom_thresholds=ctx.get("thresholds"),
        )

        # Check authorization requirements for potentially disruptive actions
        act_def = self.catalog.get(selected_candidate.action_id)
        is_disruptive = bool(
            selected_candidate.action_id in ("DRAIN_AND_FAILOVER", "CONTROLLED_SANDBOX_ISOLATION")
            or (act_def and act_def.requires_confirmation)
            or (act_def and act_def.invasiveness_risk >= 0.40)
        )
        is_approved = bool(ctx.get("approved") or ctx.get("operator_authorized"))
        requires_authorization = is_disruptive and not is_approved

        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
        decision = DecisionResult(
            decision_id=decision_id,
            incident_id=incident.incident_id,
            node_id=incident.node_id,
            incident_type=incident.incident_type,
            severity=incident.severity,
            selected_action=ActionIdRef(selected_candidate.action_id, selected_candidate.name, selected_candidate.score),
            action_name=selected_candidate.name,
            ranking_score=round(selected_candidate.score, 4),
            ranking_rationale=ranking_rationale,
            candidate_rankings=candidate_scores,
            execution_status="PENDING",
            timestamp=datetime.now(timezone.utc).isoformat(),
            escalated=(selected_candidate.action_id == "ESCALATE_TO_ADMIN"),
            escalation_reason="No safe automated recovery action available" if selected_candidate.action_id == "ESCALATE_TO_ADMIN" else None,
            recovery_criteria=criteria,
            verification_status="PENDING",
            lifecycle_status="PROPOSED",
            is_disruptive=is_disruptive,
            requires_authorization=requires_authorization,
            is_approved=is_approved,
            metrics_before=dict(incident.telemetry or {}),
        )

        # Persist decision record with baseline metrics and criteria
        save_recovery_decision({
            "decision_id": decision.decision_id,
            "incident_id": decision.incident_id,
            "node_id": decision.node_id,
            "incident_type": decision.incident_type,
            "severity": decision.severity,
            "selected_action": str(decision.selected_action),
            "ranking_score": decision.ranking_score,
            "ranking_rationale": decision.ranking_rationale,
            "candidate_rankings": [c.to_dict() if hasattr(c, "to_dict") else c for c in candidate_scores],
            "metrics_before": incident.telemetry,
            "execution_status": "PENDING",
            "verification_status": "PENDING",
            "recovery_criteria": criteria.to_dict() if hasattr(criteria, "to_dict") else criteria,
            "verification_details": {},
            "escalated": decision.escalated,
            "timestamp": decision.timestamp,
        })

        if not auto_execute:
            decision.execution_status = "PENDING"
            decision.lifecycle_status = "PROPOSED"
            return decision

        if requires_authorization:
            # Potentially disruptive action requires explicit operator approval before execution!
            decision.execution_status = "PENDING"
            decision.lifecycle_status = "PROPOSED"
            decision.ranking_rationale += f" [AUTHORIZATION REQUIRED: '{selected_candidate.action_id}' is a potentially disruptive action requiring explicit operator authorization before execution.]"
            update_recovery_decision_outcome(
                decision_id=decision.decision_id,
                success=None,
                metrics_after=decision.metrics_before,
                recovery_duration_sec=0.0,
                escalated=decision.escalated,
                verification_status="PENDING",
                verification_details={"requires_authorization": True, "action": selected_candidate.action_id},
            )
            return decision

        decision.lifecycle_status = "APPROVED" if is_approved else "EXECUTING"
        decision.execution_status = "EXECUTING"

        # 6. Execute action through RecoveryController
        exec_res = self.controller.execute_action(
            action_id=selected_candidate.action_id,
            node_id=incident.node_id,
            incident_type=incident.incident_type,
            severity=incident.severity,
            metrics_before=incident.telemetry,
            context=ctx,
        )
        decision.execution_result = exec_res
        decision.execution_status = "COMPLETED"

        # 7. Collect fresh telemetry and verify criteria within the configurable time window
        if not exec_res.success:
            verif_res = VerificationResult(
                status=VerificationStatus.FAILURE,
                verification_duration_sec=exec_res.duration_sec,
                observed_metrics=incident.telemetry or {},
                criteria_evaluations=[],
                details=f"Action execution error: {exec_res.details}",
                is_verified=True,
                timeout_exceeded=False,
                telemetry_unavailable=False,
            )
        else:
            verif_res = self.verifier.verify(
                node_id=incident.node_id,
                criteria=criteria,
                telemetry_provider=v_provider,
                timeout_sec=v_timeout,
            )

        decision.verification_result = verif_res
        decision.verification_status = verif_res.status.value if hasattr(verif_res.status, "value") else str(verif_res.status)

        metrics_after = verif_res.observed_metrics or exec_res.metrics_after
        decision.metrics_after = metrics_after
        duration = verif_res.verification_duration_sec

        # 8. Adaptive Learning & Escalation
        # Rule: Update the adaptive decision engine ONLY from verified outcomes (SUCCESS or FAILURE).
        # Inconclusive results (e.g. unavailable telemetry) MUST NOT update action history scores.
        if verif_res.status == VerificationStatus.SUCCESS:
            decision.lifecycle_status = "SUCCESSFUL"
            if selected_candidate.action_id not in ("ESCALATE_TO_ADMIN", "ROUTINE_OBSERVATION"):
                record_action_outcome(
                    node_id=incident.node_id,
                    incident_type=incident.incident_type,
                    action_id=selected_candidate.action_id,
                    success=True,
                    duration_sec=duration,
                )
            decision.escalated = False
            decision.escalation_reason = None
            update_recovery_decision_outcome(
                decision_id=decision.decision_id,
                success=True,
                metrics_after=metrics_after,
                recovery_duration_sec=duration,
                escalated=False,
                verification_status="SUCCESS",
                verification_details=verif_res.to_dict(),
            )

        elif verif_res.status == VerificationStatus.FAILURE:
            decision.lifecycle_status = "FAILED"
            if selected_candidate.action_id not in ("ESCALATE_TO_ADMIN", "ROUTINE_OBSERVATION"):
                record_action_outcome(
                    node_id=incident.node_id,
                    incident_type=incident.incident_type,
                    action_id=selected_candidate.action_id,
                    success=False,
                    duration_sec=duration,
                )
            decision.escalated = True
            if not exec_res.success:
                decision.escalation_reason = "Action execution failed to resolve incident"
            else:
                decision.escalation_reason = f"Closed-loop verification failed: {verif_res.details}"
            self._trigger_escalation_alert(incident, selected_candidate, exec_res, verif_res)
            update_recovery_decision_outcome(
                decision_id=decision.decision_id,
                success=False,
                metrics_after=metrics_after,
                recovery_duration_sec=duration,
                escalated=True,
                verification_status="FAILURE",
                verification_details=verif_res.to_dict(),
            )

        elif verif_res.status == VerificationStatus.INCONCLUSIVE:
            decision.lifecycle_status = "INCONCLUSIVE"
            # Mark inconclusive results separately from success or failure.
            # DO NOT call record_action_outcome - adaptive decision engine remains untouched!
            decision.escalated = True
            decision.escalation_reason = f"Closed-loop verification inconclusive: {verif_res.details}"
            self._trigger_escalation_alert(incident, selected_candidate, exec_res, verif_res)
            update_recovery_decision_outcome(
                decision_id=decision.decision_id,
                success=None,
                metrics_after=metrics_after,
                recovery_duration_sec=duration,
                escalated=True,
                verification_status="INCONCLUSIVE",
                verification_details=verif_res.to_dict(),
            )

        return decision

    def evaluate_and_execute(
        self,
        incident: Incident,
        context: Optional[Dict[str, Any]] = None,
        verification_timeout_sec: Optional[float] = None,
        telemetry_provider: Optional[Any] = None,
    ) -> DecisionResult:
        """Alias for evaluate_and_recover with auto_execute=True."""
        return self.evaluate_and_recover(
            incident,
            auto_execute=True,
            context=context,
            verification_timeout_sec=verification_timeout_sec,
            telemetry_provider=telemetry_provider,
        )

    def evaluate_actions(
        self,
        incident: Incident,
        context: Optional[Dict[str, Any]] = None,
        verification_timeout_sec: Optional[float] = None,
    ) -> DecisionResult:
        """Alias for evaluate_and_recover with auto_execute=False (ranking only)."""
        return self.evaluate_and_recover(
            incident,
            auto_execute=False,
            context=context,
            verification_timeout_sec=verification_timeout_sec,
        )

    def record_outcome(
        self,
        node_id: str,
        incident_type: Any,
        action_id: str,
        success: bool,
        recovery_time_sec: float = 1.0,
        cost: float = 0.2,
    ) -> None:
        """Manually records an outcome into the persistent history table."""
        inc_str = incident_type.value if hasattr(incident_type, "value") else str(incident_type)
        record_action_outcome(
            node_id=node_id,
            incident_type=inc_str,
            action_id=action_id,
            success=success,
            duration_sec=recovery_time_sec,
            cost_score=cost,
        )

    def _score_candidate(
        self,
        node_id: str,
        incident_type: Any,
        severity: Any,
        action: RecoveryActionDefinition,
    ) -> ActionCandidateScore:
        """Convenience method to score an individual action candidate definition."""
        inc = Incident(node_id=node_id, incident_type=incident_type, severity=severity)
        return self._score_action(action, inc)

    # ─────────────────────────────────────────────────────────────────────────
    # Scoring & Ranking Logic
    # ─────────────────────────────────────────────────────────────────────────

    def _get_applicable_actions(self, incident_type: str) -> List[RecoveryActionDefinition]:
        applicable = []
        for act in self.catalog.values():
            if incident_type in act.applicable_incident_types or "ALL" in act.applicable_incident_types:
                applicable.append(act)
        return applicable

    def _score_action(
        self, action: RecoveryActionDefinition, incident: Incident
    ) -> ActionCandidateScore:
        """
        Calculates explainable multi-factor score:
          Score = w_success * SuccessRate - w_time * TimeNorm - w_cost * Cost - w_risk * Risk
        """
        node_id = incident.node_id
        inc_type = incident.incident_type
        sev = incident.severity

        # Check authorization
        req_sev_level = SEVERITY_ORDER.get(action.min_authorized_severity, 0)
        curr_sev_level = SEVERITY_ORDER.get(sev, 0)
        is_authorized = (curr_sev_level >= req_sev_level)

        # 1. Historical Success Rate with Bayesian Prior (Laplace smoothing)
        hist = get_action_history(node_id, inc_type, action.action_id)
        if hist and hist["trials"] > 0:
            trials = hist["trials"]
            successes = hist["successes"]
            # Node-specific empirical success rate: (successes + 1) / (trials + 2)
            success_rate = (successes + 1.0) / (trials + 2.0)
            avg_time = (hist["total_recovery_time_sec"] / trials) if trials > 0 else action.expected_duration_sec
            source_desc = f"node history ({successes}/{trials} successes)"
        elif self.share_fleet_evidence:
            # Cold start: Check comparable fleet history only when explicitly justified & enabled
            fleet_hist = get_comparable_fleet_action_history(inc_type, action.action_id)
            if fleet_hist and fleet_hist["trials"] > 0:
                f_trials = fleet_hist["trials"]
                f_success = fleet_hist["successes"]
                fleet_rate = (f_success + 1.0) / (f_trials + 2.0)
                # Blended prior with fleet experience
                success_rate = 0.65 * action.base_effectiveness_prior + 0.35 * fleet_rate
                trials, successes = 0, 0
                avg_time = fleet_hist.get("avg_recovery_time_sec") or action.expected_duration_sec
                source_desc = f"comparable fleet prior ({f_success}/{f_trials} across nodes)"
            else:
                success_rate = action.base_effectiveness_prior
                trials, successes = 0, 0
                avg_time = action.expected_duration_sec
                source_desc = "catalog baseline prior"
        else:
            # Node-specific learning kept separate by default: cold-start uses catalog baseline prior
            success_rate = action.base_effectiveness_prior
            trials, successes = 0, 0
            avg_time = action.expected_duration_sec
            source_desc = "catalog baseline prior"

        # 2. Time efficiency penalty
        time_norm = min(1.0, avg_time / 20.0)

        # 3. Resource overhead cost
        cost = action.resource_impact_cost

        # 4. Invasiveness risk penalty (discounted at higher severity)
        sev_discount = {
            "LOW": 1.0,
            "MEDIUM": 0.8,
            "HIGH": 0.5,
            "CRITICAL": 0.2,
        }.get(sev, 0.8)
        risk_penalty = action.invasiveness_risk * sev_discount

        # Compute composite score
        score = (
            self.weights["w_success"] * success_rate
            - self.weights["w_time"] * time_norm
            - self.weights["w_cost"] * cost
            - self.weights["w_risk"] * risk_penalty
        )
        score = max(0.01, round(score, 4))

        if not is_authorized:
            rationale = f"Unauthorized: requires minimum severity {action.min_authorized_severity} (current is {sev})."
        else:
            rationale = f"Score: {score:.3f} based on {source_desc} (P_succ={success_rate:.2f}, Time={avg_time:.1f}s, Cost={cost:.2f})."

        return ActionCandidateScore(
            action_id=action.action_id,
            name=action.name,
            score=score if is_authorized else -1.0,
            historical_success_rate=round(success_rate, 4),
            trials=trials,
            successes=successes,
            resource_cost=cost,
            recovery_time_sec=round(avg_time, 2),
            risk_penalty=round(risk_penalty, 3),
            is_authorized=is_authorized,
            rationale=rationale,
        )

    def _formulate_rationale(
        self,
        chosen: ActionCandidateScore,
        all_candidates: List[ActionCandidateScore],
        incident: Incident,
    ) -> str:
        """Formulates clear, plain-English explanation for the selected action."""
        others = [c for c in all_candidates if c.action_id != chosen.action_id and c.is_authorized]
        if others:
            runner_up = others[0]
            return (
                f"Selected '{chosen.name}' (Ranking Score: {chosen.score:.3f}) for {incident.incident_type} ({incident.severity}). "
                f"{chosen.rationale} Outranked '{runner_up.name}' (Score: {runner_up.score:.3f}) due to higher verified outcome probability and optimal resource footprint."
            )
        return (
            f"Selected '{chosen.name}' (Ranking Score: {chosen.score:.3f}) for {incident.incident_type} ({incident.severity}). "
            f"{chosen.rationale}"
        )

    def _trigger_escalation_alert(
        self,
        incident: Incident,
        action: ActionCandidateScore,
        exec_res: ExecutionResult,
        verif_res: Optional[VerificationResult] = None,
    ) -> None:
        """Saves an urgent alert in maintenance alerts table upon failure or inconclusive outcome."""
        alert_id = f"esc_{uuid.uuid4().hex[:10]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        
        if verif_res:
            st = verif_res.status.value if hasattr(verif_res.status, "value") else str(verif_res.status)
            reason = f"Recovery '{action.name}' verification [{st}]: {verif_res.details}"
        else:
            reason = f"Automated recovery '{action.name}' failed to stabilize node. Details: {exec_res.details}"
            
        rec_action = "Manual administrator intervention required: Inspect host health, logs, and telemetry agent."

        try:
            save_maintenance_alert({
                "alert_id": alert_id,
                "node_id": incident.node_id,
                "timestamp": now_iso,
                "last_seen_at": now_iso,
                "failure_probability": 0.95,
                "risk_level": "CRITICAL",
                "telemetry_summary": incident.telemetry if isinstance(incident.telemetry, dict) else {},
                "reason": reason,
                "recommended_action": rec_action,
                "status": "ACTIVE",
                "repeat_count": 1,
            })
        except Exception:
            pass


_decision_engine_instance: Optional[AdaptiveRecoveryDecisionEngine] = None


def get_decision_engine() -> AdaptiveRecoveryDecisionEngine:
    """Returns the shared singleton instance of AdaptiveRecoveryDecisionEngine."""
    global _decision_engine_instance
    if _decision_engine_instance is None:
        _decision_engine_instance = AdaptiveRecoveryDecisionEngine()
    return _decision_engine_instance

