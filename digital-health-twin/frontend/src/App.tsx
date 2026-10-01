import { useEffect, useState } from "react";
import { api } from "./api/client";
import type { TwinInfo } from "./api/types";
import { LiveControls } from "./components/LiveControls";
import { PipelineStrip } from "./components/PipelineStrip";
import { useLiveTwin } from "./hooks/useLiveTwin";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { HistoryPage } from "./pages/HistoryPage";
import { Overview } from "./pages/Overview";
import { SimulationPage } from "./pages/SimulationPage";
import { SystemPage } from "./pages/SystemPage";
import { TwinPage } from "./pages/TwinPage";

const PAGES = [
  { key: "overview", label: "Overview" },
  { key: "twin", label: "Twin" },
  { key: "history", label: "History" },
  { key: "analytics", label: "Analytics" },
  { key: "simulation", label: "Simulation" },
  { key: "system", label: "System" },
] as const;

const pageFromHash = () => {
  const key = window.location.hash.replace(/^#\/?/, "");
  return PAGES.some((p) => p.key === key) ? key : "overview";
};

function utcLabel(offset?: number) {
  if (offset === undefined) return "UTC";
  const sign = offset >= 0 ? "+" : "−";
  const h = Math.floor(Math.abs(offset));
  const m = Math.round((Math.abs(offset) - h) * 60);
  return `UTC${sign}${h}${m ? `:${String(m).padStart(2, "0")}` : ""}`;
}

export default function App() {
  const twin = useLiveTwin();
  const [page, setPage] = useState(pageFromHash);
  const [info, setInfo] = useState<TwinInfo | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    api.twin().then(setInfo).catch(() => undefined);
    return () => {
      window.removeEventListener("hashchange", onHash);
      window.clearInterval(tick);
    };
  }, []);

  const navigate = (key: string) => {
    window.location.hash = `/${key}`;
    window.scrollTo({ top: 0 });
  };

  const freshness = twin.lastMessageAt ? Math.max(0, (now - twin.lastMessageAt) / 1000) : null;
  const streaming = twin.connection === "live" && twin.live?.running;
  const pill = twin.connection === "offline" ? "Backend unreachable" : streaming ? "Live" : twin.live?.running === false ? "Paused" : "Connecting";
  const version = twin.state?.twin_time ?? "";
  const offset = info?.subject.utc_offset_hours;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <svg viewBox="0 0 32 32" width="34" height="34" aria-hidden>
            <rect width="32" height="32" rx="9" fill="#1D2B36" />
            <circle cx="16" cy="9" r="4" fill="#EEF2F4" />
            <path d="M10 27c0-7 2-12 6-12s6 5 6 12" fill="none" stroke="#EEF2F4" strokeWidth="3" strokeLinecap="round" />
            <circle cx="17.5" cy="18" r="2" fill="#E0636B" />
          </svg>
          <div>
            <h1>Human Health Digital Twin</h1>
            <p>
              {info
                ? `${info.subject.pseudonym}, ${Math.round(info.subject.age_years)} years, synthetic data, ${utcLabel(offset)}`
                : "Loading twin…"}
            </p>
          </div>
        </div>
        <nav className="tabs" aria-label="Sections">
          {PAGES.map((p) => (
            <a key={p.key} href={`#/${p.key}`} className={page === p.key ? "tab tab--on" : "tab"} aria-current={page === p.key ? "page" : undefined}>
              {p.label}
            </a>
          ))}
        </nav>
        <div className={`pill pill--${streaming ? "live" : twin.connection === "offline" ? "off" : "idle"}`} role="status">
          <span className="pill__dot" aria-hidden />
          {pill}
          {streaming && freshness !== null && <small>{freshness < 1.5 ? "updated now" : `${freshness.toFixed(0)} s ago`}</small>}
        </div>
      </header>

      <LiveControls live={twin.live} onStatus={twin.setLive} />

      <main className="main">
        {twin.connection === "offline" && !twin.state && (
          <section className="panel error">
            The twin's backend isn't reachable. Start it with <code>uvicorn backend.app.main:app --port 8000</code> or{" "}
            <code>docker compose up</code>, then this page reconnects by itself.
          </section>
        )}
        {page === "overview" && (
          <>
            <PipelineStrip state={twin.state} live={twin.live} connection={twin.connection} freshness={freshness} onNavigate={navigate} />
            <Overview twin={twin} />
          </>
        )}
        {page === "twin" && <TwinPage twin={twin} />}
        {page === "history" && <HistoryPage version={version} />}
        {page === "analytics" && <AnalyticsPage version={version.slice(0, 15)} />}
        {page === "simulation" && <SimulationPage />}
        {page === "system" && <SystemPage onStatus={twin.setLive} />}
      </main>

      <footer className="footer">
        Research and demonstration prototype with synthetic data. Not a medical device; no diagnosis or treatment advice.
      </footer>
    </div>
  );
}
