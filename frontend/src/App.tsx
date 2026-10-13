import React, { useState, useEffect } from 'react';
import {
  LayoutDashboard,
  Server,
  AlertTriangle,
  RotateCcw,
  Activity,
  Shield,
  Key,
  Globe,
  X,
  Check,
} from 'lucide-react';
import { api } from './api/client';
import type { ServiceHealth, MaintenanceAlert } from './types';
import { OverviewView } from './components/views/OverviewView';
import { NodesView } from './components/views/NodesView';
import { PredictiveMaintenanceView } from './components/views/PredictiveMaintenanceView';
import { AdaptiveRecoveryView } from './components/views/AdaptiveRecoveryView';

type NavigationRoute = 'overview' | 'nodes' | 'maintenance' | 'recovery';

export const App: React.FC = () => {
  const [currentRoute, setCurrentRoute] = useState<NavigationRoute>('overview');
  const [serverHealth, setServerHealth] = useState<ServiceHealth | null>(null);
  const [activeAlerts, setActiveAlerts] = useState<MaintenanceAlert[]>([]);
  const [targetNodeId, setTargetNodeId] = useState<string | undefined>(undefined);
  const [targetAlert, setTargetAlert] = useState<MaintenanceAlert | undefined>(undefined);
  const [hasCheckedConnectivity, setHasCheckedConnectivity] = useState<boolean>(false);
  const [authModalOpen, setAuthModalOpen] = useState<boolean>(false);
  const [apiUrlInput, setApiUrlInput] = useState<string>(api.getBaseUrl());
  const [apiKeyInput, setApiKeyInput] = useState<string>(api.getDashboardApiKey() || '');
  const [authSavedMessage, setAuthSavedMessage] = useState<string | null>(null);

  const checkConnectivity = async () => {
    try {
      const [h, a] = await Promise.all([
        api.getHealth(),
        api.getActiveAlerts().catch(() => ({ active_count: 0, alerts: [] })),
      ]);
      setServerHealth(h);
      setActiveAlerts(a.alerts || []);
    } catch {
      setServerHealth(null);
    } finally {
      setHasCheckedConnectivity(true);
    }
  };

  const handleSaveSettings = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanUrl = apiUrlInput.trim() ? apiUrlInput.trim().replace(/\/+$/, '') : null;
    api.setBaseUrl(cleanUrl);
    api.setDashboardApiKey(apiKeyInput.trim() || null);
    setAuthSavedMessage('Configuration updated. Verifying connection...');
    setTimeout(() => setAuthSavedMessage(null), 3000);
    checkConnectivity();
  };

  useEffect(() => {
    checkConnectivity();
    const interval = setInterval(checkConnectivity, 15000);

    const onApiBaseChanged = () => {
      setApiUrlInput(api.getBaseUrl());
      checkConnectivity();
    };
    window.addEventListener('adaptive:api_base_changed', onApiBaseChanged);

    return () => {
      clearInterval(interval);
      window.removeEventListener('adaptive:api_base_changed', onApiBaseChanged);
    };
  }, []);

  const navigateToNodes = (nodeId?: string) => {
    setTargetNodeId(nodeId);
    setCurrentRoute('nodes');
  };

  const navigateToMaintenance = () => {
    setCurrentRoute('maintenance');
  };

  const navigateToRecovery = (nodeId?: string, alert?: MaintenanceAlert) => {
    setTargetNodeId(nodeId);
    setTargetAlert(alert);
    setCurrentRoute('recovery');
  };

  return (
    <div className="min-h-screen bg-console-bg text-slate-200 flex flex-col font-sans">
      {/* Top Console Navigation Bar */}
      <header className="sticky top-0 z-30 bg-[#0f172a] border-b border-slate-800 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            {/* Logo & Service Title */}
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
                <Shield className="w-4 h-4" />
              </div>
              <div>
                <span className="text-sm font-bold text-white tracking-tight flex items-center gap-2">
                  Adaptive Cloud Console
                  <span className="text-[10px] font-mono font-medium px-1.5 py-0.2 rounded bg-indigo-950 text-indigo-300 border border-indigo-800/60">
                    v2.0
                  </span>
                </span>
                <span className="text-[11px] text-slate-400 block -mt-0.5">
                  Security, Predictive Maintenance &amp; Adaptive Recovery
                </span>
              </div>
            </div>

            {/* Backend Connectivity Status & Alert Counter */}
            <div className="flex items-center gap-3">
              {/* Alert Badge */}
              {activeAlerts.length > 0 && (
                <button
                  type="button"
                  onClick={navigateToMaintenance}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded bg-rose-950/40 border border-rose-800/60 text-rose-300 hover:bg-rose-900/50 transition-colors"
                >
                  <AlertTriangle className="w-3.5 h-3.5 text-rose-400 animate-pulse" />
                  <span>{activeAlerts.length} Alert{activeAlerts.length > 1 ? 's' : ''}</span>
                </button>
              )}

              {/* Console Settings & Auth Modal Button */}
              <button
                type="button"
                onClick={() => setAuthModalOpen(true)}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded border transition-colors ${
                  api.getDashboardApiKey()
                    ? 'bg-indigo-950/50 border-indigo-700/70 text-indigo-300 hover:bg-indigo-900/50'
                    : serverHealth?.auth_required
                    ? 'bg-amber-950/50 border-amber-700/70 text-amber-300 hover:bg-amber-900/50'
                    : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700'
                }`}
                title="Configure Backend URL and API Key"
              >
                <Globe className="w-3.5 h-3.5 text-indigo-400" />
                <span className="hidden sm:inline">
                  {api.getDashboardApiKey() ? 'Connected · Auth Active' : 'API Connection'}
                </span>
              </button>

              {/* Server Liveness Indicator */}
              <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 text-xs rounded border border-slate-800 bg-slate-900 font-mono text-slate-300">
                <span
                  className={`w-2 h-2 rounded-full ${
                    serverHealth?.database === 'connected' ? 'bg-emerald-500' : 'bg-rose-500'
                  }`}
                  aria-hidden="true"
                />
                <span className="truncate max-w-[200px]">
                  {serverHealth ? 'FastAPI Online' : 'Connecting API...'}
                </span>
              </div>
            </div>
          </div>

          {/* Sub-header Navigation Tabs */}
          <nav className="flex space-x-1 border-t border-slate-800/80 -mb-px overflow-x-auto">
            <button
              type="button"
              onClick={() => setCurrentRoute('overview')}
              className={`flex items-center gap-2 py-3 px-3.5 border-b-2 text-xs font-semibold transition-colors whitespace-nowrap ${
                currentRoute === 'overview'
                  ? 'border-indigo-500 text-white bg-indigo-950/20'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
              }`}
            >
              <LayoutDashboard className="w-3.5 h-3.5" />
              Overview
            </button>

            <button
              type="button"
              onClick={() => setCurrentRoute('nodes')}
              className={`flex items-center gap-2 py-3 px-3.5 border-b-2 text-xs font-semibold transition-colors whitespace-nowrap ${
                currentRoute === 'nodes'
                  ? 'border-indigo-500 text-white bg-indigo-950/20'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
              }`}
            >
              <Server className="w-3.5 h-3.5" />
              Nodes &amp; Telemetry
            </button>

            <button
              type="button"
              onClick={() => setCurrentRoute('maintenance')}
              className={`flex items-center gap-2 py-3 px-3.5 border-b-2 text-xs font-semibold transition-colors whitespace-nowrap ${
                currentRoute === 'maintenance'
                  ? 'border-indigo-500 text-white bg-indigo-950/20'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
              Predictive Maintenance
              {activeAlerts.length > 0 && (
                <span className="ml-1 w-4 h-4 rounded-full bg-rose-600 text-white text-[10px] font-bold flex items-center justify-center">
                  {activeAlerts.length}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => setCurrentRoute('recovery')}
              className={`flex items-center gap-2 py-3 px-3.5 border-b-2 text-xs font-semibold transition-colors whitespace-nowrap ${
                currentRoute === 'recovery'
                  ? 'border-indigo-500 text-white bg-indigo-950/20'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
              }`}
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Adaptive Recovery Lab
            </button>
          </nav>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Network / Connectivity Error Alert */}
        {!serverHealth && hasCheckedConnectivity && (
          <div className="mb-6 p-4 rounded-lg bg-rose-950/30 border border-rose-900/60 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
              <div className="text-xs">
                <h3 className="font-semibold text-rose-300">Backend Communication Failure</h3>
                <p className="text-slate-300 mt-1">
                  Unable to establish a connection to the FastAPI backend at{' '}
                  <span className="font-mono text-rose-200 font-semibold">{api.getBaseUrl()}</span>.
                  Ensure the server is running, CORS allows this origin, and HTTPS is configured.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setAuthModalOpen(true)}
              className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded bg-rose-900/60 hover:bg-rose-800 text-rose-100 border border-rose-700/70 transition-colors"
            >
              <Globe className="w-3.5 h-3.5" />
              Configure Backend URL
            </button>
          </div>
        )}

        {currentRoute === 'overview' && (
          <OverviewView
            onNavigateToNodes={navigateToNodes}
            onNavigateToMaintenance={navigateToMaintenance}
            onNavigateToRecovery={navigateToRecovery}
          />
        )}

        {currentRoute === 'nodes' && (
          <NodesView
            initialSelectedNodeId={targetNodeId}
            onNavigateToRecovery={navigateToRecovery}
          />
        )}

        {currentRoute === 'maintenance' && (
          <PredictiveMaintenanceView
            onNavigateToRecovery={navigateToRecovery}
          />
        )}

        {currentRoute === 'recovery' && (
          <AdaptiveRecoveryView
            initialNodeId={targetNodeId}
            initialAlert={targetAlert}
          />
        )}
      </main>

      {/* Console Connection & Azure API Configuration Modal */}
      {authModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs">
          <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-lg shadow-xl overflow-hidden">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Globe className="w-4 h-4 text-indigo-400" />
                <h3 className="text-sm font-semibold text-white">Console Settings &amp; Azure Connection</h3>
              </div>
              <button
                type="button"
                onClick={() => setAuthModalOpen(false)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveSettings} className="p-5 space-y-4">
              <p className="text-xs text-slate-300">
                Configure your deployed Azure FastAPI backend endpoint and cluster secret.
                Settings are saved in your local browser session and never baked into static frontend bundles.
              </p>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5 flex items-center justify-between">
                  <span>FastAPI Backend Base URL</span>
                  <span className="text-[11px] text-slate-500 font-normal">Production HTTPS endpoint</span>
                </label>
                <input
                  type="text"
                  placeholder="https://<your-backend-app>.azurewebsites.net"
                  value={apiUrlInput}
                  onChange={(e) => setApiUrlInput(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono bg-slate-950 border border-slate-800 rounded text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500"
                />
                <span className="block mt-1 text-[11px] text-slate-500">
                  Example: <code className="text-indigo-400">https://adaptive-backend.azurewebsites.net</code> (or local dev: <code className="text-slate-400">http://localhost:8000</code>)
                </span>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5 flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <Key className="w-3 h-3 text-slate-400" />
                    Cluster API Key (X-API-Key)
                  </span>
                  <span className="text-[11px] text-slate-500 font-normal">Server authentication token</span>
                </label>
                <input
                  type="password"
                  placeholder="Paste cluster secret or leave empty if public..."
                  value={apiKeyInput}
                  onChange={(e) => setApiKeyInput(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono bg-slate-950 border border-slate-800 rounded text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500"
                />
              </div>

              {authSavedMessage && (
                <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
                  <Check className="w-3.5 h-3.5" />
                  {authSavedMessage}
                </div>
              )}

              <div className="flex items-center justify-between pt-3 border-t border-slate-800/80">
                <button
                  type="button"
                  onClick={() => {
                    api.setBaseUrl(null);
                    api.setDashboardApiKey(null);
                    setApiUrlInput(api.getBaseUrl());
                    setApiKeyInput('');
                    setAuthSavedMessage('Reset to defaults');
                    setTimeout(() => setAuthSavedMessage(null), 2000);
                  }}
                  className="text-xs text-slate-400 hover:text-rose-400 transition-colors"
                >
                  Reset Defaults
                </button>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setAuthModalOpen(false)}
                    className="px-3 py-1.5 text-xs text-slate-300 hover:text-white bg-slate-800 rounded transition-colors"
                  >
                    Close
                  </button>
                  <button
                    type="submit"
                    className="px-3 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded transition-colors"
                  >
                    Save &amp; Connect
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Restrained Console Footer */}
      <footer className="border-t border-slate-900 bg-slate-950/60 py-4 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>Adaptive Cloud Resilience Console · Real Telemetry &amp; Bayesian Policy Engine</span>
          <span className="font-mono text-[11px] text-slate-600 flex items-center gap-1.5">
            Backend API: {api.getBaseUrl()}
            <button
              type="button"
              onClick={() => setAuthModalOpen(true)}
              className="text-indigo-400 hover:text-indigo-300 underline font-sans ml-1 text-xs"
            >
              Configure
            </button>
          </span>
        </div>
      </footer>
    </div>
  );
};

export default App;
