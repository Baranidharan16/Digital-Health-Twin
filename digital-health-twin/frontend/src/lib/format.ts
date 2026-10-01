/** Parse the API's "...Z" UTC strings. */
export const toDate = (iso: string) => new Date(iso.endsWith("Z") ? iso : `${iso}Z`);

export const fmtClock = (iso: string, seconds = true) =>
  toDate(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: seconds ? "2-digit" : undefined });

export const fmtDateTime = (iso: string) =>
  toDate(iso).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });

export const fmtNum = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined || Number.isNaN(v) ? "–" : v.toFixed(digits);

export const fmtSigned = (v: number, digits = 0) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(digits)}`;

export function fmtDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  return `${h} h ${m % 60} min`;
}

export const pct = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`;
