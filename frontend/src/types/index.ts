/**
 * Core TypeScript definitions for Adaptive Cloud Monitoring & Resilience Console.
 */

export type NodeStatus = 'ONLINE' | 'STALE' | 'OFFLINE';

export interface HardwareInfo {
  cpu_count_logical?: number;
  cpu_count_physical?: number;
  ram_total_mb?: number;
  disk_total_gb?: number;
  [key: string]: unknown;
}

export interface TelemetryMetrics {
  cpu_utilization?: number;
  ram_utilization?: number;
  disk_utilization?: number;
  disk_free_gb?: number;
  disk_used_gb?: number;
  disk_total_gb?: number;
  network_sent_mb?: number;
  network_recv_mb?: number;
  disk_read_mb?: number;
  disk_write_mb?: number;
  cpu_temperature_c?: number;
  process_count?: number;
  [key: string]: unknown;
}

export interface TelemetryRecord {
  id?: number;
  node_id: string;
  timestamp: string;
  cpu_utilization: number | null;
  ram_utilization: number | null;
  disk_utilization: number | null;
  disk_free_gb?: number | null;
  disk_used_gb?: number | null;
  disk_total_gb?: number | null;
  network_sent_mb?: number | null;
  network_recv_mb?: number | null;
  disk_read_mb?: number | null;
  disk_write_mb?: number | null;
  cpu_temperature_c?: number | null;
  process_count?: number | null;
  metrics?: TelemetryMetrics;
  raw_metrics?: string;
}

export interface NodeItem {
  node_id: string;
  hostname: string;
  region?: string;
  location_label?: string | null;
  ip_address?: string;
  operating_system?: string;
  hardware_info?: HardwareInfo;
  first_seen: string;
  last_seen: string;
  last_heartbeat?: string | null;
  status: NodeStatus;
  latest_telemetry?: TelemetryRecord;
  latest_live_health?: {
    health_status: string;
    anomaly_probability: number;
    model_version?: string;
  };
  latest_security?: {
    classification: string;
    attack_type?: string;
    security_risk?: string;
    confidence?: number;
    is_simulated?: boolean;
    timestamp?: string;
  };
}

export interface ServiceHealth {
  status: string;
  service: string;
  database: string;
  auth_required: boolean;
  timestamp: string;
}

export interface MaintenanceAlert {
  alert_id: string;
  node_id: string;
  timestamp: string;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  failure_probability: number;
  main_contributing_factors?: Array<{
    feature: string;
    label: string;
    value: number;
    importance: number;
  }>;
  alert_title: string;
  alert_description: string;
  status: 'ACTIVE' | 'ACKNOWLEDGED' | 'RESOLVED';
  acknowledged_at?: string | null;
  resolved_at?: string | null;
}

export type RecoveryLifecycleStatus =
  | 'PROPOSED'
  | 'APPROVED'
  | 'EXECUTING'
  | 'SUCCESSFUL'
  | 'FAILED'
  | 'INCONCLUSIVE';

export interface IncidentRiskAssessment {
  overall_risk_score?: number;
  overall_risk_level?: string;
  failure_probability?: number;
  failure_risk_level?: string;
  security_risk_level?: string;
  action_priority?: string;
  model_name?: string;
  recommendation?: string;
}

export interface IncidentSupportingEvidence {
  telemetry?: Record<string, unknown>;
  contributing_factors?: string[];
  timestamp?: string;
  hardware_info?: Record<string, unknown>;
  node_status?: string;
  alert_id?: string | number;
}

export interface RecoveryIncidentItem {
  incident_id: string;
  node_id: string;
  hostname?: string;
  incident_type: string;
  severity: string;
  title: string;
  summary: string;
  source: string;
  risk_assessment?: IncidentRiskAssessment;
  supporting_evidence?: IncidentSupportingEvidence;
  is_disruptive_risk?: boolean;
  recommended_action_prior?: string;
  status: string;
  created_at: string;
}

export interface CandidateActionScore {
  action?: string;
  action_id?: string;
  action_name?: string;
  name?: string;
  ranking_score?: number;
  score?: number;
  success_probability?: number;
  historical_success_rate?: number;
  trials?: number;
  successes?: number;
  mean_recovery_time_sec?: number;
  recovery_time_sec?: number;
  resource_overhead_score?: number;
  resource_cost?: number;
  risk_weight?: number;
  risk_penalty?: number;
  eligible?: boolean;
  is_authorized?: boolean;
  filter_reason?: string;
  rationale?: string;
}

export interface CriterionEvaluation {
  metric: string;
  target_operator: string;
  target_threshold?: number;
  required_drop_pct?: number;
  baseline: number;
  observed: number;
  met: boolean;
  reason?: string;
}

export interface VerificationResultPayload {
  status: 'SUCCESS' | 'FAILURE' | 'TIMEOUT' | 'INCONCLUSIVE';
  verification_duration_sec: number;
  observed_metrics: Record<string, unknown>;
  criteria_evaluations: CriterionEvaluation[];
  details: string;
  is_verified: boolean;
  timeout_exceeded?: boolean;
  telemetry_unavailable?: boolean;
}

export interface RecoveryDecision {
  decision_id: string;
  incident_id: string;
  node_id: string;
  incident_type: string;
  severity: string;
  selected_action: string;
  action_name?: string;
  ranking_score: number;
  ranking_rationale: string;
  candidate_scores?: CandidateActionScore[];
  candidate_rankings?: CandidateActionScore[];
  metrics_before?: Record<string, unknown>;
  metrics_after?: Record<string, unknown>;
  measured_improvement?: Record<string, unknown>;
  execution_status: string;
  success_measured?: boolean;
  recovery_duration_sec?: number;
  verification_status?: 'SUCCESS' | 'FAILURE' | 'TIMEOUT' | 'INCONCLUSIVE';
  lifecycle_status?: RecoveryLifecycleStatus;
  is_disruptive?: boolean;
  requires_authorization?: boolean;
  is_approved?: boolean;
  recovery_criteria?: {
    incident_type?: string;
    action_id?: string;
    baseline_metrics?: Record<string, unknown>;
    timeout_sec?: number;
    sampling_interval_sec?: number;
    description?: string;
    criteria?: Array<{
      metric_name: string;
      target_operator: string;
      baseline_value?: number;
      target_threshold?: number;
      required_drop_pct?: number;
      description?: string;
    }>;
  };
  verification_result?: VerificationResultPayload;
  verification_details?: string;
  timestamp: string;
}

export interface LearnedActionHistory {
  action_name: string;
  trial_count: number;
  success_count: number;
  success_rate: number;
  mean_recovery_time_sec: number;
  last_updated?: string;
  evidence_source?: string;
}

export interface NodeRiskItem {
  node_id: string;
  overall_risk_score: number;
  overall_risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | 'N/A';
  security_risk_level: string;
  failure_risk_level: string;
  failure_probability?: number;
  action_priority?: string;
  recommendation?: string;
  status?: string;
}

export interface DriftNodeItem {
  node_id: string;
  status: 'NOMINAL' | 'DRIFT DETECTED' | 'INSUFFICIENT_DATA';
  affected_features?: string[];
  max_ks_statistic?: number;
  timestamp?: string;
}

export interface FleetSummary {
  total_nodes: number;
  online_nodes: number;
  offline_nodes: number;
  stale_nodes: number;
  active_alerts_count: number;
  avg_cpu: number | null;
  avg_ram: number | null;
  avg_disk: number | null;
  timestamp: string;
}

export interface ModelMetadata {
  name: string;
  version?: string;
  status: string;
  artifact_path?: string;
  dataset?: string;
  type?: string;
  features?: string[];
  retraining_guard?: string;
  last_retraining?: unknown;
  mode?: string;
}

export interface ModelStatusResponse {
  models: {
    predictive_maintenance: ModelMetadata;
    live_infrastructure_health: ModelMetadata;
    network_security: ModelMetadata;
    concept_drift_detector: ModelMetadata;
    adaptive_recovery: ModelMetadata;
  };
  timestamp: string;
}

export interface RecoveryBenchmark {
  id?: number;
  benchmark_id: string;
  timestamp: string;
  mode: string;
  trial_count: number;
  seed?: number;
  adaptive_metrics?: {
    mean_reward?: number;
    success_rate?: number;
    mean_recovery_time_sec?: number;
    overhead_score?: number;
    [key: string]: unknown;
  };
  baseline_metrics?: {
    mean_reward?: number;
    success_rate?: number;
    mean_recovery_time_sec?: number;
    overhead_score?: number;
    [key: string]: unknown;
  };
  deltas?: {
    reward_delta?: number;
    success_rate_delta?: number;
    time_delta_sec?: number;
    [key: string]: unknown;
  };
}

export interface DataSufficiency {
  is_sufficient: boolean;
  reading_count: number;
  min_required: number;
  status: 'SUFFICIENT' | 'INSUFFICIENT_HISTORY' | 'NO_DATA';
  message: string;
}

export interface PredictiveMaintenancePrediction {
  prediction: number;
  failure_probability: number;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  status: string;
  recommended_action?: string;
  simple_explanation?: string;
  model_name?: string;
  timestamp?: string;
  features_used?: Record<string, number>;
}

export interface ForecastPoint {
  time: string;
  timestamp: string;
  type: 'MEASURED' | 'ANOMALY' | 'FORECAST';
  cpu: number;
  ram: number;
  disk: number;
  resource_pressure: number;
  is_forecast: boolean;
  is_anomaly: boolean;
  uncertainty_lower?: number;
  uncertainty_upper?: number;
}

export interface ForecastInfo {
  forecast_horizon: string | null;
  estimated_threshold_crossing: string | null;
  threshold_crossing_message: string;
  forecast_points: ForecastPoint[];
  leading_metric?: string | null;
  leading_slope_per_min?: number;
}

export interface ActualOutcomeItem {
  alert_id: number;
  timestamp: string;
  risk_level: string;
  failure_probability: number;
  status: string;
  resolved_at?: string | null;
  repeat_count: number;
  reason?: string;
  recommended_action?: string;
  outcome_evaluated: boolean;
  actual_outcome: string;
}

export interface PredictiveModelMetadata {
  model_name: string;
  model_version: string;
  status: string;
  dataset: string;
  features: string[];
  target: string;
  evaluation_metrics?: {
    accuracy?: number;
    precision?: number;
    recall?: number;
    f1_score?: number;
    roc_auc?: number;
    threshold?: number;
    training_samples?: number;
    [key: string]: unknown;
  };
  prediction_timestamp: string;
}

export interface PredictiveMaintenanceNodeEvaluation {
  node_id: string;
  hostname: string;
  region: string;
  data_sufficiency: DataSufficiency;
  prediction: PredictiveMaintenancePrediction | null;
  forecast: ForecastInfo;
  trend_explanation: string;
  timeline: ForecastPoint[];
  actual_outcomes: ActualOutcomeItem[];
  active_alert?: MaintenanceAlert | null;
  model_metadata: PredictiveModelMetadata;
}

export interface FleetPredictiveNodeItem {
  node_id: string;
  hostname: string;
  region: string;
  status: string;
  risk_level: string;
  failure_probability: number;
  is_sufficient: boolean;
  reading_count: number;
  forecast_horizon?: string | null;
  estimated_threshold_crossing?: string | null;
  has_active_alert: boolean;
}

export interface FleetPredictiveMaintenanceResponse {
  total_nodes: number;
  nodes: FleetPredictiveNodeItem[];
  timestamp: string;
}

