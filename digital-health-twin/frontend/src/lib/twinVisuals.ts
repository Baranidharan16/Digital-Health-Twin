// Pure mapping from twin state -> what the 3D body shows.
// Kept separate from Three.js so it can be unit-tested and documented:
// every visual on the body is driven by a specific data field.

import type { AssessmentStatus, TwinStatePayload } from "../api/types";
import { STATE_STYLES, STATUS_COLORS } from "./states";

export type Region = "heart" | "lungs" | "head";

export interface TwinVisuals {
  heartBpm: number; // heart pulse frequency
  breathsPerMin: number; // lung expansion frequency
  movement: number; // 0..1 limb swing amplitude
  cadenceHz: number; // limb swing frequency
  lying: boolean; // sleep posture
  stateColor: string; // body tint
  regions: Record<Region, AssessmentStatus>;
  regionColors: Record<Region, string>;
}

const RANK: Record<AssessmentStatus, number> = { normal: 0, watch: 1, anomalous: 2 };
const worst = (...s: AssessmentStatus[]) => s.reduce((a, b) => (RANK[b] > RANK[a] ? b : a), "normal");

/** Data field -> body region (documented in docs/digital-twin-model.md). */
export const REGION_SOURCES: Record<Region, string[]> = {
  heart: ["heart_rate"],
  lungs: ["respiratory_rate", "spo2"],
  head: ["temperature"],
};

export function visualsFor(p: TwinStatePayload): TwinVisuals {
  const a = p.assessments;
  const intensity = p.observation.is_asleep ? 0 : p.observation.activity_intensity;
  const regions: Record<Region, AssessmentStatus> = {
    heart: a.heart_rate.status,
    lungs: worst(a.respiratory_rate.status, a.spo2.status),
    head: a.temperature.status,
  };
  return {
    heartBpm: clamp(p.observation.heart_rate, 30, 220),
    breathsPerMin: clamp(p.observation.respiratory_rate, 4, 60),
    movement: intensity < 0.12 ? 0 : clamp((intensity - 0.12) / 0.7, 0.15, 1),
    cadenceHz: intensity < 0.12 ? 0 : intensity < 0.5 ? 0.9 : 1.4,
    lying: p.observation.is_asleep,
    stateColor: STATE_STYLES[p.state].color,
    regions,
    regionColors: {
      heart: STATUS_COLORS[regions.heart],
      lungs: STATUS_COLORS[regions.lungs],
      head: STATUS_COLORS[regions.head],
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
