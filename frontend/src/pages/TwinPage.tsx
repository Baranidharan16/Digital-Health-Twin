import { useEffect, useState } from "react";
import { OrganCard } from "../components/OrganCard";
import type { LiveTwin } from "../hooks/useLiveTwin";
import { usePlayback } from "../hooks/usePlayback";
import { ANATOMY_CREDIT, DEFAULT_LAYERS, LAYERS, STRUCTURES, type Layer } from "../lib/anatomy";
import { fmtDateTime, fmtNum, localDayKey, toDate } from "../lib/format";
import { STATE_STYLES } from "../lib/states";
import { TwinScene } from "../twin3d/TwinScene";

export function TwinPage({ twin, twinId }: { twin: LiveTwin; twinId: string }) {
  const [labels, setLabels] = useState(true);
  const [xray, setXray] = useState(false);
  const [layers, setLayers] = useState<Record<Layer, boolean>>(DEFAULT_LAYERS);
  const [selected, setSelected] = useState<string | null>(null);
  const playback = usePlayback(twinId);
  const [day, setDay] = useState("");

  useEffect(() => {
    if (!day && twin.state) setDay(localDayKey(toDate(twin.state.twin_time)));
  }, [twin.state, day]);

  const shown = playback.active ? playback.payload : twin.state;
  const point = playback.points[playback.index];

  return (
    <div className="twin-page">
      <div className="twin-page__stage panel">
        <div className="toolbar" role="group" aria-label="Body systems">
          {LAYERS.map((l) => (
            <label key={l.key} className="toggle">
              <input type="checkbox" checked={layers[l.key]} onChange={(e) => setLayers({ ...layers, [l.key]: e.target.checked })} />
              {l.label}
            </label>
          ))}
          <span className="toolbar__sep" aria-hidden />
          <label className="toggle">
            <input type="checkbox" checked={xray} onChange={(e) => setXray(e.target.checked)} /> X-ray
          </label>
          <label className="toggle">
            <input type="checkbox" checked={labels} onChange={(e) => setLabels(e.target.checked)} /> Readings
          </label>
          {shown && (
            <span className="state-tag" style={{ ["--state" as string]: STATE_STYLES[shown.state].color }}>
              {playback.active ? "Playback: " : ""}
              {STATE_STYLES[shown.state].label}
            </span>
          )}
        </div>
        <TwinScene payload={shown} showLabels={labels} xray={xray} layers={layers} selected={selected} onSelect={setSelected} height="min(74vh, 720px)" />
        <p className="twin-caption">Click any organ to see what it does and whether live data drives it. Drag to rotate, scroll to zoom. {ANATOMY_CREDIT}</p>
      </div>

      <aside className="twin-page__side">
        <section className="panel playback">
          <h2 className="panel__label">Play back recorded data on the body</h2>
          <p className="muted small">
            Replays the stored readings for one day, minute by minute, with the state the twin computed for each.
          </p>
          <div className="playback__controls">
            <label>
              Day <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
            </label>
            <button className="btn" onClick={() => day && playback.load(day)} disabled={!day || playback.loading}>
              {playback.loading ? "Loading…" : "Load day"}
            </button>
            {playback.active && (
              <>
                <button className="btn btn--primary" onClick={() => playback.setPlaying(!playback.playing)}>
                  {playback.playing ? "Pause" : "Play"}
                </button>
                <select value={playback.speed} onChange={(e) => playback.setSpeed(Number(e.target.value))} aria-label="Playback speed">
                  <option value={10}>10 readings/s</option>
                  <option value={30}>30 readings/s</option>
                  <option value={90}>90 readings/s</option>
                </select>
              </>
            )}
          </div>
          {playback.error && <p className="error small">Couldn't load that day: {playback.error}. Pick a day inside the data range.</p>}
          {playback.active && point && (
            <>
              <input
                type="range"
                className="playback__scrub"
                min={0}
                max={playback.points.length - 1}
                value={playback.index}
                onChange={(e) => playback.setIndex(Number(e.target.value))}
                aria-label="Playback position"
              />
              <dl className="stats stats--compact">
                <div>
                  <dt>Time</dt>
                  <dd className="small-dd">{fmtDateTime(point.t)}</dd>
                </div>
                <div>
                  <dt>Heart rate</dt>
                  <dd>{fmtNum(point.heart_rate)} <small>bpm</small></dd>
                </div>
                <div>
                  <dt>Steps</dt>
                  <dd>{point.steps}</dd>
                </div>
                <div>
                  <dt>Sleep</dt>
                  <dd className="small-dd">{point.is_asleep ? "Asleep" : "Awake"}</dd>
                </div>
              </dl>
              <p className="muted small">Live view resumes when you leave this page.</p>
            </>
          )}
        </section>
        {selected ? (
          <OrganCard name={selected} state={shown} onClose={() => setSelected(null)} />
        ) : (
          <section className="panel">
            <h2 className="panel__label">What drives each part of the body</h2>
            <p className="muted small">Only structures with matching sensor data move. The rest are anatomy for context.</p>
            <table className="table">
              <tbody>
                {Object.entries(STRUCTURES)
                  .sort((a, b) => Number(!!b[1].drivenBy) - Number(!!a[1].drivenBy))
                  .map(([key, s]) => (
                    <tr key={key} className={s.drivenBy ? "" : "row--static"}>
                      <td>
                        <button className="linklike" onClick={() => setSelected(key)}>
                          {s.label}
                        </button>
                      </td>
                      <td className="small">{s.drivenBy ?? "Not monitored"}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </section>
        )}

      </aside>
    </div>
  );
}
