"""
main.py - Entry point launcher for Central Telemetry REST API server.
Runs Uvicorn ASGI web server on configured host and port.
"""

import os
import sys
import argparse
import uvicorn

# Path setup to ensure imports work cleanly when executed directly
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(SERVER_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from central_server.database import init_db


def main():
    default_port = int(os.getenv("PORT") or os.getenv("SERVER_PORT", "8000"))
    parser = argparse.ArgumentParser(description="Central Telemetry REST API Server")
    parser.add_argument("--host", type=str, default=os.getenv("SERVER_HOST", "0.0.0.0"), help="Host IP to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=default_port, help=f"Port to listen on (default: {default_port})")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload on code change")
    args = parser.parse_args()

    # Pre-initialize database schema
    init_db()

    print("=" * 65)
    print("[SERVER STARTING] CENTRAL TELEMETRY REST API SERVER")
    print(f"  • Listening on : http://{args.host}:{args.port}")
    print(f"  • API Docs     : http://localhost:{args.port}/docs")
    print(f"  • Telemetry Url: http://localhost:{args.port}/telemetry")
    print("=" * 65)

    uvicorn.run(
        "central_server.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
