# Adaptive Cloud Resilience Web Console (React + TypeScript + Vite)

A modern, restrained cloud-console web frontend for the **Adaptive Cloud Monitoring and Predictive Maintenance System**, built with **React 19**, **TypeScript**, **Vite**, and **Tailwind CSS**.

---

## 🎯 Architecture & Design Principles

* **Decoupled Architecture**: Communicates with the FastAPI central server strictly over REST API calls.
* **Restrained Cloud Console Design**: Clean slate-900 / dark aesthetic, generous whitespace, accessible status indicators, readable monospace telemetry metrics, and zero unnecessary decorative animations or cards.
* **Zero Secret Leakage**: Connects via `VITE_API_BASE_URL` without exposing cluster secrets or agent tokens to the browser.
* **Lightweight Charting**: Uses Recharts for restrained, accessible time-series telemetry charts without excessive dependencies.
* **Defensive UX**: Reusable states for loading spinners, empty lists, connection errors with retry, and stale-data age badges.

---

## 📁 Project Structure

```
frontend/
├── .env                     # Local frontend configuration
├── .env.example             # Template for frontend environment
├── index.html               # Main HTML entry point with Inter font
├── package.json             # NPM dependencies & scripts
├── postcss.config.js        # PostCSS configuration
├── tailwind.config.js       # Tailwind CSS theme & console color tokens
├── tsconfig.json            # TypeScript configuration
├── vite.config.ts           # Vite dev server & backend proxy
├── src/
│   ├── main.tsx             # React DOM root entry
│   ├── App.tsx              # Main layout, status bar, and route switcher
│   ├── index.css            # Tailwind directives & console base styling
│   ├── api/
│   │   └── client.ts        # Typed central API client with timeout & error handling
│   ├── types/
│   │   └── index.ts         # TypeScript interfaces for nodes, telemetry, alerts, recovery
│   └── components/
│       ├── common/
│       │   ├── LoadingState.tsx       # Reusable accessible spinner/loading card
│       │   ├── EmptyState.tsx         # Reusable empty list state with optional action
│       │   ├── ErrorState.tsx         # Reusable error banner with retry trigger
│       │   ├── StatusIndicator.tsx    # Accessible ONLINE / STALE / OFFLINE indicator
│       │   ├── StaleDataBadge.tsx     # Age-aware telemetry delay pill
│       │   └── MetricCard.tsx         # Restrained KPI card with value, unit, and badge
│       └── views/
│           ├── OverviewView.tsx               # Fleet KPIs, node overview, and risk matrix
│           ├── NodesView.tsx                  # Node list, live gauges, and Recharts historical trends
│           ├── PredictiveMaintenanceView.tsx  # Active alerts, attribution, acknowledge/resolve
│           └── AdaptiveRecoveryView.tsx       # Decision lab, candidate rankings, verification
```

---

## ⚙️ Environment Configuration

Configure the central API endpoint in `.env` (or set in your deployment environment):

```env
# Central FastAPI Server base URL
VITE_API_BASE_URL=http://localhost:8000
```

> **Security Note**: Never place `SERVER_API_KEY`, cluster tokens, or agent credentials in frontend `.env` files. The frontend only consumes public monitoring endpoints.

---

## 🚀 Running on Windows

### 1. Install Dependencies
In **PowerShell** or **Command Prompt**:
```powershell
cd d:\proejctom\adaptive_cloud_project\frontend
npm install
```

### 2. Run the Development Server
```powershell
npm run dev
```
Open your browser at `http://localhost:5173`.

### 3. Build for Production
```powershell
npm run build
```
Generates production-optimized static assets in `frontend/dist/`.

### 4. Preview the Production Build Locally
```powershell
npm run preview
```
Previews the compiled bundle at `http://localhost:4173`.
