import type { TwinStatePayload } from "../api/types";
import { NOT_MONITORED, STRUCTURES } from "../lib/anatomy";
import { METRICS } from "../lib/states";

/** What a structure is, and — honestly — what (if any) live data drives it. */
export function OrganCard({ name, state, onClose }: { name: string; state: TwinStatePayload | null; onClose?: () => void }) {
  const info = STRUCTURES[name];
  if (!info) return null;
  const live = (info.metrics ?? [])
    .map((m) => ({ meta: METRICS.find((x) => x.key === m)!, a: state?.assessments[m] }))
    .filter((x) => x.meta);
  const measured = live.filter((x) => x.a);
  return (
    <section className={`panel organ-card ${info.drivenBy ? "" : "organ-card--static"}`} aria-live="polite">
      <div className="panel__row">
        <div>
          <h2 className="organ-card__title">{info.label}</h2>
          <p className="muted small">{info.system} system</p>
        </div>
        {onClose && (
          <button className="btn btn--quiet" onClick={onClose} aria-label="Close organ details">
            Close
          </button>
        )}
      </div>
      <p className="organ-card__role">{info.role}</p>
      {info.drivenBy ? (
        <>
          <h3 className="panel__label">In this twin</h3>
          <p className="small">{info.drivenBy}</p>
          {measured.length > 0 && (
            <ul className="organ-card__live">
              {measured.map(({ meta, a }) => (
                <li key={meta.key} className={`status-text--${a!.status}`}>
                  {meta.label} <b>{a!.value.toFixed(meta.digits)}</b> {meta.unit}: {a!.status === "normal" ? `expected for this person ${a!.context}` : a!.reason}
                </li>
              ))}
            </ul>
          )}
          {live.length > measured.length && (
            <p className="muted small">
              Not measured by this device: {live.filter((x) => !x.a).map((x) => x.meta.label).join(", ")}. That part stays still.
            </p>
          )}
        </>
      ) : (
        <p className="muted small">{NOT_MONITORED}</p>
      )}
    </section>
  );
}
