import type { LiveStatus, TwinStatePayload } from "../api/types";
import { STATE_STYLES } from "../lib/states";
import type { Connection } from "../hooks/useLiveTwin";

interface Props {
  state: TwinStatePayload | null;
  live: LiveStatus | null;
  connection: Connection;
  freshness: number | null;
  onNavigate: (page: string) => void;
  /** True for twins built from uploaded real data (no live stream). */
  recorded?: boolean;
}

/**
 * The first thing a judge sees: the digital twin loop, each step showing what
 * it is doing right now. Doubles as the "How it works" explanation.
 */
export function PipelineStrip({ state, live, connection, freshness, onNavigate, recorded = false }: Props) {
  const anomalies = state ? Object.values(state.assessments).filter((a) => a.status !== "normal") : [];
  const steps = [
    {
      title: "Readings arrive",
      body: state
        ? `${state.observation.source} sends ${["heart rate", ...(state.observation.spo2 != null ? ["SpO₂"] : []), ...(state.observation.temperature != null ? ["temperature"] : []), ...(state.observation.respiratory_rate != null ? ["breathing"] : []), "steps", ...(state.observation.is_asleep ? ["sleep"] : [])].join(", ")}`
        : "Waiting for data",
      value: recorded
        ? state?.observation.source === "health-connect"
          ? "Synced from phone"
          : "Recorded data"
        : connection === "live" && live?.running
          ? freshness !== null
            ? `${freshness.toFixed(1)} s ago`
            : "streaming"
          : live?.running === false
            ? "paused"
            : connection,
      page: "system",
    },
    {
      title: "Twin updates",
      body: "Validated, stored and compared with what this person's own body normally does",
      value: state ? `${Math.round(state.effective_intensity * 100)}% activity context` : "–",
      page: "twin",
    },
    {
      title: "State changes",
      body: state ? STATE_STYLES[state.state].plain : "–",
      value: state ? STATE_STYLES[state.state].label : "–",
      color: state ? STATE_STYLES[state.state].color : undefined,
      page: "overview",
    },
    {
      title: "Analytics explain",
      body: anomalies.length ? anomalies[0].reason ?? "" : "Every measured vital is inside this person's expected range",
      value: anomalies.length ? `${anomalies.length} vital${anomalies.length > 1 ? "s" : ""} flagged` : "0 flags",
      page: "analytics",
    },
    {
      title: "Simulate what-ifs",
      body: "Run exercise or short-sleep scenarios on this twin's personal model",
      value: "Open simulator",
      page: "simulation",
    },
  ];
  return (
    <ol className="pipeline" aria-label="How the digital twin works">
      {steps.map((s, i) => (
        <li key={s.title} className="pipeline__step">
          <button className="pipeline__btn" onClick={() => onNavigate(s.page)}>
            <span className="pipeline__num" aria-hidden>
              {i + 1}
            </span>
            <span className="pipeline__title">{s.title}</span>
            <span className="pipeline__value" style={s.color ? { color: s.color } : undefined}>
              {s.value}
            </span>
            <span className="pipeline__body">{s.body}</span>
          </button>
        </li>
      ))}
    </ol>
  );
}
