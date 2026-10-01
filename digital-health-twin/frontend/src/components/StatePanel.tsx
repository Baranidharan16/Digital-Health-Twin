import type { TwinStatePayload } from "../api/types";
import { fmtClock, fmtDuration, toDate } from "../lib/format";
import { STATE_STYLES } from "../lib/states";

export function StatePanel({ state }: { state: TwinStatePayload | null }) {
  if (!state) return <section className="panel state-panel">Connecting to the twin…</section>;
  const style = STATE_STYLES[state.state];
  const since = (toDate(state.twin_time).getTime() - toDate(state.state_since).getTime()) / 1000;
  return (
    <section className="panel state-panel" aria-live="polite" style={{ ["--state" as string]: style.color }}>
      <h2 className="panel__label">Current state</h2>
      <p className="state-panel__name">{style.label}</p>
      <p className="state-panel__since">
        for {fmtDuration(since)} of twin time
        {state.previous_state && <> · was {STATE_STYLES[state.previous_state].label.toLowerCase()}</>}
      </p>
      <h3 className="panel__label">Why</h3>
      <p className="state-panel__reason">{state.state_reason}</p>
      <dl className="state-panel__meta">
        <div>
          <dt>Last reading</dt>
          <dd>{fmtClock(state.twin_time)} twin time</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>{state.observation.source}</dd>
        </div>
      </dl>
    </section>
  );
}
