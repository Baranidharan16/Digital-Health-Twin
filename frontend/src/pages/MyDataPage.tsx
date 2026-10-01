import { useEffect, useState, type FormEvent } from "react";
import { api, TWIN_ID } from "../api/client";
import type { ImportSummary, TwinInfo } from "../api/types";
import { fmtDateTimeAt, utcLabel } from "../lib/format";
import { PhoneConnect } from "../components/PhoneConnect";

const browserOffset = () => -new Date().getTimezoneOffset() / 60;

const OFFSETS = [
  -8, -7, -6, -5, -4, -3, 0, 1, 2, 3, 4, 5, 5.5, 5.75, 6, 7, 8, 9, 10, 12,
];

export function MyDataPage({
  onOpenTwin,
  onTwinsChanged,
}: {
  onOpenTwin: (id: string) => void;
  onTwinsChanged: () => void;
}) {
  const [twins, setTwins] = useState<TwinInfo[]>([]);
  const [files, setFiles] = useState<FileList | null>(null);
  const [name, setName] = useState("My twin");
  const [age, setAge] = useState(25);
  const [offset, setOffset] = useState(browserOffset());
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<ImportSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const resultOffset =
    twins.find((t) => t.id === result?.twin_id)?.subject.utc_offset_hours ??
    offset;

  const refresh = () =>
    api
      .twins()
      .then(setTwins)
      .catch(() => undefined);
  useEffect(() => {
    refresh();
  }, []);

  const finish = (summary: ImportSummary) => {
    setResult(summary);
    refresh();
    onTwinsChanged();
  };

  const upload = async (e: FormEvent) => {
    e.preventDefault();
    if (!files?.length) return;
    setBusy("Reading your files and building your twin…");
    setError(null);
    setResult(null);
    const form = new FormData();
    Array.from(files).forEach((f) => form.append("files", f));
    form.append("display_name", name);
    form.append("age_years", String(age));
    form.append("utc_offset_hours", String(offset));
    form.append(
      "data_source",
      guessSource(Array.from(files).map((f) => f.name)),
    );
    try {
      finish(await api.importFiles(form));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const sample = async () => {
    setBusy("Loading 14 days of a real Fitbit user's data…");
    setError(null);
    setResult(null);
    try {
      finish(await api.importSample());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const remove = async (id: string) => {
    setError(null);
    try {
      await api.deleteTwin(id);
      if (result?.twin_id === id) setResult(null);
      refresh();
      onTwinsChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="mydata">
      <section className="panel mydata__intro">
        <h2 className="mydata__title">Build a twin from real data</h2>
        <p>
          The demo twin runs on simulated data. Here the same engine learns from{" "}
          <strong>real</strong> wearable readings: your own export, or a public
          dataset from real Fitbit users. It learns that person's baseline,
          replays every reading, and flags anything unusual for them.
        </p>
        <div className="mydata__sample">
          <div>
            <h3>Try it with a real person's data</h3>
            <p className="muted small">
              14 days from one participant of the public Fitbit Fitness Tracker
              dataset (Furberg et al., 2016, CC0): heart rate every 5 s, steps
              and sleep per minute. No SpO₂, temperature or breathing, because
              that device didn't measure them.
            </p>
          </div>
          <button
            className="btn btn--primary"
            onClick={sample}
            disabled={!!busy}
          >
            Load real Fitbit sample
          </button>
        </div>
      </section>

      <PhoneConnect
        onOpenTwin={onOpenTwin}
        onTwinsChanged={() => {
          refresh();
          onTwinsChanged();
        }}
      />

      <section className="panel">
        <h2 className="panel__label">Upload your own export</h2>
        <form className="upload" onSubmit={upload}>
          <label className="upload__drop">
            <input
              type="file"
              accept=".csv,text/csv"
              multiple
              onChange={(e) => setFiles(e.target.files)}
            />
            <span>
              {files?.length
                ? `${files.length} file${files.length > 1 ? "s" : ""}: ${Array.from(
                    files,
                  )
                    .map((f) => f.name)
                    .join(", ")}`
                : "Choose one or more CSV files"}
            </span>
          </label>
          <div className="upload__fields">
            <label>
              Nickname <small>(avoid your real name)</small>
              <input
                value={name}
                maxLength={60}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Age <small>(for max heart-rate estimate)</small>
              <input
                type="number"
                min={10}
                max={100}
                value={age}
                onChange={(e) => setAge(Number(e.target.value))}
              />
            </label>
            <label>
              Device time zone
              <select
                value={offset}
                onChange={(e) => setOffset(Number(e.target.value))}
              >
                {Array.from(new Set([offset, ...OFFSETS]))
                  .sort((a, b) => a - b)
                  .map((o) => (
                    <option key={o} value={o}>
                      {utcLabel(o)}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <button
            className="btn btn--primary"
            type="submit"
            disabled={!files?.length || !!busy}
          >
            Build my twin
          </button>
        </form>
        <details className="formats">
          <summary>Which files work, and how to get them</summary>
          <ul>
            <li>
              <strong>Samsung Health</strong>: app → Settings → Download
              personal data. Upload the CSVs whose names contain{" "}
              <code>heart_rate</code>, <code>pedometer_step_count</code> and{" "}
              <code>sleep</code>.
            </li>
            <li>
              <strong>Google Fit</strong>: takeout.google.com → Fit → "Daily
              activity metrics" folder. Upload the day files (named like{" "}
              <code>2024-05-01.csv</code>).
            </li>
            <li>
              <strong>Fitbit</strong>: Fitabase-style exports (
              <code>heartrate_seconds_merged.csv</code>,{" "}
              <code>minuteStepsNarrow_merged.csv</code>,{" "}
              <code>minuteSleep_merged.csv</code>).
            </li>
            <li>
              <strong>Any watch or app</strong>: a CSV with a{" "}
              <code>timestamp</code> column and any of{" "}
              <code>
                heart_rate, spo2, temperature, respiratory_rate, steps,
                activity_intensity, is_asleep
              </code>
              .
            </li>
          </ul>
          <p className="muted small">
            Heart rate is required. Everything else is optional, and anything
            missing is shown as "not measured", never made up.
          </p>
        </details>
      </section>

      {(busy || error || result) && (
        <section className="panel" aria-live="polite">
          {busy && <p>{busy} This can take up to a minute for large files.</p>}
          {error && <p className="error">Couldn't build the twin: {error}</p>}
          {result && (
            <div className="import-result">
              <h2 className="panel__label">Twin created from real data</h2>
              <dl className="stats">
                <div>
                  <dt>Readings</dt>
                  <dd>{result.observations.toLocaleString()}</dd>
                </div>
                <div>
                  <dt>Resolution</dt>
                  <dd>{result.interval_seconds / 60} min</dd>
                </div>
                <div>
                  <dt>Sleep recorded</dt>
                  <dd>{(result.sleep_minutes / 60).toFixed(0)} h</dd>
                </div>
                <div>
                  <dt>Vitals measured</dt>
                  <dd className="small-dd">
                    {result.metrics_measured
                      .map((m) => m.replace("_", " "))
                      .join(", ")}
                  </dd>
                </div>
              </dl>
              <p className="small">
                {fmtDateTimeAt(result.start, resultOffset)} to{" "}
                {fmtDateTimeAt(result.end, resultOffset)} (device time). Files:{" "}
                {result.files.map((f) => `${f.name} (${f.format})`).join("; ")}.
              </p>
              <ul className="small muted">
                {result.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
              <button
                className="btn btn--primary"
                onClick={() => onOpenTwin(result.twin_id)}
              >
                Open this twin
              </button>
            </div>
          )}
        </section>
      )}

      <section className="panel">
        <h2 className="panel__label">Your twins</h2>
        <table className="table">
          <thead>
            <tr>
              <th>Twin</th>
              <th>Data</th>
              <th>Readings</th>
              <th>Last reading</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {twins.map((t) => (
              <tr key={t.id}>
                <td>{t.subject.pseudonym}</td>
                <td>
                  {t.subject.is_synthetic
                    ? "Simulated (demo)"
                    : (t.subject.data_source ?? "Uploaded")}
                </td>
                <td className="mono-num">
                  {t.observation_count.toLocaleString()}
                </td>
                <td className="mono-num">
                  {t.last_observation_at
                    ? fmtDateTimeAt(
                        t.last_observation_at,
                        t.subject.utc_offset_hours,
                      )
                    : "–"}
                </td>
                <td className="table__actions">
                  <button className="btn" onClick={() => onOpenTwin(t.id)}>
                    Open
                  </button>
                  {t.id !== TWIN_ID && (
                    <button
                      className="btn btn--danger"
                      onClick={() => remove(t.id)}
                    >
                      Delete data
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small">
          Privacy: files are processed on this machine by the local backend;
          only a nickname, age, time zone and the readings are stored. "Delete
          data" removes the twin and every reading permanently.
        </p>
      </section>
    </div>
  );
}

function guessSource(names: string[]): string {
  const joined = names.join(" ").toLowerCase();
  if (joined.includes("samsung")) return "Samsung Health export";
  if (joined.includes("merged")) return "Fitbit export";
  if (names.some((n) => /\d{4}-\d{2}-\d{2}\.csv$/i.test(n)))
    return "Google Fit export";
  return "Wearable export";
}
