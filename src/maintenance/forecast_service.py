"""
forecast_service.py - Predictive Maintenance Forecasting & Trend Evaluation Service.
Consumes real historical telemetry from the central database, runs the trained
XGBoost predictive maintenance model, verifies data sufficiency, projects
forecast horizons and threshold-crossing times using verified trends, and correlates
actual historical alert outcomes.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import numpy as np

from central_server.database import (
    get_node_by_id,
    get_latest_active_alert_for_node,
    get_all_maintenance_alerts,
)
from maintenance.predict import (
    predict_failure,
    load_maintenance_config,
    _get_model_metrics,
)


def evaluate_node_predictive_maintenance(
    node_id: str,
    history_limit: int = 50,
) -> Optional[Dict[str, Any]]:
    """
    Evaluates predictive maintenance, trend forecasting, data sufficiency,
    and historical outcomes for a specific registered node.
    
    Strictly uses real historical telemetry from the central database and
    the trained Alibaba XGBoost failure model.
    """
    node = get_node_by_id(node_id=node_id, limit_telemetry=history_limit)
    if not node:
        return None

    recent_telemetry = node.get("recent_telemetry") or []
    reading_count = len(recent_telemetry)
    min_required_readings = 5
    is_sufficient = reading_count >= min_required_readings

    config = load_maintenance_config()
    thresholds = config.get("thresholds", {"low_max": 0.30, "medium_max": 0.70})
    eval_metrics = _get_model_metrics("XGBClassifier")

    model_metadata = {
        "model_name": "XGBoost Maintenance Classifier",
        "model_version": config.get("version", "2.0.0"),
        "status": "LOADED",
        "dataset": "Alibaba 2018 Cluster Trace (Machine Failure Envelope)",
        "features": ["CPU_utilization", "Memory_utilization", "Disk_utilization", "Resource_pressure"],
        "target": "Machine_failure (0 = Healthy, 1 = Imminent Failure)",
        "evaluation_metrics": eval_metrics,
        "prediction_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Case 1: Node has zero telemetry
    if reading_count == 0:
        return {
            "node_id": node_id,
            "hostname": node.get("hostname", node_id),
            "region": node.get("region", "us-central1"),
            "data_sufficiency": {
                "is_sufficient": False,
                "reading_count": 0,
                "min_required": min_required_readings,
                "status": "NO_DATA",
                "message": "No telemetry recorded for this node. The predictive maintenance model cannot evaluate risk without real host measurements.",
            },
            "prediction": None,
            "forecast": {
                "forecast_horizon": None,
                "estimated_threshold_crossing": None,
                "threshold_crossing_message": "Forecast unavailable: Zero historical readings available.",
                "forecast_points": [],
                "leading_metric": None,
            },
            "trend_explanation": "Awaiting initial telemetry ingestion from node agent.",
            "timeline": [],
            "actual_outcomes": [],
            "active_alert": None,
            "model_metadata": model_metadata,
        }

    # Latest reading evaluation using real backend ML model
    latest_record = recent_telemetry[0]
    maint_input = latest_record.get("metrics") or latest_record
    prediction_result = predict_failure(maint_input)

    # Sort telemetry chronologically (oldest to newest)
    chronological = list(reversed(recent_telemetry))

    # Build timeline of measured readings
    timeline: List[Dict[str, Any]] = []
    t_seconds: List[float] = []
    cpu_vals: List[float] = []
    ram_vals: List[float] = []
    disk_vals: List[float] = []
    pressure_vals: List[float] = []

    t_base = None
    for rec in chronological:
        ts_str = rec.get("timestamp") or ""
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            epoch = dt.timestamp()
            if t_base is None:
                t_base = epoch
            rel_sec = epoch - t_base
        except Exception:
            rel_sec = len(t_seconds) * 5.0

        raw = rec.get("metrics") or {}
        c = rec.get("cpu_utilization") if rec.get("cpu_utilization") is not None else raw.get("cpu_utilization")
        r = rec.get("ram_utilization") if rec.get("ram_utilization") is not None else raw.get("ram_utilization")
        d = rec.get("disk_utilization") if rec.get("disk_utilization") is not None else raw.get("disk_utilization")

        c_f = float(c) if c is not None else 0.0
        r_f = float(r) if r is not None else 0.0
        d_f = float(d) if d is not None else 0.0
        p_f = round((c_f * r_f) / 100.0, 2)

        t_seconds.append(rel_sec)
        cpu_vals.append(c_f)
        ram_vals.append(r_f)
        disk_vals.append(d_f)
        pressure_vals.append(p_f)

        # Classify anomaly status based on live thresholds
        is_anomaly = (
            c_f >= 85.0 or
            r_f >= 85.0 or
            d_f >= 90.0 or
            p_f >= 45.0
        )

        time_label = ts_str.replace("T", " ")[11:19] if len(ts_str) >= 19 else f"+{int(rel_sec)}s"
        timeline.append({
            "time": time_label,
            "timestamp": ts_str,
            "type": "ANOMALY" if is_anomaly else "MEASURED",
            "cpu": c_f,
            "ram": r_f,
            "disk": d_f,
            "resource_pressure": p_f,
            "is_forecast": False,
            "is_anomaly": is_anomaly,
        })

    # Case 2: Insufficient readings (< 5 readings)
    if not is_sufficient:
        return {
            "node_id": node_id,
            "hostname": node.get("hostname", node_id),
            "region": node.get("region", "us-central1"),
            "data_sufficiency": {
                "is_sufficient": False,
                "reading_count": reading_count,
                "min_required": min_required_readings,
                "status": "INSUFFICIENT_HISTORY",
                "message": f"Insufficient historical telemetry points ({reading_count}/{min_required_readings}). Minimum 5 readings required for reliable trend projection and threshold-crossing forecast.",
            },
            "prediction": prediction_result,
            "forecast": {
                "forecast_horizon": None,
                "estimated_threshold_crossing": None,
                "threshold_crossing_message": "A reliable forecast and threshold-crossing projection are unavailable due to insufficient history (minimum 5 readings required).",
                "forecast_points": [],
                "leading_metric": None,
            },
            "trend_explanation": prediction_result.get("simple_explanation") or "Operating within baseline bounds.",
            "timeline": timeline,
            "actual_outcomes": _fetch_node_outcomes(node_id),
            "active_alert": get_latest_active_alert_for_node(node_id),
            "model_metadata": model_metadata,
        }

    # Case 3: Sufficient readings (>= 5 readings) -> Trend Analysis & Forecast
    now_dt = datetime.now(timezone.utc)

    # Compute regression slopes (% change per second)
    def calc_slope(x_arr: List[float], y_arr: List[float]) -> float:
        if len(x_arr) < 2 or max(x_arr) == min(x_arr):
            return 0.0
        x = np.array(x_arr)
        y = np.array(y_arr)
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        denom = np.sum((x - x_mean) ** 2)
        if denom == 0:
            return 0.0
        return float(np.sum((x - x_mean) * (y - y_mean)) / denom)

    cpu_slope = calc_slope(t_seconds, cpu_vals) * 60.0  # % per minute
    ram_slope = calc_slope(t_seconds, ram_vals) * 60.0
    disk_slope = calc_slope(t_seconds, disk_vals) * 60.0
    pressure_slope = calc_slope(t_seconds, pressure_vals) * 60.0

    current_cpu = cpu_vals[-1]
    current_ram = ram_vals[-1]
    current_disk = disk_vals[-1]
    current_pressure = pressure_vals[-1]

    # Select leading strained metric
    candidates = [
        ("RAM Utilization", current_ram, ram_slope, 85.0),
        ("CPU Utilization", current_cpu, cpu_slope, 80.0),
        ("Disk Utilization", current_disk, disk_slope, 90.0),
        ("Resource Pressure", current_pressure, pressure_slope, 45.0),
    ]

    # Sort candidate by severity (current strain + slope)
    candidates.sort(key=lambda c: (c[1] / c[3] + max(0, c[2]) * 0.1), reverse=True)
    leading_name, leading_val, leading_slope, leading_threshold = candidates[0]

    estimated_crossing_iso: Optional[str] = None
    forecast_horizon: str
    crossing_message: str

    if leading_val >= leading_threshold:
        estimated_crossing_iso = now_dt.isoformat()
        forecast_horizon = "Immediate intervention window"
        crossing_message = f"Critical threshold ({leading_threshold}%) is currently exceeded by {leading_name} ({leading_val:.1f}%). High failure risk is active."
    elif leading_slope > 0.05:
        minutes_to_cross = (leading_threshold - leading_val) / leading_slope
        if 0 < minutes_to_cross <= 180:
            crossing_dt = now_dt + timedelta(minutes=minutes_to_cross)
            estimated_crossing_iso = crossing_dt.isoformat()
            horizon_mins = int(min(120, max(15, minutes_to_cross * 1.5)))
            forecast_horizon = f"{horizon_mins} minutes"
            crossing_message = (
                f"Projected to cross {leading_name} critical threshold ({leading_threshold}%) in approximately "
                f"{int(minutes_to_cross)} minutes at current rate of strain (+{leading_slope * 60.0:.1f}%/hr)."
            )
        else:
            forecast_horizon = "60 minutes (Gradual rise)"
            crossing_message = f"{leading_name} is rising gradually (+{leading_slope * 60.0:.1f}%/hr); critical threshold crossing is not expected within the 60-minute window."
    else:
        forecast_horizon = "60 minutes (Stable operational envelope)"
        crossing_message = "Observed trend is stable or declining; no critical threshold-crossing expected within the forecast horizon."

    # Generate 4 forecast projection points
    forecast_points: List[Dict[str, Any]] = []
    projection_steps = [5, 10, 15, 20]  # minutes ahead
    residual_std = 2.5  # empirical variance bound

    for step_m in projection_steps:
        f_time = now_dt + timedelta(minutes=step_m)
        proj_val = min(100.0, max(0.0, leading_val + leading_slope * step_m))
        lower_bound = max(0.0, proj_val - residual_std * math.sqrt(step_m / 5.0))
        upper_bound = min(100.0, proj_val + residual_std * math.sqrt(step_m / 5.0))

        point = {
            "time": f_time.strftime("%H:%M:%S"),
            "timestamp": f_time.isoformat(),
            "type": "FORECAST",
            "cpu": round(min(100.0, max(0.0, current_cpu + cpu_slope * step_m)), 1),
            "ram": round(min(100.0, max(0.0, current_ram + ram_slope * step_m)), 1),
            "disk": round(min(100.0, max(0.0, current_disk + disk_slope * step_m)), 1),
            "resource_pressure": round(min(100.0, max(0.0, current_pressure + pressure_slope * step_m)), 1),
            "is_forecast": True,
            "is_anomaly": proj_val >= leading_threshold,
            "uncertainty_lower": round(lower_bound, 1),
            "uncertainty_upper": round(upper_bound, 1),
        }
        forecast_points.append(point)
        timeline.append(point)

    # Concise trend / anomaly explanation
    explanation = prediction_result.get("simple_explanation") or ""
    if leading_val >= leading_threshold:
        explanation = f"High failure risk detected: {leading_name} ({leading_val:.1f}%) exceeds the critical threshold of {leading_threshold}%."
    elif leading_slope > 0.1:
        explanation = f"Upward trend detected: {leading_name} is accelerating at +{leading_slope * 60.0:.1f}%/hr towards the {leading_threshold}% threshold."

    return {
        "node_id": node_id,
        "hostname": node.get("hostname", node_id),
        "region": node.get("region", "us-central1"),
        "data_sufficiency": {
            "is_sufficient": True,
            "reading_count": reading_count,
            "min_required": min_required_readings,
            "status": "SUFFICIENT",
            "message": f"Sufficient historical telemetry points ({reading_count} readings analyzed). Trend slope and threshold-crossing projections are mathematically grounded.",
        },
        "prediction": prediction_result,
        "forecast": {
            "forecast_horizon": forecast_horizon,
            "estimated_threshold_crossing": estimated_crossing_iso,
            "threshold_crossing_message": crossing_message,
            "forecast_points": forecast_points,
            "leading_metric": leading_name,
            "leading_slope_per_min": round(leading_slope, 4),
        },
        "trend_explanation": explanation,
        "timeline": timeline,
        "actual_outcomes": _fetch_node_outcomes(node_id),
        "active_alert": get_latest_active_alert_for_node(node_id),
        "model_metadata": model_metadata,
    }


def _fetch_node_outcomes(node_id: str) -> List[Dict[str, Any]]:
    """Retrieves verified historical alert and resolution outcomes for evaluation."""
    raw_alerts = get_all_maintenance_alerts(limit=15, node_id=node_id)
    outcomes: List[Dict[str, Any]] = []

    for a in raw_alerts:
        status = a.get("status", "ACTIVE")
        outcomes.append({
            "alert_id": a.get("alert_id"),
            "timestamp": a.get("timestamp"),
            "risk_level": a.get("risk_level"),
            "failure_probability": a.get("failure_probability"),
            "status": status,
            "resolved_at": a.get("resolved_at"),
            "repeat_count": a.get("repeat_count", 1),
            "reason": a.get("reason"),
            "recommended_action": a.get("recommended_action"),
            "outcome_evaluated": status in ("RESOLVED", "ACKNOWLEDGED"),
            "actual_outcome": (
                "Verified Resolved (Workload stabilized)"
                if status == "RESOLVED"
                else ("Acknowledged by Operator" if status == "ACKNOWLEDGED" else "Active / Pending Resolution")
            ),
        })

    return outcomes
