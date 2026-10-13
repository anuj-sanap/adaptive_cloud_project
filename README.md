# Adaptive Learning for Cloud Security, Predictive Maintenance & Closed-Loop Autonomous Recovery

An end-to-end, enterprise-grade cloud resilience system integrating **UNSW-NB15 Cyber Threat Detection**, **Alibaba Cluster Trace 2017 Predictive Maintenance**, **Kolmogorov-Smirnov Concept Drift Detection & Retraining**, **Real-Time Secure Multi-Node Telemetry Ingestion**, **Closed-Loop Recovery Verification**, and an **Adaptive Recovery Decision Engine** with a 5-tab **Streamlit Control Center & Recovery Decision Lab**.

---

## 🎯 Executive Overview

Modern cloud distributed environments face dual operational hazards: **cybersecurity network intrusions** and **server infrastructure hardware failures**. Traditional cloud monitoring systems operate in static operational silos:
- Static machine learning models degrade rapidly when underlying data distributions shift (concept drift).
- Fixed-rule runbooks execute rigid recovery actions regardless of whether the action succeeded in the past or degraded system performance.
- Telemetry monitoring is disconnected from closed-loop automated recovery verification.

This project delivers an **Adaptive Cloud Resilience Framework** that solves these challenges end-to-end:
1. **Cloud Security Threat Detection (UNSW-NB15 Dataset)**: Detects cyber intrusions with up to **98.50% Accuracy** and **0.9991 ROC-AUC** across binary and multiclass attack vectors.
2. **Cloud Predictive Maintenance (Alibaba Cluster Trace 2017)**: Predicts server hardware and node failure events with up to **91.33% Accuracy** and **0.9591 ROC-AUC** using real cloud traces.
3. **Adaptive Concept Drift Detection & Dynamic Retraining**: Continuously monitors streaming distributions with the **Kolmogorov-Smirnov (KS) 2-Sample Test**, triggering automated retraining upon environmental shifts.
4. **Secure Real-Time Multi-Node Telemetry (FastAPI + SQLite WAL)**: Edge node agents collect live hardware telemetry (CPU, RAM, Disk, IO, Network) and transmit it securely to a centralized server over authenticated HTTP(S) with buffered offline fallback.
5. **Closed-Loop Recovery Verification Engine**: Pre-defines measurable success criteria before executing an action, gathers fresh post-action metrics within a strict time window, and categorizes outcomes into `SUCCESS`, `FAILURE`, `TIMEOUT`, and `INCONCLUSIVE`.
6. **Adaptive Recovery Decision Engine**: Utilizes a Bayesian multi-factor scoring policy (success history, recovery latency, resource overhead, operational risk) to rank candidate actions, updating dynamic scores only from verified outcomes.
7. **Interactive Command Center & Recovery Decision Lab**: A 5-tab Streamlit dashboard providing fleet-wide health monitoring, per-node telemetry graphs, real-time alert dispatching, live adaptive recovery execution, and reproducible benchmarks against fixed-rule baselines.

---

## 🏗️ System Architecture & Data Flow

```
   ┌─────────────────────────────────────────────────────────────────────────────────┐
   │                          DISTRIBUTED EDGE NODES / LAPTOPS                       │
   │  ┌───────────────────────────────┐     ┌─────────────────────────────────────┐  │
   │  │   Node Agent: "node-alpha"    │     │      Node Agent: "node-beta"        │  │
   │  │   - Hardware Fingerprint ID   │     │      - Hardware Fingerprint ID      │  │
   │  │   - Live psutil Telemetry     │     │      - Live psutil Telemetry        │  │
   │  │   - Buffered In-Memory Spool  │     │      - Buffered In-Memory Spool     │  │
   │  └───────────────┬───────────────┘     └──────────────────┬──────────────────┘  │
   └──────────────────┼────────────────────────────────────────┼─────────────────────┘
                      │ (Authenticated JSON Telemetry)          │
                      │ Bearer / X-API-Key (HMAC Cluster Key)  │
                      ▼                                        ▼
   ┌─────────────────────────────────────────────────────────────────────────────────┐
   │                    CENTRAL FASTAPI SERVER (api.py / port 8000)                  │
   │  ┌───────────────────────────────────────────────────────────────────────────┐  │
   │  │ Authentication & Authorization Guard (/register, /telemetry, /heartbeat)  │  │
   │  ├───────────────────────────────────────────────────────────────────────────┤  │
   │  │ Persistent SQLite Database with Write-Ahead Logging (WAL)                 │  │
   │  │ - nodes, telemetry, alerts, recovery_decisions, recovery_action_history  │  │
   │  └─────────────────────────────────────┬─────────────────────────────────────┘  │
   └────────────────────────────────────────┼────────────────────────────────────────┘
                                            │
               ┌────────────────────────────┼────────────────────────────┐
               ▼                            ▼                            ▼
   ┌───────────────────────┐    ┌───────────────────────┐    ┌───────────────────────┐
   │  MACHINE LEARNING     │    │     ADAPTIVE DRIFT    │    │ CLOSED-LOOP RECOVERY  │
   │  PREDICTION ENGINES   │    │      KS DETECTOR      │    │    DECISION ENGINE    │
   │  - Security Engine    │    │  - 2-Sample KS Test   │    │  - Candidate Ranking  │
   │    (UNSW-NB15 RF/XGB) │    │  - Automated Pipeline │    │  - Pre-Action Criteria│
   │  - Maintenance Engine │    │    Retraining Trigger │    │  - Action Handlers    │
   │    (Alibaba 2017 RF)  │    └───────────────────────┘    │  - Post-Verification  │
   │  - Isolation Forest   │                                 │  - Bayesian Updates   │
   │  - Weighted Fusion    │                                 └───────────┬───────────┘
   └───────────┬───────────┘                                             │
               │                                                         │
               └────────────────────────────┬────────────────────────────┘
                                            ▼
   ┌─────────────────────────────────────────────────────────────────────────────────┐
   │                   STREAMLIT 5-TAB FLEET COMMAND CENTER & LAB                    │
   │  [Tab 1: Fleet Overview]  [Tab 2: Security]  [Tab 3: Maintenance]              │
   │  [Tab 4: Adaptive Drift]  [Tab 5: Recovery Decision Lab (Live Benchmarking)]   │
   └─────────────────────────────────────────────────────────────────────────────────┘
```

---

## ⚡ Quick Start: Exact Windows Setup Commands

Follow these exact steps in **PowerShell** or **Command Prompt** on Windows 10/11.

### 1. Prerequisites
- **Python 3.10, 3.11, 3.12, or 3.13** installed and added to your Windows PATH.
- Administrative or developer permissions to run PowerShell scripts.

### 2. Clone and Navigate to Directory
```powershell
cd d:\proejctom\adaptive_cloud_project
```

### 3. Create and Activate Virtual Environment
In **PowerShell**:
```powershell
# If script execution is disabled on your machine, enable it for this process:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Create virtual environment:
python -m venv .venv

# Activate virtual environment:
.\.venv\Scripts\Activate.ps1
```
*(If using classic **Command Prompt (cmd.exe)**: run `.\.venv\Scripts\activate.bat` instead)*

### 4. Upgrade Pip and Install Dependencies
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Run the Automated Master End-to-End Audit
Verify that all 10 core audit points pass cleanly on your environment:
```powershell
python scripts/audit_end_to_end.py
```
*Expected output:* `ALL 10 END-TO-END AUDIT VERIFICATION POINTS PASSED!`

---

## ⚙️ Environment Variables Reference

All components support configuration via environment variables or a `.env` file in the project root (see `.env.example`).

| Variable Name | Default Value | Component | Description |
|---|---|---|---|
| `SERVER_HOST` | `0.0.0.0` | Central Server | IP address to bind FastAPI server (`0.0.0.0` enables LAN/WAN access). |
| `SERVER_PORT` | `8000` | Central Server | TCP port for FastAPI API service. |
| `SERVER_API_KEY` or `CLUSTER_API_KEY` | Auto-generated in `data/.api_key` | Central Server & Agent | Shared cluster secret key for HMAC/Bearer token authentication. |
| `TELEMETRY_DB_PATH` | `data/telemetry.db` | Central Server | Relative or absolute path to persistent SQLite database file. |
| `NODE_OFFLINE_THRESHOLD_SEC` | `30` | Central Server | Maximum seconds since last contact before marking a node `OFFLINE`. |
| `NODE_SERVER_URL` | `http://localhost:8000` | Node Agent | HTTP(S) endpoint URL of the central FastAPI server. |
| `NODE_API_KEY` | Reads `data/.api_key` | Node Agent | Cluster authentication key (must match server's API key). |
| `NODE_TELEMETRY_INTERVAL` | `5` | Node Agent | Interval in seconds between hardware telemetry reports. |
| `NODE_HEARTBEAT_INTERVAL` | `15` | Node Agent | Interval in seconds between lightweight node heartbeat pings. |
| `NODE_HTTP_TIMEOUT` | `10.0` | Node Agent | Timeout in seconds for HTTP requests before spooling locally. |
| `NODE_BUFFER_MAX` | `120` | Node Agent | Maximum telemetry snapshots spooled in RAM during network drops. |
| `NODE_SSL_VERIFY` | `true` | Node Agent | Whether to verify SSL certificates on HTTPS endpoints. |

---

## 🖥️ Two-Node Demonstration Procedure (4-Terminal Windows Workflow)

To conduct a live demonstration showing two distinct node agents streaming live telemetry to the central server and interacting with the Streamlit dashboard:

### Terminal 1: Launch FastAPI Central Server
Open PowerShell Terminal 1:
```powershell
cd d:\proejctom\adaptive_cloud_project
.\.venv\Scripts\Activate.ps1
python src/central_server/api.py
```
*Verification:* Terminal displays `Starting Adaptive Cloud Central Server on 0.0.0.0:8000...` and Uvicorn begins serving requests.

---

### Terminal 2: Launch Node Agent 1 ("Alpha")
Open PowerShell Terminal 2:
```powershell
cd d:\proejctom\adaptive_cloud_project
.\.venv\Scripts\Activate.ps1
python -m src.node_agent.collector --server-url http://localhost:8000 --node-suffix alpha --interval 3 --heartbeat 10
```
*Verification:* Agent generates unique ID `node_<hostname>_<hash>_alpha`, successfully registers with HTTP 200, and logs periodic telemetry transmissions.

---

### Terminal 3: Launch Node Agent 2 ("Beta")
Open PowerShell Terminal 3:
```powershell
cd d:\proejctom\adaptive_cloud_project
.\.venv\Scripts\Activate.ps1
python -m src.node_agent.collector --server-url http://localhost:8000 --node-suffix beta --interval 3 --heartbeat 10
```
*Verification:* Agent generates unique ID `node_<hostname>_<hash>_beta`, registers independently, and streams separate hardware telemetry.

---

### Terminal 4: Launch Streamlit Fleet & Recovery Lab Dashboard
Open PowerShell Terminal 4:
```powershell
cd d:\proejctom\adaptive_cloud_project
.\.venv\Scripts\Activate.ps1
python -m streamlit run app/dashboard.py
```
*Access:* Automatically opens `http://localhost:8501` in your default browser.

#### Alternative: Launch React + TypeScript Frontend (Vite)
Open PowerShell in `frontend/`:
```powershell
cd d:\proejctom\adaptive_cloud_project\frontend
npm run dev
```
*Access:* Opens `http://localhost:5173` in your default browser.

#### What to Demonstrate in the Dashboard:
1. **Fleet Status Banner (Sidebar)**: Observe total active nodes, online status indicators, and telemetry freshness.
2. **Tab 1 (Fleet Overview)**:
   - Toggle the **Node Selector** between *Fleet Overview*, *Node Alpha*, and *Node Beta*.
   - Point out live CPU, RAM, Disk utilization, and real-time historical time-series graphs.
3. **Tab 2 & 3 (Security & Predictive Maintenance)**:
   - Demonstrate the UNSW-NB15 attack classifier and Alibaba failure predictor identifying stress conditions.
4. **Tab 4 (Adaptive Drift Detection)**:
   - Show KS 2-Sample Test detecting concept drift and initiating model retraining.
5. **Tab 5 (Recovery Decision Lab)**:
   - Select an incident type (e.g. `HIGH_CPU_LOAD` or `MEMORY_LEAK_WARNING`).
   - Click **Run Adaptive Recovery Evaluation**: Show candidate action ranking, before-and-after metric verification, and dynamic Bayesian policy weight updates.
   - Run the **Reproducible Policy Benchmark**: Compare the Adaptive Policy against the Fixed-Rule Baseline across identical trials with measurable MTTR and success rates.

---

## 🔒 Deployment Requirements & Production Guidelines

### Operating Environment
- **Development & Demonstration**: Windows 10/11 or Linux Ubuntu 22.04 LTS running Python 3.10–3.13.
- **Production Server**: 2+ vCPUs, 4GB+ RAM, 20GB SSD storage.

### Concurrency & Database Architecture
- **SQLite Write-Ahead Logging (WAL)**: The central server automatically enables SQLite WAL mode (`PRAGMA journal_mode=WAL;`), allowing concurrent read queries while telemetry writes proceed. A built-in exponential backoff retry handler (`MAX_RETRIES=5`, `BASE_DELAY=0.05s`) ensures zero write collisions under multi-process load.
- **Enterprise Scale Transition**: For large-scale distributed deployments exceeding 500+ concurrent edge nodes, migrate SQLite to **PostgreSQL with TimescaleDB extension** by swapping the database driver in `src/central_server/database.py`.

### Process Management
- In production, manage the FastAPI service via Uvicorn with multiple workers behind **Gunicorn** on Linux or as a managed **Windows Service** (using NSSM or Task Scheduler).

### Secure Internet / WAN Reachability
- To connect laptops across separate external networks or over the internet:
  1. **HTTPS Reverse Proxy**: Terminate TLS at **Nginx** or **Caddy** with a valid Let's Encrypt SSL certificate, proxying traffic to `http://127.0.0.1:8000`.
  2. **Zero-Trust Tunnels (Cloudflare Tunnel / ngrok)**: Run `cloudflared tunnel` or `ngrok http 8000` on the central host to obtain an encrypted public HTTPS endpoint without port-forwarding your router firewall. Set `NODE_SERVER_URL=https://your-tunnel.domain.com` on edge laptops.
  3. **Cluster API Key Enforcement**: Always distribute the cluster API secret via `NODE_API_KEY` environment variables. The server rejects unauthenticated requests with HTTP 401.

---

## ⚠️ Architectural Boundaries & Limitations

To ensure strict scientific and engineering rigor, the project's boundaries are explicitly documented:

1. **Host-Level OS Telemetry vs. Raw Packet Capture**:
   - The edge node agent gathers real-time host hardware metrics (CPU, RAM, Disk, IO, Network bytes sent/received) via `psutil`.
   - The UNSW-NB15 cyber threat engine operates on high-dimensional network flow features (e.g., `sbytes`, `dbytes`, `sttl`, `sloss`). In live agent deployments, flow features are either streamed from host packet analyzers or evaluated via standard benchmark simulation profiles.
2. **Database Concurrency Scope**:
   - SQLite WAL is optimized for single-host, high-throughput edge telemetry. It is not a distributed multi-region database. Distributed high-availability clustering requires an external distributed database (e.g., PostgreSQL).
3. **Verification Scope Disclosure**:
   - Multi-node testing and agent communication were verified on **distinct local operating system processes** with hardware fingerprinting, unique process namespaces, isolated local identity stores, and simulated network disconnects.
   - Remote cross-region WAN deployment was not executed and is not claimed.

---

## 🛠️ Troubleshooting Guide

### 1. Port 8000 Already in Use (`[Errno 10048] address already in use`)
- **Cause**: A previous instance of the FastAPI server or Uvicorn is still running in the background.
- **Fix (PowerShell)**:
  ```powershell
  Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess | Stop-Process -Force
  ```
- **Alternative**: Start the server on an alternative port:
  ```powershell
  python -m uvicorn src.central_server.api:app --host 0.0.0.0 --port 8080
  ```

### 2. HTTP 401 Unauthorized (`Cluster API Key missing or invalid`)
- **Cause**: Node agent `NODE_API_KEY` does not match the server's `SERVER_API_KEY`.
- **Fix**: The central server auto-saves its active key to `data/.api_key` on startup. Ensure edge agents read this file or set the environment variable:
  ```powershell
  $env:NODE_API_KEY = (Get-Content data\.api_key).Trim()
  ```

### 3. SQLite Database Locked (`sqlite3.OperationalError: database is locked`)
- **Cause**: A long-running external process or SQLite browser opened the database in exclusive lock mode.
- **Fix**: Ensure SQLite WAL mode is active (enabled by default) and close external GUI viewers like DB Browser for SQLite.

### 4. Node Status Shows "OFFLINE" in Streamlit Dashboard
- **Cause**: Node agent has not reported telemetry or a heartbeat within `NODE_OFFLINE_THRESHOLD_SEC` (default: 30 seconds).
- **Fix**: Verify the agent terminal is running and transmitting. If the node is on a slow network, increase the threshold:
  ```powershell
  $env:NODE_OFFLINE_THRESHOLD_SEC = "60"
  ```

### 5. PowerShell Script Execution Disabled Error
- **Cause**: Windows default execution policy prevents running unsigned activation scripts.
- **Fix**: Run PowerShell with process-level bypass:
  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  ```

---

## 🧪 Comprehensive Test & Audit Suite

Execute the automated test suites to verify each layer of the project:

| Test Script | Purpose | Execution Command |
|---|---|---|
| `scripts/audit_end_to_end.py` | **Master Audit Suite** verifying all 10 core audit points | `python scripts/audit_end_to_end.py` |
| `scripts/test_secure_multi_node.py` | Multi-node registration, auth rejection, & telemetry isolation | `python scripts/test_secure_multi_node.py` |
| `scripts/test_adaptive_recovery_engine.py` | Adaptive Bayesian scoring & action selection logic | `python scripts/test_adaptive_recovery_engine.py` |
| `scripts/test_closed_loop_verification.py` | Success, failure, timeout, & inconclusive verification | `python scripts/test_closed_loop_verification.py` |
| `scripts/test_recovery_decision_lab.py` | Recovery Decision Lab UI data structures & API feeds | `python scripts/test_recovery_decision_lab.py` |
| `scripts/test_recovery_policy_benchmark.py` | Reproducible benchmark comparing adaptive vs fixed rules | `python scripts/test_recovery_policy_benchmark.py` |
| `scripts/run_all_models.py` | Full ML training, testing, and drift evaluation pipeline | `python scripts/run_all_models.py` |
| `scripts/verify_azure_deployment.py` | **Azure Cloud Verification Suite** testing live HTTPS, CORS, persistence & agents | `python scripts/verify_azure_deployment.py --frontend-url <url> --backend-url <url>` |

---

## ☁️ Microsoft Azure Production Deployment

The project is fully prepared for real **Microsoft Azure** deployment using cost-conscious, free and entry-level tiers ($0.00 – $13.00/mo) suitable for college student budgets:

- **Frontend**: **Azure Static Web Apps (Free)** with global Anycast CDN, automatic SSL/TLS HTTPS, SPA routing fallback (`staticwebapp.config.json`), and CI/CD via GitHub Actions.
- **Backend**: **Azure App Service Linux (B1 Basic / F1 Free)** with FastAPI, Uvicorn proxy headers, and automated `/health` probes.
- **Database & Predictions**: Persistent SQLite database mounted at `/home/data/telemetry.db` via `WEBSITES_ENABLE_APP_SERVICE_STORAGE=true`. Machine learning model joblib artifacts embedded directly in the container.
- **Edge Laptops**: Independent monitoring agents connect over public HTTPS port 443 with cluster secret authentication and in-memory offline buffering.

📖 **Detailed Instructions**: See the comprehensive [Azure Deployment Guide](file:///d:/proejctom/adaptive_cloud_project/docs/AZURE_DEPLOYMENT_GUIDE.md) and environment template [.env.azure.example](file:///d:/proejctom/adaptive_cloud_project/.env.azure.example).

---

## 👨‍🎓 Academic Defense & Project Presentation Notes

- **Title**: Adaptive Learning for Cloud Security and Predictive Maintenance with Closed-Loop Autonomous Recovery
- **Core Technology Stack**: Python 3.10–3.13, Scikit-Learn, XGBoost, FastAPI, Uvicorn, Streamlit, Plotly, SQLite (WAL), psutil, SciPy, SHAP.
- **Key Scientific Innovations**:
  1. **Dual-Hazard Fusion**: Unification of cyber security threat classification (UNSW-NB15) with infrastructure failure prediction (Alibaba Cluster Trace 2017).
  2. **Active Concept Drift Resilience**: Real-time KS 2-Sample statistical drift detection with automated dynamic retraining.
  3. **Closed-Loop Autonomous Recovery**: Moving beyond open-loop recommendations to measurable, criteria-verified recovery with dynamic Bayesian policy optimization.
