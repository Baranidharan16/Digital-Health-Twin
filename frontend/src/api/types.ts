// Types mirroring the FastAPI responses (see backend/app/schemas.py and
// backend/app/services/*). Kept hand-written and small on purpose.

export type TwinStateName =
  | "STABLE"
  | "ACTIVE"
  | "HIGH_ACTIVITY"
  | "RECOVERY"
  | "SLEEPING"
  | "ELEVATED"
  | "ANOMALOUS";

export type VitalMetric = "heart_rate" | "spo2" | "temperature" | "respiratory_rate";
export type AssessmentStatus = "normal" | "watch" | "anomalous";

export interface Observation {
  timestamp: string;
  heart_rate: number;
  spo2: number | null;
  temperature: number | null;
  respiratory_rate: number | null;
  steps: number;
  activity_intensity: number;
  is_asleep: boolean;
  source: string;
}

export interface Assessment {
  metric: VitalMetric;
  value: number;
  expected: number;
  expected_low: number;
  expected_high: number;
  deviation: number;
  deviation_pct: number;
  robust_z: number;
  status: AssessmentStatus;
  consecutive: number;
  context: string;
  reason: string | null;
  reference_flag: string | null;
}

export interface TwinStatePayload {
  twin_id: string;
  state: TwinStateName;
  previous_state: TwinStateName | null;
  state_since: string;
  state_reason: string;
  state_description: string;
  twin_time: string;
  received_at: string | null;
  data_age_seconds: number | null;
  observation: Observation;
  /** Only vitals the data source actually measures are present. */
  assessments: Partial<Record<VitalMetric, Assessment>>;
  effective_intensity: number;
  activity_level: string;
  rolling: Record<string, number>;
  last_hr_recovery_bpm: number | null;
}

export interface ScenarioInfo {
  key: string;
  label: string;
  description: string;
}

export interface LiveStatus {
  running: boolean;
  twin_id: string | null;
  mode: "simulator" | "replay";
  scenario: string | null;
  guided: boolean;
  guided_step: string | null;
  guided_sequence: { scenario: string; twin_seconds: number }[];
  ticks: number;
  started_at: string | null;
  last_error: string | null;
  tick_seconds: number;
  twin_seconds_per_tick: number;
  time_acceleration: number;
  scenarios: ScenarioInfo[];
}

export interface Subject {
  id: string;
  pseudonym: string;
  age_years: number;
  is_synthetic: boolean;
  utc_offset_hours: number;
  data_source: string | null;
}

export interface ImportSummary {
  twin_id: string;
  observations: number;
  interval_seconds: number;
  start: string;
  end: string;
  metrics_measured: string[];
  sleep_minutes: number;
  intensity_estimated: boolean;
  files: { name: string; format: string; rows: number }[];
  notes: string[];
}

export interface TwinInfo {
  id: string;
  name: string;
  subject: Subject;
  created_at: string;
  updated_at: string;
  current_state: TwinStateName | null;
  state_since: string | null;
  observation_count: number;
  last_observation_at: string | null;
  last_received_at: string | null;
}

export interface TwinEvent {
  id: number;
  kind: "transition" | "anomaly";
  timestamp: string;
  title: string;
  detail: string;
  from_state?: string | null;
  to_state?: string | null;
  metric?: string | null;
  ended_at?: string | null;
  active?: boolean | null;
}

export interface HistoryPoint {
  t: string;
  heart_rate: number;
  spo2: number | null;
  temperature: number | null;
  respiratory_rate: number | null;
  steps: number;
  activity_intensity: number;
  is_asleep: boolean;
  state: TwinStateName;
  anomalous: string[];
}

export interface HistoryResponse {
  twin_id: string;
  start: string;
  end: string;
  resolution_seconds: number;
  raw_points: number;
  points: HistoryPoint[];
  state_segments: { state: TwinStateName; start: string; end: string }[];
  anomaly_markers: { id: number; metric: string; start: string; end: string; active: boolean; reason: string }[];
}

export interface BaselineData {
  hr_rest: number;
  hr_rest_spread: number;
  hr_sleep: number;
  rr_rest: number;
  rr_rest_spread: number;
  rr_sleep: number;
  spo2: number;
  spo2_spread: number;
  temp_awake: number;
  temp_spread: number;
  temp_sleep: number;
  hr_max_est: number;
  daily_steps: number;
  sleep_hours: number;
  sample_count: number;
  window_start: string | null;
  window_end: string | null;
  metrics_available?: string[];
}

export interface BaselineComparison {
  metric: VitalMetric;
  label: string;
  unit: string;
  current: number;
  rolling_5min: number | null;
  baseline: number;
  baseline_context: string;
  diff_from_baseline: number;
  diff_from_baseline_pct: number;
  expected: number;
  expected_low: number;
  expected_high: number;
  context: string;
  status: AssessmentStatus;
}

export interface BaselineResponse {
  twin_id: string;
  computed_at: string;
  data: BaselineData;
  comparison: BaselineComparison[];
}

export interface Wellness {
  sleep: {
    start: string;
    end: string;
    duration_hours: number;
    baseline_hours: number;
    restless_fraction: number;
    mean_sleep_hr: number;
    hr_dip_pct: number;
    quality_score: number;
  } | null;
  activity: {
    day: string;
    steps: number;
    baseline_daily_steps: number;
    active_minutes: number;
    current_intensity: number;
    activity_level: string;
  } | null;
  resting_hr_recent: number | null;
  resting_hr_baseline: number;
  hr_recovery_1min: number | null;
  recovery_index: { score: number; factors: string[]; heuristic: boolean };
}

export interface MetricSummary {
  label: string;
  unit: string;
  mean: number;
  min: number;
  max: number;
  p95: number;
  resting_median: number | null;
  resting_trend_per_day: number | null;
}

export interface AnalyticsResponse {
  twin_id: string;
  range: string;
  observations: number;
  metrics: Record<VitalMetric, MetricSummary>;
  time_in_state_minutes: Record<string, number>;
  time_in_state_pct: Record<string, number>;
  transitions: number;
  transition_counts: Record<string, number>;
  anomaly_episodes: number;
  anomalies_by_metric: Record<string, number>;
  hr_intensity_correlation: number | null;
  baseline_hr_rest: number;
  daily:
    | {
        day: string;
        steps: number;
        resting_hr: number | null;
        active_minutes: number;
        sleep_hours: number;
        anomalous_readings: number;
      }[]
    | null;
}

export interface Evaluation {
  description: string;
  seeds: number[];
  test_days_total: number;
  injected_episodes: number;
  twin: { event_recall: number; false_alarms_per_day: number; median_detection_latency_min: number | null };
  population_threshold_rule: { rule: string; event_recall: number; false_alarms_per_day: number };
  recall_by_severity: Record<
    string,
    { magnitude_range: number[]; episodes: number; twin_recall: number | null; population_rule_recall: number | null }
  >;
  baseline_learning: { mean_abs_error_resting_hr_bpm: number; max_abs_error_resting_hr_bpm: number };
}

export interface SimPoint {
  t_min: number;
  heart_rate: number;
  respiratory_rate: number;
  temperature: number;
  spo2: number;
  intensity: number;
}

export interface SimMetrics {
  peak_heart_rate: number;
  mean_exercise_heart_rate: number;
  peak_pct_heart_rate_reserve: number;
  heart_rate_recovery_1min: number | null;
  minutes_to_settle: number | null;
  temperature_rise: number;
  estimated_steps: number;
  minutes_in_state: Record<string, number>;
}

export interface SimulationResult {
  scenario: "exercise" | "sleep_restriction";
  label: string;
  inputs: Record<string, number | null>;
  phases: { name: string; start_min: number; end_min: number }[];
  baseline: { heart_rate: number; hr_max_est: number };
  sleep_effect: { hr_rest_offset: number; recovery_tau_scale: number; deficit_hours: number };
  nights?: { night: number; sleep_hours: number; resting_hr: number; recovery_slowdown: number }[];
  series: SimPoint[];
  reference_series: SimPoint[];
  metrics: SimMetrics;
  reference_metrics: SimMetrics;
  state_transitions: { t_min: number; state: TwinStateName; reason: string }[];
  assumptions: string[];
  run_id: number;
}

export interface SystemInfo {
  app: string;
  database: string;
  counts: Record<string, number>;
  websocket_clients: number;
  live: LiveStatus;
  pipeline: { step: string; detail: string }[];
  adapters: { name: string; status: string; detail: string }[];
  engine: {
    anomaly_rules: Record<
      string,
      {
        direction: string;
        z_anomalous: number;
        z_watch: number;
        min_abs_change: number;
        min_pct_change: number;
        spread_floor: number;
      }
    >;
    persistence_readings: number;
    clear_readings: number;
    state_confirm_readings: number;
    state_priority: string[];
    state_descriptions: Record<string, string>;
  };
  disclaimer: string;
}

export interface Pairing {
  code: string;
  expires_at: string;
  ttl_seconds: number;
  server_urls: string[];
  deep_link: string;
}

export interface PhoneSyncSummary {
  status: "synced" | "nothing_new" | "waiting_for_more_data" | "no_heart_rate";
  received: Record<string, number>;
  readings_ingested: number;
  metrics: string[];
  twin_id: string;
  detail: string | null;
  synced_at: string;
}

export interface PhoneDevice {
  id: number;
  name: string;
  twin_id: string;
  created_at: string;
  last_seen_at: string | null;
  last_sync: PhoneSyncSummary | null;
}
