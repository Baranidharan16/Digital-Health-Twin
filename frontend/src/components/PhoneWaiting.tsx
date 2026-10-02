import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { PhoneDevice } from "../api/types";

const STATUS: Record<string, string> = {
  waiting_for_more_data:
    "The phone synced, but there isn't enough heart-rate history yet to learn your normal (about a day including some rest). Wear your watch and tap Sync now again later.",
  no_heart_rate:
    "The phone synced, but Health Connect had no heart-rate readings. Check that your watch app (Samsung Health, Fitbit, Google Fit…) shares heart rate with Health Connect.",
  nothing_new: "The phone synced, but there were no readings in the last 7 days.",
};

/** Shown for a paired phone whose twin has no readings yet, instead of empty dashboards. */
export function PhoneWaiting({ twinId, onBack }: { twinId: string; onBack: () => void }) {
  const [device, setDevice] = useState<PhoneDevice | null>(null);
  useEffect(() => {
    const load = () =>
      api
        .devices()
        .then((list) => setDevice(list.find((d) => d.twin_id === twinId) ?? null))
        .catch(() => undefined);
    load();
    const id = window.setInterval(load, 4000);
    return () => window.clearInterval(id);
  }, [twinId]);

  const sync = device?.last_sync;
  return (
    <section className="panel phone-wait" aria-live="polite">
      <h2 className="mydata__title">Waiting for your phone's first readings</h2>
      {!sync && (
        <ol className="phone__steps">
          <li>
            Open the <strong>Health Twin</strong> app on the phone.
          </li>
          <li>
            Tap <strong>Allow Health Connect access</strong> and allow heart rate (the rest is optional).
          </li>
          <li>
            Tap <strong>Sync now</strong>. This page switches to your twin by itself when the data arrives.
          </li>
        </ol>
      )}
      {sync && <p>{STATUS[sync.status] ?? `Last sync: ${sync.status}.`}</p>}
      {sync?.detail && <p className="muted small">Server detail: {sync.detail}</p>}
      {sync && Object.keys(sync.received).length > 0 && (
        <p className="muted small">
          Received in the last sync:{" "}
          {Object.entries(sync.received)
            .map(([k, v]) => `${v} ${k.replace("_", " ")}`)
            .join(", ")}
          .
        </p>
      )}
      <p className="muted small">
        Paired device: {device ? device.name : "…"}. Phone and computer must be on the same network (or use the deployed
        website address).
      </p>
      <button className="btn" onClick={onBack}>
        Back to the demo twin
      </button>
    </section>
  );
}
