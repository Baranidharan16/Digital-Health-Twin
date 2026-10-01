// Pure mapping from twin state -> what the 3D anatomy shows.
// Kept separate from Three.js so it can be unit-tested and documented:
// every animated structure is driven by one specific data field, and a
// structure whose data is not measured is shown still and labelled as such.

import type { AssessmentStatus, TwinStatePayload } from "../api/types";
import { STATE_STYLES, STATUS_COLORS } from "./states";

export type Region = "heart" | "lungs" | "skin";

export interface TwinVisuals {
  heartBpm: number; // heart pulse + arterial pulse wave frequency
  breathsPerMin: number | null; // lungs + diaphragm; null = not measured (no animation)
  spo2: number | null; // arterial colour; null = not measured
  movement: number; // 0..1 muscle activation glow
  lying: boolean; // sleep posture; brain shows the sleep glow
  stateColor: string;
  regions: Record<Region, AssessmentStatus>;
  regionColors: Record<Region, string>;
  monitored: Record<Region, boolean>;
}

const RANK: Record<AssessmentStatus, number> = { normal: 0, watch: 1, anomalous: 2 };
const worst = (...s: (AssessmentStatus | undefined)[]) =>
  s.reduce<AssessmentStatus>((a, b) => (b && RANK[b] > RANK[a] ? b : a), "normal");

/** Data field -> anatomical structure (documented in docs/digital-twin-model.md). */
export const REGION_SOURCES: Record<Region, string[]> = {
  heart: ["heart_rate"],
  lungs: ["respiratory_rate", "spo2"],
  skin: ["temperature"],
};

export function visualsFor(p: TwinStatePayload): TwinVisuals {
  const a = p.assessments;
  const o = p.observation;
  const intensity = o.is_asleep ? 0 : o.activity_intensity;
  const regions: Record<Region, AssessmentStatus> = {
    heart: a.heart_rate?.status ?? "normal",
    lungs: worst(a.respiratory_rate?.status, a.spo2?.status),
    skin: a.temperature?.status ?? "normal",
  };
  return {
    heartBpm: clamp(o.heart_rate, 30, 220),
    breathsPerMin: o.respiratory_rate == null ? null : clamp(o.respiratory_rate, 4, 60),
    spo2: o.spo2 ?? null,
    movement: intensity < 0.12 ? 0 : clamp((intensity - 0.12) / 0.7, 0.15, 1),
    lying: o.is_asleep,
    stateColor: STATE_STYLES[p.state].color,
    regions,
    regionColors: {
      heart: STATUS_COLORS[regions.heart],
      lungs: STATUS_COLORS[regions.lungs],
      skin: STATUS_COLORS[regions.skin],
    },
    monitored: {
      heart: true,
      lungs: o.respiratory_rate != null || o.spo2 != null,
      skin: o.temperature != null,
    },
  };
}

function clamp(v: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, v));
}

/** Sharp systole then a smaller second bump: reads as a heartbeat, not a sine. */
export function heartbeatShape(phase: number): number {
  const x = phase - Math.floor(phase);
  const beat = (c: number, w: number) => Math.exp(-((x - c) ** 2) / (2 * w * w));
  return beat(0.08, 0.035) + 0.45 * beat(0.28, 0.05);
}

/** Arterial blood colour from SpO2: bright red when saturated, darker and bluer as it falls. */
export function arterialColor(spo2: number | null): [number, number, number] {
  if (spo2 == null) return [0.75, 0.08, 0.1];
  const k = Math.min(Math.max((100 - spo2) / 15, 0), 1); // 100% -> 0, 85% -> 1
  return [0.78 - 0.38 * k, 0.08, 0.1 + 0.32 * k];
}
