import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import { api } from "../api/client";
import type { Pairing, PhoneDevice } from "../api/types";

const STATUS_TEXT: Record<string, string> = {
  synced: "Synced",
  nothing_new: "Up to date",
  waiting_for_more_data: "Waiting for more history",
  no_heart_rate: "No heart rate on phone",
};

function ago(iso: string | null): string {
  if (!iso) return "never";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.round(s)} s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

function useQr(text: string | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!text) {
      setUrl(null);
      return;
    }
    let live = true;
    QRCode.toDataURL(text, {
      margin: 1,
      width: 220,
      color: { dark: "#1d2b36", light: "#ffffff" },
    })
      .then((u) => live && setUrl(u))
      .catch(() => live && setUrl(null));
    return () => {
      live = false;
    };
  }, [text]);
  return url;
}

export function PhoneConnect({
  onOpenTwin,
  onTwinsChanged,
}: {
  onOpenTwin: (id: string) => void;
  onTwinsChanged: () => void;
}) {
  const [name, setName] = useState("My phone");
  const [age, setAge] = useState(25);
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [server, setServer] = useState<string>("");
  const [left, setLeft] = useState(0);
  const [devices, setDevices] = useState<PhoneDevice[]>([]);
  const [apk, setApk] = useState(false);
  const [isPublic, setIsPublic] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justPaired, setJustPaired] = useState<PhoneDevice | null>(null);
  const known = useRef<Set<number> | null>(null);
  const changed = useRef(onTwinsChanged);
  changed.current = onTwinsChanged;

  const deepLink =
    pairing && server
      ? `healthtwin://pair?server=${encodeURIComponent(server)}&code=${pairing.code}`
      : null;
  const qr = useQr(deepLink);
  const apkUrl = server ? `${server}/api/devices/app.apk` : null;
  const apkQr = useQr(apk ? apkUrl : null);

  // Poll the device list: detects the moment the phone claims the code, and shows each sync.
  useEffect(() => {
    let stop = false;
    const load = () =>
      api
        .devices()
        .then((list) => {
          if (stop) return;
          if (known.current) {
            const fresh = list.find((d) => !known.current!.has(d.id));
            if (fresh) {
              setJustPaired(fresh);
              setPairing(null);
              changed.current();
            }
          }
          known.current = new Set(list.map((d) => d.id));
          setDevices(list);
        })
        .catch(() => undefined);
    load();
    fetch("/api/system/network")
      .then((r) => r.json())
      .then((n) => {
        setApk(Boolean(n.apk_available));
        setIsPublic(Boolean(n.public));
      })
      .catch(() => undefined);
    const id = window.setInterval(load, 4000);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (!pairing) return;
    const tick = () => {
      const s = Math.max(
        0,
        Math.round(
          (new Date(pairing.expires_at).getTime() - Date.now()) / 1000,
        ),
      );
      setLeft(s);
      if (s === 0) setPairing(null);
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [pairing]);

  const start = async () => {
    setError(null);
    setJustPaired(null);
    try {
      const p = await api.createPairing(name, age);
      setPairing(p);
      setServer((current) =>
        current && p.server_urls.includes(current)
          ? current
          : (p.server_urls[0] ?? ""),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const revoke = async (d: PhoneDevice) => {
    await api.revokeDevice(d.id).catch((err) => setError(String(err)));
    setDevices((list) => list.filter((x) => x.id !== d.id));
  };

  const onLocalhostOnly = pairing && pairing.server_urls.length === 0;

  return (
    <section className="panel phone" id="connect-phone">
      <div className="phone__head">
        <div>
          <h2 className="mydata__title">Connect your Android phone</h2>
          <p className="muted">
            The <strong>Health Twin</strong> app reads Android{" "}
            <strong>Health Connect</strong>: steps, heart rate, SpO₂, breathing
            rate, temperature and sleep from your phone and any watch that syncs
            to it (Samsung Health, Fitbit, Google Fit, Pixel Watch, Mi
            Fitness…). It sends them to this computer over your Wi-Fi, and the
            twin updates live.
          </p>
        </div>
      </div>

      <div className="phone__grid">
        <div className="phone__pair">
          {!pairing && (
            <div className="phone__form">
              <label>
                Nickname <small>(avoid your real name)</small>
                <input
                  value={name}
                  maxLength={60}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <label>
                Age
                <input
                  type="number"
                  min={10}
                  max={100}
                  value={age}
                  onChange={(e) => setAge(Number(e.target.value))}
                />
              </label>
              <button className="btn btn--primary" onClick={start}>
                Show pairing code
              </button>
            </div>
          )}

          {pairing && (
            <div className="phone__code">
              {qr ? (
                <img
                  src={qr}
                  alt="QR code to pair the Health Twin app"
                  width={200}
                  height={200}
                />
              ) : (
                <div className="phone__qr-empty" />
              )}
              <div>
                <div className="phone__digits" aria-label="Pairing code">
                  {pairing.code.slice(0, 3)} {pairing.code.slice(3)}
                </div>
                <div className="small muted">
                  Expires in {Math.floor(left / 60)}:
                  {String(left % 60).padStart(2, "0")}
                </div>
                <label className="small phone__server">
                  Server address for the app
                  {pairing.server_urls.length > 1 ? (
                    <select
                      value={server}
                      onChange={(e) => setServer(e.target.value)}
                    >
                      {pairing.server_urls.map((u) => (
                        <option key={u}>{u}</option>
                      ))}
                    </select>
                  ) : (
                    <code>{server || "not found"}</code>
                  )}
                </label>
                {onLocalhostOnly && (
                  <p className="error small">
                    No network address found. Connect this computer to Wi-Fi and
                    start the server with run.bat / run.sh (they listen on the
                    network).
                  </p>
                )}
                <p className="small">Waiting for the phone…</p>
                <button className="btn" onClick={() => setPairing(null)}>
                  Cancel
                </button>
              </div>
            </div>
          )}

          {justPaired && (
            <div className="phone__done" role="status">
              <strong>Phone connected: {justPaired.name}.</strong> Its first
              sync sends the last 7 days; the twin learns a baseline from it.
              <button
                className="btn btn--primary"
                onClick={() => onOpenTwin(justPaired.twin_id)}
              >
                Open phone twin
              </button>
            </div>
          )}
          {error && <p className="error">{error}</p>}
        </div>

        <ol className="phone__steps small">
          {isPublic ? (
            <li>
              This website is online, so the phone can connect from{" "}
              <strong>any network</strong> (Wi-Fi or mobile data).
            </li>
          ) : (
            <li>
              Phone and computer on the <strong>same Wi-Fi</strong>. On Windows,
              allow Python through the firewall when asked (Private networks).
            </li>
          )}
          <li>
            Install the <strong>Health Twin</strong> app (Android 8+, with
            Health Connect).{" "}
            {apk && apkUrl ? (
              <>
                Scan to download from this computer:
                {apkQr && (
                  <img
                    className="phone__apkqr"
                    src={apkQr}
                    alt="QR code to download the app"
                    width={110}
                    height={110}
                  />
                )}
              </>
            ) : (
              <>
                Download it on the phone:{" "}
                <a
                  href="https://github.com/Baranidharan16/Digital-Health-Twin/releases/download/app-latest/health-twin.apk"
                  target="_blank"
                  rel="noreferrer"
                >
                  health-twin.apk
                </a>{" "}
                (or build it in Android Studio; see docs/mobile.md).
              </>
            )}
          </li>
          <li>
            In the app tap <strong>Scan QR</strong> (or type the server address
            and the 6-digit code), then <strong>Allow</strong> the Health
            Connect permissions.
          </li>
          <li>
            Tap <strong>Sync now</strong>. While the app is open it syncs every
            minute; this page and the twin update by themselves.
          </li>
        </ol>
      </div>

      {devices.length > 0 && (
        <table className="table phone__devices">
          <thead>
            <tr>
              <th>Phone</th>
              <th>Last sync</th>
              <th>Status</th>
              <th>Measured</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {devices.map((d) => (
              <tr key={d.id}>
                <td>{d.name}</td>
                <td className="mono-num">{ago(d.last_seen_at)}</td>
                <td>
                  {d.last_sync
                    ? (STATUS_TEXT[d.last_sync.status] ?? d.last_sync.status)
                    : "Paired, no data yet"}
                  {d.last_sync?.readings_ingested ? (
                    <span className="muted small">
                      {" "}
                      · +{d.last_sync.readings_ingested.toLocaleString()} min
                    </span>
                  ) : null}
                </td>
                <td className="small">
                  {d.last_sync?.metrics
                    ?.map((m) => m.replace("_", " "))
                    .join(", ") || "–"}
                </td>
                <td className="table__actions">
                  <button className="btn" onClick={() => onOpenTwin(d.twin_id)}>
                    Open
                  </button>
                  <button className="btn btn--danger" onClick={() => revoke(d)}>
                    Disconnect
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
