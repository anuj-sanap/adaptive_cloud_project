import React, { useState, useEffect } from 'react';
import {
  Server,
  CheckCircle2,
  AlertTriangle,
  ShieldAlert,
  ShieldCheck,
  RefreshCw,
  ArrowRight,
} from 'lucide-react';
import { api } from '../../api/client';
import type {
  NodeItem,
  MaintenanceAlert,
  NodeRiskItem,
} from '../../types';
import { StatusIndicator, formatTimeAge } from '../common/StatusIndicator';
import { MetricCard } from '../common/MetricCard';
import { LoadingState } from '../common/LoadingState';
import { ErrorState } from '../common/ErrorState';
import { EmptyState } from '../common/EmptyState';

interface OverviewViewProps {
  onNavigateToNodes: (nodeId?: string) => void;
  onNavigateToMaintenance: () => void;
  onNavigateToRecovery: (nodeId?: string) => void;
}

export const OverviewView: React.FC<OverviewViewProps> = ({
  onNavigateToNodes,
  onNavigateToMaintenance,
  onNavigateToRecovery,
}) => {
  const [nodes, setNodes] = useState<NodeItem[]>([]);
  const [alerts, setAlerts] = useState<MaintenanceAlert[]>([]);
  const [risks, setRisks] = useState<NodeRiskItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());

  const loadData = async () => {
    try {
      setError(null);
      const [nodesData, alertsData, risksData] = await Promise.all([
        api.getNodes(),
        api.getActiveAlerts(),
        api.getNodeRisks(),
      ]);

      setNodes(nodesData.nodes || []);
      setAlerts(alertsData.alerts || []);
      setRisks(risksData.nodes || []);
      setLastRefreshed(new Date());
    } catch (err: unknown) {
      setError((err as Error).message || 'Failed to connect to central backend');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading && !nodes.length) {
    return <LoadingState message="Connecting to central backend..." subtext="Retrieving telemetry and node registry" />;
  }

  if (error && !nodes.length) {
    return (
      <div className="space-y-4">
        <ErrorState
          title="Backend Communication Failure"
          message={error}
          onRetry={loadData}
        />
      </div>
    );
  }

  // 1. Registered real-node count
  const registeredCount = nodes.length;

  // Set of node IDs with active incidents
  const incidentNodeIds = new Set(alerts.map((a) => a.node_id));

  // Set of node IDs with validated critical or high risk
  const highRiskNodeIds = new Set(
    risks
      .filter(
        (r) =>
          r.overall_risk_level === 'CRITICAL' ||
          r.overall_risk_level === 'HIGH' ||
          r.failure_risk_level === 'CRITICAL' ||
          r.failure_risk_level === 'HIGH'
      )
      .map((r) => r.node_id)
  );

  // 2. Healthy-node count: ONLINE, not anomalous live health, no active incident or high risk
  const healthyNodes = nodes.filter((n) => {
    const isOnline = n.status === 'ONLINE';
    const isNotAnomalous = n.latest_live_health?.health_status !== 'ANOMALOUS';
    const hasNoIncident = !incidentNodeIds.has(n.node_id);
    const hasNoHighRisk = !highRiskNodeIds.has(n.node_id);
    return isOnline && isNotAnomalous && hasNoIncident && hasNoHighRisk;
  });
  const healthyCount = healthyNodes.length;

  // 3. Active incident count
  const activeIncidentCount = alerts.length;

  // 4. At-risk-node count from validated prediction results
  const atRiskNodes = nodes.filter(
    (n) =>
      highRiskNodeIds.has(n.node_id) ||
      incidentNodeIds.has(n.node_id) ||
      n.latest_live_health?.health_status === 'ANOMALOUS'
  );
  const atRiskCount = atRiskNodes.length;

  // Determine highest-priority validated risk
  const sortedAlerts = [...alerts].sort((a, b) => {
    const rank: Record<string, number> = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };
    const rA = rank[a.risk_level] || 0;
    const rB = rank[b.risk_level] || 0;
    if (rB !== rA) return rB - rA;
    return (b.failure_probability || 0) - (a.failure_probability || 0);
  });

  const sortedRisks = [...risks].sort((a, b) => {
    const rank: Record<string, number> = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1, NOMINAL: 0 };
    const rA = rank[a.overall_risk_level] || 0;
    const rB = rank[b.overall_risk_level] || 0;
    if (rB !== rA) return rB - rA;
    return (b.overall_risk_score || 0) - (a.overall_risk_score || 0);
  });

  const topAlert = sortedAlerts[0];
  const topRisk = sortedRisks[0];

  const hasValidatedRisk =
    topAlert ||
    (topRisk && (topRisk.overall_risk_level === 'CRITICAL' || topRisk.overall_risk_level === 'HIGH'));

  return (
    <div className="space-y-6">
      {/* Console Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">Overview</h1>
          <p className="text-xs text-slate-400 mt-1">
            Real-time fleet health, active incident monitoring, and validated predictive risk assessment.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400 font-mono">
            Updated {lastRefreshed.toLocaleTimeString()}
          </span>
          <button
            type="button"
            onClick={loadData}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-200 bg-slate-900 hover:bg-slate-800 border border-slate-700 rounded transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
        </div>
      </div>

      {/* Summary Cards: Exactly Four Minimal Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 1. Registered real-node count */}
        <MetricCard
          label="Registered Nodes"
          value={registeredCount}
          unit="nodes"
          subtext={registeredCount > 0 ? 'Fleet agents enrolled' : 'No agents enrolled'}
          icon={<Server className="w-4 h-4" />}
          badge={{
            text: registeredCount > 0 ? 'Active' : 'Empty',
            variant: registeredCount > 0 ? 'info' : 'neutral',
          }}
        />

        {/* 2. Healthy-node count */}
        <MetricCard
          label="Healthy Nodes"
          value={healthyCount}
          unit={`/ ${registeredCount}`}
          subtext={
            registeredCount > 0
              ? `${Math.round((healthyCount / registeredCount) * 100)}% nominal operation`
              : 'Awaiting nodes'
          }
          icon={<CheckCircle2 className="w-4 h-4" />}
          badge={{
            text: healthyCount === registeredCount && registeredCount > 0 ? 'Optimal' : healthyCount > 0 ? 'Partial' : 'None',
            variant: healthyCount === registeredCount && registeredCount > 0 ? 'success' : healthyCount > 0 ? 'warning' : 'neutral',
          }}
        />

        {/* 3. Active incident count */}
        <MetricCard
          label="Active Incidents"
          value={activeIncidentCount}
          unit={activeIncidentCount === 1 ? 'incident' : 'incidents'}
          subtext={activeIncidentCount === 0 ? 'All services nominal' : 'Action required'}
          icon={<AlertTriangle className="w-4 h-4" />}
          badge={{
            text: activeIncidentCount === 0 ? 'Zero Incidents' : 'Attention',
            variant: activeIncidentCount === 0 ? 'success' : 'danger',
          }}
        />

        {/* 4. At-risk-node count from validated prediction results */}
        <MetricCard
          label="At-Risk Nodes"
          value={atRiskCount}
          unit="nodes"
          subtext={atRiskCount === 0 ? 'Zero critical predictions' : 'Elevated failure / threat'}
          icon={<ShieldAlert className="w-4 h-4" />}
          badge={{
            text: atRiskCount === 0 ? 'Protected' : 'Elevated Risk',
            variant: atRiskCount === 0 ? 'success' : 'danger',
          }}
        />
      </div>

      {/* Highest-Priority Validated Risk Section */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-800/80 mb-3">
          <h2 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
            Highest-Priority Validated Risk
          </h2>
          {hasValidatedRisk && (
            <button
              type="button"
              onClick={onNavigateToMaintenance}
              className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 font-medium transition-colors"
            >
              View Maintenance Alerts
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {topAlert ? (
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 bg-rose-950/20 border border-rose-900/40 rounded-md">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 text-[11px] font-bold rounded bg-rose-950 text-rose-300 border border-rose-800 font-mono">
                  {topAlert.risk_level} RISK
                </span>
                <span className="text-sm font-semibold text-white">{topAlert.alert_title}</span>
              </div>
              <p className="text-xs text-slate-300 line-clamp-2">
                {topAlert.alert_description}
              </p>
              <p className="text-[11px] text-slate-400 font-mono">
                Target Node: <span className="text-slate-200 font-semibold">{topAlert.node_id}</span> · Failure Probability:{' '}
                <span className="text-rose-400 font-bold">
                  {(topAlert.failure_probability * 100).toFixed(1)}%
                </span>
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0 self-start sm:self-auto">
              <button
                type="button"
                onClick={() => onNavigateToRecovery(topAlert.node_id)}
                className="px-3 py-1.5 text-xs font-medium text-indigo-200 bg-indigo-950/60 hover:bg-indigo-900/60 border border-indigo-800/60 rounded transition-colors"
              >
                Adaptive Recovery
              </button>
              <button
                type="button"
                onClick={onNavigateToMaintenance}
                className="px-3 py-1.5 text-xs font-medium text-rose-200 bg-rose-900/40 hover:bg-rose-900/60 border border-rose-800/80 rounded transition-colors"
              >
                Review Alert
              </button>
            </div>
          </div>
        ) : topRisk && (topRisk.overall_risk_level === 'CRITICAL' || topRisk.overall_risk_level === 'HIGH') ? (
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 bg-amber-950/20 border border-amber-900/40 rounded-md">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 text-[11px] font-bold rounded bg-amber-950 text-amber-300 border border-amber-800 font-mono">
                  {topRisk.overall_risk_level} RISK
                </span>
                <span className="text-sm font-semibold text-white">Elevated Multi-Hazard Risk</span>
              </div>
              <p className="text-xs text-slate-300">
                {topRisk.recommendation || 'Validated risk score indicates elevated threat and potential infrastructure degradation.'}
              </p>
              <p className="text-[11px] text-slate-400 font-mono">
                Target Node: <span className="text-slate-200 font-semibold">{topRisk.node_id}</span> · Security:{' '}
                <span className="text-amber-300">{topRisk.security_risk_level || 'Normal'}</span> · Failure:{' '}
                <span className="text-amber-300">{topRisk.failure_risk_level || 'Low'}</span>
              </p>
            </div>
            <div className="shrink-0 self-start sm:self-auto">
              <button
                type="button"
                onClick={() => onNavigateToRecovery(topRisk.node_id)}
                className="px-3 py-1.5 text-xs font-medium text-amber-200 bg-amber-950/60 hover:bg-amber-900/60 border border-amber-800/60 rounded transition-colors"
              >
                Adaptive Recovery
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-3 p-3 bg-slate-950/40 border border-slate-800/80 rounded-md">
            <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0" />
            <div>
              <p className="text-xs font-semibold text-slate-200">
                No Validated Risks Requiring Attention
              </p>
              <p className="text-[11px] text-slate-400 mt-0.5">
                All monitored nodes are operating within nominal baseline parameters with zero active failure alerts.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Compact Node Table: Hostname, Region, Status, Last Seen */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Server className="w-4 h-4 text-slate-400" />
            <h2 className="text-sm font-semibold text-slate-200">Connected Nodes</h2>
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400">
              {nodes.length}
            </span>
          </div>
          {nodes.length > 0 && (
            <button
              type="button"
              onClick={() => onNavigateToNodes()}
              className="text-xs text-indigo-400 hover:text-indigo-300 font-medium transition-colors"
            >
              View Node Details &rarr;
            </button>
          )}
        </div>

        {nodes.length === 0 ? (
          <div className="p-8">
            <EmptyState
              title="No nodes registered"
              description="No live monitoring agents are currently connected. Start an agent to begin streaming telemetry."
              icon={<Server className="w-10 h-10 text-slate-600" />}
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-800/80 bg-slate-950/40 text-slate-400 font-mono">
                  <th className="py-2.5 px-4 font-semibold">Hostname</th>
                  <th className="py-2.5 px-4 font-semibold">Region</th>
                  <th className="py-2.5 px-4 font-semibold">Status</th>
                  <th className="py-2.5 px-4 font-semibold text-right">Last Seen</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {nodes.map((node) => {
                  const region =
                    node.region ||
                    (node.hardware_info as Record<string, unknown>)?.region ||
                    'us-central1';

                  return (
                    <tr
                      key={node.node_id}
                      onClick={() => onNavigateToNodes(node.node_id)}
                      className="hover:bg-slate-800/40 cursor-pointer transition-colors"
                      title={`Click to inspect telemetry for ${node.node_id}`}
                    >
                      {/* Hostname */}
                      <td className="py-3 px-4">
                        <div className="flex flex-col">
                          <span className="font-semibold text-slate-200 font-sans">
                            {node.hostname || node.node_id}
                          </span>
                          {node.hostname && node.hostname !== node.node_id && (
                            <span className="text-[10px] text-slate-500 font-mono">
                              {node.node_id}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Region */}
                      <td className="py-3 px-4 text-slate-300">
                        <span className="px-2 py-0.5 rounded bg-slate-950/60 border border-slate-800 text-[11px] text-slate-300">
                          {String(region)}
                        </span>
                      </td>

                      {/* Status */}
                      <td className="py-3 px-4">
                        <StatusIndicator status={node.status} lastSeen={node.last_seen} showAge={false} />
                      </td>

                      {/* Last Seen */}
                      <td className="py-3 px-4 text-right text-slate-400 font-mono text-[11px]">
                        <span title={node.last_seen}>{formatTimeAge(node.last_seen)}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
