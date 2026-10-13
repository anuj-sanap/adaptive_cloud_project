"""
cleanup_dummy_nodes.py - Safely remove test fixtures and dummy nodes from telemetry.db.
Creates an automatic backup 'data/telemetry.db.bak_<timestamp>' before pruning.
Retains all genuine machines and production agent records.
"""

import os
import sys
import shutil
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "telemetry.db")

DUMMY_PATTERNS = [
    "api-test-%",
    "test-verify-%",
    "frontend-test-%",
    "node_audit_%",
    "test-node-%",
    "test_node_%",
    "retrain_test_%",
    "drift-test-%",
    "%lifecycle%",
    "%sec_test%",
]

DUMMY_HOSTNAMES = [
    "web-console-host",
    "verify-host",
    "api-node",
    "test-host",
    "sec-test-host",
    "DISCONNECT-NODE",
    "Unknown-Host",
    "rogue_node_agent",
    "dynamic-host-1",
]


def is_dummy(node_id: str, hostname: str = "") -> bool:
    nid = (node_id or "").lower()
    host = (hostname or "").lower()
    
    import re
    for pat in [
        "api-test", "test-verify", "frontend-test", "node_audit", 
        "test-node", "test_node", "retrain_test", "drift-test", 
        "sec_test", "lifecycle", "disco_node", "rogue_node", "dummy", "mock"
    ]:
        if pat in nid:
            return True
            
    if host in [h.lower() for h in DUMMY_HOSTNAMES]:
        return True

    # Check for ephemeral test runs using PID suffixes (e.g. _alpha_36809, _beta_37949)
    if re.search(r"_(alpha|beta)_\d{4,7}$", nid):
        return True
        
    return False


def run_cleanup():
    if not os.path.exists(DB_PATH):
        print(f"[CLEANUP] Database file not found at {DB_PATH}")
        return

    # 1. Create a timestamped backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_path = f"{DB_PATH}.bak_{ts}"
    shutil.copy2(DB_PATH, bak_path)
    print(f"[CLEANUP] Created backup at: {bak_path}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 2. Find all dummy node_ids
    cursor.execute("SELECT node_id, hostname FROM nodes")
    all_nodes = cursor.fetchall()
    
    dummy_ids = [nid for nid, host in all_nodes if is_dummy(nid, host)]
    genuine_nodes = [(nid, host) for nid, host in all_nodes if not is_dummy(nid, host)]

    print(f"[CLEANUP] Found {len(all_nodes)} total nodes: {len(dummy_ids)} dummy/test, {len(genuine_nodes)} genuine.")

    if not dummy_ids:
        print("[CLEANUP] No dummy nodes to delete.")
        conn.close()
        return

    # 3. Clean related tables
    placeholders = ",".join("?" for _ in dummy_ids)
    
    tables_to_prune = [
        ("telemetry", "node_id"),
        ("maintenance_alerts", "node_id"),
        ("recovery_decisions", "node_id"),
        ("recovery_action_history", "node_id"),
        ("node_security_predictions", "node_id"),
        ("live_health_predictions", "node_id"),
        ("drift_reference_samples", "node_id"),
        ("live_drift_results", "node_id"),
        ("adaptive_retraining_runs", "node_id"),
        ("closed_loop_experiments", "node_id"),
        ("node_credentials", "node_id"),
        ("nodes", "node_id"),
    ]

    for table, col in tables_to_prune:
        try:
            cursor.execute(f"DELETE FROM {table} WHERE {col} IN ({placeholders})", dummy_ids)
            print(f"  -> Deleted {cursor.rowcount} rows from {table}")
        except sqlite3.OperationalError as e:
            # Table might not exist or column different
            pass

    conn.commit()
    cursor.execute("VACUUM")
    conn.commit()
    conn.close()

    print("\n[CLEANUP] Prune complete! Remaining Genuine Devices:")
    for nid, host in genuine_nodes:
        print(f"  - Node ID: {nid} (Hostname: {host})")


if __name__ == "__main__":
    run_cleanup()
