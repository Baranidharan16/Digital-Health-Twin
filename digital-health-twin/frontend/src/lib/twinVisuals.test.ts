import { describe, expect, it } from "vitest";
import type { Assessment, TwinStatePayload, VitalMetric } from "../api/types";
import { heartbeatShape, visualsFor } from "./twinVisuals";

function assessment(metric: VitalMetric, status: Assessment["status"] = "normal"): Assessment {
  return {
    metric,
    value: 1,
    expected: 1,
    expected_low: 1,
    expected_high: 1,
    deviation: 0,
    deviation_pct: 0,
    robust_z: 0,
    status,
    consecutive: 0,
    context: "at rest",
    reason: null,
    reference_flag: null,
  };
}

function payload(overrides: Partial<TwinStatePayload["observation"]> = {}, statuses: Partial<Record<VitalMetric, Assessment["status"]>> = {}): TwinStatePayload {
  return {
    twin_id: "twin-001",
    state: "STABLE",
    previous_state: null,
    state_since: "2026-01-01T00:00:00Z",
    state_reason: "",
    state_description: "",
    twin_time: "2026-01-01T00:00:00Z",
    received_at: null,
    data_age_seconds: 0,
    observation: {
      timestamp: "2026-01-01T00:00:00Z",
      heart_rate: 72,
      spo2: 98,
      temperature: 36.7,
      respiratory_rate: 14,
      steps: 0,
      activity_intensity: 0.03,
      is_asleep: false,
      source: "test",
      ...overrides,
    },
    assessments: {
      heart_rate: assessment("heart_rate", statuses.heart_rate),
      spo2: assessment("spo2", statuses.spo2),
      temperature: assessment("temperature", statuses.temperature),
      respiratory_rate: assessment("respiratory_rate", statuses.respiratory_rate),
    },
    effective_intensity: 0,
    activity_level: "Still",
    rolling: {},
    last_hr_recovery_bpm: null,
  };
}

describe("visualsFor", () => {
  it("drives heart and lungs from live vitals", () => {
    const v = visualsFor(payload({ heart_rate: 150, respiratory_rate: 30 }));
    expect(v.heartBpm).toBe(150);
    expect(v.breathsPerMin).toBe(30);
  });

  it("is still at rest and moves when running", () => {
    expect(visualsFor(payload()).movement).toBe(0);
    const run = visualsFor(payload({ activity_intensity: 0.8 }));
    expect(run.movement).toBeGreaterThan(0.8);
    expect(run.cadenceHz).toBeGreaterThan(1);
  });

  it("lies down while asleep and stops moving", () => {
    const v = visualsFor(payload({ is_asleep: true, activity_intensity: 0.5 }));
    expect(v.lying).toBe(true);
    expect(v.movement).toBe(0);
  });

  it("maps each flagged vital to its body region", () => {
    const v = visualsFor(payload({}, { spo2: "anomalous", temperature: "watch" }));
    expect(v.regions).toEqual({ heart: "normal", lungs: "anomalous", head: "watch" });
  });

  it("produces a periodic heartbeat with a clear peak", () => {
    expect(heartbeatShape(0.08)).toBeGreaterThan(0.9);
    expect(heartbeatShape(0.6)).toBeLessThan(0.05);
    expect(heartbeatShape(1.08)).toBeCloseTo(heartbeatShape(0.08));
  });
});
