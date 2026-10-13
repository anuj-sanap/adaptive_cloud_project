# Microsoft Azure Deployment Guide
## Adaptive Cloud Resilience & Monitoring System

This production deployment guide prepares and deploys the **Adaptive Cloud Resilience Console** (React 19 + TypeScript frontend) and **Central Telemetry Server** (FastAPI backend) to **Microsoft Azure**.

The deployment architecture is optimized for **cost-conscious college and university projects**, utilizing free and entry-level tiers to keep total monthly spend between **$0.00 and ~$13.00/month**.

---

## 1. Cloud Architecture & Service Selection

```
┌────────────────────────────────────────────────────────────────────────┐
│                        EDGE CLIENTS & AGENTS                           │
├────────────────────────────────┬───────────────────────────────────────┤
│  Browser Users (Laptops/Phones)│  Independent Node Agents (Campus/Home)│
└────────────────┬───────────────┴───────────────────┬───────────────────┘
                 │ HTTPS (Port 443)                  │ HTTPS (Port 443)
                 ▼                                   ▼
┌────────────────────────────────┐ ┌─────────────────────────────────────┐
│  Azure Static Web Apps (Free)  │ │ Azure App Service Linux (B1 / F1)   │
│  • React 19 Frontend (SPA)     │ │ • FastAPI Central Telemetry API     │
│  • Global Edge CDN             │ │ • Pre-trained XGBoost / RF Models   │
│  • Free Auto-Renewing SSL/TLS  │ │ • Production TLS & Reverse Proxy    │
│  • SPA Routing Fallback        │ │ • Health Probes (/health, /healthz) │
└────────────────┬───────────────┘ └──────────────────┬──────────────────┘
                 │ CORS Allowed                       │ Persistent Mount
                 └───────────────────────────────────►│ (/home/data/)
                                                      ▼
                                   ┌─────────────────────────────────────┐
                                   │ Persistent Centralized Telemetry DB │
                                   │ • SQLite in WAL mode                │
                                   │ • /home/data/telemetry.db           │
                                   └─────────────────────────────────────┘
```

### Component Breakdown & Cost Analysis

| Component | Selected Azure Service | Recommended SKU | Monthly Cost (Est.) | Rationale |
|---|---|---|---|---|
| **Frontend UI** | **Azure Static Web Apps** | Free Tier | **$0.00** | Unlimited bandwidth (within free quota), global Anycast CDN, automated GitHub Actions CI/CD, free SSL/TLS certificate, zero server maintenance. |
| **Backend API** | **Azure App Service (Linux)** | Basic B1 (or Free F1) | **$0.00 (F1)** / **~$13.00 (B1)** | Full Linux container or Python 3.11 runtime, built-in persistent storage under `/home`, automatic HTTPS on `*.azurewebsites.net`, health check probes. |
| **Telemetry Database** | **Persistent App Service Storage** | Included in App Service | **$0.00** | Stored at `/home/data/telemetry.db`. Mounts an Azure Files SMB/NFS share to `/home` via `WEBSITES_ENABLE_APP_SERVICE_STORAGE=true`. Survives container restarts and redeployments without paying for separate managed databases ($15–$30/mo saved). |
| **ML Model Storage** | **Container / Code Bundle** | Local Image Storage | **$0.00** | Static `.joblib` model artifacts (~3.5 MB) packaged directly with the backend code. Zero latency, zero egress charges. |
| **Secrets Manager** | **Azure Key Vault** *(Optional)* | Standard | **< $0.05** | Centralized secret storage for `SERVER_API_KEY`, resolved via App Service Managed Identity references. |
| **Total Estimated Spend** | | | **$0.00 – $13.00 / month** | |

---

## 2. Security, HTTPS & Secrets Architecture

1. **Production HTTPS Enforced**:
   - Azure Static Web Apps and Azure App Service enforce HTTPS with TLS 1.2/1.3 and automatic HTTP-to-HTTPS redirection.
   - `uvicorn` runs with `--proxy-headers --forwarded-allow-ips "*"` to preserve client IPs and detect `X-Forwarded-Proto: https`.
2. **Secrets Stay on the Server**:
   - The cluster authentication secret (`SERVER_API_KEY`) is stored as an **Azure App Service Application Setting** or **Azure Key Vault Secret**.
   - The React frontend bundle **never** contains this secret. In the browser, users can enter an operator key into session storage or browse public health metrics.
3. **CORS Hardened**:
   - The backend restricts cross-origin requests to your deployed Azure Static Web Apps domain via `CORS_ORIGINS`.
   - Wildcard regex `^https://.*\.azurestaticapps\.net$` allows staging and PR preview branches without CORS errors.
4. **No Localhost in Production**:
   - The frontend API client resolves endpoints dynamically. If `VITE_API_BASE_URL` is omitted or set to localhost at build time, it detects production mode and uses the current origin or runtime operator configuration instead of attempting to connect to `localhost:8000` on client computers.

---

## 3. Environment Variables Reference

### Backend (Azure App Service)
Configure these in **Azure Portal -> App Service -> Configuration / Environment variables**:

| Variable | Required | Example / Placeholder | Description |
|---|---|---|---|
| `PORT` | Auto | `8000` | Port assigned by Azure (defaults to 8000). |
| `SERVER_HOST` | Yes | `0.0.0.0` | Bind address. |
| `SERVER_API_KEY` | Yes | `<your-secure-random-secret>` | Shared secret key for authenticating agents. |
| `TELEMETRY_DB_PATH` | Yes | `/home/data/telemetry.db` | Persistent SQLite file location. |
| `WEBSITES_ENABLE_APP_SERVICE_STORAGE` | Yes | `true` | Enables persistent `/home` disk mount in App Service. |
| `CORS_ORIGINS` | Yes | `https://<your-app>.azurestaticapps.net` | Comma-separated list of allowed frontend origins (no trailing slashes). |
| `CORS_ORIGIN_REGEX` | Optional | `^https://.*\.azurestaticapps\.net$` | Regex for Azure Static Web Apps preview environments. |
| `NODE_OFFLINE_THRESHOLD_SEC` | Optional | `30` | Seconds before a quiet node is marked offline. |
| `ENVIRONMENT` | Optional | `azure_production` | Tag displayed in `/health` probe. |

### Frontend (Azure Static Web Apps)
Configure in **GitHub Actions Secrets / Build Variables**:

| Variable | Required | Example / Placeholder | Description |
|---|---|---|---|
| `VITE_API_BASE_URL` | Yes | `https://<your-backend-app>.azurewebsites.net` | Public HTTPS endpoint of your FastAPI backend. |

### Edge Node Agents (External Laptops)
Configure on each laptop running the monitoring agent:

| Variable | Required | Example / Placeholder | Description |
|---|---|---|---|
| `NODE_SERVER_URL` | Yes | `https://<your-backend-app>.azurewebsites.net` | Public HTTPS endpoint of the Azure backend. |
| `NODE_API_KEY` | Yes | `<same-secret-as-SERVER_API_KEY>` | Secret key matching the server's `SERVER_API_KEY`. |
| `NODE_TELEMETRY_INTERVAL` | Optional | `5` | Telemetry transmission interval in seconds. |
| `NODE_HEARTBEAT_INTERVAL` | Optional | `15` | Heartbeat interval in seconds. |
| `NODE_SSL_VERIFY` | Optional | `true` | Enforces TLS certificate validation. |

---

## 4. Step-by-Step Deployment Guide

### Option A: Deployment via Azure CLI

#### Step 1: Login & Setup Resource Group
```bash
# 1. Login to Azure
az login

# 2. Select subscription (if multiple)
az account set --subscription "<your-subscription-id-or-name>"

# 3. Create a dedicated Resource Group in your closest region
az group create \
  --name rg-adaptive-cloud-prod \
  --location eastus
```

#### Step 2: Deploy the FastAPI Backend (App Service Linux)
```bash
# 1. Create an App Service Plan (B1 Basic: ~$13/mo, or F1 Free for zero-budget testing)
az appservice plan create \
  --name plan-adaptive-backend \
  --resource-group rg-adaptive-cloud-prod \
  --sku B1 \
  --is-linux

# 2. Create the Linux Web App with Python 3.11 runtime
az webapp create \
  --name app-adaptive-backend-<unique-suffix> \
  --resource-group rg-adaptive-cloud-prod \
  --plan plan-adaptive-backend \
  --runtime "PYTHON:3.11"

# 3. Enable persistent storage under /home and configure startup command
az webapp config set \
  --name app-adaptive-backend-<unique-suffix> \
  --resource-group rg-adaptive-cloud-prod \
  --startup-file "python -m uvicorn central_server.api:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'"

# 4. Generate a strong cluster secret key
# (PowerShell: -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 32 | ForEach-Object {[char]$_}))
CLUSTER_KEY="adapt_$(openssl rand -hex 16)"

# 5. Configure Backend Application Settings (Environment Variables)
az webapp config appsettings set \
  --name app-adaptive-backend-<unique-suffix> \
  --resource-group rg-adaptive-cloud-prod \
  --settings \
    SERVER_HOST="0.0.0.0" \
    SERVER_PORT="8000" \
    SERVER_API_KEY="$CLUSTER_KEY" \
    TELEMETRY_DB_PATH="/home/data/telemetry.db" \
    WEBSITES_ENABLE_APP_SERVICE_STORAGE="true" \
    CORS_ORIGINS="https://salmon-tree-0a1b2c3d.azurestaticapps.net" \
    CORS_ORIGIN_REGEX="^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https://.*\.azurestaticapps\.net$" \
    NODE_OFFLINE_THRESHOLD_SEC="30" \
    ENVIRONMENT="azure_production"

# 6. Configure Azure Health Check Probe
az webapp config set \
  --name app-adaptive-backend-<unique-suffix> \
  --resource-group rg-adaptive-cloud-prod \
  --generic-configurations '{"healthCheckPath": "/health"}'

# 7. Deploy code via Zip Deploy (from project root)
# Make sure to create a clean zip containing requirements.txt, src/, models/, and config/
zip -r backend_deploy.zip requirements.txt config/ models/ src/
az webapp deploy \
  --name app-adaptive-backend-<unique-suffix> \
  --resource-group rg-adaptive-cloud-prod \
  --src-path backend_deploy.zip \
  --type zip
```

#### Step 3: Deploy the React Frontend (Azure Static Web Apps)
```bash
# 1. Create the Static Web App linked to your GitHub repository
az staticwebapp create \
  --name swa-adaptive-frontend \
  --resource-group rg-adaptive-cloud-prod \
  --source https://github.com/<your-username>/<your-repo> \
  --branch main \
  --app-location "frontend" \
  --output-location "dist" \
  --login-with-github

# 2. Set the build-time backend URL in the Static Web App configuration
az staticwebapp appsettings set \
  --name swa-adaptive-frontend \
  --resource-group rg-adaptive-cloud-prod \
  --setting-names VITE_API_BASE_URL="https://app-adaptive-backend-<unique-suffix>.azurewebsites.net"

# 3. Retrieve your Static Web App URL
az staticwebapp show \
  --name swa-adaptive-frontend \
  --resource-group rg-adaptive-cloud-prod \
  --query "defaultHostname" -o tsv
# Note the URL: https://<your-static-web-app>.azurestaticapps.net

# 4. Update the Backend's CORS_ORIGINS with the real Static Web App URL
az webapp config appsettings set \
  --name app-adaptive-backend-<unique-suffix> \
  --resource-group rg-adaptive-cloud-prod \
  --settings CORS_ORIGINS="https://<your-static-web-app>.azurestaticapps.net"
```

---

### Option B: Deployment via Azure Portal (GUI Walkthrough)

#### Part 1: Deploy FastAPI Backend (App Service Linux)
1. Go to **Azure Portal** ([portal.azure.com](https://portal.azure.com)).
2. Click **Create a resource** -> search for **Web App** -> click **Create**.
3. Configure the **Basics** tab:
   - **Subscription**: Select your Azure subscription (e.g., Azure for Students).
   - **Resource Group**: Create new: `rg-adaptive-cloud-prod`.
   - **Name**: `app-adaptive-backend-<your-name>` (must be globally unique).
   - **Publish**: `Code` (or `Docker Container` if using DockerHub/ACR).
   - **Runtime stack**: `Python 3.11`.
   - **Operating System**: `Linux`.
   - **Region**: Choose closest to you (e.g. `East US` or `West Europe`).
   - **Pricing Plan**: Select `Basic B1` (~$13/month) or `Free F1`.
4. Click **Review + create** -> **Create**.
5. Once created, go to **Settings** -> **Environment variables**:
   - Add `SERVER_HOST` = `0.0.0.0`
   - Add `SERVER_PORT` = `8000`
   - Add `SERVER_API_KEY` = `<your-secure-secret-token>`
   - Add `TELEMETRY_DB_PATH` = `/home/data/telemetry.db`
   - Add `WEBSITES_ENABLE_APP_SERVICE_STORAGE` = `true`
   - Add `CORS_ORIGINS` = `https://<your-swa-name>.azurestaticapps.net`
   - Add `ENVIRONMENT` = `azure_production`
   - Click **Apply**.
6. Go to **Settings** -> **Configuration**:
   - In **General Settings** -> **Startup Command**, enter:
     `python -m uvicorn central_server.api:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'`
   - In **Health check**, check **Enable** and set Path to: `/health`.
   - Click **Save**.

#### Part 2: Deploy React Frontend (Azure Static Web Apps)
1. In Azure Portal, click **Create a resource** -> search for **Static Web App** -> **Create**.
2. Configure **Basics**:
   - **Subscription & Resource Group**: `rg-adaptive-cloud-prod`.
   - **Name**: `swa-adaptive-frontend`.
   - **Plan type**: `Free` ($0/mo).
   - **Deployment details**: Select **GitHub**, authorize Azure, and choose your repository and branch (`main`).
   - **Build Presets**: Select `Custom`.
   - **App location**: `frontend`.
   - **Api location**: Leave blank.
   - **Output location**: `dist`.
3. Click **Review + Create** -> **Create**.
   - Azure automatically commits `.github/workflows/azure-static-web-apps-<id>.yml` to your GitHub repo and triggers the build.
4. Add the backend URL variable in GitHub repo:
   - Go to your GitHub repository -> **Settings** -> **Secrets and variables** -> **Actions** -> **Variables**.
   - Add `VITE_API_BASE_URL` = `https://app-adaptive-backend-<your-name>.azurewebsites.net`.

---

## 5. Connecting Remote Node Agents on Independent Computers

Any student or team member can run an independent node agent on their physical laptop (connected via home Wi-Fi, campus lab Wi-Fi, or mobile hotspot) to report real system telemetry directly to the deployed Azure API:

### Running on Windows (PowerShell / Command Prompt)
```powershell
# 1. Clone repository or copy src/node_agent and requirements.txt
git clone https://github.com/<your-username>/<your-repo>.git
cd adaptive_cloud_project

# 2. Install lightweight agent dependencies
pip install psutil requests

# 3. Set Azure Backend connection variables
$env:NODE_SERVER_URL="https://app-adaptive-backend-<unique-suffix>.azurewebsites.net"
$env:NODE_API_KEY="<your-cluster-secret>"

# 4. Start the live monitoring agent
python scripts/run_agent_azure.py
```

### Running on Linux / macOS
```bash
export NODE_SERVER_URL="https://app-adaptive-backend-<unique-suffix>.azurewebsites.net"
export NODE_API_KEY="<your-cluster-secret>"

python3 scripts/run_agent_azure.py --node-suffix "laptop-macbook-pro"
```

### Network & Firewall Resilience
- **Port 443 (HTTPS)**: Uses standard HTTPS, open on virtually all university campus firewalls and home Wi-Fi routers.
- **TLS Certificate Validation**: Validated via Microsoft Azure RSA TLS CA certificates trusted by standard OS root stores.
- **Offline Buffering**: If the laptop goes to sleep or campus Wi-Fi drops, the agent buffers up to 120 snapshots in memory and automatically flushes them via `POST /telemetry/batch` as soon as internet connectivity returns.

---

## 6. Azure Cost Management & Budget Alerts

To guarantee you never exceed your student budget:

### How to Create an Azure Budget with Email Alerts
1. In the **Azure Portal**, search for **Cost Management + Billing** in the search bar.
2. Under **Cost Management**, click on **Budgets** -> **+ Add**.
3. Fill in the budget details:
   - **Scope**: Select your Resource Group (`rg-adaptive-cloud-prod`) or Subscription.
   - **Name**: `College-Project-Budget`.
   - **Reset period**: `Monthly`.
   - **Budget amount**: Enter `$10.00` (or `$5.00`).
4. Set up **Alert conditions**:
   - Alert 1: **Actual** > `50%` ($5.00) -> Enter your email address.
   - Alert 2: **Actual** > `80%` ($8.00) -> Enter your email address.
   - Alert 3: **Forecasted** > `100%` ($10.00) -> Enter your email address.
5. Click **Create**.

### How to Monitor Live Resource Usage
1. Open your App Service (`app-adaptive-backend-<name>`).
2. In the left navigation, click **Monitoring** -> **Metrics**:
   - Select metric **CPU Percentage** to see average CPU utilization across workers.
   - Select metric **Memory Percentage** to monitor RAM usage.
   - Select metric **Http 2xx / 4xx / 5xx** to inspect request volume and errors.
3. In **Monitoring** -> **Live Metrics**, you can view real-time streaming telemetry, incoming request rates, and active server exceptions as agents transmit data.

---

## 7. Post-Deployment Verification

> **Important**: Do not claim the project is deployed until all 5 points below are verified against the real cloud URLs.

Run the post-deployment verification script from your development machine:

```bash
python scripts/verify_azure_deployment.py \
  --frontend-url https://<your-app>.azurestaticapps.net \
  --backend-url https://app-adaptive-backend-<unique-suffix>.azurewebsites.net \
  --api-key <your-cluster-secret>
```

### What this script verifies:
1. **Frontend Reachability**: Probes the HTTPS frontend URL and confirms the React single-page application is served.
2. **Backend Health & Liveness**: Calls `/health` and `/healthz` to confirm `status: healthy` and `database: connected`.
3. **CORS Headers**: Sends an `OPTIONS` preflight request with your frontend origin to ensure cross-origin browser requests are accepted.
4. **Authentication Enforcement**: Tests that unauthorized requests are rejected (HTTP 401) and valid cluster secret requests succeed (HTTP 200).
5. **Real Telemetry & Persistence**: Registers a test node, ingests real metrics over HTTPS, verifies the record in SQLite, and flushes a batch buffer.

When all checks pass, you will see:
```
===========================================================================
ALL AZURE DEPLOYMENT VERIFICATION CHECKS PASSED SUCCESSFULLY!
Your React frontend, FastAPI backend, SQLite persistence, and edge agent reachability are operational.
===========================================================================
```
