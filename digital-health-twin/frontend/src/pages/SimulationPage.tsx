import { useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type { SimMetrics, SimulationResult } from "../api/types";
import { fmtNum } from "../lib/format";
import { STATE_STYLES } from "../lib/states";

type Scenario = "exercise" | "sleep_restriction";

const INTENSITY_LABELS: [number, string][] = [
  [0.3, "Easy walk"],
  [0.45, "Brisk walk"],
  [0.6, "Jog"],
  [0.75, "Run"],
  [0.9, "Hard run"],
];

const intensityLabel = (v: number) => INTENSITY_LABELS.reduce((best, cur) => (Math.abs(cur[0] - v) < Math.abs(best[0] - v) ? cur : best))[1];

export function SimulationPage() {
  const [scenario, setScenario] = useState<Scenario>("exercise");
  const [intensity, setIntensity] = useState(0.7);
  const [duration, setDuration] = useState(30);
  const [priorSleep, setPriorSleep] = useState(5);
  const [usePriorSleep, setUsePriorSleep] = useState(false);
  const [sleepHours, setSleepHours] = useState(5);
  const [nights, setNights] = useState(3);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const body =
        scenario === "exercise"
          ? { scenario, intensity, duration_min: duration, prior_sleep_hours: usePriorSleep ? priorSleep : null }
          : { scenario, sleep_hours: sleepHours, nights };
      setResult(await api.simulate(body));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="simulation">
      <section className="panel simulation__form">
        <h2 className="panel__label">What-if scenario</h2>
        <p className="muted small">
          Runs the twin's physiology model, calibrated to this person's learned baseline, and classifies the simulated
          future with the same state engine used for live data. It is a scenario simulation, not a medical prediction.
        </p>
        <div className="segmented" role="radiogroup" aria-label="Scenario">
          <button role="radio" aria-checked={scenario === "exercise"} className={scenario === "exercise" ? "on" : ""} onClick={() => setScenario("exercise")}>
            Exercise session
          </button>
          <button role="radio" aria-checked={scenario === "sleep_restriction"} className={scenario === "sleep_restriction" ? "on" : ""} onClick={() => setScenario("sleep_restriction")}>
            Short sleep
          </button>
        </div>

        {scenario === "exercise" ? (
          <>
            <Slider label="Intensity" value={intensity} min={0.2} max={1} step={0.05} onChange={setIntensity} display={`${intensityLabel(intensity)} (${intensity.toFixed(2)})`} />
            <Slider label="Duration" value={duration} min={5} max={90} step={5} onChange={setDuration} display={`${duration} min`} />
            <label className="check">
              <input type="checkbox" checked={usePriorSleep} onChange={(e) => setUsePriorSleep(e.target.checked)} /> After a short night
            </label>
            {usePriorSleep && <Slider label="Sleep the night before" value={priorSleep} min={3} max={9} step={0.5} onChange={setPriorSleep} display={`${priorSleep} h`} />}
          </>
        ) : (
          <>
            <Slider label="Sleep per night" value={sleepHours} min={3} max={9} step={0.5} onChange={setSleepHours} display={`${sleepHours} h`} />
            <Slider label="Nights in a row" value={nights} min={1} max={7} step={1} onChange={setNights} display={`${nights}`} />
            <p className="muted small">Then a standard 10-minute brisk walk is simulated to compare recovery against a normal night.</p>
          </>
        )}
        <button className="btn btn--primary" onClick={run} disabled={busy}>
          {busy ? "Simulating…" : "Run simulation"}
        </button>
        {error && <p className="error" role="alert">Simulation failed: {error}</p>}
      </section>

      <section className="panel simulation__result">
        {!result ? (
          <div className="empty">
            <p>Pick a scenario and run it. The chart compares the simulated outcome with this person's normal baseline.</p>
          </div>
        ) : (
          <SimulationResultView r={result} />
        )}
      </section>
    </div>
  );
}

function Slider(props: { label: string; value: number; min: number; max: number; step: number; display: string; onChange: (v: number) => void }) {
  return (
    <label className="slider">
      <span className="slider__head">
        <span>{props.label}</span>
        <output>{props.display}</output>
      </span>
      <input type="range" min={props.min} max={props.max} step={props.step} value={props.value} onChange={(e) => props.onChange(Number(e.target.value))} />
    </label>
  );
}

function SimulationResultView({ r }: { r: SimulationResult }) {
  const rows = r.series.map((p, i) => ({ t: p.t_min, scenario: p.heart_rate, reference: r.reference_series[i]?.heart_rate }));
  const hasReference = r.scenario === "sleep_restriction" || r.sleep_effect.deficit_hours > 0;
  const metricRows: { label: string; key: keyof SimMetrics; unit: string; digits?: number }[] = [
    { label: "Peak heart rate", key: "peak_heart_rate", unit: "bpm" },
    { label: "Peak, % of heart-rate reserve", key: "peak_pct_heart_rate_reserve", unit: "%" },
    { label: "Heart-rate drop in first minute after", key: "heart_rate_recovery_1min", unit: "bpm" },
    { label: "Minutes to settle near resting", key: "minutes_to_settle", unit: "min", digits: 1 },
    { label: "Temperature rise", key: "temperature_rise", unit: "°C", digits: 2 },
    { label: "Estimated steps", key: "estimated_steps", unit: "" },
  ];
  return (
    <>
      <p className="sim-label">{r.label}</p>
      <figure className="chart">
        <figcaption>
          <strong>Simulated heart rate</strong> (bpm) over the scenario, minutes from start
          {hasReference ? "; dashed line is the same activity after a normal night" : ""}
        </figcaption>
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={rows} margin={{ top: 10, right: 16, bottom: 4, left: -8 }}>
            <CartesianGrid stroke="#D5DEE3" strokeDasharray="2 4" vertical={false} />
            {r.phases.map((p, i) => (
              <ReferenceArea key={p.name} x1={p.start_min} x2={p.end_min} fill={i === 1 ? "#2F78B7" : "#5C8C5A"} fillOpacity={i === 1 ? 0.08 : 0.04} label={{ value: p.name, position: "insideTop", fontSize: 11, fill: "#5B6F7C" }} />
            ))}
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tick={{ fontSize: 11, fill: "#5B6F7C" }} unit=" min" />
            <YAxis domain={[40, "auto"]} tick={{ fontSize: 11, fill: "#5B6F7C" }} width={44} />
            <ReferenceLine y={r.baseline.heart_rate} stroke="#0E7C7B" strokeDasharray="5 4" label={{ value: "resting baseline", position: "insideBottomRight", fontSize: 11, fill: "#0E7C7B" }} />
            <ReferenceLine y={r.baseline.hr_max_est} stroke="#B4363F" strokeDasharray="2 4" label={{ value: "est. max HR", position: "insideTopRight", fontSize: 11, fill: "#B4363F" }} />
            <Tooltip formatter={(v, n) => [`${Number(v).toFixed(0)} bpm`, n === "scenario" ? "Scenario" : "Normal night"]} labelFormatter={(t) => `${Number(t).toFixed(1)} min`} />
            {hasReference && <Legend formatter={(v) => (v === "scenario" ? "Scenario" : "After a normal night")} />}
            {hasReference && <Line dataKey="reference" stroke="#8597A3" strokeDasharray="5 4" dot={false} isAnimationActive={false} />}
            <Line dataKey="scenario" stroke="#1D2B36" strokeWidth={2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </figure>

      <div className="sim-grid">
        <table className="table">
          <thead>
            <tr>
              <th>Outcome</th>
              <th>Scenario</th>
              {hasReference && <th>Normal night</th>}
            </tr>
          </thead>
          <tbody>
            {metricRows.map((m) => (
              <tr key={m.key}>
                <td>{m.label}</td>
                <td className="mono-num">
                  {fmtNum(r.metrics[m.key] as number | null, m.digits ?? 0)} {m.unit}
                </td>
                {hasReference && (
                  <td className="mono-num">
                    {fmtNum(r.reference_metrics[m.key] as number | null, m.digits ?? 0)} {m.unit}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        <div>
          <h3 className="panel__label">States the twin would pass through</h3>
          <ol className="sim-states">
            {r.state_transitions.map((t, i) => (
              <li key={i} style={{ ["--state" as string]: STATE_STYLES[t.state].color }}>
                <span className="mono-num">{t.t_min.toFixed(0)} min</span> <strong>{STATE_STYLES[t.state].label}</strong>
                <p className="muted small">{t.reason}</p>
              </li>
            ))}
          </ol>
          {r.nights && (
            <>
              <h3 className="panel__label">Resting heart rate after each short night</h3>
              <ol className="nights">
                {r.nights.map((n) => (
                  <li key={n.night}>
                    Night {n.night}: <span className="mono-num">{n.resting_hr} bpm</span> (baseline {r.baseline.heart_rate}), recovery{" "}
                    {n.recovery_slowdown.toFixed(2)}× slower
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>
      </div>
      <details className="assumptions">
        <summary>Model assumptions ({r.assumptions.length})</summary>
        <ul>
          {r.assumptions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      </details>
    </>
  );
}
