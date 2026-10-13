"""
run_agent_azure.py - Helper launcher to connect an edge Node Agent to the Azure deployment.

Usage:
    python scripts/run_agent_azure.py --server-url https://<your-backend-app>.azurewebsites.net --api-key <cluster-secret>

Or set environment variables:
    $env:NODE_SERVER_URL="https://<your-backend-app>.azurewebsites.net"
    $env:NODE_API_KEY="<cluster-secret>"
    python scripts/run_agent_azure.py
"""

import os
import sys
import json
import urllib.request
import urllib.error
import ssl
import argparse

# Setup path so node_agent package can be imported
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from node_agent.collector import run_agent
from node_agent.config import NODE_SSL_VERIFY


def test_azure_health(server_url: str) -> dict:
    """Pre-flight check to verify Azure backend reachability and health status."""
    health_url = f"{server_url.rstrip('/')}/health"
    print(f"[PRE-FLIGHT] Testing reachability of Azure backend at: {health_url}")
    
    context = ssl.create_default_context()
    if not NODE_SSL_VERIFY:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
    req = urllib.request.Request(
        health_url,
        headers={"User-Agent": "LiveNodeAgent-Preflight/2.0"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10.0, context=context) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"  ✓ Connected successfully! HTTP {resp.status}")
            print(f"  ✓ Service   : {data.get('service')}")
            print(f"  ✓ Status    : {data.get('status')}")
            print(f"  ✓ Database  : {data.get('database')}")
            print(f"  ✓ Auth Reqd : {data.get('auth_required')}")
            return data
    except urllib.error.HTTPError as e:
        print(f"  ✗ Server returned HTTP {e.code}: {e.reason}")
        raise
    except urllib.error.URLError as e:
        print(f"  ✗ Cannot connect to Azure endpoint: {e.reason}")
        print("    Ensure the URL is correct, includes 'https://', and the Azure App Service is running.")
        raise


def main():
    parser = argparse.ArgumentParser(description="Connect Node Agent to Deployed Azure Central Telemetry API")
    parser.add_argument(
        "--server-url",
        type=str,
        default=os.getenv("NODE_SERVER_URL"),
        help="Azure Backend URL (e.g. https://<app-name>.azurewebsites.net)"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("NODE_API_KEY") or os.getenv("ADAPTIVE_CLOUD_API_KEY"),
        help="Shared Cluster API Secret Key"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.getenv("NODE_TELEMETRY_INTERVAL", "5")),
        help="Telemetry interval in seconds (default: 5)"
    )
    parser.add_argument(
        "--heartbeat",
        type=int,
        default=int(os.getenv("NODE_HEARTBEAT_INTERVAL", "15")),
        help="Heartbeat interval in seconds (default: 15)"
    )
    parser.add_argument(
        "--node-suffix",
        type=str,
        default="",
        help="Custom suffix for node ID (e.g. laptop-alpha, campus-lab-1)"
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip pre-flight /health probe check"
    )
    args = parser.parse_args()

    server_url = args.server_url
    if not server_url:
        print("=" * 70)
        print("ERROR: Missing --server-url or NODE_SERVER_URL environment variable.")
        print("=" * 70)
        print("Example usage:")
        print("  python scripts/run_agent_azure.py \\")
        print("    --server-url https://adaptive-backend.azurewebsites.net \\")
        print("    --api-key your-cluster-secret")
        print("=" * 70)
        sys.exit(1)

    if not server_url.startswith("https://") and not server_url.startswith("http://"):
        server_url = f"https://{server_url}"

    print("=" * 70)
    print("ADAPTIVE CLOUD RESILIENCE: AZURE NODE MONITORING AGENT")
    print(f"  Target Server : {server_url}")
    print(f"  Auth Key      : {'[CONFIGURED]' if args.api_key else '[NONE / PUBLIC]'}")
    print(f"  Interval      : {args.interval}s (Telemetry), {args.heartbeat}s (Heartbeat)")
    print("=" * 70)

    if not args.skip_preflight:
        try:
            test_azure_health(server_url)
        except Exception:
            print("\n[WARNING] Pre-flight health check failed. Agent will still attempt retry loop.")

    print("\n[STARTING AGENT] Launching metric collection and heartbeat background workers...")
    run_agent(
        server_base_url=server_url,
        interval_sec=args.interval,
        heartbeat_sec=args.heartbeat,
        enable_post=True,
        node_suffix=args.node_suffix,
        api_key=args.api_key
    )


if __name__ == "__main__":
    main()
