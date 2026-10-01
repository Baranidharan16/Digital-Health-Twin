import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type { BaselineData, HistoryResponse, TwinStateName } from "../api/types";
import { fmtClockDate, fmtDateTime, fmtDay, toDate, twinLocalToUtcIso, utcToTwinLocalInput } from "../lib/format";
import { STATE_STYLES } from "../lib/states";

const RANGES = [
  { key: "1h", label: "Last hour" },
  { key: "today", label: "Today" },
  { key: "24h", label: "Last 24 h" },
  { key: "7d", label: "Last 7 days" },
  { key: "custom", label: "Custom" },
];

const CHARTS = [
  { key: "heart_rate", label: "Heart rate", unit: "bpm", digits: 0, base: (b: BaselineData) => b.hr_rest, metric: "heart_rate" },
  { key: "spo2", label: "SpO₂", unit: "%", digits: 1, base: (b: BaselineData) => b.spo2, metric: "spo2" },
  { key: "temperature", label: "Temperature", unit: "°C", digits: 2, base: (b: BaselineData) => b.temp_awake, metric: "temperature" },
  { key: "respiratory_rate", label: "Respiratory rate", unit: "br/min", digits: 1, base: (b: BaselineData) => b.rr_rest, metric: "respiratory_rate" },
] as const;



export function HistoryPage({ version }: { version: string }) {
  const [range, setRange] = useState("24h");
  const [custom, setCustom] = useState(() => {
    const end = new Date();
    return { start: utcToTwinLocalInput(new Date(end.getTime() - 6 * 3600e3)), end: utcToTwinLocalInput(end) };
  });
  const [data, setData] = useState<HistoryResponse | null>(null);
  const [baseline, setBaseline] = useState<BaselineData | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Reload when the range changes, and every new state version for short ranges.
  const refreshKey = range === "1h" || range === "today" ? version : "";
  useEffect(() => {
    const start = range === "custom" ? twinLocalToUtcIso(custom.start) : undefined;
    const end = range === "custom" ? twinLocalToUtcIso(custom.end) : undefined;
    api
      .history(range, start, end)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(e.message));
  }, [range, custom, refreshKey]);
  useEffect(() => {
    api.baseline().then((b) => setBaseline(b.data)).catch(() => undefined);
  }, []);

  const rows = useMemo(
    () => (data?.points ?? []).map((p) => ({ ...p, t: toDate(p.t).getTime() })),
    [data],
  );
  const domain: [number, number] | undefined = data ? [toDate(data.start).getTime(), toDate(data.end).getTime()] : undefined;
  const markers = data?.anomaly_markers ?? [];

  return (
    <div className="history">
      <div className="toolbar panel" role="group" aria-label="Time range">
        {RANGES.map((r) => (
          <button key={r.key} className={`chip ${range === r.key ? "chip--on" : ""}`} aria-pressed={range === r.key} onClick={() => setRange(r.key)}>
            <span>{r.label}</span>
          </button>
        ))}
        {range === "custom" && (
          <span className="toolbar__custom">
            <label>
              From <input type="datetime-local" value={custom.start} onChange={(e) => setCustom({ ...custom, start: e.target.value })} />
            </label>
            <label>
              to <input type="datetime-local" value={custom.end} onChange={(e) => setCustom({ ...custom, end: e.target.value })} />
            </label>
          </span>
        )}
        {data && (
          <span className="muted small">
            {data.raw_points.toLocaleString()} readings
            {data.resolution_seconds ? `, averaged into ${Math.round(data.resolution_seconds / 60)}-min buckets` : ""}. Times
            are twin time.
          </span>
        )}
      </div>
      {error && <p className="panel error">Couldn't load history: {error}. Check the time range and try again.</p>}

      {data && domain && (
        <>
          <section className="panel">
            <h2 className="panel__label">State timeline</h2>
            <StateTimeline data={data} domain={domain} />
          </section>
          {CHARTS.filter((c) => rows.some((r) => r[c.key] != null)).map((c) => (
            <section className="panel" key={c.key}>
              <figure className="chart">
                <figcaption>
                  <strong>{c.label}</strong> ({c.unit}). Dashed line is the personal resting baseline; shaded spans are
                  anomaly flags on this metric.
                </figcaption>
                <ResponsiveContainer width="100%" height={170}>
                  <ComposedChart data={rows} margin={{ top: 6, right: 12, bottom: 0, left: -10 }} syncId="history">
                    <CartesianGrid stroke="#D5DEE3" strokeDasharray="2 4" vertical={false} />
                    <XAxis dataKey="t" type="number" scale="time" domain={domain} tickFormatter={(t) => tick(t, domain)} tick={{ fontSize: 11, fill: "#5B6F7C" }} minTickGap={50} />
                    <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11, fill: "#5B6F7C" }} width={50} />
                    <Tooltip labelFormatter={(t) => fmtDateTime(new Date(Number(t)).toISOString())} formatter={(v) => [`${Number(v).toFixed(c.digits)} ${c.unit}`, c.label]} />
                    {markers
                      .filter((m) => m.metric === c.metric)
                      .map((m) => (
                        <ReferenceArea key={m.id} x1={toDate(m.start).getTime()} x2={toDate(m.end).getTime()} fill="#B4363F" fillOpacity={0.14} stroke="#B4363F" strokeOpacity={0.4} />
                      ))}
                    {baseline && <ReferenceLine y={c.base(baseline)} stroke="#0E7C7B" strokeDasharray="5 4" />}
                    <Line dataKey={c.key} stroke="#1D2B36" dot={false} strokeWidth={1.4} isAnimationActive={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </figure>
            </section>
          ))}
          <section className="panel">
            <figure className="chart">
              <figcaption>
                <strong>Activity</strong>: steps per reading (bars) and movement intensity 0–1 (line)
              </figcaption>
              <ResponsiveContainer width="100%" height={170}>
                <ComposedChart data={rows} margin={{ top: 6, right: 12, bottom: 0, left: -10 }} syncId="history">
                  <CartesianGrid stroke="#D5DEE3" strokeDasharray="2 4" vertical={false} />
                  <XAxis dataKey="t" type="number" scale="time" domain={domain} tickFormatter={(t) => tick(t, domain)} tick={{ fontSize: 11, fill: "#5B6F7C" }} minTickGap={50} />
                  <YAxis yAxisId="steps" tick={{ fontSize: 11, fill: "#5B6F7C" }} width={50} />
                  <YAxis yAxisId="int" orientation="right" domain={[0, 1]} tick={{ fontSize: 11, fill: "#5B6F7C" }} width={32} />
                  <Tooltip labelFormatter={(t) => fmtDateTime(new Date(Number(t)).toISOString())} />
                  <Bar yAxisId="steps" dataKey="steps" fill="#2F78B7" fillOpacity={0.55} isAnimationActive={false} name="Steps" />
                  <Line yAxisId="int" dataKey="activity_intensity" stroke="#1D2B36" dot={false} strokeWidth={1.2} isAnimationActive={false} name="Intensity" />
                </ComposedChart>
              </ResponsiveContainer>
            </figure>
          </section>
        </>
      )}
    </div>
  );
}

function tick(t: number, domain: [number, number]) {
  const d = new Date(t);
  return domain[1] - domain[0] > 36 * 3600e3 ? fmtDay(d) : fmtClockDate(d, false);
}

function StateTimeline({ data, domain }: { data: HistoryResponse; domain: [number, number] }) {
  const span = domain[1] - domain[0] || 1;
  const present = Array.from(new Set(data.state_segments.map((s) => s.state)));
  return (
    <>
      <div className="timeline" role="img" aria-label="Twin state over time">
        {data.state_segments.map((s, i) => {
          const next = data.state_segments[i + 1];
          const a = toDate(s.start).getTime();
          const b = next ? toDate(next.start).getTime() : toDate(s.end).getTime();
          return (
            <span
              key={i}
              className="timeline__seg"
              title={`${STATE_STYLES[s.state].label}: ${fmtDateTime(s.start)}`}
              style={{ left: `${((a - domain[0]) / span) * 100}%`, width: `${Math.max(((b - a) / span) * 100, 0.15)}%`, background: STATE_STYLES[s.state].color }}
            />
          );
        })}
      </div>
      <ul className="legend">
        {present.map((s) => (
          <li key={s}>
            <span style={{ background: STATE_STYLES[s as TwinStateName].color }} /> {STATE_STYLES[s as TwinStateName].label}
          </li>
        ))}
      </ul>
    </>
  );
}
