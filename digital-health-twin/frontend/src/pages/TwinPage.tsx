import { useState } from "react";
import { LiveChart } from "../components/LiveChart";
import type { LiveTwin } from "../hooks/useLiveTwin";
import { fmtNum } from "../lib/format";
import { STATE_STYLES } from "../lib/states";
import { visualsFor } from "../lib/twinVisuals";
import { TwinScene } from "../twin3d/TwinScene";

export function TwinPage({ twin }: { twin: LiveTwin }) {
  const [labels, setLabels] = useState(true);
  const [xray, setXray] = useState(false);
  const s = twin.state;
  const v = s ? visualsFor(s) : null;

  const mapping = s && v
    ? [
        { part: "Heart", shows: "Pulse rate and glow", data: `heart_rate = ${fmtNum(s.observation.heart_rate)} bpm`, status: v.regions.heart },
        { part: "Lungs", shows: "Breathing motion and glow", data: `respiratory_rate = ${fmtNum(s.observation.respiratory_rate)} br/min, spo2 = ${fmtNum(s.observation.spo2, 1)}%`, status: v.regions.lungs },
        { part: "Head", shows: "Temperature highlight", data: `temperature = ${fmtNum(s.observation.temperature, 1)} °C`, status: v.regions.head },
        { part: "Arms and legs", shows: "Gait amplitude and speed", data: `activity_intensity = ${fmtNum(s.observation.activity_intensity, 2)}, steps = ${s.observation.steps}`, status: "normal" },
        { part: "Posture", shows: "Standing or lying down", data: `is_asleep = ${s.observation.is_asleep}`, status: "normal" },
        { part: "Body tint", shows: "Overall twin state", data: `state = ${s.state}`, status: s.state === "ANOMALOUS" ? "anomalous" : s.state === "ELEVATED" ? "watch" : "normal" },
      ]
    : [];

  return (
    <div className="twin-page">
      <div className="twin-page__stage panel">
        <div className="toolbar">
          <label>
            <input type="checkbox" checked={labels} onChange={(e) => setLabels(e.target.checked)} /> Show readings on the body
          </label>
          <label>
            <input type="checkbox" checked={xray} onChange={(e) => setXray(e.target.checked)} /> X-ray view
          </label>
          {s && (
            <span className="state-tag" style={{ ["--state" as string]: STATE_STYLES[s.state].color }}>
              {STATE_STYLES[s.state].label}
            </span>
          )}
        </div>
        <TwinScene payload={s} showLabels={labels} xray={xray} height="min(72vh, 680px)" />
      </div>
      <aside className="twin-page__side">
        <section className="panel">
          <h2 className="panel__label">What drives each part of the body</h2>
          <p className="muted small">
            The 3D body is not decoration: every visual is bound to one field of the twin state. Model built in Blender
            (blender/build_human_twin.py) and exported as GLB.
          </p>
          <table className="table">
            <thead>
              <tr>
                <th>Body part</th>
                <th>Shows</th>
                <th>Live data</th>
              </tr>
            </thead>
            <tbody>
              {mapping.map((m) => (
                <tr key={m.part} className={`row--${m.status}`}>
                  <td>{m.part}</td>
                  <td>{m.shows}</td>
                  <td className="mono-num">{m.data}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="panel">
          <LiveChart buffer={twin.buffer} metric="respiratory_rate" height={150} />
          <LiveChart buffer={twin.buffer} metric="spo2" height={150} />
          <LiveChart buffer={twin.buffer} metric="temperature" height={150} />
        </section>
      </aside>
    </div>
  );
}
