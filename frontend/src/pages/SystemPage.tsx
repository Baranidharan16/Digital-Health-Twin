import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { LiveStatus, SystemInfo } from "../api/types";

export function SystemPage({ onStatus }: { onStatus: (s: LiveStatus) => void }) {
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => api.system().then(setInfo).catch((e) => setMessage(`Couldn't load system info: ${e.message}`));
  useEffect(() => {
    load();
  }, []);

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(true);
    setMessage(null);
    try {
      const out = await fn();
      if (out && typeof out === "object" && "running" in out) onStatus(out as LiveStatus);
      setMessage(label);
      load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const curl = `curl -X POST http://localhost:8000/api/twin/twin-001/observations \\
  -H "Content-Type: application/json" \\
  -d '{"timestamp":"2026-10-01T10:00:00Z","heart_rate":72,"spo2":98,
       "temperature":36.7,"respiratory_rate":14,"steps":12,
       "activity_intensity":0.1,"source":"my-wearable"}'`;

  return (
    <div className="system">
      <section className="panel">
        <h2 className="panel__label">Data pipeline</h2>
        <ol className="flow">
          {info?.pipeline.map((p) => (
            <li key={p.step}>
              <strong>{p.step}</strong>
              <span>{p.detail}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="panel">
        <h2 className="panel__label">Data sources (adapters)</h2>
        <p className="muted small">
          Every source is converted to one normalized observation format before it reaches the twin engine, so a real
          wearable can replace the simulator without changing the engine.
        </p>
        <table className="table">
          <tbody>
            {info?.adapters.map((a) => (
              <tr key={a.name}>
                <td>
                  <strong>{a.name}</strong>
                </td>
                <td>
                  <span className={`status status--${a.status === "active" ? "normal" : a.status === "planned" ? "planned" : "available"}`}>{a.status}</span>
                </td>
                <td>{a.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <h3 className="panel__label">Send your own reading</h3>
        <pre className="code">{curl}</pre>
        <p className="muted small">
          Pause the simulator first. Full API reference: <a href="/docs" target="_blank" rel="noreferrer">OpenAPI docs</a>.
        </p>
      </section>

      <section className="panel">
        <h2 className="panel__label">Engine rules</h2>
        {info && (
          <>
            <table className="table">
              <thead>
                <tr>
                  <th>Vital</th>
                  <th>Direction</th>
                  <th>Flag at robust z ≥</th>
                  <th>Watch at z ≥</th>
                  <th>And change ≥</th>
                  <th>Spread floor</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(info.engine.anomaly_rules).map(([m, r]) => (
                  <tr key={m}>
                    <td>{m}</td>
                    <td>{r.direction}</td>
                    <td className="mono-num">{r.z_anomalous}</td>
                    <td className="mono-num">{r.z_watch}</td>
                    <td className="mono-num">
                      {r.min_abs_change} and {r.min_pct_change}%
                    </td>
                    <td className="mono-num">{r.spread_floor}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">
              A flag needs {info.engine.persistence_readings} consecutive unusual readings and clears after{" "}
              {info.engine.clear_readings} normal ones. Other state changes need {info.engine.state_confirm_readings}{" "}
              confirming readings. Priority: {info.engine.state_priority.join(" > ")}.
            </p>
          </>
        )}
      </section>

      <section className="panel">
        <h2 className="panel__label">Demo and storage</h2>
        {info && (
          <dl className="stats">
            {Object.entries(info.counts).map(([k, v]) => (
              <div key={k}>
                <dt>{k.replace("_", " ")}</dt>
                <dd>{v.toLocaleString()}</dd>
              </div>
            ))}
            <div>
              <dt>database</dt>
              <dd>{info.database}</dd>
            </div>
            <div>
              <dt>live viewers</dt>
              <dd>{info.websocket_clients}</dd>
            </div>
          </dl>
        )}
        <div className="button-row">
          <button className="btn" disabled={busy} onClick={() => act("Replaying the recorded demo session.", () => api.liveStart("NORMAL", false, "replay"))}>
            Play recorded session (backup demo)
          </button>
          <button className="btn" disabled={busy} onClick={() => act("Demo data reset. Press Resume data to start streaming.", api.resetDemo)}>
            Reset demo data
          </button>
        </div>
        {message && <p className="muted" role="status">{message}</p>}
      </section>

      <section className="panel privacy">
        <h2 className="panel__label">Privacy and intended use</h2>
        <p>
          This is a research and demonstration prototype. All data is synthetic: the subject is a pseudonym with an age
          and simulated physiology, and no names, contact details or device identifiers are stored. The ingestion API
          rejects unknown fields. It is not a medical device; states and flags describe the data, not a diagnosis, and
          nothing here is treatment advice.
        </p>
      </section>
    </div>
  );
}
