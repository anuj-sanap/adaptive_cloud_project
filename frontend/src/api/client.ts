/**
 * Central API Client for Adaptive Cloud Monitoring & Resilience Backend.
 * Configured dynamically through Vite environment variables (VITE_API_BASE_URL).
 * Never exposes server secret tokens or cluster keys to the browser.
 */

import type {
  ServiceHealth,
  NodeItem,
  MaintenanceAlert,
  RecoveryDecision,
  LearnedActionHistory,
  NodeRiskItem,
  DriftNodeItem,
  FleetSummary,
  ModelStatusResponse,
  RecoveryBenchmark,
  PredictiveMaintenanceNodeEvaluation,
  FleetPredictiveMaintenanceResponse,
  RecoveryIncidentItem,
} from '../types';

let customApiBaseUrl: string | null = typeof window !== 'undefined'
  ? (localStorage.getItem('adaptive_api_base_url') || sessionStorage.getItem('adaptive_api_base_url'))
  : null;

/**
 * Resolves the active Backend API Base URL safely.
 * Precedence:
 * 1. User manual override stored in localStorage / sessionStorage (allows operator to configure live URL without rebuild).
 * 2. Runtime window config (__ADAPTIVE_CONFIG__.API_BASE_URL) injected dynamically in index.html.
 * 3. Vite build-time environment variable (VITE_API_BASE_URL).
 * 4. Production fallback: If in production mode (import.meta.env.PROD), never fallback to localhost.
 *    Defaults to window.location.origin (if hosted with reverse proxy / same domain).
 * 5. Local development fallback: 'http://localhost:8000' (strictly in DEV mode).
 */
export function getApiBaseUrl(): string {
  // 1. Runtime override in localStorage/sessionStorage
  if (customApiBaseUrl && customApiBaseUrl.trim()) {
    return customApiBaseUrl.trim().replace(/\/+$/, '');
  }

  // 2. Runtime window config
  if (typeof window !== 'undefined') {
    const win = window as unknown as { __ADAPTIVE_CONFIG__?: { API_BASE_URL?: string } };
    if (win.__ADAPTIVE_CONFIG__?.API_BASE_URL) {
      return win.__ADAPTIVE_CONFIG__.API_BASE_URL.trim().replace(/\/+$/, '');
    }
  }

  // 3. Vite build-time environment variable
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl && typeof envUrl === 'string' && envUrl.trim()) {
    const trimmed = envUrl.trim().replace(/\/+$/, '');
    if (import.meta.env.PROD) {
      // In production, ensure we are not accidentally pointing to localhost
      const isLocal = trimmed.includes('localhost') || trimmed.includes('127.0.0.1');
      if (!isLocal) {
        return trimmed;
      }
      console.warn('[Adaptive Console] VITE_API_BASE_URL is set to localhost in production mode. Falling back to origin.');
    } else {
      return trimmed;
    }
  }

  // 4. In production mode, never default to localhost
  if (typeof window !== 'undefined' && import.meta.env.PROD) {
    return window.location.origin.replace(/\/+$/, '');
  }

  // 5. In local development only
  return 'http://localhost:8000';
}

export function setApiBaseUrl(url: string | null): void {
  customApiBaseUrl = url ? url.trim().replace(/\/+$/, '') : null;
  if (typeof window !== 'undefined') {
    if (customApiBaseUrl) {
      localStorage.setItem('adaptive_api_base_url', customApiBaseUrl);
      sessionStorage.setItem('adaptive_api_base_url', customApiBaseUrl);
    } else {
      localStorage.removeItem('adaptive_api_base_url');
      sessionStorage.removeItem('adaptive_api_base_url');
    }
    window.dispatchEvent(new CustomEvent('adaptive:api_base_changed', { detail: customApiBaseUrl }));
  }
}

const DEFAULT_TIMEOUT_MS = 10000;

let dashboardApiKey: string | null = typeof window !== 'undefined' ? sessionStorage.getItem('adaptive_dashboard_api_key') : null;

export function setDashboardApiKey(key: string | null): void {
  dashboardApiKey = key ? key.trim() : null;
  if (typeof window !== 'undefined') {
    if (dashboardApiKey) {
      sessionStorage.setItem('adaptive_dashboard_api_key', dashboardApiKey);
    } else {
      sessionStorage.removeItem('adaptive_dashboard_api_key');
    }
  }
}

export function getDashboardApiKey(): string | null {
  return dashboardApiKey;
}

export class ApiError extends Error {
  public statusCode: number;
  public details?: unknown;

  constructor(message: string, statusCode: number, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = statusCode;
    this.details = details;
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  try {
    const headers: Record<string, string> = {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    };
    if (dashboardApiKey) {
      headers['X-API-Key'] = dashboardApiKey;
    }

    const res = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers,
    });

    if (!res.ok) {
      let errorDetail = `HTTP ${res.status}: ${res.statusText}`;
      try {
        const errorJson = await res.json();
        errorDetail = errorJson.detail || errorJson.error || errorDetail;
      } catch {
        // Fallback to text status
      }
      if (res.status === 401 || res.status === 403) {
        throw new ApiError(`Authentication failed (${res.status}): ${errorDetail}`, res.status);
      }
      throw new ApiError(errorDetail, res.status);
    }

    return await res.json() as T;
  } catch (err: unknown) {
    if (err instanceof ApiError) {
      throw err;
    }
    if ((err as Error)?.name === 'AbortError') {
      throw new ApiError(`Request timed out after ${DEFAULT_TIMEOUT_MS}ms`, 504);
    }
    throw new ApiError((err as Error)?.message || 'Failed to connect to backend server', 0);
  } finally {
    clearTimeout(timeoutId);
  }
}

export const api = {
  getBaseUrl(): string {
    return getApiBaseUrl();
  },

  setBaseUrl(url: string | null): void {
    setApiBaseUrl(url);
  },

  getDashboardApiKey(): string | null {
    return getDashboardApiKey();
  },

  setDashboardApiKey(key: string | null): void {
    setDashboardApiKey(key);
  },

  async getHealth(): Promise<ServiceHealth> {
    return request<ServiceHealth>('/health');
  },

  async getFleetSummary(): Promise<FleetSummary> {
    return request<FleetSummary>('/fleet/summary');
  },

  async getModelsStatus(): Promise<ModelStatusResponse> {
    return request<ModelStatusResponse>('/models/status');
  },

  async getNodes(genuineOnly: boolean = true): Promise<{ total_nodes: number; nodes: NodeItem[] }> {
    const query = genuineOnly ? '?genuine_only=true' : '';
    return request<{ total_nodes: number; nodes: NodeItem[] }>(`/nodes${query}`);
  },

  async getNodeDetails(nodeId: string, limit: number = 30): Promise<NodeItem & { recent_telemetry: unknown[] }> {
    return request<NodeItem & { recent_telemetry: unknown[] }>(`/nodes/${encodeURIComponent(nodeId)}?limit=${limit}`);
  },

  async getActiveAlerts(nodeId?: string): Promise<{ active_count: number; alerts: MaintenanceAlert[] }> {
    const query = nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : '';
    return request<{ active_count: number; alerts: MaintenanceAlert[] }>(`/alerts/active${query}`);
  },

  async getAlertHistory(limit: number = 50, nodeId?: string): Promise<{ active_count: number; alerts: MaintenanceAlert[]; history: MaintenanceAlert[] }> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (nodeId) params.append('node_id', nodeId);
    return request<{ active_count: number; alerts: MaintenanceAlert[]; history: MaintenanceAlert[] }>(`/alerts?${params.toString()}`);
  },

  async acknowledgeAlert(alertId: string): Promise<{ status: string; alert_id: string; state: string }> {
    return request<{ status: string; alert_id: string; state: string }>(`/alerts/${encodeURIComponent(alertId)}/acknowledge`, {
      method: 'POST',
    });
  },

  async resolveAlert(alertId: string): Promise<{ status: string; alert_id: string; state: string }> {
    return request<{ status: string; alert_id: string; state: string }>(`/alerts/${encodeURIComponent(alertId)}/resolve`, {
      method: 'POST',
    });
  },

  async getNodeRisks(): Promise<{ total_nodes: number; nodes: NodeRiskItem[] }> {
    return request<{ total_nodes: number; nodes: NodeRiskItem[] }>('/risk/nodes');
  },

  async getLiveDrift(): Promise<{ total_nodes: number; nodes: DriftNodeItem[] }> {
    return request<{ total_nodes: number; nodes: DriftNodeItem[] }>('/live-drift');
  },

  async getAdaptiveRetraining(): Promise<{ retraining: Record<string, unknown> }> {
    return request<{ retraining: Record<string, unknown> }>('/adaptive/retraining');
  },

  async getPreventionRecommendations(): Promise<{ recommendations: Array<{ node_id: string; recommendation: string; action_priority: string; overall_risk: string }> }> {
    return request<{ recommendations: Array<{ node_id: string; recommendation: string; action_priority: string; overall_risk: string }> }>('/prevention/nodes');
  },

  async getRecoveryIncidents(nodeId?: string, limit: number = 25, genuineOnly: boolean = true): Promise<{ total: number; incidents: RecoveryIncidentItem[] }> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (nodeId) params.append('node_id', nodeId);
    if (genuineOnly) params.append('genuine_only', 'true');
    return request<{ total: number; incidents: RecoveryIncidentItem[] }>(`/recovery/incidents?${params.toString()}`);
  },

  async getRecoveryDecisions(nodeId?: string, limit: number = 25): Promise<{ total: number; decisions: RecoveryDecision[] }> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (nodeId) params.append('node_id', nodeId);
    return request<{ total: number; decisions: RecoveryDecision[] }>(`/recovery/decisions?${params.toString()}`);
  },

  async getNodeRecoveryHistory(nodeId: string): Promise<{ node_id: string; total: number; history: LearnedActionHistory[] }> {
    return request<{ node_id: string; total: number; history: LearnedActionHistory[] }>(`/recovery/history/${encodeURIComponent(nodeId)}`);
  },

  async getRecoveryBenchmarks(mode?: string, limit: number = 10): Promise<{ total: number; benchmarks: RecoveryBenchmark[] }> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (mode) params.append('mode', mode);
    return request<{ total: number; benchmarks: RecoveryBenchmark[] }>(`/recovery/benchmarks?${params.toString()}`);
  },

  async evaluateRecovery(payload: {
    node_id: string;
    incident_type: string;
    severity?: string;
    incident_id?: string;
    telemetry?: Record<string, unknown>;
    execute?: boolean;
    approved?: boolean;
    operator_id?: string;
    verification_timeout_sec?: number;
    fresh_telemetry?: Record<string, unknown>;
  }): Promise<RecoveryDecision> {
    return request<RecoveryDecision>('/recovery/evaluate', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async approveAndExecuteRecovery(payload: {
    node_id: string;
    incident_type: string;
    severity?: string;
    incident_id?: string;
    telemetry?: Record<string, unknown>;
    operator_id?: string;
    verification_timeout_sec?: number;
    fresh_telemetry?: Record<string, unknown>;
  }): Promise<RecoveryDecision> {
    return request<RecoveryDecision>('/recovery/approve-and-execute', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async injectDemoSecurityEvent(nodeId: string, attackCategory: string): Promise<Record<string, unknown>> {
    return request<Record<string, unknown>>('/security/demo-event', {
      method: 'POST',
      body: JSON.stringify({
        node_id: nodeId,
        attack_category: attackCategory,
      }),
    });
  },

  async getPredictiveMaintenance(nodeId: string, historyLimit: number = 50): Promise<PredictiveMaintenanceNodeEvaluation> {
    return request<PredictiveMaintenanceNodeEvaluation>(`/predictive-maintenance/${encodeURIComponent(nodeId)}?history_limit=${historyLimit}`);
  },

  async getFleetPredictiveMaintenance(genuineOnly: boolean = true): Promise<FleetPredictiveMaintenanceResponse> {
    const query = genuineOnly ? '?genuine_only=true' : '';
    return request<FleetPredictiveMaintenanceResponse>(`/predictive-maintenance${query}`);
  },
};


