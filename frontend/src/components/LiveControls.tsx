import { useState } from "react";
import { api } from "../api/client";
import type { LiveStatus } from "../api/types";
import { SCENARIO_HINTS } from "../lib/states";

const ORDER = ["NORMAL", "EXERCISE", "RECOVERY", "ANOMALY", "SLEEP"];

export function LiveControls({ live, onStatus }: { live: LiveStatus | null; onStatus: (s: LiveStatus) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (fn: () => Promise<LiveStatus>) => {
    setBusy(true);
    setError(null);
    try {
      onStatus(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const choose = (key: string) =>
    run(() => (live?.running && live.mode === "simulator" ? api.liveScenario(key) : api.liveStart(key)));

  const scenarios = live?.scenarios.length
    ? [...live.scenarios].sort((a, b) => ORDER.indexOf(a.key) - ORDER.indexOf(b.key))
    : ORDER.map((key) => ({ key, label: key[0] + key.slice(1).toLowerCase(), description: "" }));

  return (
    <section className="live-controls" aria-label="Live data controls">
      <div className="live-controls__group" role="group" aria-label="What the simulated person is doing">
        <span className="live-controls__title">Simulated person is</span>
        {scenarios.map((s) => {
          const active = live?.running && live.scenario === s.key;
          return (
            <button
              key={s.key}
              className={`chip ${active ? "chip--on" : ""} ${s.key === "ANOMALY" ? "chip--warn" : ""}`}
              disabled={busy}
              aria-pressed={!!active}
              title={s.description}
              onClick={() => choose(s.key)}
            >
              <span>{s.label}</span>
              <small>{SCENARIO_HINTS[s.key] ?? ""}</small>
            </button>
          );
        })}
      </div>
      <div className="live-controls__group">
        <button className="btn btn--primary" disabled={busy} onClick={() => run(() => api.liveStart("NORMAL", true))}>
          {live?.guided ? `Guided demo ${live.guided_step ?? ""}` : "Run guided demo"}
        </button>
        {live?.running ? (
          <button className="btn" disabled={busy} onClick={() => run(api.liveStop)}>
            Pause data
          </button>
        ) : (
          <button className="btn" disabled={busy} onClick={() => run(() => api.liveStart(live?.scenario && live.scenario !== "REPLAY" ? live.scenario : "NORMAL"))}>
            Resume data
          </button>
        )}
        <span className="live-controls__note">
          {live?.mode === "replay"
            ? "Replaying recorded session"
            : `1 s on screen = ${live?.twin_seconds_per_tick ?? 15} s of twin time`}
        </span>
      </div>
      {error && (
        <p className="live-controls__error" role="alert">
          Couldn't change live data: {error}
        </p>
      )}
    </section>
  );
}
