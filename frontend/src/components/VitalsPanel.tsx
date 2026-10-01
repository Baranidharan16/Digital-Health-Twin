import type { Assessment, TwinStatePayload } from "../api/types";
import { fmtNum } from "../lib/format";
import { METRICS, STATUS_COLORS } from "../lib/states";

/** One gauge per vital: the personal expected band, and where the reading sits. */
export function VitalsPanel({ state }: { state: TwinStatePayload | null }) {
  return (
    <section className="panel vitals" aria-label="Vital signs">
      <h2 className="panel__label">Vitals vs. this person's expected range</h2>
      {METRICS.map((m) => {
        const a = state?.assessments[m.key];
        if (state && !a) {
          return (
            <div key={m.key} className="vital vital--unmeasured">
              <div className="vital__head">
                <span className="vital__label">{m.label}</span>
                <span className="vital__value">
                  –<small>{m.unit}</small>
                </span>
              </div>
              <p className="vital__note">Not measured by this device, so the twin does not monitor it.</p>
            </div>
          );
        }
        return (
          <div key={m.key} className={`vital vital--${a?.status ?? "normal"}`}>
            <div className="vital__head">
              <span className="vital__label">{m.label}</span>
              <span className="vital__value">
                {fmtNum(a?.value, m.digits)}
                <small>{m.unit}</small>
              </span>
            </div>
            {a && <Gauge a={a} digits={m.digits} />}
            <p className="vital__note">
              {a ? (a.status === "normal" ? `Expected ${band(a, m.digits)} ${m.unit} ${a.context}` : a.reason) : "–"}
            </p>
          </div>
        );
      })}
    </section>
  );
}

function band(a: Assessment, digits: number) {
  return a.expected_low === a.expected_high
    ? `≈${a.expected_low.toFixed(digits)}`
    : `${a.expected_low.toFixed(digits)}–${a.expected_high.toFixed(digits)}`;
}

function Gauge({ a, digits }: { a: Assessment; digits: number }) {
  // Scale: expected band ± 4 personal spreads (deviation/z gives the spread).
  const spread = a.robust_z !== 0 ? Math.abs(a.deviation / a.robust_z) : Math.max((a.expected_high - a.expected_low) / 2, Math.abs(a.expected) * 0.04);
  const lo = Math.min(a.expected_low - 4 * spread, a.value);
  const hi = Math.max(a.expected_high + 4 * spread, a.value);
  const x = (v: number) => `${((v - lo) / (hi - lo || 1)) * 100}%`;
  return (
    <div
      className="gauge"
      role="meter"
      aria-valuenow={a.value}
      aria-valuemin={lo}
      aria-valuemax={hi}
      aria-label={`${a.value.toFixed(digits)}, expected ${band(a, digits)}`}
    >
      <div className="gauge__track" />
      <div
        className="gauge__band"
        style={{ left: x(a.expected_low - spread), width: `calc(${x(a.expected_high + spread)} - ${x(a.expected_low - spread)})` }}
      />
      <div className="gauge__marker" style={{ left: x(a.value), background: STATUS_COLORS[a.status] }} />
    </div>
  );
}
