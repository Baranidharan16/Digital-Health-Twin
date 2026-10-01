import type { TwinEvent } from "../api/types";
import { fmtDateTime } from "../lib/format";
import { STATE_STYLES } from "../lib/states";
import type { TwinStateName } from "../api/types";

export function EventFeed({ events, limit = 8 }: { events: TwinEvent[]; limit?: number }) {
  return (
    <section className="panel events" aria-label="State changes and anomaly flags">
      <h2 className="panel__label">What changed, and why</h2>
      {events.length === 0 && <p className="muted">No events yet. Start the exercise scenario to see the twin change state.</p>}
      <ol className="events__list">
        {events.slice(0, limit).map((e) => {
          const color =
            e.kind === "anomaly"
              ? "#B4363F"
              : e.to_state
                ? STATE_STYLES[e.to_state as TwinStateName]?.color ?? "#5B6F7C"
                : "#5B6F7C";
          return (
            <li key={`${e.kind}-${e.id}`} className={`event event--${e.kind}`} style={{ ["--event" as string]: color }}>
              <div className="event__head">
                <span className="event__title">
                  {e.kind === "transition" && e.to_state
                    ? `${e.from_state ? STATE_STYLES[e.from_state as TwinStateName]?.label ?? e.from_state : "Start"} to ${STATE_STYLES[e.to_state as TwinStateName]?.label ?? e.to_state}`
                    : e.title}
                </span>
                <time>{fmtDateTime(e.timestamp)}</time>
              </div>
              <p className="event__detail">{e.detail}</p>
              {e.kind === "anomaly" && <span className="event__badge">{e.active ? "Still active" : "Resolved"}</span>}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
