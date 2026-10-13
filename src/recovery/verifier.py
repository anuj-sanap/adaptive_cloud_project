"""
verifier.py - Closed-Loop Recovery Verification Module.

Defines measurable recovery criteria before action execution,
collects fresh post-action telemetry within a configurable time window,
verifies outcomes objectively against criteria,
records actual recovery durations,
and marks inconclusive results separately from success and failure.
"""

from __future__ import annotations

import time
import json
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from datetime import datetime, timezone

from recovery.models import (
    Incident,
    VerificationStatus,
    MetricCriterion,
    RecoveryCriteria,
    VerificationResult,
)


class ClosedLoopVerifier:
    """
    Closed-Loop Recovery Verifier.
    Enforces objective verification of recovery actions using fresh telemetry.
    """

    def __init__(self, default_timeout_sec: float = 10.0, poll_interval_sec: float = 0.5):
        self.default_timeout_sec = default_timeout_sec
        self.poll_interval_sec = poll_interval_sec

    def define_criteria(
        self,
        incident: Incident,
        action_id: str,
        timeout_sec: Optional[float] = None,
        custom_thresholds: Optional[Dict[str, float]] = None,
    ) -> RecoveryCriteria:
        """
        Defines quantitative recovery criteria based on the incident type, baseline metrics, and action.
        """
        baseline = dict(incident.telemetry or {})
        timeout = float(timeout_sec if timeout_sec is not None else self.default_timeout_sec)
        thresholds = custom_thresholds or {}
        criteria_list: List[MetricCriterion] = []
        inc_type = str(incident.incident_type).upper()

        if inc_type in ("HIGH_CPU", "CPU_STRESS"):
            base_cpu = float(baseline.get("cpu_utilization", 85.0))
            target_cpu = thresholds.get("target_cpu", 75.0)
            criteria_list.append(MetricCriterion(
                metric_name="cpu_utilization",
                target_operator="<=",
                baseline_value=base_cpu,
                target_threshold=target_cpu,
                required_drop_pct=10.0,
                description=f"CPU utilization must stabilize <= {target_cpu}% (baseline: {base_cpu}%)",
            ))

        elif inc_type in ("HIGH_MEMORY", "MEMORY_STRESS"):
            base_ram = float(baseline.get("ram_utilization", 88.0))
            target_ram = thresholds.get("target_ram", 78.0)
            criteria_list.append(MetricCriterion(
                metric_name="ram_utilization",
                target_operator="<=",
                baseline_value=base_ram,
                target_threshold=target_ram,
                required_drop_pct=8.0,
                description=f"RAM utilization must drop <= {target_ram}% (baseline: {base_ram}%)",
            ))

        elif inc_type in ("HIGH_DISK", "DISK_STRESS"):
            base_disk = float(baseline.get("disk_utilization", 85.0))
            target_disk = thresholds.get("target_disk", 85.0)
            criteria_list.append(MetricCriterion(
                metric_name="disk_utilization",
                target_operator="<=",
                baseline_value=base_disk,
                target_threshold=target_disk,
                required_drop_pct=2.0,
                description=f"Disk utilization must stabilize <= {target_disk}% (baseline: {base_disk}%)",
            ))

        elif inc_type in ("PREDICTIVE_FAILURE", "COMPOUND_RESOURCE_PRESSURE"):
            base_cpu = float(baseline.get("cpu_utilization", 75.0))
            base_ram = float(baseline.get("ram_utilization", 75.0))
            base_pressure = (base_cpu * base_ram) / 100.0
            target_pressure = thresholds.get("target_pressure", 50.0)

            criteria_list.append(MetricCriterion(
                metric_name="cpu_utilization",
                target_operator="<=",
                baseline_value=base_cpu,
                target_threshold=thresholds.get("target_cpu", 75.0),
                description="CPU load must return to safe operating band (<= 75%)",
            ))
            criteria_list.append(MetricCriterion(
                metric_name="ram_utilization",
                target_operator="<=",
                baseline_value=base_ram,
                target_threshold=thresholds.get("target_ram", 78.0),
                description="Memory working set must trim to safe bounds (<= 78%)",
            ))

        elif inc_type == "SECURITY_ANOMALY":
            criteria_list.append(MetricCriterion(
                metric_name="quarantine_active",
                target_operator="boolean_true",
                baseline_value=0.0,
                target_threshold=1.0,
                description="Network quarantine isolation tag active on target node",
            ))

        else:
            # Generic bounded variance criterion
            criteria_list.append(MetricCriterion(
                metric_name="status_online",
                target_operator="boolean_true",
                baseline_value=1.0,
                target_threshold=1.0,
                description="Node must maintain heartbeat and respond to health probe",
            ))

        desc = f"Recovery verification for {inc_type} via {action_id} within {timeout:.1f}s window."
        return RecoveryCriteria(
            incident_type=inc_type,
            action_id=action_id,
            baseline_metrics=baseline,
            criteria=criteria_list,
            timeout_sec=timeout,
            sampling_interval_sec=self.poll_interval_sec,
            description=desc,
        )

    def verify(
        self,
        node_id: str,
        criteria: RecoveryCriteria,
        telemetry_provider: Optional[Union[Callable[[], Optional[Dict[str, Any]]], Dict[str, Any]]] = None,
        timeout_sec: Optional[float] = None,
    ) -> VerificationResult:
        """
        Executes the verification loop:
        1. Collects fresh telemetry within the timeout window.
        2. Evaluates metrics against defined recovery criteria.
        3. Returns SUCCESS, FAILURE, or INCONCLUSIVE.
        """
        timeout = float(timeout_sec if timeout_sec is not None else criteria.timeout_sec)
        start_time = time.perf_counter()
        action_start_time = datetime.now(timezone.utc)
        last_observed: Optional[Dict[str, Any]] = None
        evaluations_summary: List[Dict[str, Any]] = []
        fresh_evidence_received = False
        stale_detected = False

        # Determine how to query telemetry
        collector = self._resolve_collector(node_id, telemetry_provider)

        while True:
            elapsed = time.perf_counter() - start_time
            telemetry_snapshot = collector()

            if telemetry_snapshot is not None and isinstance(telemetry_snapshot, dict) and len(telemetry_snapshot) > 0:
                is_stale = False
                if telemetry_snapshot.get("is_stale") is True or telemetry_snapshot.get("stale") is True:
                    is_stale = True
                elif not isinstance(telemetry_provider, dict) and telemetry_snapshot.get("timestamp"):
                    # Check database/polled telemetry timestamp freshness
                    try:
                        ts_str = str(telemetry_snapshot["timestamp"]).replace("Z", "+00:00")
                        t_dt = datetime.fromisoformat(ts_str)
                        if t_dt.tzinfo is None:
                            t_dt = t_dt.replace(tzinfo=timezone.utc)
                        age_sec = (datetime.now(timezone.utc) - t_dt).total_seconds()
                        if age_sec > 45.0:
                            is_stale = True
                    except Exception:
                        pass

                if is_stale:
                    stale_detected = True
                else:
                    fresh_evidence_received = True
                    last_observed = telemetry_snapshot
                    all_met, eval_list = self._evaluate_criteria(criteria, telemetry_snapshot)
                    evaluations_summary = eval_list

                    if all_met:
                        duration = max(0.01, round(elapsed, 3))
                        return VerificationResult(
                            status=VerificationStatus.SUCCESS,
                            verification_duration_sec=duration,
                            observed_metrics=telemetry_snapshot,
                            criteria_evaluations=eval_list,
                            details=f"Verification successful: All {len(eval_list)} recovery criteria met in {duration:.2f}s.",
                            is_verified=True,
                            timeout_exceeded=False,
                            telemetry_unavailable=False,
                        )

            # Check if timeout window expired
            if elapsed >= timeout:
                break

            time.sleep(min(self.poll_interval_sec, max(0.01, timeout - elapsed)))

        # Verification window expired: determine if FAILURE or INCONCLUSIVE
        total_duration = max(0.01, round(time.perf_counter() - start_time, 3))

        # Case 1: Telemetry was completely unavailable or stale
        if not fresh_evidence_received or last_observed is None or len(last_observed) == 0:
            details_msg = (
                "Verification inconclusive: Telemetry evidence was stale (no fresh post-action telemetry reported within window)."
                if stale_detected
                else "Verification inconclusive: Fresh telemetry was unavailable or node did not report within window."
            )
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                verification_duration_sec=total_duration,
                observed_metrics=last_observed or {},
                criteria_evaluations=[],
                details=details_msg,
                is_verified=False,
                timeout_exceeded=True,
                telemetry_unavailable=True,
            )

        # Case 2: Fresh telemetry was collected, but metrics failed criteria
        failed_items = [e["description"] for e in evaluations_summary if not e["met"]]
        failed_details = "; ".join(failed_items) if failed_items else "Observed metrics did not meet targets"

        return VerificationResult(
            status=VerificationStatus.FAILURE,
            verification_duration_sec=total_duration,
            observed_metrics=last_observed,
            criteria_evaluations=evaluations_summary,
            details=f"Verification failed: Metrics did not meet recovery criteria within {timeout:.1f}s window ({failed_details}).",
            is_verified=True,
            timeout_exceeded=True,
            telemetry_unavailable=False,
        )

    def _resolve_collector(
        self,
        node_id: str,
        provider: Optional[Union[Callable[[], Optional[Dict[str, Any]]], Dict[str, Any]]],
    ) -> Callable[[], Optional[Dict[str, Any]]]:
        """Resolves the telemetry source: callable, static dict, or default database lookup."""
        if callable(provider):
            return provider
        elif isinstance(provider, dict):
            # Static dict supplied (instantaneous evaluation)
            return lambda: provider
        else:
            # Default database telemetry reader
            def db_reader():
                try:
                    from central_server.database import get_latest_telemetry
                    return get_latest_telemetry(node_id)
                except Exception:
                    return None
            return db_reader

    def _evaluate_criteria(
        self,
        criteria: RecoveryCriteria,
        observed: Dict[str, Any],
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """Evaluates each criterion against the observed telemetry payload."""
        all_passed = True
        evaluations = []

        # Flatten nested metrics if metrics dictionary is nested under 'metrics'
        flattened = dict(observed)
        if "metrics" in flattened and isinstance(flattened["metrics"], dict):
            flattened.update(flattened["metrics"])

        for crit in criteria.criteria:
            val = flattened.get(crit.metric_name)

            if crit.target_operator == "boolean_true":
                met = bool(val is True or val == 1 or flattened.get("quarantined") is True or flattened.get("online") is True)
                evaluations.append({
                    "metric": crit.metric_name,
                    "target": "True",
                    "observed": str(val),
                    "met": met,
                    "description": crit.description,
                })
                if not met:
                    all_passed = False
                continue

            # Numeric evaluation
            if val is None:
                all_passed = False
                evaluations.append({
                    "metric": crit.metric_name,
                    "target": str(crit.target_threshold),
                    "observed": "None (Missing)",
                    "met": False,
                    "description": f"{crit.description} - Metric missing in telemetry",
                })
                continue

            try:
                obs_float = float(val)
                met = False
                if crit.target_operator == "<=":
                    target = float(crit.target_threshold or 0.0)
                    met = (obs_float <= target)
                    # Also accept relative drop if required_drop_pct specified
                    if not met and crit.baseline_value and crit.required_drop_pct and crit.baseline_value > 0:
                        drop_pct = ((crit.baseline_value - obs_float) / crit.baseline_value) * 100.0
                        if drop_pct >= crit.required_drop_pct:
                            met = True
                elif crit.target_operator == ">=":
                    target = float(crit.target_threshold or 0.0)
                    met = (obs_float >= target)

                if not met:
                    all_passed = False

                evaluations.append({
                    "metric": crit.metric_name,
                    "target": f"{crit.target_operator} {crit.target_threshold}",
                    "observed": round(obs_float, 2),
                    "met": met,
                    "description": crit.description,
                })
            except (ValueError, TypeError):
                all_passed = False
                evaluations.append({
                    "metric": crit.metric_name,
                    "target": str(crit.target_threshold),
                    "observed": str(val),
                    "met": False,
                    "description": "Metric value non-numeric",
                })

        return all_passed, evaluations
