"""
models.py - Data schemas and structures for the Adaptive Recovery Decision Engine.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone


class SeverityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentType(str, Enum):
    HIGH_CPU = "HIGH_CPU"
    HIGH_MEMORY = "HIGH_MEMORY"
    HIGH_DISK = "HIGH_DISK"
    PREDICTIVE_FAILURE = "PREDICTIVE_FAILURE"
    SECURITY_ANOMALY = "SECURITY_ANOMALY"
    COMPOUND_RESOURCE_PRESSURE = "COMPOUND_RESOURCE_PRESSURE"
    GENERIC_WARNING = "GENERIC_WARNING"


class VerificationStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    INCONCLUSIVE = "INCONCLUSIVE"


class ActionIdRef(str):
    """String subclass that allows .action_id, .name, and .score attribute access."""
    def __new__(cls, val, name=None, score=0.0):
        obj = str.__new__(cls, val)
        obj._name = name or val
        obj._score = score
        return obj

    @property
    def action_id(self) -> str:
        return str(self)

    @property
    def name(self) -> str:
        return self._name

    @property
    def score(self) -> float:
        return self._score


@dataclass
class Incident:
    node_id: str
    incident_type: str
    severity: str
    telemetry: Dict[str, Any] = field(default_factory=dict)
    incident_id: Optional[str] = None
    timestamp: Optional[str] = None
    reason: Optional[str] = None
    source: Optional[str] = None

    def __init__(
        self,
        node_id: str = "",
        incident_type: Any = "HIGH_CPU",
        severity: Any = "MEDIUM",
        telemetry: Optional[Dict[str, Any]] = None,
        incident_id: Optional[str] = None,
        timestamp: Optional[str] = None,
        reason: Optional[str] = None,
        source: Optional[str] = None,
        **kwargs,
    ):
        self.node_id = str(node_id)
        self.incident_type = incident_type.value if hasattr(incident_type, "value") else str(incident_type)
        self.severity = (severity.value if hasattr(severity, "value") else str(severity)).upper()
        self.telemetry = telemetry if telemetry is not None else kwargs.get("metrics", {})
        self.incident_id = incident_id or f"inc_{uuid.uuid4().hex[:10]}"
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.reason = reason or ""
        self.source = source or "system"


@dataclass
class RecoveryActionDefinition:
    action_id: str
    name: str
    description: str
    applicable_incident_types: List[str]
    base_effectiveness_prior: float
    expected_duration_sec: float
    resource_impact_cost: float
    invasiveness_risk: float
    min_authorized_severity: str = "LOW"
    requires_confirmation: bool = False


@dataclass
class ActionCandidateScore:
    action_id: str
    name: str
    score: float
    historical_success_rate: float
    trials: int
    successes: int
    resource_cost: float
    recovery_time_sec: float
    risk_penalty: float
    is_authorized: bool
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MetricCriterion:
    metric_name: str
    target_operator: str = "<="
    baseline_value: Optional[float] = None
    target_threshold: Optional[float] = None
    required_drop_pct: Optional[float] = None
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RecoveryCriteria:
    incident_type: str
    action_id: str
    baseline_metrics: Dict[str, Any] = field(default_factory=dict)
    criteria: List[MetricCriterion] = field(default_factory=list)
    timeout_sec: float = 10.0
    sampling_interval_sec: float = 0.5
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_type": self.incident_type,
            "action_id": self.action_id,
            "baseline_metrics": self.baseline_metrics,
            "timeout_sec": self.timeout_sec,
            "sampling_interval_sec": self.sampling_interval_sec,
            "description": self.description,
            "criteria": [c.to_dict() if hasattr(c, "to_dict") else asdict(c) for c in self.criteria],
        }


@dataclass
class VerificationResult:
    status: VerificationStatus
    verification_duration_sec: float
    observed_metrics: Dict[str, Any] = field(default_factory=dict)
    criteria_evaluations: List[Dict[str, Any]] = field(default_factory=list)
    details: str = ""
    is_verified: bool = False
    timeout_exceeded: bool = False
    telemetry_unavailable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "verification_duration_sec": round(self.verification_duration_sec, 3),
            "observed_metrics": self.observed_metrics,
            "criteria_evaluations": self.criteria_evaluations,
            "details": self.details,
            "is_verified": self.is_verified,
            "timeout_exceeded": self.timeout_exceeded,
            "telemetry_unavailable": self.telemetry_unavailable,
        }


@dataclass
class ExecutionResult:
    action_id: str
    success: bool
    duration_sec: float
    details: Any
    metrics_before: Dict[str, Any] = field(default_factory=dict)
    metrics_after: Dict[str, Any] = field(default_factory=dict)
    measured_improvement: Dict[str, Any] = field(default_factory=dict)
    escalation_triggered: bool = False
    status: str = "COMPLETED"
    message: str = ""
    outcome_verified: bool = False

    def __post_init__(self):
        if not self.status or self.status == "COMPLETED":
            self.status = "SUCCESS" if self.success else "FAILED"
        if not self.message:
            self.message = str(self.details) if self.details else ""
        if not self.outcome_verified and self.success:
            self.outcome_verified = bool(
                self.measured_improvement.get("improved", False)
                or self.action_id in ("ROUTINE_OBSERVATION", "ESCALATE_TO_ADMIN", "SCHEDULE_NODE_DIAGNOSTIC")
            )


@dataclass
class DecisionResult:
    decision_id: str
    incident_id: str
    node_id: str
    incident_type: str
    severity: str
    selected_action: Any
    action_name: str
    ranking_score: float
    ranking_rationale: str
    candidate_rankings: List[Any]
    execution_status: str
    timestamp: str
    execution_result: Optional[ExecutionResult] = None
    escalated: bool = False
    escalation_reason: Optional[str] = None
    recovery_criteria: Optional[RecoveryCriteria] = None
    verification_result: Optional[VerificationResult] = None
    verification_status: Optional[str] = None
    lifecycle_status: Optional[str] = None
    is_disruptive: bool = False
    requires_authorization: bool = False
    is_approved: bool = False
    metrics_before: Optional[Dict[str, Any]] = None
    metrics_after: Optional[Dict[str, Any]] = None

    @property
    def is_escalated(self) -> bool:
        return self.escalated

    @property
    def rationale(self) -> str:
        return self.ranking_rationale

    def to_dict(self) -> Dict[str, Any]:
        # Determine canonical lifecycle status: PROPOSED, APPROVED, EXECUTING, SUCCESSFUL, FAILED, INCONCLUSIVE
        lifecycle = self.lifecycle_status
        if not lifecycle:
            v_stat = (self.verification_status or "").upper()
            exec_stat = (self.execution_status or "").upper()
            if v_stat == "SUCCESS":
                lifecycle = "SUCCESSFUL"
            elif v_stat == "FAILURE":
                lifecycle = "FAILED"
            elif v_stat == "INCONCLUSIVE":
                lifecycle = "INCONCLUSIVE"
            elif exec_stat == "EXECUTING":
                lifecycle = "EXECUTING"
            elif exec_stat == "APPROVED":
                lifecycle = "APPROVED"
            else:
                lifecycle = "PROPOSED"

        m_before = self.metrics_before or (self.recovery_criteria.baseline_metrics if self.recovery_criteria else (self.execution_result.metrics_before if self.execution_result else {}))
        m_after = self.metrics_after or (self.verification_result.observed_metrics if self.verification_result and self.verification_result.observed_metrics else (self.execution_result.metrics_after if self.execution_result else {}))
        improvement = self.execution_result.measured_improvement if self.execution_result else {}

        return {
            "decision_id": self.decision_id,
            "incident_id": self.incident_id,
            "node_id": self.node_id,
            "incident_type": self.incident_type,
            "severity": self.severity,
            "selected_action": str(self.selected_action) if self.selected_action else None,
            "action_name": self.action_name,
            "ranking_score": self.ranking_score,
            "ranking_rationale": self.ranking_rationale,
            "candidate_rankings": [
                (c.to_dict() if hasattr(c, "to_dict") else c) for c in self.candidate_rankings
            ],
            "execution_status": self.execution_status,
            "timestamp": self.timestamp,
            "execution_result": asdict(self.execution_result) if self.execution_result else None,
            "escalated": self.escalated,
            "escalation_reason": self.escalation_reason,
            "recovery_criteria": self.recovery_criteria.to_dict() if self.recovery_criteria else None,
            "verification_result": self.verification_result.to_dict() if self.verification_result else None,
            "verification_status": self.verification_status,
            "lifecycle_status": lifecycle,
            "is_disruptive": self.is_disruptive,
            "requires_authorization": self.requires_authorization,
            "is_approved": self.is_approved,
            "metrics_before": m_before,
            "metrics_after": m_after,
            "measured_improvement": improvement,
        }
