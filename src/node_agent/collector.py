"""
collector.py - Main execution loop for the Live Node Monitoring Agent.

Full workflow:
  1. Generate (or load) a persistent unique node_id.
  2. Register with the central server — retries with exponential back-off until
     the server is reachable.
  3. Launch a background heartbeat thread that fires every HEARTBEAT_INTERVAL_SEC.
  4. Enter the main telemetry loop:
       - Collect live system metrics.
       - POST to /telemetry.
       - If the POST fails, queue the snapshot and retry on the next tick.
       - If registration is lost (server restarted), re-register transparently.
  5. Handles KeyboardInterrupt cleanly.

CLI flags:
  --server-url  Override the central server base URL.
  --interval    Override telemetry collection interval (seconds).
  --heartbeat   Override heartbeat interval (seconds).
  --no-post     Dry-run mode: collect and print but do not POST.
  --node-suffix Append a custom suffix to the auto-generated node_id
                (useful for simulating multiple agents on the same machine).
"""

import os
import sys
import time
import threading
import argparse

# ── Path bootstrap ────────────────────────────────────────────────────────────
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR   = os.path.dirname(AGENT_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)
# ─────────────────────────────────────────────────────────────────────────────

import psutil

try:
    from node_agent.config import (
        TELEMETRY_INTERVAL_SEC,
        HEARTBEAT_INTERVAL_SEC,
        ENABLE_HTTP_POST,
        SERVER_BASE_URL,
        NODE_API_KEY,
    )
    from node_agent.id_generator import get_or_create_node_id
    from node_agent.metrics      import collect_node_telemetry
    from node_agent.server_client import (
        register_with_retry,
        send_telemetry,
        send_telemetry_with_response,
        send_heartbeat,
        fetch_node_alert,
        buffer_telemetry,
        get_buffered_count,
        flush_buffered_telemetry,
    )
    from node_agent.notifier import NodeAlertNotifier
except ImportError:
    from config import (
        TELEMETRY_INTERVAL_SEC,
        HEARTBEAT_INTERVAL_SEC,
        ENABLE_HTTP_POST,
        SERVER_BASE_URL,
        NODE_API_KEY,
    )
    from id_generator import get_or_create_node_id
    from metrics      import collect_node_telemetry
    from server_client import (
        register_with_retry,
        send_telemetry,
        send_telemetry_with_response,
        send_heartbeat,
        fetch_node_alert,
        buffer_telemetry,
        get_buffered_count,
        flush_buffered_telemetry,
    )
    from notifier import NodeAlertNotifier


# ─────────────────────────────────────────────────────────────────────────────
# Heartbeat thread
# ─────────────────────────────────────────────────────────────────────────────

class HeartbeatThread(threading.Thread):
    """
    Sends a lightweight heartbeat to the server every *interval_sec* seconds.
    Runs as a daemon so it dies when the main process exits.
    """

    def __init__(self, node_id: str, interval_sec: int, enable_post: bool):
        super().__init__(daemon=True, name=f"heartbeat-{node_id[:12]}")
        self.node_id      = node_id
        self.interval_sec = interval_sec
        self.enable_post  = enable_post
        self._stop_event  = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        # Stagger first beat so it doesn't collide with initial registration.
        time.sleep(self.interval_sec)
        while not self._stop_event.is_set():
            if self.enable_post:
                ok = send_heartbeat(self.node_id)
                status = "[OK]" if ok else "[WARN - server unreachable]"
                print(f"  [HEARTBEAT] {self.node_id} -> {status}")
            self._stop_event.wait(timeout=self.interval_sec)


# ─────────────────────────────────────────────────────────────────────────────
# Main agent loop
# ─────────────────────────────────────────────────────────────────────────────

def run_agent(
    server_base_url: str  = SERVER_BASE_URL,
    interval_sec: int     = TELEMETRY_INTERVAL_SEC,
    heartbeat_sec: int    = HEARTBEAT_INTERVAL_SEC,
    enable_post: bool     = ENABLE_HTTP_POST,
    node_suffix: str      = "",
    api_key: str          = None,
):
    """
    Full agent lifecycle:
      register → heartbeat thread → telemetry loop (with reconnect & offline buffering on failure)
    """

    # ── 1. Persistent node identity ──────────────────────────────────────────
    node_id = get_or_create_node_id(suffix=node_suffix)

    # Patch config URLs if a custom base URL was provided via CLI
    if server_base_url != SERVER_BASE_URL:
        for mod_name in ["node_agent.config", "config"]:
            if mod_name in sys.modules:
                mod = sys.modules[mod_name]
                mod.SERVER_BASE_URL     = server_base_url
                mod.REGISTER_URL        = f"{server_base_url}/register"
                mod.TELEMETRY_URL       = f"{server_base_url}/telemetry"
                mod.BATCH_TELEMETRY_URL = f"{server_base_url}/telemetry/batch"
                mod.HEARTBEAT_URL       = f"{server_base_url}/heartbeat"
        for mod_name in ["node_agent.server_client", "server_client"]:
            if mod_name in sys.modules:
                mod = sys.modules[mod_name]
                mod.REGISTER_URL        = f"{server_base_url}/register"
                mod.TELEMETRY_URL       = f"{server_base_url}/telemetry"
                mod.BATCH_TELEMETRY_URL = f"{server_base_url}/telemetry/batch"
                mod.HEARTBEAT_URL       = f"{server_base_url}/heartbeat"

    # Patch API key if explicitly provided via CLI
    if api_key:
        for mod_name in ["node_agent.config", "config", "node_agent.server_client", "server_client"]:
            if mod_name in sys.modules:
                mod = sys.modules[mod_name]
                mod.NODE_API_KEY = api_key

    # Retrieve active key for logging
    active_key = api_key or os.getenv("NODE_API_KEY") or getattr(sys.modules.get("node_agent.config", None), "NODE_API_KEY", "")
    key_display = f"Configured ({active_key[:4]}...)" if active_key else "None / Unauthenticated"

    print("=" * 65)
    print("[NODE AGENT] LIVE NODE MONITORING AGENT STARTING")
    print(f"  Node ID      : {node_id}")
    print(f"  Server       : {server_base_url}")
    print(f"  Auth API Key : {key_display}")
    print(f"  Telemetry    : every {interval_sec}s")
    print(f"  Heartbeat    : every {heartbeat_sec}s")
    print(f"  HTTP POST    : {'ENABLED' if enable_post else 'DISABLED (dry-run)'}")
    print("=" * 65)

    # ── 2. Register with central server (blocks until server is up) ──────────
    if enable_post:
        register_with_retry(node_id)

    # ── 3. Start background heartbeat thread ─────────────────────────────────
    hb_thread = HeartbeatThread(node_id, heartbeat_sec, enable_post)
    hb_thread.start()

    # Warm up CPU percent baseline
    psutil.cpu_percent(interval=None)
    time.sleep(0.5)

    # ── 4. Telemetry loop ────────────────────────────────────────────────────
    notifier = NodeAlertNotifier(node_id)
    consecutive_failures = 0
    MAX_FAILURES_BEFORE_REREGISTER = 3
    tick = 0

    try:
        while True:
            tick += 1
            payload = collect_node_telemetry(node_id)
            m = payload["metrics"]

            print(f"\n[TICK #{tick}] {payload['timestamp']}  node={node_id}")
            print(f"  CPU: {m['cpu_utilization']}%  "
                  f"RAM: {m['ram_utilization']}% ({m['ram_used_mb']}/{m['ram_total_mb']} MB)  "
                  f"Disk: {m['disk_utilization']}%")
            print(f"  Net Sent: {m['network_sent_mb']} MB  "
                  f"Net Recv: {m['network_recv_mb']} MB  "
                  f"Processes: {m['process_count']}")
            if m["cpu_temperature_c"] is not None:
                print(f"  CPU Temp : {m['cpu_temperature_c']} deg C")

            if enable_post:
                ok, resp = send_telemetry_with_response(payload)
                if ok:
                    print("  Telemetry : sent [OK]")
                    consecutive_failures = 0

                    # Flush any snapshots that were buffered while disconnected
                    buffered_count = get_buffered_count()
                    if buffered_count > 0:
                        print(f"  [RECONNECTED] Flushing {buffered_count} buffered snapshot(s) ...")
                        flush_buffered_telemetry(node_id)

                    # ── Process Server-Side Predictive Maintenance Alert ──
                    alert_data = resp.get("alert") if isinstance(resp, dict) else None
                    notifier.process_server_alert(alert_data)
                else:
                    consecutive_failures += 1
                    buffered_now = buffer_telemetry(payload)
                    print(f"  Telemetry : FAILED (consecutive={consecutive_failures}, offline_buffered={buffered_now})")

                    # After N consecutive failures, attempt non-blocking re-registration
                    if consecutive_failures >= MAX_FAILURES_BEFORE_REREGISTER:
                        print(f"[RECONNECT] {MAX_FAILURES_BEFORE_REREGISTER} consecutive failures."
                              " Attempting to re-register with server ...")
                        re_ok = register_with_retry(node_id, max_attempts=2)
                        if re_ok:
                            consecutive_failures = 0
                            print("[RECONNECT] Re-registered successfully. Resuming normal telemetry.")

            time.sleep(interval_sec)

    except KeyboardInterrupt:
        print("\n[NODE AGENT] Stopped by user (Ctrl+C).")
    finally:
        hb_thread.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Live Node Monitoring Agent - connects to Central Telemetry API"
    )
    parser.add_argument(
        "--server-url", type=str, default=SERVER_BASE_URL,
        help=f"Central server base URL (default: {SERVER_BASE_URL})"
    )
    parser.add_argument(
        "--server-ip", type=str, default=None,
        help="Central server IP address (e.g. 10.175.163.77), port defaults to 8000"
    )
    parser.add_argument(
        "--api-key", type=str, default=None,
        help="Cluster API Key for authenticating with the Central Server"
    )
    parser.add_argument(
        "--interval", type=int, default=TELEMETRY_INTERVAL_SEC,
        help=f"Telemetry interval in seconds (default: {TELEMETRY_INTERVAL_SEC})"
    )
    parser.add_argument(
        "--heartbeat", type=int, default=HEARTBEAT_INTERVAL_SEC,
        help=f"Heartbeat interval in seconds (default: {HEARTBEAT_INTERVAL_SEC})"
    )
    parser.add_argument(
        "--no-post", action="store_true",
        help="Dry-run: collect metrics but do not POST to server"
    )
    parser.add_argument(
        "--node-suffix", type=str, default="",
        help="Append a suffix to node_id (use to simulate multiple agents on one machine)"
    )
    args = parser.parse_args()

    # If --server-ip is provided, format it into full URL
    target_server_url = args.server_url
    if args.server_ip:
        ip = args.server_ip.strip()
        if not ip.startswith("http://") and not ip.startswith("https://"):
            target_server_url = f"http://{ip}:8000" if ":" not in ip else f"http://{ip}"
        else:
            target_server_url = ip

    run_agent(
        server_base_url=target_server_url,
        interval_sec=args.interval,
        heartbeat_sec=args.heartbeat,
        enable_post=not args.no_post,
        node_suffix=args.node_suffix,
        api_key=args.api_key,
    )


if __name__ == "__main__":
    main()
