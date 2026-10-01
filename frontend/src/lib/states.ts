import type { AssessmentStatus, TwinStateName, VitalMetric } from "../api/types";

export interface StateStyle {
  label: string;
  color: string;
  plain: string; // one-line plain-language meaning
}

// Colours are defined once here and in styles.css (--state-*).
export const STATE_STYLES: Record<TwinStateName, StateStyle> = {
  STABLE: { label: "Stable", color: "#0E7C7B", plain: "Vitals match this person's own baseline." },
  ACTIVE: { label: "Active", color: "#2F78B7", plain: "Walking-level movement; vitals rising as expected." },
  HIGH_ACTIVITY: { label: "High activity", color: "#1F4F8F", plain: "Vigorous exercise; high heart rate is expected." },
  RECOVERY: { label: "Recovering", color: "#5C8C5A", plain: "Exercise stopped; vitals are settling back." },
  SLEEPING: { label: "Sleeping", color: "#4B57A6", plain: "Compared against this person's sleeping baseline." },
  ELEVATED: { label: "Elevated", color: "#C98A1B", plain: "Something is unusual, not yet persistent." },
  ANOMALOUS: { label: "Anomaly flagged", color: "#B4363F", plain: "A vital has stayed outside the expected range." },
};

export const STATUS_COLORS: Record<AssessmentStatus, string> = {
  normal: "#0E7C7B",
  watch: "#C98A1B",
  anomalous: "#B4363F",
};

export const METRICS: { key: VitalMetric; label: string; unit: string; digits: number; region: string }[] = [
  { key: "heart_rate", label: "Heart rate", unit: "bpm", digits: 0, region: "Heart" },
  { key: "respiratory_rate", label: "Breathing", unit: "br/min", digits: 0, region: "Lungs" },
  { key: "spo2", label: "SpO₂", unit: "%", digits: 1, region: "Lungs" },
  { key: "temperature", label: "Temperature", unit: "°C", digits: 1, region: "Head" },
];

export const SCENARIO_HINTS: Record<string, string> = {
  NORMAL: "Seated, everyday",
  EXERCISE: "Warm-up, then running",
  RECOVERY: "Stops moving",
  ANOMALY: "Unexplained change at rest",
  SLEEP: "Asleep",
};
