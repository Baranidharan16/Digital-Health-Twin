import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Assessment, HistoryPoint, TwinStatePayload, VitalMetric } from "../api/types";
import { twinLocalToUtcIso } from "../lib/format";

const VITALS: VitalMetric[] = ["heart_rate", "spo2", "temperature", "respiratory_rate"];

/**
 * Replays stored readings (real uploads or the demo history) through the 3D
 * twin: one stored reading per frame step, using the state and anomaly flags
 * the engine recorded for that reading when it was ingested.
 */
export function usePlayback(twinId: string) {
  const [points, setPoints] = useState<HistoryPoint[]>([]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(30); // readings per second
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  const load = useCallback(
    async (day: string) => {
      setLoading(true);
      setError(null);
      setPlaying(false);
      try {
        const start = twinLocalToUtcIso(`${day}T00:00`);
        const end = new Date(new Date(start).getTime() + 24 * 3600e3).toISOString();
        const h = await api.history("custom", start, end, twinId, 1600);
        if (!h.points.length) throw new Error("no readings on that day");
        setPoints(h.points);
        setIndex(0);
      } catch (e) {
        setPoints([]);
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [twinId],
  );

  useEffect(() => {
    window.clearInterval(timer.current);
    if (!playing || !points.length) return;
    const stepMs = 100;
    timer.current = window.setInterval(() => {
      setIndex((i) => {
        const next = i + Math.max(1, Math.round((speed * stepMs) / 1000));
        if (next >= points.length - 1) {
          setPlaying(false);
          return points.length - 1;
        }
        return next;
      });
    }, stepMs);
    return () => window.clearInterval(timer.current);
  }, [playing, speed, points]);

  const payload = points.length ? toPayload(twinId, points[Math.min(index, points.length - 1)]) : null;
  return { points, index, setIndex, playing, setPlaying, speed, setSpeed, load, loading, error, payload, active: points.length > 0 };
}

function toPayload(twinId: string, p: HistoryPoint): TwinStatePayload {
  const assessments: Partial<Record<VitalMetric, Assessment>> = {};
  for (const m of VITALS) {
    const value = p[m];
    if (value == null) continue;
    const flagged = p.anomalous.includes(m);
    assessments[m] = {
      metric: m,
      value,
      expected: value,
      expected_low: value,
      expected_high: value,
      deviation: 0,
      deviation_pct: 0,
      robust_z: 0,
      status: flagged ? "anomalous" : "normal",
      consecutive: 0,
      context: p.is_asleep ? "asleep" : "recorded",
      reason: flagged ? "Flagged by the twin when this reading was ingested." : null,
      reference_flag: null,
    };
  }
  return {
    twin_id: twinId,
    state: p.state,
    previous_state: null,
    state_since: p.t,
    state_reason: "Recorded state at this time.",
    state_description: "",
    twin_time: p.t,
    received_at: null,
    data_age_seconds: null,
    observation: {
      timestamp: p.t,
      heart_rate: p.heart_rate,
      spo2: p.spo2,
      temperature: p.temperature,
      respiratory_rate: p.respiratory_rate,
      steps: p.steps,
      activity_intensity: p.activity_intensity,
      is_asleep: p.is_asleep,
      source: "playback",
    },
    assessments,
    effective_intensity: p.activity_intensity,
    activity_level: "",
    rolling: {},
    last_hr_recovery_bpm: null,
  };
}
