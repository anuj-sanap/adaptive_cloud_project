import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Server,
  Search,
  RefreshCw,
  HardDrive,
  Cpu,
  Layers,
  Activity,
  ArrowRight,
  Shield,
  Clock,
  Database,
  Check,
  Copy,
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import { api } from '../../api/client';
import type { NodeItem, TelemetryRecord, HardwareInfo } from '../../types';
import { isGenuineNode } from '../../utils/nodes';
import { StatusIndicator, formatTimeAge } from '../common/StatusIndicator';
import { StaleDataBadge } from '../common/StaleDataBadge';
import { MetricCard } from '../common/MetricCard';
import { LoadingState } from '../common/LoadingState';
import { ErrorState } from '../common/ErrorState';
import { EmptyState } from '../common/EmptyState';

interface NodesViewProps {
  initialSelectedNodeId?: string;
  onNavigateToRecovery: (nodeId: string) => void;
}

type ChartMetricType = 'cpu' | 'ram' | 'disk';

interface ChartPoint {
  time: string;
  timestamp: string;
  cpu: number | null;
  ram: number | null;
  disk: number | null;
}

export const NodesView: React.FC<NodesViewProps> = ({
  initialSelectedNodeId,
  onNavigateToRecovery,
}) => {
  const [nodes, setNodes] = useState<NodeItem[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(initialSelectedNodeId || null);
  const [nodeDetails, setNodeDetails] = useState<(NodeItem & { recent_telemetry: TelemetryRecord[] }) | null>(null);
  const [loadingNodes, setLoadingNodes] = useState(true);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [onlyGenuine, setOnlyGenuine] = useState<boolean>(true);
  const [selectedMetric, setSelectedMetric] = useState<ChartMetricType>('cpu');
  const [refreshIntervalSec, setRefreshIntervalSec] = useState<number>(5);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [copiedId, setCopiedId] = useState(false);

  const inFlightRef = useRef(false);

  // Helper to calculate available disk space accurately without treating missing as zero
  const getAvailableDiskSpace = (
    latestTelemetry?: TelemetryRecord,
    hardwareInfo?: HardwareInfo
  ): { text: string; subtext?: string } => {
    if (!latestTelemetry) return { text: '—' };

    const m = latestTelemetry.metrics || {};

    // 1. Direct disk_free_gb on telemetry record or in raw metrics
    if (typeof latestTelemetry.disk_free_gb === 'number') {
      return { text: `${latestTelemetry.disk_free_gb.toFixed(1)} GB`, subtext: 'Free physical space' };
    }
    if (typeof m.disk_free_gb === 'number') {
      return { text: `${m.disk_free_gb.toFixed(1)} GB`, subtext: 'Free physical space' };
    }

    // 2. Compute from total - used
    const total = typeof m.disk_total_gb === 'number' ? m.disk_total_gb : hardwareInfo?.disk_total_gb;
    if (typeof total === 'number' && total > 0) {
      if (typeof m.disk_used_gb === 'number') {
        const free = Math.max(0, total - m.disk_used_gb);
        return { text: `${free.toFixed(1)} GB`, subtext: `of ${total.toFixed(0)} GB total` };
      }
      // 3. Compute from total * (1 - util/100)
      const util = typeof latestTelemetry.disk_utilization === 'number' ? latestTelemetry.disk_utilization : m.disk_utilization;
      if (typeof util === 'number') {
        const free = Math.max(0, total * (1 - util / 100));
        return { text: `${free.toFixed(1)} GB`, subtext: `of ${total.toFixed(0)} GB total` };
      }
    }

    return { text: '—' };
  };

  // Coordinated refresh function avoiding duplicate in-flight requests
  const refreshFleetData = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;

    try {
      setError(null);
      const data = await api.getNodes(onlyGenuine);
      const fetchedNodes = data.nodes || [];
      const cleanNodes = onlyGenuine ? fetchedNodes.filter(isGenuineNode) : fetchedNodes;
      setNodes(cleanNodes);
      setLastRefreshedAt(new Date());

      // Preserve selected node where possible; otherwise pick first available
      setSelectedNodeId((prev) => {
        if (prev && cleanNodes.some((n) => n.node_id === prev)) {
          return prev;
        }
        return cleanNodes.length > 0 ? cleanNodes[0].node_id : null;
      });
    } catch (err: unknown) {
      setError((err as Error).message || 'Failed to fetch node registry');
    } finally {
      inFlightRef.current = false;
      setLoadingNodes(false);
    }
  }, [onlyGenuine]);

  // Fetch individual node details whenever selected node changes or polls
  const fetchSelectedNodeDetails = useCallback(async (nodeId: string) => {
    if (!nodeId) return;
    try {
      const data = await api.getNodeDetails(nodeId, 30);
      setNodeDetails(data as unknown as NodeItem & { recent_telemetry: TelemetryRecord[] });
      setLastRefreshedAt(new Date());
    } catch {
      // Retain existing state during transient network hiccups
    } finally {
      setLoadingDetails(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    refreshFleetData();
  }, [refreshFleetData]);

  // Load details on selection change
  useEffect(() => {
    if (selectedNodeId) {
      setLoadingDetails(true);
      fetchSelectedNodeDetails(selectedNodeId);
    }
  }, [selectedNodeId, fetchSelectedNodeDetails]);

  // Configurable polling interval (default: 5s, configurable by user)
  useEffect(() => {
    if (refreshIntervalSec <= 0) return;

    const timer = setInterval(() => {
      refreshFleetData();
      if (selectedNodeId) {
        fetchSelectedNodeDetails(selectedNodeId);
      }
    }, refreshIntervalSec * 1000);

    return () => clearInterval(timer);
  }, [refreshIntervalSec, refreshFleetData, fetchSelectedNodeDetails, selectedNodeId]);

  const handleCopyNodeId = (id: string) => {
    if (navigator?.clipboard) {
      navigator.clipboard.writeText(id);
      setCopiedId(true);
      setTimeout(() => setCopiedId(false), 2000);
    }
  };

  // Filtered nodes list
  const visibleNodes = onlyGenuine ? nodes.filter(isGenuineNode) : nodes;
  const filteredNodes = visibleNodes.filter((n) => {
    const q = searchQuery.toLowerCase();
    const region = n.region || (n.hardware_info as Record<string, unknown>)?.region || '';
    return (
      n.node_id.toLowerCase().includes(q) ||
      (n.hostname || '').toLowerCase().includes(q) ||
      (n.operating_system || '').toLowerCase().includes(q) ||
      String(region).toLowerCase().includes(q)
    );
  });

  const selectedNode = nodes.find((n) => n.node_id === selectedNodeId) || nodeDetails;
  const latestTelemetry = nodeDetails?.recent_telemetry?.[0] || selectedNode?.latest_telemetry;

  // Extract raw metrics dictionary safely
  let latestRawMetrics: Record<string, unknown> = {};
  if (latestTelemetry) {
    try {
      if (typeof latestTelemetry.raw_metrics === 'string') {
        latestRawMetrics = JSON.parse(latestTelemetry.raw_metrics);
      } else if (latestTelemetry.raw_metrics && typeof latestTelemetry.raw_metrics === 'object') {
        latestRawMetrics = latestTelemetry.raw_metrics as Record<string, unknown>;
      } else if (latestTelemetry.metrics && typeof latestTelemetry.metrics === 'object') {
        latestRawMetrics = latestTelemetry.metrics as Record<string, unknown>;
      }
    } catch {
      latestRawMetrics = {};
    }
  }

  // Real current metric values without inventing or defaulting missing to zero
  const currentCpu = typeof latestTelemetry?.cpu_utilization === 'number'
    ? latestTelemetry.cpu_utilization
    : (typeof latestRawMetrics.cpu_utilization === 'number' ? latestRawMetrics.cpu_utilization : null);

  const currentRam = typeof latestTelemetry?.ram_utilization === 'number'
    ? latestTelemetry.ram_utilization
    : (typeof latestRawMetrics.ram_utilization === 'number' ? latestRawMetrics.ram_utilization : null);

  const currentDisk = typeof latestTelemetry?.disk_utilization === 'number'
    ? latestTelemetry.disk_utilization
    : (typeof latestRawMetrics.disk_utilization === 'number' ? latestRawMetrics.disk_utilization : null);

  const diskSpaceInfo = getAvailableDiskSpace(latestTelemetry, selectedNode?.hardware_info);

  // Format real historical telemetry for Recharts without inventing fake records
  const chartData: ChartPoint[] = (nodeDetails?.recent_telemetry || [])
    .slice()
    .reverse()
    .map((record) => {
      let raw: Record<string, unknown> = {};
      try {
        if (typeof record.raw_metrics === 'string') {
          raw = JSON.parse(record.raw_metrics);
        } else if (record.raw_metrics && typeof record.raw_metrics === 'object') {
          raw = record.raw_metrics as Record<string, unknown>;
        } else if (record.metrics && typeof record.metrics === 'object') {
          raw = record.metrics as Record<string, unknown>;
        }
      } catch {
        raw = {};
      }

      const timeStr = record.timestamp
        ? record.timestamp.replace('T', ' ').substring(11, 19)
        : '';

      const c = typeof record.cpu_utilization === 'number'
        ? record.cpu_utilization
        : (typeof raw.cpu_utilization === 'number' ? raw.cpu_utilization : null);

      const r = typeof record.ram_utilization === 'number'
        ? record.ram_utilization
        : (typeof raw.ram_utilization === 'number' ? raw.ram_utilization : null);

      const d = typeof record.disk_utilization === 'number'
        ? record.disk_utilization
        : (typeof raw.disk_utilization === 'number' ? raw.disk_utilization : null);

      return {
        time: timeStr,
        timestamp: record.timestamp,
        cpu: c,
        ram: r,
        disk: d,
      };
    });

  // Single chart configuration mapping
  const metricConfigs = {
    cpu: {
      label: 'CPU Utilization',
      unit: '%',
      stroke: '#10b981', // emerald
      dataKey: 'cpu' as const,
      domain: [0, 100],
    },
    ram: {
      label: 'Memory Utilization',
      unit: '%',
      stroke: '#6366f1', // indigo
      dataKey: 'ram' as const,
      domain: [0, 100],
    },
    disk: {
      label: 'Disk Utilization',
      unit: '%',
      stroke: '#f59e0b', // amber
      dataKey: 'disk' as const,
      domain: [0, 100],
    },
  };

  const activeConfig = metricConfigs[selectedMetric];

  // Display only location metadata that the operator configured.
  const getNodeLocation = (node?: NodeItem | null): string => {
    if (!node) return 'Not configured';
    return (
      node.location_label ||
      node.region ||
      ((node.hardware_info as Record<string, unknown>)?.region as string | undefined) ||
      'Not configured'
    );
  };

  return (
    <div className="space-y-6">
      {/* Header with Configurable Refresh & Separate Timestamps */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">Nodes &amp; Real Telemetry</h1>
          <p className="text-xs text-slate-400 mt-1">
            Registered edge nodes, hardware resource metrics, and individual telemetry streams.
          </p>
        </div>

        {/* Polling Interval Controls & Last Refresh Indicator */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <Clock className="w-3.5 h-3.5 text-slate-500" />
            <span className="font-mono text-[11px]">
              Refresh:
            </span>
            <select
              value={refreshIntervalSec}
              onChange={(e) => setRefreshIntervalSec(Number(e.target.value))}
              className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded px-2 py-1 font-mono focus:outline-hidden"
              title="Configure backend polling frequency"
            >
              <option value={5}>5s (Default)</option>
              <option value={10}>10s</option>
              <option value={30}>30s</option>
              <option value={0}>Paused</option>
            </select>
          </div>

          {/* Last successful refresh timestamp (shown separately from telemetry timestamp) */}
          <span className="text-[11px] text-slate-400 font-mono">
            {lastRefreshedAt ? `Refreshed ${lastRefreshedAt.toLocaleTimeString()}` : 'Connecting...'}
          </span>

          <button
            type="button"
            onClick={() => {
              refreshFleetData();
              if (selectedNodeId) fetchSelectedNodeDetails(selectedNodeId);
            }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-200 bg-slate-900 hover:bg-slate-800 border border-slate-700 rounded transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Sync Now
          </button>
        </div>
      </div>

      {error && !nodes.length && <ErrorState message={error} onRetry={refreshFleetData} />}

      {/* 2-Column Responsive Layout: Node Selector (Left) & Node Details (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Registered Node Registry Selector (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          <div className="flex items-center justify-between px-1">
            <span className="text-xs font-semibold text-slate-300">
              Registered Devices ({filteredNodes.length})
            </span>
            <label className="flex items-center gap-1.5 cursor-pointer text-[11px] text-slate-400 select-none hover:text-white transition-colors">
              <input
                type="checkbox"
                checked={onlyGenuine}
                onChange={(e) => setOnlyGenuine(e.target.checked)}
                className="rounded bg-slate-950 border-slate-700 text-indigo-500 focus:ring-0 focus:ring-offset-0 cursor-pointer"
              />
              <span className="font-medium">Genuine Only</span>
            </label>
          </div>

          <div className="flex items-center gap-2 p-2.5 bg-slate-900 border border-slate-800 rounded-lg">
            <Search className="w-4 h-4 text-slate-500 shrink-0" />
            <input
              type="text"
              placeholder="Search by ID, hostname, region, or OS..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-transparent border-none text-xs text-slate-200 placeholder-slate-500 focus:outline-hidden w-full font-mono"
            />
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden divide-y divide-slate-800/60 max-h-[640px] overflow-y-auto">
            {loadingNodes && !nodes.length ? (
              <div className="p-8">
                <LoadingState message="Polling node registry..." />
              </div>
            ) : filteredNodes.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  title="No nodes found"
                  description={
                    searchQuery
                      ? 'No registered nodes match your filter criteria'
                      : 'No edge nodes registered yet'
                  }
                />
              </div>
            ) : (
              filteredNodes.map((n) => {
                const isSelected = n.node_id === selectedNodeId;
                const nodeLocation = getNodeLocation(n);

                return (
                  <button
                    key={n.node_id}
                    type="button"
                    onClick={() => setSelectedNodeId(n.node_id)}
                    className={`w-full text-left p-3.5 transition-colors flex items-center justify-between gap-3 ${
                      isSelected
                        ? 'bg-indigo-950/30 border-l-2 border-indigo-500'
                        : 'hover:bg-slate-800/40'
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-sans text-xs font-semibold text-slate-200 truncate">
                          {n.hostname || n.node_id}
                        </span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-400 font-mono">
                          {nodeLocation}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-1 truncate font-mono">
                        {n.node_id}
                      </p>
                    </div>

                    <div className="shrink-0 text-right">
                      <StatusIndicator status={n.status} lastSeen={n.last_heartbeat || n.last_seen} showAge={false} />
                      <span className="block text-[10px] text-slate-500 mt-1 font-mono">
                        {formatTimeAge(n.last_heartbeat || n.last_seen)}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Individual Node Details & Historical Metrics (7 cols) */}
        <div className="lg:col-span-7 space-y-5">
          {!selectedNode ? (
            <div className="p-12 bg-slate-900 border border-slate-800 rounded-lg text-center">
              <Server className="w-8 h-8 text-slate-500 mx-auto mb-2" />
              <p className="text-sm font-medium text-slate-300">Select a node to inspect telemetry</p>
              <p className="text-xs text-slate-500 mt-1">
                Choose any registered agent from the fleet registry on the left.
              </p>
            </div>
          ) : (
            <>
              {/* Selected Node Summary Card: Hostname, Stable Node ID, Region, Status, Timestamps */}
              <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 pb-3 border-b border-slate-800">
                  <div className="space-y-1">
                    {/* Hostname & Node ID */}
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-base font-bold text-white font-sans">
                        {selectedNode.hostname || selectedNode.node_id}
                      </h2>
                      <StatusIndicator status={selectedNode.status} lastSeen={selectedNode.last_heartbeat || selectedNode.last_seen} />
                      <StaleDataBadge timestamp={latestTelemetry?.timestamp} />
                    </div>

                    {/* Stable Node ID with Copy */}
                    <div className="flex items-center gap-1.5 text-xs text-slate-400 font-mono">
                      <span>ID:</span>
                      <span className="text-slate-200 font-semibold">{selectedNode.node_id}</span>
                      <button
                        type="button"
                        onClick={() => handleCopyNodeId(selectedNode.node_id)}
                        className="text-slate-500 hover:text-slate-300 p-0.5 rounded transition-colors"
                        title="Copy stable node ID"
                      >
                        {copiedId ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                      </button>
                    </div>

                    {/* Configured Location & OS */}
                    <p className="text-xs text-slate-400">
                      Location: <span className="text-slate-200 font-mono font-medium">{getNodeLocation(selectedNode)}</span> · IP:{' '}
                      <span className="font-mono text-slate-300">{selectedNode.ip_address || 'Not reported'}</span> · OS:{' '}
                      <span className="text-slate-300">{selectedNode.operating_system || 'Unknown'}</span>
                    </p>
                  </div>

                  {/* Adaptive Recovery Action Button */}
                  <button
                    type="button"
                    onClick={() => onNavigateToRecovery(selectedNode.node_id)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-indigo-300 bg-indigo-950/40 hover:bg-indigo-900/50 border border-indigo-800/60 rounded transition-colors shrink-0"
                  >
                    Adaptive Recovery Lab
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>

                {/* Separate Timestamps: Last Successful Telemetry & UI Refresh */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono bg-slate-950/40 p-2.5 rounded border border-slate-800/80">
                  <div className="flex items-center gap-1.5 text-slate-400">
                    <Activity className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                    <span className="text-slate-400 font-sans">Telemetry Received:</span>
                    <span className="text-slate-200 truncate">
                      {latestTelemetry?.timestamp
                        ? `${latestTelemetry.timestamp.replace('T', ' ').substring(0, 19)} UTC (${formatTimeAge(latestTelemetry.timestamp)})`
                        : selectedNode.last_seen
                        ? `${selectedNode.last_seen.replace('T', ' ').substring(0, 19)} UTC (${formatTimeAge(selectedNode.last_seen)})`
                        : 'No telemetry recorded'}
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5 text-slate-400">
                    <Clock className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                    <span className="text-slate-400 font-sans">Last Heartbeat:</span>
                    <span className="text-slate-200 truncate">
                      {selectedNode.last_heartbeat
                        ? `${selectedNode.last_heartbeat.replace('T', ' ').substring(0, 19)} UTC (${formatTimeAge(selectedNode.last_heartbeat)})`
                        : 'No heartbeat recorded'}
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5 text-slate-400 sm:justify-end">
                    <Clock className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                    <span className="text-slate-400 font-sans">Data Refresh:</span>
                    <span className="text-slate-200">
                      {lastRefreshedAt ? lastRefreshedAt.toLocaleTimeString() : '—'}
                    </span>
                  </div>
                </div>

                {/* Hardware Spec Badges */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono pt-1">
                  <div className="p-2 bg-slate-950/40 rounded border border-slate-800">
                    <span className="text-[10px] text-slate-400 block uppercase font-sans">CPU Cores</span>
                    <span className="text-slate-200 font-semibold">
                      {selectedNode.hardware_info?.cpu_count_logical
                        ? `${selectedNode.hardware_info.cpu_count_logical} Cores`
                        : '—'}
                    </span>
                  </div>
                  <div className="p-2 bg-slate-950/40 rounded border border-slate-800">
                    <span className="text-[10px] text-slate-400 block uppercase font-sans">Total Memory</span>
                    <span className="text-slate-200 font-semibold">
                      {selectedNode.hardware_info?.ram_total_mb
                        ? `${(selectedNode.hardware_info.ram_total_mb / 1024).toFixed(1)} GB`
                        : '—'}
                    </span>
                  </div>
                  <div className="p-2 bg-slate-950/40 rounded border border-slate-800">
                    <span className="text-[10px] text-slate-400 block uppercase font-sans">Total Storage</span>
                    <span className="text-slate-200 font-semibold">
                      {selectedNode.hardware_info?.disk_total_gb
                        ? `${selectedNode.hardware_info.disk_total_gb.toFixed(0)} GB`
                        : '—'}
                    </span>
                  </div>
                  <div className="p-2 bg-slate-950/40 rounded border border-slate-800">
                    <span className="text-[10px] text-slate-400 block uppercase font-sans">Configured Location</span>
                    <span className="text-slate-200 font-semibold">
                      {getNodeLocation(selectedNode)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Current Metrics: CPU, Memory, Disk, and Available Disk Space */}
              {/* NOTE: Missing or stale readings are displayed as '—', NEVER as false 0.0 */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {/* 1. CPU Utilization */}
                <MetricCard
                  label="CPU Load"
                  value={currentCpu !== null ? currentCpu.toFixed(1) : '—'}
                  unit={currentCpu !== null ? '%' : ''}
                  icon={<Cpu className="w-3.5 h-3.5" />}
                  badge={{
                    text:
                      currentCpu !== null
                        ? currentCpu > 80
                          ? 'High'
                          : 'Normal'
                        : 'No Data',
                    variant:
                      currentCpu !== null
                        ? currentCpu > 80
                          ? 'danger'
                          : 'success'
                        : 'neutral',
                  }}
                />

                {/* 2. Memory Utilization */}
                <MetricCard
                  label="Memory Usage"
                  value={currentRam !== null ? currentRam.toFixed(1) : '—'}
                  unit={currentRam !== null ? '%' : ''}
                  icon={<Layers className="w-3.5 h-3.5" />}
                  badge={{
                    text:
                      currentRam !== null
                        ? currentRam > 85
                          ? 'High'
                          : 'Normal'
                        : 'No Data',
                    variant:
                      currentRam !== null
                        ? currentRam > 85
                          ? 'warning'
                          : 'success'
                        : 'neutral',
                  }}
                />

                {/* 3. Disk Utilization */}
                <MetricCard
                  label="Disk Usage"
                  value={currentDisk !== null ? currentDisk.toFixed(1) : '—'}
                  unit={currentDisk !== null ? '%' : ''}
                  icon={<HardDrive className="w-3.5 h-3.5" />}
                  badge={{
                    text:
                      currentDisk !== null
                        ? currentDisk > 90
                          ? 'Critical'
                          : 'Normal'
                        : 'No Data',
                    variant:
                      currentDisk !== null
                        ? currentDisk > 90
                          ? 'danger'
                          : 'neutral'
                        : 'neutral',
                  }}
                />

                {/* 4. Available Disk Space */}
                <MetricCard
                  label="Available Disk"
                  value={diskSpaceInfo.text}
                  subtext={diskSpaceInfo.subtext}
                  icon={<Database className="w-3.5 h-3.5" />}
                  badge={{
                    text: diskSpaceInfo.text !== '—' ? 'Measured' : 'Unavailable',
                    variant: diskSpaceInfo.text !== '—' ? 'info' : 'neutral',
                  }}
                />
              </div>

              {/* One Historical Chart with Metric Selector (CPU, Memory, Disk) */}
              {/* Requirement: Keep ONE chart visible at a time */}
              <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3 pb-3 border-b border-slate-800/80">
                  <div className="flex items-center gap-2">
                    <Activity className="w-4 h-4 text-slate-400" />
                    <h3 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
                      Historical Metrics ({activeConfig.label})
                    </h3>
                  </div>

                  {/* Selector Tabs: Toggle between CPU, Memory, or Disk */}
                  <div className="flex items-center gap-1 p-0.5 bg-slate-950/60 rounded border border-slate-800 self-start sm:self-auto font-mono">
                    <button
                      type="button"
                      onClick={() => setSelectedMetric('cpu')}
                      className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                        selectedMetric === 'cpu'
                          ? 'bg-slate-800 text-emerald-400 font-semibold shadow-xs'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      CPU (%)
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelectedMetric('ram')}
                      className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                        selectedMetric === 'ram'
                          ? 'bg-slate-800 text-indigo-400 font-semibold shadow-xs'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      Memory (%)
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelectedMetric('disk')}
                      className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                        selectedMetric === 'disk'
                          ? 'bg-slate-800 text-amber-400 font-semibold shadow-xs'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      Disk (%)
                    </button>
                  </div>
                </div>

                {loadingDetails ? (
                  <div className="p-12 text-center text-xs text-indigo-400 font-mono animate-pulse">
                    Refreshing telemetry points from central database...
                  </div>
                ) : chartData.length < 2 ? (
                  <div className="p-12 text-center text-xs text-slate-500">
                    Awaiting sufficient telemetry records (past readings from central database)...
                  </div>
                ) : (
                  <div className="h-56 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
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
                          unit="%"
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#0f172a',
                            borderColor: '#334155',
                            borderRadius: '6px',
                            fontSize: '11px',
                            fontFamily: 'monospace',
                          }}
                          formatter={(value: unknown) => [
                            typeof value === 'number' ? `${value.toFixed(1)}%` : '—',
                            activeConfig.label,
                          ]}
                          labelFormatter={(label) => `Time: ${String(label)}`}
                        />
                        <Line
                          type="monotone"
                          dataKey={activeConfig.dataKey}
                          name={activeConfig.label}
                          stroke={activeConfig.stroke}
                          strokeWidth={2}
                          dot={false}
                          isAnimationActive={false}
                          connectNulls={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>

              {/* Host Anomaly Detection Status Card (Isolation Forest & Security) */}
              {selectedNode.latest_security && (
                <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg text-xs space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Shield className="w-4 h-4 text-slate-400" />
                      <h4 className="font-semibold text-slate-200 uppercase tracking-wider text-[11px]">
                        UNSW-NB15 Threat Classification
                      </h4>
                    </div>
                    {selectedNode.latest_security.is_simulated ? (
                      <span className="text-[10px] px-2 py-0.5 rounded bg-amber-950/40 text-amber-300 border border-amber-800/60 font-semibold font-mono">
                        Simulated Event
                      </span>
                    ) : (
                      <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-950/40 text-indigo-300 border border-indigo-800/60 font-semibold font-mono">
                        Network Flow
                      </span>
                    )}
                  </div>
                  <div className="flex items-center justify-between font-mono pt-1 text-slate-300">
                    <span>
                      Attack: <b className="text-white">{selectedNode.latest_security.attack_type || 'Normal'}</b>
                    </span>
                    <span>
                      Confidence:{' '}
                      {selectedNode.latest_security.confidence
                        ? `${(selectedNode.latest_security.confidence * 100).toFixed(1)}%`
                        : '—'}
                    </span>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
