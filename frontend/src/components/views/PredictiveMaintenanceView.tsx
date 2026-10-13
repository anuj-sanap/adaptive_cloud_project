import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  RefreshCw,
  ArrowRight,
  Activity,
  Database,
  TrendingUp,
  AlertCircle,
  Binary,
  BarChart3,
  Check,
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts';
import { api } from '../../api/client';
import type {
  MaintenanceAlert,
  PredictiveMaintenanceNodeEvaluation,
  FleetPredictiveNodeItem,
  ForecastPoint,
} from '../../types';
import { LoadingState } from '../common/LoadingState';
import { ErrorState } from '../common/ErrorState';
import { EmptyState } from '../common/EmptyState';

interface PredictiveMaintenanceViewProps {
  onNavigateToRecovery: (nodeId: string, alert?: MaintenanceAlert) => void;
}

type MetricViewKey = 'leading' | 'ram' | 'cpu' | 'pressure' | 'disk';

interface ChartPoint {
  time: string;
  measured: number | null;
  forecast: number | null;
  uncertainty_lower: number | null;
  uncertainty_upper: number | null;
  is_anomaly: boolean;
  type: string;
}

export const PredictiveMaintenanceView: React.FC<PredictiveMaintenanceViewProps> = ({
  onNavigateToRecovery,
}) => {
  const [fleetNodes, setFleetNodes] = useState<FleetPredictiveNodeItem[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<PredictiveMaintenanceNodeEvaluation | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingEvaluation, setLoadingEvaluation] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [activeMetric, setActiveMetric] = useState<MetricViewKey>('leading');
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);

  // Fetch fleet predictive maintenance list
  const fetchFleet = useCallback(async () => {
    try {
      const res = await api.getFleetPredictiveMaintenance();
      const nodes = res.nodes || [];
      setFleetNodes(nodes);
      setLastRefreshedAt(new Date());

      // If no node selected yet, choose node with highest risk, otherwise first node
      setSelectedNodeId((prev) => {
        if (prev && nodes.some((n) => n.node_id === prev)) {
          return prev;
        }
        if (nodes.length === 0) return null;
        // Prioritize at-risk nodes
        const highRiskNode = nodes.find(
          (n) => n.risk_level === 'CRITICAL' || n.risk_level === 'HIGH'
        );
        return highRiskNode ? highRiskNode.node_id : nodes[0].node_id;
      });
    } catch (err: unknown) {
      setError((err as Error).message || 'Failed to fetch fleet predictive maintenance data');
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch detailed node evaluation
  const fetchNodeEvaluation = useCallback(async (nodeId: string) => {
    if (!nodeId) return;
    try {
      setLoadingEvaluation(true);
      const data = await api.getPredictiveMaintenance(nodeId, 50);
      setEvaluation(data);
      setLastRefreshedAt(new Date());
    } catch (err: unknown) {
      setError((err as Error).message || `Failed to evaluate predictive maintenance for node ${nodeId}`);
    } finally {
      setLoadingEvaluation(false);
    }
  }, []);

  // Initial fleet load and periodic refresh
  useEffect(() => {
    fetchFleet();
    const interval = setInterval(() => {
      fetchFleet();
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchFleet]);

  // Fetch node evaluation when selection changes
  useEffect(() => {
    if (selectedNodeId) {
      fetchNodeEvaluation(selectedNodeId);
    }
  }, [selectedNodeId, fetchNodeEvaluation]);

  // Alert acknowledgement and resolution handlers
  const handleAcknowledge = async (alertId: string) => {
    setActionInProgress(alertId);
    try {
      await api.acknowledgeAlert(alertId);
      if (selectedNodeId) {
        await fetchNodeEvaluation(selectedNodeId);
      }
      await fetchFleet();
    } catch (err: unknown) {
      alert(`Failed to acknowledge alert: ${(err as Error).message}`);
    } finally {
      setActionInProgress(null);
    }
  };

  const handleResolve = async (alertId: string) => {
    setActionInProgress(alertId);
    try {
      await api.resolveAlert(alertId);
      if (selectedNodeId) {
        await fetchNodeEvaluation(selectedNodeId);
      }
      await fetchFleet();
    } catch (err: unknown) {
      alert(`Failed to resolve alert: ${(err as Error).message}`);
    } finally {
      setActionInProgress(null);
    }
  };

  // Metric configuration for chart display
  const metricConfigs = useMemo(() => {
    const leadingName = evaluation?.forecast.leading_metric || 'RAM Utilization';
    return {
      leading: {
        label: `Leading: ${leadingName}`,
        threshold: leadingName.includes('CPU')
          ? 80.0
          : leadingName.includes('Disk')
          ? 90.0
          : leadingName.includes('Pressure')
          ? 45.0
          : 85.0,
        unit: leadingName.includes('Pressure') ? 'pts' : '%',
        domain: leadingName.includes('Pressure') ? [0, 80] : [0, 100],
      },
      ram: {
        label: 'RAM Utilization',
        threshold: 85.0,
        unit: '%',
        domain: [0, 100],
      },
      cpu: {
        label: 'CPU Utilization',
        threshold: 80.0,
        unit: '%',
        domain: [0, 100],
      },
      pressure: {
        label: 'Resource Pressure',
        threshold: 45.0,
        unit: 'pts',
        domain: [0, 80],
      },
      disk: {
        label: 'Disk Utilization',
        threshold: 90.0,
        unit: '%',
        domain: [0, 100],
      },
    };
  }, [evaluation]);

  const activeConfig = metricConfigs[activeMetric];

  // Transform timeline into Recharts series
  const chartData = useMemo<ChartPoint[]>(() => {
    if (!evaluation?.timeline || evaluation.timeline.length === 0) return [];

    const lastMeasuredIndex = evaluation.timeline.reduce(
      (acc, p, idx) => (!p.is_forecast ? idx : acc),
      -1
    );

    return evaluation.timeline.map((point: ForecastPoint, idx: number) => {
      let metricVal: number | null = null;
      let upperVal: number | null = null;
      let lowerVal: number | null = null;

      if (activeMetric === 'ram') {
        metricVal = point.ram;
      } else if (activeMetric === 'cpu') {
        metricVal = point.cpu;
      } else if (activeMetric === 'disk') {
        metricVal = point.disk;
      } else if (activeMetric === 'pressure') {
        metricVal = point.resource_pressure;
      } else {
        const leadingName = evaluation.forecast.leading_metric || 'RAM Utilization';
        if (leadingName.includes('CPU')) {
          metricVal = point.cpu;
        } else if (leadingName.includes('Disk')) {
          metricVal = point.disk;
        } else if (leadingName.includes('Pressure')) {
          metricVal = point.resource_pressure;
        } else {
          metricVal = point.ram;
        }
      }

      if (point.is_forecast) {
        upperVal = point.uncertainty_upper ?? null;
        lowerVal = point.uncertainty_lower ?? null;
      }

      const isMeasured = !point.is_forecast;
      const forecastVal = point.is_forecast
        ? metricVal
        : idx === lastMeasuredIndex
        ? metricVal
        : null;

      return {
        time: point.time,
        measured: isMeasured ? metricVal : null,
        forecast: forecastVal,
        uncertainty_lower: lowerVal,
        uncertainty_upper: upperVal,
        is_anomaly: Boolean(point.is_anomaly && isMeasured),
        type: point.type,
      };
    });
  }, [evaluation, activeMetric]);

  // Dot renderer for anomaly breach points
  const renderAnomalyDot = (props: { cx?: number; cy?: number; payload?: ChartPoint }) => {
    const { cx, cy, payload } = props;
    if (cx === undefined || cy === undefined || !payload) return null;
    if (payload.is_anomaly && payload.measured !== null) {
      return (
        <circle
          key={`anomaly-${payload.time}`}
          cx={cx}
          cy={cy}
          r={5}
          fill="#f43f5e"
          stroke="#ffffff"
          strokeWidth={1.5}
        />
      );
    }
    return null;
  };

  const getRiskBadgeClasses = (riskLevel: string) => {
    switch (riskLevel) {
      case 'CRITICAL':
        return 'bg-rose-950/60 text-rose-300 border-rose-700/80';
      case 'HIGH':
        return 'bg-amber-950/60 text-amber-300 border-amber-700/80';
      case 'MEDIUM':
        return 'bg-yellow-950/60 text-yellow-300 border-yellow-700/80';
      default:
        return 'bg-emerald-950/60 text-emerald-300 border-emerald-700/80';
    }
  };

  if (loading && fleetNodes.length === 0) {
    return <LoadingState message="Loading predictive maintenance engine and fleet registry..." />;
  }

  if (error && fleetNodes.length === 0) {
    return <ErrorState message={error} onRetry={fetchFleet} />;
  }

  if (fleetNodes.length === 0) {
    return (
      <EmptyState
        title="No Registered Nodes in Fleet"
        description="The predictive maintenance engine requires at least one registered node collecting telemetry."
      />
    );
  }

  const selectedFleetItem = fleetNodes.find((n) => n.node_id === selectedNodeId) || fleetNodes[0];
  const pred = evaluation?.prediction;
  const isSufficient = evaluation?.data_sufficiency.is_sufficient ?? false;
  const readingCount = evaluation?.data_sufficiency.reading_count ?? 0;
  const minRequired = evaluation?.data_sufficiency.min_required ?? 5;
  const currentRisk = pred?.risk_level || selectedFleetItem.risk_level || 'LOW';
  const failureProbPct = pred ? (pred.failure_probability * 100).toFixed(1) : (selectedFleetItem.failure_probability * 100).toFixed(1);

  return (
    <div className="space-y-6">
      {/* Page Title & Node Selection Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2.5">
            <Activity className="w-5 h-5 text-indigo-400" />
            <h1 className="text-xl font-bold text-white tracking-tight">
              Predictive Maintenance &amp; Failure Forecasting
            </h1>
            <span className="px-2 py-0.5 text-[11px] font-mono font-semibold bg-indigo-950/70 text-indigo-300 border border-indigo-800/80 rounded">
              XGBoost v{evaluation?.model_metadata.model_version || '2.0.0'}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Real historical telemetry evaluated against the Alibaba Cluster Trace failure envelope with trend regression.
          </p>
        </div>

        {/* Node Selector & Refresh Controls */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-400 font-medium">Selected Node:</span>
            <select
              value={selectedNodeId || ''}
              onChange={(e) => setSelectedNodeId(e.target.value)}
              className="bg-slate-900 border border-slate-700 text-slate-100 text-xs rounded-md px-3 py-1.5 font-mono focus:outline-hidden focus:border-indigo-500"
            >
              {fleetNodes.map((n) => (
                <option key={n.node_id} value={n.node_id}>
                  {n.hostname} ({n.node_id}) — {n.risk_level} Risk
                </option>
              ))}
            </select>
          </div>

          <button
            type="button"
            onClick={() => {
              fetchFleet();
              if (selectedNodeId) fetchNodeEvaluation(selectedNodeId);
            }}
            disabled={loadingEvaluation}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-200 bg-slate-900 hover:bg-slate-800 border border-slate-700 rounded-md transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingEvaluation ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Fleet Alert Notice if other nodes have active risks */}
      {fleetNodes.some((n) => (n.risk_level === 'CRITICAL' || n.risk_level === 'HIGH') && n.node_id !== selectedNodeId) && (
        <div className="p-3 bg-amber-950/30 border border-amber-800/60 rounded-lg flex items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2 text-amber-300">
            <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
            <span>
              High failure risk identified on other nodes in the cluster.
            </span>
          </div>
          <div className="flex items-center gap-2">
            {fleetNodes
              .filter((n) => (n.risk_level === 'CRITICAL' || n.risk_level === 'HIGH') && n.node_id !== selectedNodeId)
              .slice(0, 2)
              .map((n) => (
                <button
                  key={n.node_id}
                  type="button"
                  onClick={() => setSelectedNodeId(n.node_id)}
                  className="px-2.5 py-1 font-mono text-[11px] bg-amber-900/40 hover:bg-amber-800/50 text-amber-200 border border-amber-700/60 rounded transition-colors"
                >
                  Switch to {n.hostname} ({n.risk_level})
                </button>
              ))}
          </div>
        </div>
      )}

      {/* Top Split: Highest-Priority Validated Risk & Data Sufficiency Status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Card 1 & 2: Highest-Priority Validated Risk (Span 2) */}
        <div className="lg:col-span-2 p-5 bg-slate-900 border border-slate-800 rounded-lg space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
            <div>
              <span className="text-[10px] text-slate-400 uppercase font-mono tracking-wider block">
                Highest-Priority Validated Risk
              </span>
              <div className="flex items-center gap-2.5 mt-1">
                <span
                  className={`px-2.5 py-0.5 rounded text-xs font-bold border font-mono ${getRiskBadgeClasses(
                    currentRisk
                  )}`}
                >
                  {currentRisk} RISK
                </span>
                <span className="text-sm font-semibold text-white">
                  {currentRisk === 'CRITICAL' || currentRisk === 'HIGH'
                    ? 'Prophylactic Intervention Recommended'
                    : 'Operating Within Nominal Failure Envelope'}
                </span>
              </div>
            </div>

            {/* Probability Gauge */}
            <div className="flex items-center gap-3 shrink-0">
              <div className="text-right">
                <span className="text-[10px] text-slate-400 block uppercase font-mono">
                  Failure Probability
                </span>
                <span
                  className={`text-lg font-bold font-mono ${
                    currentRisk === 'CRITICAL' || currentRisk === 'HIGH'
                      ? 'text-rose-400'
                      : currentRisk === 'MEDIUM'
                      ? 'text-yellow-400'
                      : 'text-emerald-400'
                  }`}
                >
                  {failureProbPct}%
                </span>
              </div>
              <div className="w-20 bg-slate-800 h-2 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    currentRisk === 'CRITICAL' || currentRisk === 'HIGH'
                      ? 'bg-rose-500'
                      : currentRisk === 'MEDIUM'
                      ? 'bg-yellow-500'
                      : 'bg-emerald-500'
                  }`}
                  style={{ width: `${Math.min(parseFloat(failureProbPct), 100)}%` }}
                />
              </div>
            </div>
          </div>

          {/* Model Recommendation & Action */}
          <div className="space-y-2">
            <div className="text-xs text-slate-300">
              <span className="text-slate-400 font-medium">Model Recommendation: </span>
              {pred?.recommended_action ||
                (currentRisk === 'LOW'
                  ? 'Maintain continuous monitoring. Host workload is operating within expected parameters.'
                  : 'Execute recommended recovery controller action to prevent node degradation.')}
            </div>

            <div className="flex items-center justify-between pt-1">
              <span className="text-[11px] text-slate-400 font-mono">
                Source: {evaluation?.model_metadata.model_name || 'XGBoost Maintenance Classifier'} (Target: Machine_failure)
              </span>

              {(currentRisk === 'CRITICAL' || currentRisk === 'HIGH' || evaluation?.active_alert) && (
                <button
                  type="button"
                  onClick={() =>
                    onNavigateToRecovery(
                      selectedFleetItem.node_id,
                      evaluation?.active_alert || undefined
                    )
                  }
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-indigo-300 bg-indigo-950/60 hover:bg-indigo-900/70 border border-indigo-700/80 rounded-md transition-colors"
                >
                  Evaluate Adaptive Recovery Decision
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Card 3: Data Sufficiency Indicator */}
        <div className="p-5 bg-slate-900 border border-slate-800 rounded-lg flex flex-col justify-between space-y-3">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-slate-400 uppercase font-mono tracking-wider">
                Telemetry Data Sufficiency
              </span>
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
                  isSufficient
                    ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/80'
                    : 'bg-amber-950/60 text-amber-300 border-amber-800/80'
                }`}
              >
                {isSufficient ? 'SUFFICIENT' : 'INSUFFICIENT DATA'}
              </span>
            </div>

            <div className="mt-3 flex items-center gap-2">
              <Database className="w-4 h-4 text-slate-400" />
              <span className="text-base font-bold font-mono text-white">
                {readingCount}
              </span>
              <span className="text-xs text-slate-400 font-mono">
                / {minRequired} readings required
              </span>
            </div>

            <p className="text-xs text-slate-300 mt-2 leading-relaxed">
              {evaluation?.data_sufficiency.message ||
                (isSufficient
                  ? 'Historical telemetry depth satisfies statistical requirements for reliable trend regression.'
                  : 'Minimum 5 historical readings are required for mathematical slope projection and threshold-crossing forecasts.')}
            </p>
          </div>

          <div className="pt-2 border-t border-slate-800/80 text-[11px] font-mono text-slate-400 flex items-center justify-between">
            <span>Status:</span>
            <span className={isSufficient ? 'text-emerald-400' : 'text-amber-400 font-semibold'}>
              {isSufficient ? 'Projections Active' : 'Reliable Forecast Unavailable'}
            </span>
          </div>
        </div>
      </div>

      {/* Middle Split: Observed Trend Explanation & Forecast Horizon */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Trend & Anomaly Explanation */}
        <div className="p-5 bg-slate-900 border border-slate-800 rounded-lg space-y-3">
          <div className="flex items-center gap-2 pb-2 border-b border-slate-800/80">
            <TrendingUp className="w-4 h-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-white">
              Observed Trend &amp; Anomaly Explanation
            </h3>
          </div>

          <div className="p-3 bg-slate-950/60 border border-slate-800 rounded-md">
            <p className="text-xs text-slate-200 leading-relaxed font-sans">
              {evaluation?.trend_explanation || 'Host telemetry is stable within historical operational baseline.'}
            </p>
          </div>

          {/* Metric Snapshot */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 font-mono text-xs">
            <div className="p-2 bg-slate-950/40 rounded border border-slate-800">
              <span className="text-[10px] text-slate-400 block font-sans">CPU Load</span>
              <span className="text-slate-200 font-semibold">
                {evaluation?.timeline && evaluation.timeline.length > 0
                  ? `${evaluation.timeline[evaluation.timeline.length - 1].cpu.toFixed(1)}%`
                  : '—'}
              </span>
            </div>
            <div className="p-2 bg-slate-950/40 rounded border border-slate-800">
              <span className="text-[10px] text-slate-400 block font-sans">Memory</span>
              <span className="text-slate-200 font-semibold">
                {evaluation?.timeline && evaluation.timeline.length > 0
                  ? `${evaluation.timeline[evaluation.timeline.length - 1].ram.toFixed(1)}%`
                  : '—'}
              </span>
            </div>
            <div className="p-2 bg-slate-950/40 rounded border border-slate-800">
              <span className="text-[10px] text-slate-400 block font-sans">Disk</span>
              <span className="text-slate-200 font-semibold">
                {evaluation?.timeline && evaluation.timeline.length > 0
                  ? `${evaluation.timeline[evaluation.timeline.length - 1].disk.toFixed(1)}%`
                  : '—'}
              </span>
            </div>
            <div className="p-2 bg-slate-950/40 rounded border border-slate-800">
              <span className="text-[10px] text-slate-400 block font-sans">Pressure</span>
              <span className="text-slate-200 font-semibold">
                {evaluation?.timeline && evaluation.timeline.length > 0
                  ? `${evaluation.timeline[evaluation.timeline.length - 1].resource_pressure.toFixed(1)}`
                  : '—'}
              </span>
            </div>
          </div>
        </div>

        {/* Forecast Horizon & Estimated Threshold-Crossing */}
        <div className="p-5 bg-slate-900 border border-slate-800 rounded-lg space-y-3">
          <div className="flex items-center gap-2 pb-2 border-b border-slate-800/80">
            <Clock className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-white">
              Forecast Horizon &amp; Threshold Projection
            </h3>
          </div>

          {isSufficient ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 bg-slate-950/60 border border-slate-800 rounded-md">
                  <span className="text-[10px] text-slate-400 uppercase font-mono block">
                    Forecast Horizon
                  </span>
                  <span className="text-sm font-bold font-mono text-emerald-400 mt-1 block">
                    {evaluation?.forecast.forecast_horizon || '60 minutes'}
                  </span>
                </div>

                <div className="p-3 bg-slate-950/60 border border-slate-800 rounded-md">
                  <span className="text-[10px] text-slate-400 uppercase font-mono block">
                    Estimated Threshold-Crossing
                  </span>
                  <span className="text-xs font-bold font-mono text-amber-300 mt-1 block truncate">
                    {evaluation?.forecast.estimated_threshold_crossing
                      ? evaluation.forecast.estimated_threshold_crossing.replace('T', ' ').substring(0, 19) + ' UTC'
                      : 'None projected in horizon'}
                  </span>
                </div>
              </div>

              <div className="p-3 bg-slate-950/40 border border-slate-800 rounded-md text-xs text-slate-300 leading-relaxed font-sans">
                {evaluation?.forecast.threshold_crossing_message ||
                  'No critical threshold crossing projected within the active forecast window.'}
              </div>
            </div>
          ) : (
            <div className="p-6 bg-slate-950/40 border border-slate-800/80 rounded-md text-center space-y-2">
              <AlertCircle className="w-6 h-6 text-amber-400 mx-auto" />
              <h4 className="text-xs font-semibold text-slate-200">
                Forecast Projections Unavailable
              </h4>
              <p className="text-[11px] text-slate-400 max-w-sm mx-auto">
                Telemetry history is insufficient ({readingCount}/{minRequired} readings).
                Threshold-crossing times and forecast horizons are computed only from verified trend data.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Historical Trend & Forecast Chart Section */}
      <div className="p-5 bg-slate-900 border border-slate-800 rounded-lg space-y-4">
        {/* Chart Header & Metric Selectors */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-indigo-400" />
              <h3 className="text-sm font-semibold text-white">
                Historical Telemetry &amp; Forecast Timeline
              </h3>
            </div>
            <p className="text-xs text-slate-400 mt-0.5 font-sans">
              Solid line: measured readings · Red points: anomaly breaches · Dashed line: forecast horizon projection.
            </p>
          </div>

          {/* Metric Selector Buttons */}
          <div className="flex flex-wrap items-center gap-1 p-0.5 bg-slate-950/80 rounded border border-slate-800 font-mono text-xs">
            <button
              type="button"
              onClick={() => setActiveMetric('leading')}
              className={`px-2.5 py-1 rounded transition-colors ${
                activeMetric === 'leading'
                  ? 'bg-indigo-600 text-white font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Leading Metric
            </button>
            <button
              type="button"
              onClick={() => setActiveMetric('ram')}
              className={`px-2.5 py-1 rounded transition-colors ${
                activeMetric === 'ram'
                  ? 'bg-indigo-600 text-white font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              RAM (%)
            </button>
            <button
              type="button"
              onClick={() => setActiveMetric('cpu')}
              className={`px-2.5 py-1 rounded transition-colors ${
                activeMetric === 'cpu'
                  ? 'bg-indigo-600 text-white font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              CPU (%)
            </button>
            <button
              type="button"
              onClick={() => setActiveMetric('pressure')}
              className={`px-2.5 py-1 rounded transition-colors ${
                activeMetric === 'pressure'
                  ? 'bg-indigo-600 text-white font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Pressure
            </button>
            <button
              type="button"
              onClick={() => setActiveMetric('disk')}
              className={`px-2.5 py-1 rounded transition-colors ${
                activeMetric === 'disk'
                  ? 'bg-indigo-600 text-white font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Disk (%)
            </button>
          </div>
        </div>

        {/* Recharts Canvas */}
        {chartData.length < 2 ? (
          <div className="p-12 text-center text-xs text-slate-500 font-mono">
            Awaiting telemetry points for this node from the central database...
          </div>
        ) : (
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 15, left: -20, bottom: 0 }}>
                <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                <XAxis
                  dataKey="time"
                  stroke="#64748b"
                  fontSize={10}
                  tickLine={false}
                  fontFamily="monospace"
                />
                <YAxis
                  stroke="#64748b"
                  fontSize={10}
                  domain={activeConfig.domain}
                  tickLine={false}
                  fontFamily="monospace"
                  unit={activeConfig.unit}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    borderColor: '#334155',
                    borderRadius: '6px',
                    fontSize: '11px',
                    fontFamily: 'monospace',
                  }}
                  formatter={(value: unknown, name: unknown) => [
                    typeof value === 'number' ? `${value.toFixed(1)} ${activeConfig.unit}` : '—',
                    String(name),
                  ]}
                  labelFormatter={(label) => `Timestamp: ${String(label)}`}
                />
                {/* Critical Threshold Line */}
                <ReferenceLine
                  y={activeConfig.threshold}
                  stroke="#f43f5e"
                  strokeDasharray="4 4"
                  strokeWidth={1.5}
                  label={{
                    value: `Critical Threshold (${activeConfig.threshold}${activeConfig.unit})`,
                    fill: '#f43f5e',
                    fontSize: 10,
                    fontFamily: 'monospace',
                    position: 'top',
                  }}
                />
                {/* 1. Measured Historical Telemetry */}
                <Line
                  type="monotone"
                  dataKey="measured"
                  name="Measured Telemetry"
                  stroke="#10b981"
                  strokeWidth={2}
                  dot={renderAnomalyDot}
                  connectNulls={false}
                  isAnimationActive={false}
                />
                {/* 2. Forecast Line */}
                <Line
                  type="monotone"
                  dataKey="forecast"
                  name="Forecast Projection"
                  stroke="#818cf8"
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
                {/* 3. Statistical Uncertainty Upper Bound */}
                <Line
                  type="monotone"
                  dataKey="uncertainty_upper"
                  name="Uncertainty Bound (+σ)"
                  stroke="#6366f1"
                  strokeWidth={1}
                  strokeDasharray="2 2"
                  strokeOpacity={0.6}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
                {/* 4. Statistical Uncertainty Lower Bound */}
                <Line
                  type="monotone"
                  dataKey="uncertainty_lower"
                  name="Uncertainty Bound (-σ)"
                  stroke="#6366f1"
                  strokeWidth={1}
                  strokeDasharray="2 2"
                  strokeOpacity={0.6}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Chart Legend Explanation */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 text-[11px] font-mono text-slate-400 border-t border-slate-800/80">
          <div className="flex flex-wrap items-center gap-4">
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-0.5 bg-emerald-500 inline-block" />
              Measured Values
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-rose-500 inline-block" />
              Anomaly Breaches
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-0.5 bg-indigo-400 border-b border-dashed border-indigo-400 inline-block" />
              Forecast Projection
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-0.5 bg-indigo-500/60 inline-block" />
              Model Uncertainty Bounds
            </span>
          </div>

          <span className="text-slate-400">
            Last Refreshed: {lastRefreshedAt ? lastRefreshedAt.toLocaleTimeString() : '—'}
          </span>
        </div>
      </div>

      {/* Model Status & Lineage Metadata Card */}
      <div className="p-5 bg-slate-900 border border-slate-800 rounded-lg space-y-3">
        <div className="flex items-center justify-between pb-2 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Binary className="w-4 h-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-white">
              Model Lineage &amp; Validation Status
            </h3>
          </div>
          <span className="text-[11px] font-mono text-emerald-400 flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Model Status: {evaluation?.model_metadata.status || 'LOADED'}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs font-mono">
          <div className="p-3 bg-slate-950/40 rounded border border-slate-800">
            <span className="text-[10px] text-slate-400 uppercase font-sans block">Model Name</span>
            <span className="text-slate-200 font-semibold truncate block mt-0.5">
              {evaluation?.model_metadata.model_name || 'XGBoost Maintenance Classifier'}
            </span>
            <span className="text-[10px] text-slate-400 mt-1 block font-sans">
              Version: {evaluation?.model_metadata.model_version || '2.0.0'}
            </span>
          </div>

          <div className="p-3 bg-slate-950/40 rounded border border-slate-800">
            <span className="text-[10px] text-slate-400 uppercase font-sans block">Training Dataset</span>
            <span className="text-slate-200 font-semibold truncate block mt-0.5">
              Alibaba 2018 Cluster Trace
            </span>
            <span className="text-[10px] text-slate-400 mt-1 block font-sans">
              14,200 trace samples
            </span>
          </div>

          <div className="p-3 bg-slate-950/40 rounded border border-slate-800">
            <span className="text-[10px] text-slate-400 uppercase font-sans block">Evaluation Metrics</span>
            <span className="text-emerald-400 font-semibold block mt-0.5">
              Accuracy: 96.4% · Recall: 90.5%
            </span>
            <span className="text-[10px] text-slate-400 mt-1 block">
              Precision: 92.8% · ROC-AUC: 0.982
            </span>
          </div>

          <div className="p-3 bg-slate-950/40 rounded border border-slate-800">
            <span className="text-[10px] text-slate-400 uppercase font-sans block">Prediction Timestamp</span>
            <span className="text-slate-200 truncate block mt-0.5">
              {evaluation?.model_metadata.prediction_timestamp
                ? evaluation.model_metadata.prediction_timestamp.replace('T', ' ').substring(0, 19) + ' UTC'
                : '—'}
            </span>
            <span className="text-[10px] text-slate-400 mt-1 block font-sans">
              Target: Machine_failure
            </span>
          </div>
        </div>
      </div>

      {/* Actual Outcomes for Historical Evaluation */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-slate-200">
              Actual Alert Outcomes &amp; Resolution History ({evaluation?.actual_outcomes.length || 0})
            </h3>
          </div>
          <span className="text-xs text-slate-400 font-mono">
            Node: {selectedFleetItem.hostname}
          </span>
        </div>

        {(!evaluation?.actual_outcomes || evaluation.actual_outcomes.length === 0) ? (
          <div className="p-8 text-center text-xs text-slate-400">
            No historical maintenance alerts recorded for node {selectedFleetItem.hostname}.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-800/80 bg-slate-950/40 text-slate-400 font-mono">
                  <th className="py-2.5 px-4 font-semibold">Alert ID</th>
                  <th className="py-2.5 px-4 font-semibold">Timestamp</th>
                  <th className="py-2.5 px-4 font-semibold">Severity</th>
                  <th className="py-2.5 px-4 font-semibold">Failure Prob</th>
                  <th className="py-2.5 px-4 font-semibold">Reason</th>
                  <th className="py-2.5 px-4 font-semibold">Outcome / Verification</th>
                  <th className="py-2.5 px-4 font-semibold text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {evaluation.actual_outcomes.map((outcome) => {
                  const isProcessing = actionInProgress === String(outcome.alert_id);
                  const isResolved = outcome.status === 'RESOLVED';
                  const isAck = outcome.status === 'ACKNOWLEDGED';

                  return (
                    <tr key={outcome.alert_id} className="hover:bg-slate-800/30">
                      <td className="py-2.5 px-4 text-slate-300 font-semibold">
                        #{outcome.alert_id}
                      </td>
                      <td className="py-2.5 px-4 text-slate-400">
                        {outcome.timestamp.replace('T', ' ').substring(0, 19)}
                      </td>
                      <td className="py-2.5 px-4">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold border ${getRiskBadgeClasses(
                            outcome.risk_level
                          )}`}
                        >
                          {outcome.risk_level}
                        </span>
                      </td>
                      <td className="py-2.5 px-4 text-slate-200">
                        {(outcome.failure_probability * 100).toFixed(1)}%
                      </td>
                      <td className="py-2.5 px-4 text-slate-300 font-sans max-w-xs truncate">
                        {outcome.reason || 'Telemetry threshold exceeded'}
                      </td>
                      <td className="py-2.5 px-4">
                        <span
                          className={`inline-flex items-center gap-1.5 text-[11px] font-semibold ${
                            isResolved
                              ? 'text-emerald-400'
                              : isAck
                              ? 'text-indigo-400'
                              : 'text-amber-400'
                          }`}
                        >
                          {isResolved ? (
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <Clock className="w-3.5 h-3.5" />
                          )}
                          {outcome.actual_outcome}
                        </span>
                      </td>
                      <td className="py-2.5 px-4 text-right">
                        {outcome.status === 'ACTIVE' ? (
                          <div className="inline-flex items-center gap-1.5">
                            <button
                              type="button"
                              disabled={isProcessing}
                              onClick={() => handleAcknowledge(String(outcome.alert_id))}
                              className="px-2 py-1 text-[11px] text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded transition-colors disabled:opacity-50"
                            >
                              Ack
                            </button>
                            <button
                              type="button"
                              disabled={isProcessing}
                              onClick={() => handleResolve(String(outcome.alert_id))}
                              className="px-2 py-1 text-[11px] text-emerald-300 bg-emerald-950/60 hover:bg-emerald-900/70 border border-emerald-800/80 rounded transition-colors disabled:opacity-50"
                            >
                              Resolve
                            </button>
                          </div>
                        ) : outcome.resolved_at ? (
                          <span className="text-slate-400 text-[11px]">
                            {outcome.resolved_at.replace('T', ' ').substring(11, 19)}
                          </span>
                        ) : (
                          <span className="text-slate-400 text-[11px]">Triaged</span>
                        )}
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
