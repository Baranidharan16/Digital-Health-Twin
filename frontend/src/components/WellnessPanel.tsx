import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { TwinStatePayload, Wellness } from "../api/types";
import { fmtNum } from "../lib/format";

export function WellnessPanel({ state }: { state: TwinStatePayload | null }) {
  const [w, setW] = useState<Wellness | null>(null);
  useEffect(() => {
    // A twin with no readings yet returns {}: treat it as no data.
    const load = () => api.wellness().then((x) => setW(x && x.recovery_index ? x : null)).catch(() => undefined);
    load();
    const id = window.setInterval(load, 8000);
    return () => window.clearInterval(id);
  }, []);
  const a = w?.activity;
  return (
    <section className="panel wellness" aria-label="Activity and recovery">
      <h2 className="panel__label">Activity and recovery</h2>
      <dl className="stats">
        <div>
          <dt>Steps today</dt>
          <dd>
            {a ? a.steps.toLocaleString() : "–"}
            <small className="sub">of usual {a ? Math.round(a.baseline_daily_steps).toLocaleString() : "–"}</small>
          </dd>
        </div>
        <div>
          <dt>Active minutes</dt>
          <dd>{a ? fmtNum(a.active_minutes) : "–"}</dd>
        </div>
        <div>
          <dt>Movement now</dt>
          <dd>{state ? state.activity_level : "–"}</dd>
        </div>
        <div>
          <dt>Last sleep</dt>
          <dd>
            {w?.sleep ? `${w.sleep.duration_hours.toFixed(1)} h` : "–"}
            <small className="sub">quality {w?.sleep?.quality_score ?? "–"}/100</small>
          </dd>
        </div>
        <div>
          <dt>HR recovery, 1 min</dt>
          <dd>{state?.last_hr_recovery_bpm != null ? `${fmtNum(state.last_hr_recovery_bpm)} bpm` : "after exercise"}</dd>
        </div>
        <div>
          <dt>Recovery index</dt>
          <dd>
            {w ? w.recovery_index.score : "–"}
            <small>/100</small>
          </dd>
        </div>
      </dl>
      {w && <p className="muted small">{w.recovery_index.factors.join(" ")} Heuristic score, not clinical.</p>}
    </section>
  );
}
