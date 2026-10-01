import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AnalyticsResponse, BaselineResponse, Evaluation, TwinStateName } from "../api/types";
import { fmtDateTime, fmtNum, fmtSigned, pct } from "../lib/format";
import { STATE_STYLES } from "../lib/states";

export function AnalyticsPage({ version }: { version: string }) {
  const [baseline, setBaseline] = useState<BaselineResponse | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [recomputing, setRecomputing] = useState(false);

  useEffect(() => {
    api.baseline().then(setBaseline).catch(() => undefined);
  }, [version]);
  useEffect(() => {
    api.analytics("7d").then(setAnalytics).catch(() => undefined);
    api.evaluation().then(setEvaluation).catch(() => undefined);
  }, []);

  const recompute = async () => {
    setRecomputing(true);
    try {
      await api.recomputeBaseline();
      setBaseline(await api.baseline());
    } finally {
      setRecomputing(false);
    }
  };

  const b = baseline?.data;
  return (
    <div className="analytics">
      <section className="panel analytics__baseline">
        <div className="panel__row">
          <h2 className="panel__label">Now vs. personal baseline</h2>
          <button className="btn" onClick={recompute} disabled={recomputing}>
            {recomputing ? "Re-learning…" : "Re-learn baseline from last 7 days"}
          </button>
        </div>
        <p className="muted small">
          The twin learns what is normal for this person (median and spread of their own readings, excluding flagged
          periods), then expects vitals to move with activity. A resting heart rate of 80 bpm is ordinary for many
          people, but it is a large change for someone whose baseline is 64 bpm.
        </p>
        <table className="table">
          <thead>
            <tr>
              <th>Vital</th>
              <th>Now</th>
              <th>Personal baseline</th>
              <th>Change</th>
              <th>Expected right now</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {baseline?.comparison.map((c) => (
              <tr key={c.metric} className={`row--${c.status}`}>
                <td>{c.label}</td>
                <td className="mono-num">
                  {fmtNum(c.current, c.metric === "temperature" || c.metric === "spo2" ? 1 : 0)} {c.unit}
                </td>
                <td className="mono-num">
                  {fmtNum(c.baseline, 1)} {c.unit} <span className="muted">({c.baseline_context})</span>
                </td>
                <td className="mono-num">
                  {fmtSigned(c.diff_from_baseline, 1)} ({fmtSigned(c.diff_from_baseline_pct)}%)
                </td>
                <td className="mono-num">
                  {c.expected_low === c.expected_high ? fmtNum(c.expected, 1) : `${fmtNum(c.expected_low, 1)}–${fmtNum(c.expected_high, 1)}`}{" "}
                  <span className="muted">{c.context}</span>
                </td>
                <td>
                  <span className={`status status--${c.status}`}>{c.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {b && (
          <p className="muted small">
            Learned from {b.sample_count.toLocaleString()} readings
            {b.window_start && b.window_end ? `, ${fmtDateTime(b.window_start)} to ${fmtDateTime(b.window_end)}` : ""}.
            Resting HR {b.hr_rest} ± {b.hr_rest_spread} bpm, sleeping HR {b.hr_sleep} bpm, estimated max HR {b.hr_max_est}{" "}
            bpm, typical sleep {b.sleep_hours} h, typical {Math.round(b.daily_steps).toLocaleString()} steps/day.
          </p>
        )}
      </section>

      <section className="panel analytics__validation">
        <h2 className="panel__label">Does the anomaly detector work? Measured against ground truth</h2>
        {!evaluation ? (
          <p className="muted">Running validation on 5 synthetic weeks…</p>
        ) : (
          <>
            <p className="muted small">
              The simulator injected {evaluation.injected_episodes} anomaly episodes of varying strength into{" "}
              {evaluation.test_days_total} unseen days (with normal exercise and sleep). Same data, two detectors.
            </p>
            <div className="versus">
              <div className="versus__col versus__col--twin">
                <h3>Personal, activity-aware twin</h3>
                <p className="versus__big">{pct(evaluation.twin.event_recall)}</p>
                <p>of episodes caught</p>
                <p className="versus__big">{evaluation.twin.false_alarms_per_day.toFixed(1)}</p>
                <p>false alarms per day</p>
                <p className="muted small">median {evaluation.twin.median_detection_latency_min} min to flag (5-min readings)</p>
              </div>
              <div className="versus__col">
                <h3>Population thresholds</h3>
                <p className="versus__big">{pct(evaluation.population_threshold_rule.event_recall)}</p>
                <p>of episodes caught</p>
                <p className="versus__big">{evaluation.population_threshold_rule.false_alarms_per_day.toFixed(1)}</p>
                <p>false alarms per day</p>
                <p className="muted small">{evaluation.population_threshold_rule.rule}</p>
              </div>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>Episode strength</th>
                  <th>Episodes</th>
                  <th>Twin caught</th>
                  <th>Thresholds caught</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(evaluation.recall_by_severity).map(([k, v]) => (
                  <tr key={k}>
                    <td>{k[0].toUpperCase() + k.slice(1)}</td>
                    <td className="mono-num">{v.episodes}</td>
                    <td className="mono-num">{v.twin_recall == null ? "–" : pct(v.twin_recall)}</td>
                    <td className="mono-num">{v.population_rule_recall == null ? "–" : pct(v.population_rule_recall)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">
              Baseline learning error: resting HR within {evaluation.baseline_learning.max_abs_error_resting_hr_bpm} bpm of the
              simulator's true value. This validates the engine against its own simulator, not clinically.
            </p>
          </>
        )}
      </section>

      {analytics && !("empty" in analytics) && (
        <>
          <section className="panel">
            <h2 className="panel__label">Time in each state, last 7 days</h2>
            <div className="stack-bar" role="img" aria-label="Share of time per state">
              {Object.entries(analytics.time_in_state_pct)
                .sort((a, b) => b[1] - a[1])
                .map(([s, v]) => (
                  <span key={s} title={`${STATE_STYLES[s as TwinStateName]?.label}: ${v}%`} style={{ width: `${v}%`, background: STATE_STYLES[s as TwinStateName]?.color }} />
                ))}
            </div>
            <ul className="legend">
              {Object.entries(analytics.time_in_state_pct)
                .sort((a, b) => b[1] - a[1])
                .map(([s, v]) => (
                  <li key={s}>
                    <span style={{ background: STATE_STYLES[s as TwinStateName]?.color }} /> {STATE_STYLES[s as TwinStateName]?.label} {v}%
                  </li>
                ))}
            </ul>
            <p className="muted small">
              {analytics.transitions} state transitions and {analytics.anomaly_episodes} anomaly episodes from{" "}
              {analytics.observations.toLocaleString()} readings. Heart rate vs movement correlation r ={" "}
              {fmtNum(analytics.hr_intensity_correlation, 2)}.
            </p>
          </section>

          {analytics.daily && (
            <section className="panel">
              <h2 className="panel__label">Day by day</h2>
              <table className="table">
                <thead>
                  <tr>
                    <th>Day</th>
                    <th>Steps</th>
                    <th>Active min</th>
                    <th>Resting HR</th>
                    <th>Sleep</th>
                    <th>Flagged readings</th>
                  </tr>
                </thead>
                <tbody>
                  {analytics.daily.map((d) => (
                    <tr key={d.day} className={d.anomalous_readings ? "row--anomalous" : ""}>
                      <td>{new Date(d.day).toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })}</td>
                      <td className="mono-num">{d.steps.toLocaleString()}</td>
                      <td className="mono-num">{fmtNum(d.active_minutes)}</td>
                      <td className="mono-num">{d.resting_hr ? `${d.resting_hr} bpm` : "–"}</td>
                      <td className="mono-num">{d.sleep_hours.toFixed(1)} h</td>
                      <td className="mono-num">{d.anomalous_readings}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted small">
                Resting heart-rate trend: {fmtNum(analytics.metrics.heart_rate.resting_trend_per_day, 2)} bpm/day. Days are in the
                subject's local time; first and last days are partial.
              </p>
            </section>
          )}
        </>
      )}
    </div>
  );
}
