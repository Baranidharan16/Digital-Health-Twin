/**
 * Times are shown on the twin's own clock (the subject's time zone), not the
 * browser's: a twin built from a US Fitbit export should show the user's
 * night as night even when viewed from India.
 */
let offsetHours: number | null = null;
export const setDisplayOffset = (hours: number | null) => {
  offsetHours = hours;
};
export const displayOffset = () => offsetHours;

/** Parse the API's "...Z" UTC strings. */
export const toDate = (iso: string) => new Date(iso.endsWith("Z") || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);

const shifted = (d: Date) => (offsetHours === null ? d : new Date(d.getTime() + offsetHours * 3600e3));
const tz = () => (offsetHours === null ? undefined : "UTC");

export const fmtClockDate = (d: Date, seconds = true) =>
  shifted(d).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: seconds ? "2-digit" : undefined, timeZone: tz() });

export const fmtClock = (iso: string, seconds = true) => fmtClockDate(toDate(iso), seconds);

export const fmtDateTime = (iso: string) =>
  shifted(toDate(iso)).toLocaleString([], { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: tz() });

/** Format on an explicit clock (e.g. another twin's time zone). */
export const fmtDateTimeAt = (iso: string, hours: number) =>
  new Date(toDate(iso).getTime() + hours * 3600e3).toLocaleString([], {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });

export const fmtDay = (d: Date) =>
  shifted(d).toLocaleDateString([], { weekday: "short", day: "numeric", month: "short", timeZone: tz() });

/** "YYYY-MM-DD" of a UTC instant on the twin's clock. */
export const localDayKey = (d: Date) => shifted(d).toISOString().slice(0, 10);

/** Convert a twin-local "YYYY-MM-DDTHH:mm" (datetime-local input) to a UTC ISO string. */
export const twinLocalToUtcIso = (local: string) => {
  const asUtc = new Date(`${local}:00Z`).getTime();
  return new Date(asUtc - (offsetHours ?? -new Date().getTimezoneOffset() / 60) * 3600e3).toISOString();
};
/** Inverse of twinLocalToUtcIso, for filling datetime-local inputs. */
export const utcToTwinLocalInput = (d: Date) =>
  new Date(d.getTime() + (offsetHours ?? -new Date().getTimezoneOffset() / 60) * 3600e3).toISOString().slice(0, 16);

export const fmtNum = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined || Number.isNaN(v) ? "–" : v.toFixed(digits);

export const fmtSigned = (v: number, digits = 0) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(digits)}`;

export function fmtDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h} h ${m % 60} min`;
  return `${Math.floor(h / 24)} days`;
}

export const pct = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`;

export function utcLabel(offset?: number | null) {
  if (offset === undefined || offset === null) return "UTC";
  const sign = offset >= 0 ? "+" : "−";
  const h = Math.floor(Math.abs(offset));
  const m = Math.round((Math.abs(offset) - h) * 60);
  return `UTC${sign}${h}${m ? `:${String(m).padStart(2, "0")}` : ""}`;
}
