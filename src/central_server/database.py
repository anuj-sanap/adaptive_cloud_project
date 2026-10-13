"""
database.py - SQLite Database management for Central Telemetry Server.
Handles database schema initialization, node registration, telemetry storage, and node status tracking.
"""

import os
import json
import sqlite3
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

# Default database location inside data/ directory
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "telemetry.db"
)
DEFAULT_OFFLINE_THRESHOLD_SEC = 30


def get_db_path() -> str:
    if "TELEMETRY_DB_PATH" in os.environ and os.environ["TELEMETRY_DB_PATH"].strip():
        db_path = os.environ["TELEMETRY_DB_PATH"].strip()
    elif os.getenv("WEBSITE_SITE_NAME"):
        # Automatically use Azure App Service Linux persistent storage mount (/home)
        db_path = "/home/data/telemetry.db"
    else:
        db_path = DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return db_path


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA synchronous = NORMAL")
    except Exception:
        pass
    return conn


def get_offline_threshold_sec() -> int:
    return int(os.getenv("NODE_OFFLINE_THRESHOLD_SEC", str(DEFAULT_OFFLINE_THRESHOLD_SEC)))


def init_db():
    """
    Initializes SQLite tables for registered nodes and time-series telemetry.
    """
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Nodes Registry Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                hostname TEXT NOT NULL,
                ip_address TEXT,
                operating_system TEXT,
                hardware_info TEXT,
                location_label TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                last_heartbeat TEXT,
                status TEXT NOT NULL DEFAULT 'ONLINE'
            )
        """)

        node_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(nodes)").fetchall()}
        if "location_label" not in node_columns:
            cursor.execute("ALTER TABLE nodes ADD COLUMN location_label TEXT")
        if "last_heartbeat" not in node_columns:
            cursor.execute("ALTER TABLE nodes ADD COLUMN last_heartbeat TEXT")
            cursor.execute("UPDATE nodes SET last_heartbeat = last_seen WHERE last_heartbeat IS NULL")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS node_agent_credentials (
                node_id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
        """)
        
        # Telemetry Time-Series Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                cpu_utilization REAL,
                ram_utilization REAL,
                disk_utilization REAL,
                network_sent_mb REAL,
                network_recv_mb REAL,
                disk_read_mb REAL,
                disk_write_mb REAL,
                cpu_temperature_c REAL,
                process_count INTEGER,
                raw_metrics TEXT,
                FOREIGN KEY (node_id) REFERENCES nodes(node_id)
            )
        """)
        
        # Index on (node_id, timestamp) for fast telemetry lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_telemetry_node_time 
            ON telemetry(node_id, timestamp)
        """)

        # Live infrastructure health predictions (separate from Alibaba maintenance model)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS live_health_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                health_status TEXT NOT NULL,
                anomaly_probability REAL,
                model_name TEXT NOT NULL,
                model_version TEXT NOT NULL,
                contributing_features TEXT,
                feature_vector TEXT,
                node_status TEXT,
                FOREIGN KEY (node_id) REFERENCES nodes(node_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_live_health_node_time
            ON live_health_predictions(node_id, timestamp)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS node_security_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                classification TEXT NOT NULL,
                attack_type TEXT,
                security_risk TEXT,
                confidence REAL,
                model_name TEXT NOT NULL,
                model_version TEXT NOT NULL,
                prediction_source TEXT NOT NULL,
                is_simulated INTEGER NOT NULL DEFAULT 0,
                source_label TEXT,
                extra_json TEXT,
                FOREIGN KEY (node_id) REFERENCES nodes(node_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_node_security_node_time
            ON node_security_predictions(node_id, timestamp)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS drift_reference_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                feature TEXT NOT NULL,
                value REAL NOT NULL,
                FOREIGN KEY (node_id) REFERENCES nodes(node_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_drift_reference_node_time
            ON drift_reference_samples(node_id, timestamp)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS live_drift_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                feature TEXT NOT NULL,
                drift_statistic REAL,
                p_value REAL,
                drift_status TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                reference_window TEXT NOT NULL,
                current_window TEXT NOT NULL,
                FOREIGN KEY (node_id) REFERENCES nodes(node_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_live_drift_node_feature
            ON live_drift_results(node_id, feature, timestamp)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS adaptive_model_state (
                target_model TEXT PRIMARY KEY,
                current_version TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS adaptive_retraining_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                target_model TEXT NOT NULL,
                previous_model_version TEXT NOT NULL,
                new_model_version TEXT NOT NULL,
                drift_event TEXT NOT NULL,
                affected_features TEXT NOT NULL,
                new_data_samples INTEGER NOT NULL,
                training_time_seconds REAL NOT NULL,
                validation_metrics TEXT NOT NULL,
                deployment_decision TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_adaptive_retraining_node_time
            ON adaptive_retraining_runs(node_id, target_model, timestamp)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS closed_loop_experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id TEXT NOT NULL UNIQUE,
                node_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                baseline_json TEXT NOT NULL,
                after_json TEXT NOT NULL,
                recommendation_json TEXT NOT NULL,
                intervention TEXT NOT NULL,
                measured_change_json TEXT NOT NULL,
                label TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_closed_loop_node_time
            ON closed_loop_experiments(node_id, timestamp)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS maintenance_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT NOT NULL UNIQUE,
                node_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                failure_probability REAL NOT NULL,
                risk_level TEXT NOT NULL,
                telemetry_summary TEXT NOT NULL,
                reason TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                repeat_count INTEGER NOT NULL DEFAULT 1,
                resolved_at TEXT,
                FOREIGN KEY (node_id) REFERENCES nodes(node_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_node_status
            ON maintenance_alerts(node_id, status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_timestamp
            ON maintenance_alerts(timestamp)
        """)

        # Adaptive Recovery Engine: Historical Action Outcomes & Decisions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recovery_action_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                incident_type TEXT NOT NULL,
                action_id TEXT NOT NULL,
                trials INTEGER NOT NULL DEFAULT 0,
                successes INTEGER NOT NULL DEFAULT 0,
                total_recovery_time_sec REAL NOT NULL DEFAULT 0.0,
                last_outcome TEXT,
                last_updated TEXT NOT NULL,
                UNIQUE(node_id, incident_type, action_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_recovery_hist_lookup
            ON recovery_action_history(node_id, incident_type, action_id)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recovery_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id TEXT NOT NULL UNIQUE,
                incident_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                incident_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                selected_action TEXT NOT NULL,
                ranking_score REAL NOT NULL,
                ranking_rationale TEXT NOT NULL,
                candidate_scores_json TEXT NOT NULL,
                metrics_before_json TEXT,
                metrics_after_json TEXT,
                execution_status TEXT NOT NULL,
                success_measured INTEGER,
                recovery_duration_sec REAL,
                verification_status TEXT,
                recovery_criteria_json TEXT,
                verification_details_json TEXT,
                escalated INTEGER NOT NULL DEFAULT 0,
                timestamp TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_recovery_decisions_node_time
            ON recovery_decisions(node_id, timestamp)
        """)

        # Idempotent migration for verification columns
        for col_name, col_type in [
            ("verification_status", "TEXT"),
            ("recovery_criteria_json", "TEXT"),
            ("verification_details_json", "TEXT"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE recovery_decisions ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

        # Reproducible Recovery Policy Benchmark Results
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recovery_policy_benchmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                benchmark_id TEXT NOT NULL UNIQUE,
                timestamp TEXT NOT NULL,
                mode TEXT NOT NULL,
                trial_count INTEGER NOT NULL,
                seed INTEGER,
                adaptive_metrics_json TEXT NOT NULL,
                baseline_metrics_json TEXT NOT NULL,
                deltas_json TEXT NOT NULL,
                episodes_log_json TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_benchmarks_mode_time
            ON recovery_policy_benchmarks(mode, timestamp)
        """)
        
        conn.commit()
    print(f"[CENTRAL DB]: Initialized SQLite database at '{db_path}'")


def update_node_statuses(offline_threshold_sec: Optional[int] = None):
    """
    Marks nodes as OFFLINE if their last_seen timestamp is older than offline_threshold_sec.
    """
    if offline_threshold_sec is None:
        offline_threshold_sec = get_offline_threshold_sec()
    now_utc = datetime.now(timezone.utc)
    threshold_time = (now_utc - timedelta(seconds=offline_threshold_sec)).isoformat()
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE nodes 
            SET status = 'OFFLINE'
            WHERE COALESCE(last_heartbeat, last_seen) < ? AND status != 'OFFLINE'
        """, (threshold_time,))
        conn.commit()


def has_agent_credential(node_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM node_agent_credentials WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        return row is not None


def store_agent_credential(node_id: str, token_hash: str) -> bool:
    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO node_agent_credentials (node_id, token_hash, created_at) VALUES (?, ?, ?)",
                (node_id, token_hash, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def get_agent_node_id(token_hash: str) -> Optional[str]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT node_id FROM node_agent_credentials WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        return row["node_id"] if row else None


def register_node(
    node_id: str,
    hostname: str,
    ip_address: Optional[str] = "127.0.0.1",
    operating_system: Optional[str] = "Unknown OS",
    hardware_info: Optional[Dict[str, Any]] = None,
    location_label: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Registers a node or updates its metadata if already registered.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    hw_str = json.dumps(hardware_info or {})
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT node_id, first_seen FROM nodes WHERE node_id = ?", (node_id,))
        row = cursor.fetchone()
        
        if row:
            # Update existing node
            cursor.execute("""
                UPDATE nodes 
                SET hostname = ?, ip_address = ?, operating_system = ?,
                    hardware_info = ?, location_label = COALESCE(?, location_label),
                    last_seen = ?, last_heartbeat = ?, status = 'ONLINE'
                WHERE node_id = ?
            """, (hostname, ip_address, operating_system, hw_str, location_label, now_iso, now_iso, node_id))
            first_seen = row["first_seen"]
        else:
            # Insert new node
            first_seen = now_iso
            cursor.execute("""
                INSERT INTO nodes (node_id, hostname, ip_address, operating_system, hardware_info, location_label, first_seen, last_seen, last_heartbeat, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ONLINE')
            """, (node_id, hostname, ip_address, operating_system, hw_str, location_label, first_seen, now_iso, now_iso))
        
        conn.commit()
        
    return {
        "node_id": node_id,
        "hostname": hostname,
        "ip_address": ip_address,
        "operating_system": operating_system,
        "hardware_info": hardware_info or {},
        "location_label": location_label,
        "first_seen": first_seen,
        "last_seen": now_iso,
        "last_heartbeat": now_iso,
        "status": "ONLINE"
    }


def record_telemetry(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stores telemetry payload and updates node last_seen timestamp & status.
    Auto-registers node if not seen before.
    """
    node_id = payload.get("node_id")
    if not node_id:
        raise ValueError("Payload missing required 'node_id'")
        
    hostname = payload.get("hostname", "Unknown-Host")
    operating_system = payload.get("operating_system", "Unknown OS")
    timestamp = payload.get("timestamp") or datetime.now(timezone.utc).isoformat()
    metrics = payload.get("metrics", {})
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Ensure node is registered without calling nested connection
        cursor.execute("SELECT node_id FROM nodes WHERE node_id = ?", (node_id,))
        if not cursor.fetchone():
            now_iso = datetime.now(timezone.utc).isoformat()
            hw_str = json.dumps({
                "cpu_count_logical": metrics.get("cpu_count_logical"),
                "cpu_count_physical": metrics.get("cpu_count_physical"),
                "ram_total_mb": metrics.get("ram_total_mb"),
                "disk_total_gb": metrics.get("disk_total_gb")
            })
            cursor.execute("""
                INSERT INTO nodes (node_id, hostname, ip_address, operating_system, hardware_info, location_label, first_seen, last_seen, last_heartbeat, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ONLINE')
            """, (node_id, hostname, payload.get("ip_address"), operating_system, hw_str, payload.get("location_label"), now_iso, timestamp, now_iso))
        else:
            # Telemetry timestamps do not refresh heartbeat-based online status.
            cursor.execute("""
                UPDATE nodes 
                SET last_seen = ?
                WHERE node_id = ?
            """, (timestamp, node_id))
            
        # Insert telemetry data
        cursor.execute("""
            INSERT INTO telemetry (
                node_id, timestamp, cpu_utilization, ram_utilization, disk_utilization,
                network_sent_mb, network_recv_mb, disk_read_mb, disk_write_mb,
                cpu_temperature_c, process_count, raw_metrics
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            node_id,
            timestamp,
            metrics.get("cpu_utilization"),
            metrics.get("ram_utilization"),
            metrics.get("disk_utilization"),
            metrics.get("network_sent_mb"),
            metrics.get("network_recv_mb"),
            metrics.get("disk_read_mb"),
            metrics.get("disk_write_mb"),
            metrics.get("cpu_temperature_c"),
            metrics.get("process_count"),
            json.dumps(metrics)
        ))
        
        conn.commit()
        
    return {"status": "success", "node_id": node_id, "timestamp": timestamp}


def record_batch_telemetry(payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Ingests a list of buffered telemetry snapshots atomically.
    Preserves historical timestamps from edge nodes after network reconnection.
    """
    if not payloads:
        return {"status": "success", "ingested_count": 0, "inserted_count": 0}
        
    ingested = 0
    with get_connection() as conn:
        cursor = conn.cursor()
        for p in payloads:
            node_id = p.get("node_id")
            if not node_id:
                continue
            hostname = p.get("hostname", "Unknown-Host")
            operating_system = p.get("operating_system", "Unknown OS")
            ts = p.get("timestamp") or datetime.now(timezone.utc).isoformat()
            metrics = p.get("metrics") or {}
            
            cursor.execute("SELECT node_id FROM nodes WHERE node_id = ?", (node_id,))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO nodes (node_id, hostname, ip_address, operating_system, hardware_info, location_label, first_seen, last_seen, last_heartbeat, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ONLINE')
                """, (
                    node_id,
                    hostname,
                    p.get("ip_address"),
                    operating_system,
                    json.dumps({
                        "cpu_count_logical": metrics.get("cpu_count_logical"),
                        "cpu_count_physical": metrics.get("cpu_count_physical"),
                        "ram_total_mb": metrics.get("ram_total_mb"),
                        "disk_total_gb": metrics.get("disk_total_gb")
                    }),
                    p.get("location_label"),
                    ts,
                    ts,
                    datetime.now(timezone.utc).isoformat()
                ))
            else:
                cursor.execute("""
                    UPDATE nodes 
                    SET last_seen = CASE WHEN last_seen < ? THEN ? ELSE last_seen END
                    WHERE node_id = ?
                """, (ts, ts, node_id))
                
            cursor.execute("""
                INSERT INTO telemetry (
                    node_id, timestamp, cpu_utilization, ram_utilization, disk_utilization,
                    network_sent_mb, network_recv_mb, disk_read_mb, disk_write_mb,
                    cpu_temperature_c, process_count, raw_metrics
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                node_id,
                ts,
                metrics.get("cpu_utilization"),
                metrics.get("ram_utilization"),
                metrics.get("disk_utilization"),
                metrics.get("network_sent_mb"),
                metrics.get("network_recv_mb"),
                metrics.get("disk_read_mb"),
                metrics.get("disk_write_mb"),
                metrics.get("cpu_temperature_c"),
                metrics.get("process_count"),
                json.dumps(metrics)
            ))
            ingested += 1
            
        conn.commit()
    return {"status": "success", "ingested_count": ingested, "inserted_count": ingested}


def heartbeat_node(node_id: str) -> Dict[str, Any]:
    """
    Updates node's last_seen and status to ONLINE.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE nodes
            SET last_seen = ?, last_heartbeat = ?, status = 'ONLINE'
            WHERE node_id = ?
        """, (now_iso, now_iso, node_id))
        if cursor.rowcount == 0:
            raise ValueError(f"Node '{node_id}' is not registered")
        conn.commit()
        
    return {"status": "acknowledged", "node_id": node_id, "last_seen": now_iso}


def is_genuine_node(node_id: str, hostname: str = "") -> bool:
    """
    Returns True if the node appears to be a genuine physical machine or long-lived agent,
    and False if it is a synthetic unit test fixture or audit runner artifact.
    """
    nid = (node_id or "").lower().strip()
    host = (hostname or "").lower().strip()
    for pat in [
        "api-test", "test-verify", "frontend-test", "node_audit", 
        "test-node", "test_node", "retrain_test", "drift-test", 
        "sec_test", "lifecycle", "disco_node", "rogue_node", "dummy", "mock"
    ]:
        if pat in nid:
            return False
    if host in [
        "web-console-host", "verify-host", "api-node", "test-host", 
        "sec-test-host", "disconnect-node", "unknown-host", "rogue_node_agent", "dynamic-host-1"
    ]:
        return False
    import re
    if re.search(r"_(alpha|beta)_\d{4,7}$", nid):
        return False
    return True


def get_all_nodes(genuine_only: bool = False, **kwargs) -> List[Dict[str, Any]]:
    """
    Returns list of all registered nodes with metadata, updated status, and latest telemetry.
    If genuine_only is True, filters out synthetic unit test fixtures and mock runners.
    """
    update_node_statuses()
    health_by_node = {h["node_id"]: h for h in get_all_latest_live_health()}
    security_by_node = {s["node_id"]: s for s in get_all_latest_node_security()}
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM nodes ORDER BY last_seen DESC")
        rows = cursor.fetchall()
        
        cursor.execute("""
            SELECT * FROM telemetry 
            WHERE id IN (SELECT MAX(id) FROM telemetry GROUP BY node_id)
        """)
        tel_by_node = {}
        for tr in cursor.fetchall():
            row_dict = dict(tr)
            raw = row_dict.get("raw_metrics")
            row_dict["metrics"] = json.loads(raw) if (raw and isinstance(raw, str)) else {}
            tel_by_node[row_dict["node_id"]] = row_dict

        nodes = []
        for r in rows:
            nid = r["node_id"]
            host = r["hostname"]
            if genuine_only and not is_genuine_node(nid, host):
                continue
            hw = json.loads(r["hardware_info"]) if r["hardware_info"] else {}
            nodes.append({
                "node_id": nid,
                "hostname": r["hostname"],
                "region": hw.get("region"),
                "location_label": r["location_label"],
                "ip_address": r["ip_address"],
                "operating_system": r["operating_system"],
                "hardware_info": hw,
                "first_seen": r["first_seen"],
                "last_seen": r["last_seen"],
                "last_heartbeat": r["last_heartbeat"],
                "status": r["status"],
                "latest_telemetry": tel_by_node.get(nid),
                "latest_live_health": health_by_node.get(nid),
                "latest_security": security_by_node.get(nid),
            })
        return nodes


def get_node_by_id(node_id: str, limit_telemetry: int = 50) -> Optional[Dict[str, Any]]:
    """
    Returns single node metadata, status, and recent telemetry history.
    """
    update_node_statuses()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
        row = cursor.fetchone()
        if not row:
            return None
            
        hw = json.loads(row["hardware_info"]) if row["hardware_info"] else {}
        node_data = {
            "node_id": row["node_id"],
            "hostname": row["hostname"],
            "region": hw.get("region"),
            "location_label": row["location_label"],
            "ip_address": row["ip_address"],
            "operating_system": row["operating_system"],
            "hardware_info": hw,
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "last_heartbeat": row["last_heartbeat"],
            "status": row["status"],
            "recent_telemetry": []
        }
        
        cursor.execute("""
            SELECT * FROM telemetry 
            WHERE node_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (node_id, limit_telemetry))
        t_rows = cursor.fetchall()
        
        telemetry_list = []
        for t in t_rows:
            telemetry_list.append({
                "id": t["id"],
                "timestamp": t["timestamp"],
                "cpu_utilization": t["cpu_utilization"],
                "ram_utilization": t["ram_utilization"],
                "disk_utilization": t["disk_utilization"],
                "network_sent_mb": t["network_sent_mb"],
                "network_recv_mb": t["network_recv_mb"],
                "disk_read_mb": t["disk_read_mb"],
                "disk_write_mb": t["disk_write_mb"],
                "cpu_temperature_c": t["cpu_temperature_c"],
                "process_count": t["process_count"],
                "metrics": json.loads(t["raw_metrics"]) if t["raw_metrics"] else {}
            })
            
        node_data["recent_telemetry"] = telemetry_list
        node_data["latest_live_health"] = get_latest_live_health(node_id)
        node_data["latest_security"] = get_latest_node_security(node_id)
        return node_data


def get_latest_telemetry(node_id: str) -> Optional[Dict[str, Any]]:
    """Return the most recent telemetry row for a node, or None."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM telemetry
            WHERE node_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
        """, (node_id,))
        t = cursor.fetchone()
        if not t:
            return None
        return {
            "id": t["id"],
            "node_id": t["node_id"],
            "timestamp": t["timestamp"],
            "cpu_utilization": t["cpu_utilization"],
            "ram_utilization": t["ram_utilization"],
            "disk_utilization": t["disk_utilization"],
            "network_sent_mb": t["network_sent_mb"],
            "network_recv_mb": t["network_recv_mb"],
            "disk_read_mb": t["disk_read_mb"],
            "disk_write_mb": t["disk_write_mb"],
            "cpu_temperature_c": t["cpu_temperature_c"],
            "process_count": t["process_count"],
            "metrics": json.loads(t["raw_metrics"]) if t["raw_metrics"] else {}
        }


def save_live_health_prediction(result: Dict[str, Any]) -> None:
    """Persist one live-infrastructure health prediction."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO live_health_predictions (
                node_id, timestamp, health_status, anomaly_probability,
                model_name, model_version, contributing_features, feature_vector, node_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.get("node_id"),
            result.get("timestamp"),
            result.get("health_status"),
            result.get("anomaly_probability"),
            result.get("model_name"),
            result.get("model_version"),
            json.dumps(result.get("contributing_features") or []),
            json.dumps(result.get("feature_vector") or {}),
            result.get("node_status"),
        ))
        conn.commit()


def get_latest_live_health(node_id: str) -> Optional[Dict[str, Any]]:
    """Return the most recent live-health prediction for a node."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM live_health_predictions
            WHERE node_id = ?
            ORDER BY id DESC
            LIMIT 1
        """, (node_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return _row_to_live_health(row)


def get_all_latest_live_health() -> List[Dict[str, Any]]:
    """Return the latest live-health prediction for every node that has one."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.* FROM live_health_predictions p
            INNER JOIN (
                SELECT node_id, MAX(id) AS max_id
                FROM live_health_predictions
                GROUP BY node_id
            ) latest ON p.id = latest.max_id
        """)
        return [_row_to_live_health(r) for r in cursor.fetchall()]


def save_node_security_prediction(result: Dict[str, Any]) -> None:
    """Persist one per-node security result (genuine flow or demo sample)."""
    extra = {
        k: result.get(k)
        for k in (
            "predicted_attack_cat", "sample_attack_cat",
            "security_risk_score", "security_risk_reason", "model_path",
        )
    }
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO node_security_predictions (
                node_id, timestamp, classification, attack_type, security_risk,
                confidence, model_name, model_version, prediction_source,
                is_simulated, source_label, extra_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.get("node_id"),
            result.get("timestamp"),
            result.get("classification"),
            result.get("attack_type"),
            result.get("security_risk"),
            result.get("confidence"),
            result.get("model_name"),
            result.get("model_version"),
            result.get("prediction_source"),
            1 if result.get("is_simulated") else 0,
            result.get("source_label"),
            json.dumps(extra),
        ))
        conn.commit()


def get_latest_node_security(node_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM node_security_predictions
                WHERE node_id = ?
                ORDER BY id DESC
                LIMIT 1
            """, (node_id,))
        except sqlite3.OperationalError:
            return None
        row = cursor.fetchone()
        if not row:
            return None
        return _row_to_node_security(row)


def get_all_latest_node_security() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT p.* FROM node_security_predictions p
                INNER JOIN (
                    SELECT node_id, MAX(id) AS max_id
                    FROM node_security_predictions
                    GROUP BY node_id
                ) latest ON p.id = latest.max_id
            """)
        except sqlite3.OperationalError:
            return []
        return [_row_to_node_security(r) for r in cursor.fetchall()]


def _row_to_node_security(row: sqlite3.Row) -> Dict[str, Any]:
    extra = json.loads(row["extra_json"]) if row["extra_json"] else {}
    result = {
        "node_id": row["node_id"],
        "classification": row["classification"],
        "attack_type": row["attack_type"],
        "security_risk": row["security_risk"],
        "confidence": row["confidence"],
        "timestamp": row["timestamp"],
        "model_name": row["model_name"],
        "model_version": row["model_version"],
        "prediction_source": row["prediction_source"],
        "is_simulated": bool(row["is_simulated"]),
        "source_label": row["source_label"],
    }
    result.update(extra)
    return result


def _row_to_live_health(row: sqlite3.Row) -> Dict[str, Any]:
    contrib = json.loads(row["contributing_features"]) if row["contributing_features"] else []
    fvec = json.loads(row["feature_vector"]) if row["feature_vector"] else {}
    return {
        "node_id": row["node_id"],
        "health_status": row["health_status"],
        "anomaly_probability": row["anomaly_probability"],
        "model_name": row["model_name"],
        "model_version": row["model_version"],
        "timestamp": row["timestamp"],
        "contributing_features": contrib,
        "feature_vector": fvec,
        "node_status": row["node_status"],
    }


def _row_to_alert(row: sqlite3.Row) -> Dict[str, Any]:
    raw_ts = row["telemetry_summary"]
    ts_dict = {}
    if raw_ts:
        if isinstance(raw_ts, dict):
            ts_dict = raw_ts
        elif isinstance(raw_ts, str):
            try:
                parsed = json.loads(raw_ts)
                if isinstance(parsed, dict):
                    ts_dict = parsed
                elif isinstance(parsed, str):
                    try:
                        inner = json.loads(parsed)
                        if isinstance(inner, dict):
                            ts_dict = inner
                    except Exception:
                        pass
            except Exception:
                ts_dict = {}

    return {
        "id": row["id"],
        "alert_id": row["alert_id"],
        "node_id": row["node_id"],
        "timestamp": row["timestamp"],
        "last_seen_at": row["last_seen_at"],
        "failure_probability": float(row["failure_probability"]),
        "risk_level": row["risk_level"],
        "telemetry_summary": ts_dict,
        "reason": row["reason"],
        "recommended_action": row["recommended_action"],
        "status": row["status"],
        "repeat_count": int(row["repeat_count"]),
        "resolved_at": row["resolved_at"]
    }


def save_maintenance_alert(alert_data: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a new predictive-maintenance alert."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO maintenance_alerts (
                alert_id, node_id, timestamp, last_seen_at, failure_probability,
                risk_level, telemetry_summary, reason, recommended_action,
                status, repeat_count, resolved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            alert_data["alert_id"],
            alert_data["node_id"],
            alert_data["timestamp"],
            alert_data.get("last_seen_at", alert_data["timestamp"]),
            float(alert_data["failure_probability"]),
            alert_data["risk_level"],
            json.dumps(alert_data.get("telemetry_summary", {})),
            alert_data["reason"],
            alert_data["recommended_action"],
            alert_data.get("status", "ACTIVE"),
            int(alert_data.get("repeat_count", 1)),
            alert_data.get("resolved_at")
        ))
        conn.commit()
    return alert_data


def update_maintenance_alert_repeat(
    alert_id: str,
    new_prob: float,
    new_risk: str,
    new_telemetry: Dict[str, Any],
    last_seen_at: str
) -> None:
    """Updates repeat count and last_seen timestamp on an existing active alert (deduplication)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE maintenance_alerts
            SET repeat_count = repeat_count + 1,
                last_seen_at = ?,
                failure_probability = ?,
                risk_level = ?,
                telemetry_summary = ?
            WHERE alert_id = ? AND status = 'ACTIVE'
        """, (
            last_seen_at,
            float(new_prob),
            new_risk,
            json.dumps(new_telemetry or {}),
            alert_id
        ))
        conn.commit()


def get_latest_active_alert_for_node(node_id: str) -> Optional[Dict[str, Any]]:
    """Return the most recent ACTIVE maintenance alert for a specific node, or None."""
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM maintenance_alerts
                WHERE node_id = ? AND status = 'ACTIVE'
                ORDER BY timestamp DESC, id DESC
                LIMIT 1
            """, (node_id,))
            row = cursor.fetchone()
            if row:
                return _row_to_alert(row)
        except sqlite3.OperationalError:
            return None
    return None


def get_active_maintenance_alerts() -> List[Dict[str, Any]]:
    """Return all currently ACTIVE maintenance alerts across the fleet."""
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM maintenance_alerts
                WHERE status = 'ACTIVE'
                ORDER BY last_seen_at DESC, id DESC
            """)
            rows = cursor.fetchall()
            return [_row_to_alert(r) for r in rows]
        except sqlite3.OperationalError:
            return []


def get_all_maintenance_alerts(limit: int = 100, node_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return full historical maintenance alerts log."""
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            if node_id:
                cursor.execute("""
                    SELECT * FROM maintenance_alerts
                    WHERE node_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                """, (node_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM maintenance_alerts
                    ORDER BY id DESC
                    LIMIT ?
                """, (limit,))
            rows = cursor.fetchall()
            return [_row_to_alert(r) for r in rows]
        except sqlite3.OperationalError:
            return []


def acknowledge_maintenance_alert(alert_id: str) -> bool:
    """Mark an active alert as ACKNOWLEDGED."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE maintenance_alerts
            SET status = 'ACKNOWLEDGED'
            WHERE alert_id = ?
        """, (alert_id,))
        conn.commit()
        return cursor.rowcount > 0


def resolve_maintenance_alert(alert_id: str, resolved_at: Optional[str] = None) -> bool:
    """Mark an alert as RESOLVED."""
    from datetime import datetime, timezone
    now_iso = resolved_at or datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE maintenance_alerts
            SET status = 'RESOLVED', resolved_at = ?
            WHERE alert_id = ?
        """, (now_iso, alert_id))
        conn.commit()
        return cursor.rowcount > 0


# ═════════════════════════════════════════════════════════════════════════════
# Adaptive Recovery Engine Persistence
# ═════════════════════════════════════════════════════════════════════════════

def get_action_history(node_id: str, incident_type: str, action_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves learned trial history for a specific (node_id, incident_type, action_id)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT node_id, incident_type, action_id, trials, successes,
                   total_recovery_time_sec, last_outcome, last_updated
            FROM recovery_action_history
            WHERE node_id = ? AND incident_type = ? AND action_id = ?
        """, (node_id, incident_type, action_id))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["success_rate"] = round(d["successes"] / max(1, d["trials"]), 4)
        d["avg_recovery_time_sec"] = round(d["total_recovery_time_sec"] / max(1, d["trials"]), 2)
        return d


def get_all_action_history_for_node(node_id: str) -> List[Dict[str, Any]]:
    """Retrieves all action trial records for a specific node."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT node_id, incident_type, action_id, trials, successes,
                   total_recovery_time_sec, last_outcome, last_updated
            FROM recovery_action_history
            WHERE node_id = ?
            ORDER BY incident_type, action_id
        """, (node_id,))
        res = []
        for r in cursor.fetchall():
            d = dict(r)
            d["success_rate"] = round(d["successes"] / max(1, d["trials"]), 4)
            d["avg_recovery_time_sec"] = round(d["total_recovery_time_sec"] / max(1, d["trials"]), 2)
            res.append(d)
        return res


def get_comparable_fleet_action_history(incident_type: str, action_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves aggregated fleet-wide empirical evidence for comparable incidents across all nodes.
    Used when a node has zero personal trials for this incident type.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT SUM(trials) as total_trials, SUM(successes) as total_successes,
                   SUM(total_recovery_time_sec) as total_time, COUNT(DISTINCT node_id) as node_count
            FROM recovery_action_history
            WHERE incident_type = ? AND action_id = ?
        """, (incident_type, action_id))
        row = cursor.fetchone()
        if not row or not row["total_trials"]:
            return None
        return {
            "trials": int(row["total_trials"]),
            "successes": int(row["total_successes"]),
            "avg_recovery_time_sec": round(float(row["total_time"]) / max(1, int(row["total_trials"])), 2),
            "node_count": int(row["node_count"]),
        }


def record_action_outcome(
    node_id: str,
    incident_type: str,
    action_id: str,
    success: bool,
    duration_sec: float,
    **kwargs
) -> None:
    """
    Atomically updates trials, successes, recovery time, and last_outcome for an action.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    outcome_str = "SUCCESS" if success else "FAILURE"
    success_inc = 1 if success else 0

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO recovery_action_history (
                node_id, incident_type, action_id, trials, successes,
                total_recovery_time_sec, last_outcome, last_updated
            )
            VALUES (?, ?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(node_id, incident_type, action_id) DO UPDATE SET
                trials = trials + 1,
                successes = successes + excluded.successes,
                total_recovery_time_sec = total_recovery_time_sec + excluded.total_recovery_time_sec,
                last_outcome = excluded.last_outcome,
                last_updated = excluded.last_updated
        """, (node_id, incident_type, action_id, success_inc, duration_sec, outcome_str, now_iso))
        conn.commit()


def save_recovery_decision(decision_data: Dict[str, Any]) -> None:
    """Persists an evaluated recovery decision and ranking rationale."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO recovery_decisions (
                decision_id, incident_id, node_id, incident_type, severity,
                selected_action, ranking_score, ranking_rationale, candidate_scores_json,
                metrics_before_json, metrics_after_json, execution_status,
                success_measured, recovery_duration_sec, verification_status,
                recovery_criteria_json, verification_details_json, escalated, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            decision_data["decision_id"],
            decision_data["incident_id"],
            decision_data["node_id"],
            decision_data["incident_type"],
            decision_data["severity"],
            decision_data["selected_action"],
            decision_data["ranking_score"],
            decision_data["ranking_rationale"],
            json.dumps(decision_data.get("candidate_rankings", [])),
            json.dumps(decision_data.get("metrics_before", {})),
            json.dumps(decision_data.get("metrics_after", {})),
            decision_data.get("execution_status", "PENDING"),
            1 if decision_data.get("success_measured") is True else (0 if decision_data.get("success_measured") is False else None),
            decision_data.get("recovery_duration_sec"),
            decision_data.get("verification_status", "PENDING"),
            json.dumps(decision_data.get("recovery_criteria") or {}),
            json.dumps(decision_data.get("verification_details") or {}),
            1 if decision_data.get("escalated") else 0,
            decision_data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()


def update_recovery_decision_outcome(
    decision_id: str,
    success: Optional[bool],
    metrics_after: Optional[Dict[str, Any]],
    recovery_duration_sec: float,
    escalated: bool = False,
    verification_status: Optional[str] = None,
    verification_details: Optional[Dict[str, Any]] = None,
) -> None:
    """Updates a decision with the measured execution outcome and verification result."""
    with get_connection() as conn:
        cursor = conn.cursor()
        succ_val = 1 if success is True else (0 if success is False else None)
        exec_status = verification_status or ("COMPLETED" if success is not None else "PENDING")
        cursor.execute("""
            UPDATE recovery_decisions
            SET execution_status = ?,
                success_measured = ?,
                metrics_after_json = ?,
                recovery_duration_sec = ?,
                escalated = ?,
                verification_status = ?,
                verification_details_json = ?
            WHERE decision_id = ?
        """, (
            exec_status,
            succ_val,
            json.dumps(metrics_after or {}),
            recovery_duration_sec,
            1 if escalated else 0,
            verification_status or ("SUCCESS" if success else ("FAILURE" if success is False else "INCONCLUSIVE")),
            json.dumps(verification_details or {}),
            decision_id,
        ))
        conn.commit()


def get_recovery_decisions(
    node_id: Optional[str] = None,
    incident_type: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Retrieves recent recovery decisions with parsed JSON fields."""
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM recovery_decisions"
        params: List[Any] = []
        conditions = []

        if node_id:
            conditions.append("node_id = ?")
            params.append(node_id)
        if incident_type:
            conditions.append("incident_type = ?")
            params.append(incident_type)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try:
                d["candidate_rankings"] = json.loads(d.get("candidate_scores_json") or "[]")
            except Exception:
                d["candidate_rankings"] = []
            try:
                d["metrics_before"] = json.loads(d.get("metrics_before_json") or "{}")
            except Exception:
                d["metrics_before"] = {}
            try:
                d["metrics_after"] = json.loads(d.get("metrics_after_json") or "{}")
            except Exception:
                d["metrics_after"] = {}
            try:
                d["recovery_criteria"] = json.loads(d.get("recovery_criteria_json") or "{}")
            except Exception:
                d["recovery_criteria"] = {}
            try:
                d["verification_details"] = json.loads(d.get("verification_details_json") or "{}")
            except Exception:
                d["verification_details"] = {}
            d["success_measured"] = (d["success_measured"] == 1) if d["success_measured"] is not None else None
            d["escalated"] = (d["escalated"] == 1)
            # Add convenience alias keys
            d["candidate_scores"] = d["candidate_rankings"]
            d["selection_reason"] = d.get("ranking_rationale", "")
            d["selected_action_id"] = d.get("selected_action", "")
            d["outcome_verified"] = bool(d.get("success_measured"))
            d["execution_duration_sec"] = d.get("recovery_duration_sec") or 0.0
            if not d.get("verification_status"):
                d["verification_status"] = "SUCCESS" if d.get("success_measured") == 1 else ("FAILURE" if d.get("success_measured") == 0 else "PENDING")
            
            # Canonical lifecycle status
            v_stat = (d.get("verification_status") or "").upper()
            exec_stat = (d.get("execution_status") or "").upper()
            if v_stat == "SUCCESS":
                d["lifecycle_status"] = "SUCCESSFUL"
            elif v_stat == "FAILURE":
                d["lifecycle_status"] = "FAILED"
            elif v_stat == "INCONCLUSIVE":
                d["lifecycle_status"] = "INCONCLUSIVE"
            elif exec_stat == "EXECUTING":
                d["lifecycle_status"] = "EXECUTING"
            elif exec_stat == "APPROVED":
                d["lifecycle_status"] = "APPROVED"
            else:
                d["lifecycle_status"] = "PROPOSED"

            # Ensure metrics_before and metrics_after exist
            if not d.get("metrics_before"):
                d["metrics_before"] = d.get("recovery_criteria", {}).get("baseline_metrics", {})
            if not d.get("metrics_after") and d.get("verification_details"):
                d["metrics_after"] = d.get("verification_details", {}).get("observed_metrics", {})

            results.append(d)
        return results


def save_recovery_benchmark_result(summary: Dict[str, Any]) -> None:
    """Persists a reproducible evaluation benchmark summary comparing adaptive vs baseline policies."""
    now_iso = summary.get("timestamp") or datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO recovery_policy_benchmarks (
                benchmark_id, timestamp, mode, trial_count, seed,
                adaptive_metrics_json, baseline_metrics_json, deltas_json, episodes_log_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            summary["benchmark_id"],
            now_iso,
            summary.get("mode", "SIMULATED"),
            int(summary.get("trial_count", 0)),
            summary.get("seed"),
            json.dumps(summary.get("adaptive_metrics", {})),
            json.dumps(summary.get("baseline_metrics", {})),
            json.dumps(summary.get("deltas", {})),
            json.dumps(summary.get("episodes_log", [])),
        ))
        conn.commit()


def get_latest_recovery_benchmark(mode: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves the most recent benchmark evaluation run."""
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            if mode:
                cursor.execute("""
                    SELECT * FROM recovery_policy_benchmarks
                    WHERE mode = ?
                    ORDER BY id DESC LIMIT 1
                """, (mode,))
            else:
                cursor.execute("""
                    SELECT * FROM recovery_policy_benchmarks
                    ORDER BY id DESC LIMIT 1
                """)
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            d["adaptive_metrics"] = json.loads(d.get("adaptive_metrics_json") or "{}")
            d["baseline_metrics"] = json.loads(d.get("baseline_metrics_json") or "{}")
            d["deltas"] = json.loads(d.get("deltas_json") or "{}")
            d["episodes_log"] = json.loads(d.get("episodes_log_json") or "[]")
            return d
        except sqlite3.OperationalError:
            return None


def get_all_recovery_benchmarks(limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieves recent benchmark runs."""
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM recovery_policy_benchmarks
                ORDER BY id DESC LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["adaptive_metrics"] = json.loads(d.get("adaptive_metrics_json") or "{}")
                d["baseline_metrics"] = json.loads(d.get("baseline_metrics_json") or "{}")
                d["deltas"] = json.loads(d.get("deltas_json") or "{}")
                d["episodes_log"] = json.loads(d.get("episodes_log_json") or "[]")
                results.append(d)
            return results
        except sqlite3.OperationalError:
            return []

