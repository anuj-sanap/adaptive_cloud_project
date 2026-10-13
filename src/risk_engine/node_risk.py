"""Transparent per-node risk combination for independent risk signals."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CONFIG_PATH = os.path.join(BASE_DIR, "config", "node_risk.json")


def load_node_risk_config(config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Load experiment weights and thresholds from the external JSON config."""
    with open(config_path, "r", encoding="utf-8") as config_file:
        config = json.load(config_file)
    if config.get("missing_signal_policy") != "available_only":
        raise ValueError("node risk currently requires missing_signal_policy=available_only")
    return config


def _clamp_score(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return round(max(0.0, min(1.0, number)), 4)


def _risk_level(score: Optional[float], thresholds: Dict[str, float]) -> str:
    if score is None:
        return "N/A"
    if score < thresholds["low_max"]:
        return "LOW"
    if score < thresholds["medium_max"]:
        return "MEDIUM"
    if score < thresholds["high_max"]:
        return "HIGH"
    return "CRITICAL"


def _security_factors(result: Optional[Dict[str, Any]], score: Optional[float]) -> List[str]:
    if result is None or score is None:
        return ["No network-flow security result available"]
    if score >= 0.6:
        return ["Elevated security risk"]
    if score >= 0.3:
        return ["Moderate security risk"]
    return ["Low security risk"]


def _maintenance_factors(result: Optional[Dict[str, Any]], score: Optional[float]) -> List[str]:
    if result is None or score is None:
        return ["No live maintenance/health result available"]

    factors = []
    if score >= 0.7:
        factors.append("Increased health/failure probability")
    elif score >= 0.3:
        factors.append("Elevated health anomaly probability")
    else:
        factors.append("Low health anomaly probability")

    vector = result.get("feature_vector") or {}
    if any(float(vector.get(name) or 0.0) >= 70.0 for name in (
        "cpu_utilization", "ram_utilization", "disk_utilization"
    )):
        factors.append("High resource utilization")
    return factors


def combine_node_risk(
    node_id: str,
    security_result: Optional[Dict[str, Any]],
    maintenance_result: Optional[Dict[str, Any]],
    *,
    timestamp: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Combine independent security and live-health scores for one node.

    Scores are normalized to [0, 1]. Missing component scores are omitted from
    the weighted average and called out in contributing_factors.
    """
    settings = config or load_node_risk_config()
    weights = settings["weights"]
    thresholds = settings["overall_thresholds"]

    security_score = _clamp_score((security_result or {}).get("security_risk_score"))
    maintenance_score = _clamp_score((maintenance_result or {}).get("anomaly_probability"))
    available = []
    if security_score is not None:
        available.append(("security", security_score, float(weights["security"])))
    if maintenance_score is not None:
        available.append(("maintenance", maintenance_score, float(weights["maintenance"])))

    total_weight = sum(weight for _, _, weight in available)
    overall_score = None
    normalized_weights = {"security": 0.0, "maintenance": 0.0}
    if total_weight > 0:
        overall_score = round(
            sum(score * weight for _, score, weight in available) / total_weight,
            4,
        )
        for name, _, weight in available:
            normalized_weights[name] = round(weight / total_weight, 4)

    timestamps = [
        value.get("timestamp")
        for value in (security_result, maintenance_result)
        if value and value.get("timestamp")
    ]
    result_timestamp = timestamp or (max(timestamps) if timestamps else datetime.now(timezone.utc).isoformat())
    factors = _security_factors(security_result, security_score)
    factors.extend(_maintenance_factors(maintenance_result, maintenance_score))

    sec_level = _risk_level(security_score, thresholds) if security_score is not None else "N/A"
    maint_level = _risk_level(maintenance_score, thresholds) if maintenance_score is not None else "N/A"

    return {
        "node_id": node_id,
        "security_risk": security_score,
        "maintenance_risk": maintenance_score,
        "overall_risk": overall_score,
        "overall_risk_score": overall_score,
        "risk_level": _risk_level(overall_score, thresholds),
        "overall_risk_level": _risk_level(overall_score, thresholds),
        "security_risk_level": sec_level,
        "failure_risk_level": maint_level,
        "maintenance_risk_level": maint_level,
        "timestamp": result_timestamp,
        "contributing_factors": factors,
        "weights_used": normalized_weights,
        "calculation": "weighted average of available independent signals",
    }


def get_node_risk(node_id: str) -> Dict[str, Any]:
    """Build a current result from the latest persisted component predictions."""
    from central_server.database import get_latest_live_health, get_latest_node_security

    return combine_node_risk(
        node_id,
        get_latest_node_security(node_id),
        get_latest_live_health(node_id),
    )


def get_all_node_risks() -> List[Dict[str, Any]]:
    """Build one current risk result for every registered node."""
    from central_server.database import get_all_nodes, get_all_latest_live_health, get_all_latest_node_security

    health_by_node = {item["node_id"]: item for item in get_all_latest_live_health()}
    security_by_node = {item["node_id"]: item for item in get_all_latest_node_security()}
    return [
        combine_node_risk(node["node_id"], security_by_node.get(node["node_id"]), health_by_node.get(node["node_id"]))
        for node in get_all_nodes()
    ]
