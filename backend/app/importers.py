"""Import real wearable exports and turn them into normalized observations.

Supported inputs (detected from the CSV header, several files at once):

* **Fitbit / Fitabase** export: ``heartrate_seconds_merged.csv`` (Id,Time,Value),
  ``minuteStepsNarrow_merged.csv`` (Id,ActivityMinute,Steps),
  ``minuteSleep_merged.csv`` (Id,date,value,logId; value 1 = asleep).
* **Samsung Health** export: ``com.samsung.health.heart_rate.*.csv``,
  ``com.samsung.shealth.tracker.pedometer_step_count.*.csv``,
  ``com.samsung.health.sleep.*.csv`` (first line is metadata; columns are
  prefixed with the data type, e.g. ``com.samsung.health.heart_rate.heart_rate``).
* **Google Fit (Takeout)** "Daily activity metrics" day files
  (``2024-05-01.csv`` with ``Start time``, ``Average heart rate (bpm)``, ``Step count``).
* **Generic CSV** (this project's template): ``timestamp`` plus any of
  ``heart_rate, spo2, temperature, respiratory_rate, steps, activity_intensity,
  is_asleep`` (common aliases accepted).

Everything is merged on one time grid (1-minute buckets, or 5-minute for
long histories): heart rate and other vitals are averaged, steps are summed,
and sleep minutes mark a bucket as asleep. Buckets without a heart rate are
dropped; missing vitals stay missing (never invented).

Movement intensity: if the source does not provide it, it is **estimated from
step cadence** (steps per minute). This is a documented approximation.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from backend.app.ingestion import FIELD_ALIASES
from digital_twin.types import Observation

MAX_ROWS = 80_000


class ImportFormatError(ValueError):
    """Raised when no usable data could be read from the uploaded files."""


@dataclass
class ParsedFile:
    name: str
    format: str
    samples: pd.DataFrame | None = None  # columns: t (naive local), field, value
    sleep: list[tuple[datetime, datetime]] = field(default_factory=list)
    rows: int = 0


@dataclass
class ImportResult:
    observations: list[Observation]
    files: list[dict]
    interval_s: int
    metrics: list[str]
    start: datetime
    end: datetime
    sleep_minutes: int
    intensity_estimated: bool
    notes: list[str]


# ----------------------------------------------------------------- helpers
def intensity_from_cadence(steps_per_min: float) -> float:
    """Approximate 0–1 movement intensity from step cadence (inverse of the simulator's cadence model)."""
    s = max(float(steps_per_min), 0.0)
    if s < 1:
        return 0.02
    if s < 60:
        return 0.02 + 0.13 * s / 60.0  # shuffling around: up to 0.15
    if s < 110:
        return 0.15 + 0.35 * (s - 60.0) / 50.0  # walking: 0.15 -> 0.50
    return min(0.5 + 0.3 * (s - 110.0) / 40.0, 0.95)  # jogging/running


def _read_text(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ImportFormatError("file is not text/CSV")


def _parse_times(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    numeric = pd.to_numeric(s, errors="coerce")
    if numeric.notna().mean() > 0.9:  # epoch seconds / milliseconds
        unit = "ms" if numeric.median() > 1e11 else "s"
        return pd.to_datetime(numeric, unit=unit, utc=True).dt.tz_localize(None)
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        parsed = pd.to_datetime(s, format=fmt, errors="coerce")
        if parsed.notna().mean() > 0.9:
            return parsed
    parsed = pd.to_datetime(s, errors="coerce", utc=False, format="mixed")
    if getattr(parsed.dt, "tz", None) is not None:
        parsed = parsed.dt.tz_convert(None)
    return parsed


def _long(t: pd.Series, field_name: str, values: pd.Series) -> pd.DataFrame:
    df = pd.DataFrame({"t": t, "field": field_name, "value": pd.to_numeric(values, errors="coerce")})
    return df.dropna(subset=["t", "value"])


def _find(cols: list[str], *candidates: str, suffix: bool = False) -> str | None:
    low = {c.lower().strip(): c for c in cols}
    for cand in candidates:
        if cand in low:
            return low[cand]
    if suffix:
        for c in cols:
            if any(c.lower().endswith("." + cand) for cand in candidates):
                return c
    return None


# ------------------------------------------------------------------ parsers
def _parse_fitbit(name: str, df: pd.DataFrame) -> ParsedFile | None:
    cols = list(df.columns)
    if {"Id", "Time", "Value"} <= set(cols):
        return ParsedFile(name, "Fitbit heart rate (seconds)", _long(_parse_times(df["Time"]), "heart_rate", df["Value"]), rows=len(df))
    if {"Id", "ActivityMinute", "Steps"} <= set(cols):
        return ParsedFile(name, "Fitbit steps (minute)", _long(_parse_times(df["ActivityMinute"]), "steps", df["Steps"]), rows=len(df))
    if {"Id", "date", "value", "logId"} <= set(cols):
        t = _parse_times(df["date"]).dt.floor("min")
        asleep = df["value"] == 1  # 1 = asleep, 2 = restless, 3 = awake
        minutes = t[asleep].dropna()
        sleep = [(m.to_pydatetime(), (m + pd.Timedelta(minutes=1)).to_pydatetime()) for m in minutes]
        return ParsedFile(name, "Fitbit sleep (minute)", sleep=sleep, rows=len(df))
    return None


def _parse_samsung(name: str, text: str) -> ParsedFile | None:
    lines = text.splitlines()
    if len(lines) < 2 or not lines[0].startswith("com.samsung"):
        return None
    df = pd.read_csv(io.StringIO("\n".join(lines[1:])), index_col=False, low_memory=False)
    cols = list(df.columns)
    start = _find(cols, "start_time", suffix=True)
    if start is None:
        return None
    t = _parse_times(df[start])
    offset_col = _find(cols, "time_offset", suffix=True)
    if offset_col is not None:  # Samsung stores UTC + an offset like "UTC+0530"; convert to local clock
        def to_hours(v: str) -> float:
            m = re.match(r"UTC([+-])(\d{2})(\d{2})", str(v))
            return 0.0 if not m else (1 if m.group(1) == "+" else -1) * (int(m.group(2)) + int(m.group(3)) / 60)
        t = t + pd.to_timedelta(df[offset_col].map(to_hours), unit="h")
    hr = _find(cols, "heart_rate", suffix=True)
    if hr is not None and "heart_rate" in name.lower():
        return ParsedFile(name, "Samsung Health heart rate", _long(t, "heart_rate", df[hr]), rows=len(df))
    steps = _find(cols, "count", suffix=True)
    if steps is not None and "step" in name.lower():
        return ParsedFile(name, "Samsung Health steps", _long(t, "steps", df[steps]), rows=len(df))
    spo2 = _find(cols, "spo2", suffix=True)
    if spo2 is not None:
        return ParsedFile(name, "Samsung Health SpO2", _long(t, "spo2", df[spo2]), rows=len(df))
    end = _find(cols, "end_time", suffix=True)
    if end is not None and "sleep" in name.lower():
        e = _parse_times(df[end])
        if offset_col is not None:
            e = e + (t - _parse_times(df[start]))
        sleep = [(a.to_pydatetime(), b.to_pydatetime()) for a, b in zip(t, e) if pd.notna(a) and pd.notna(b) and b > a]
        return ParsedFile(name, "Samsung Health sleep", sleep=sleep, rows=len(df))
    return None


def _parse_google_fit(name: str, df: pd.DataFrame) -> ParsedFile | None:
    cols = list(df.columns)
    if "Start time" not in cols:
        return None
    m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    if not m:
        raise ImportFormatError(f"{name}: Google Fit daily files must keep their date file name (YYYY-MM-DD.csv)")
    day = m.group(1)
    t = pd.to_datetime(day + " " + df["Start time"].astype(str).str.slice(0, 8), errors="coerce")
    parts = []
    hr = _find(cols, "average heart rate (bpm)")
    if hr:
        parts.append(_long(t, "heart_rate", df[hr]))
    st = _find(cols, "step count")
    if st:
        parts.append(_long(t, "steps", df[st]))
    if not parts:
        return None
    return ParsedFile(name, "Google Fit daily activity", pd.concat(parts), rows=len(df))


def _parse_generic(name: str, df: pd.DataFrame) -> ParsedFile | None:
    cols = list(df.columns)
    ts = _find(cols, *FIELD_ALIASES["timestamp"])
    if ts is None:
        return None
    t = _parse_times(df[ts])
    parts = []
    for fld in ("heart_rate", "respiratory_rate", "steps", "activity_intensity"):
        c = _find(cols, *FIELD_ALIASES[fld])
        if c:
            parts.append(_long(t, fld, df[c]))
    c = _find(cols, *FIELD_ALIASES["spo2"])
    if c:
        v = pd.to_numeric(df[c], errors="coerce")
        parts.append(_long(t, "spo2", v.where(v > 1, v * 100)))
    cf = _find(cols, "temperature_f", "temp_f")
    c = _find(cols, *FIELD_ALIASES["temperature"])
    if cf:
        parts.append(_long(t, "temperature", (pd.to_numeric(df[cf], errors="coerce") - 32) * 5 / 9))
    elif c:
        parts.append(_long(t, "temperature", df[c]))
    c = _find(cols, *FIELD_ALIASES["is_asleep"])
    sleep = []
    if c:
        flags = df[c].astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y", "asleep"})
        sleep = [(a.to_pydatetime(), a.to_pydatetime() + timedelta(seconds=1)) for a in t[flags].dropna()]
    if not parts and not sleep:
        return None
    return ParsedFile(name, "Generic CSV", pd.concat(parts) if parts else None, sleep=sleep, rows=len(df))


def parse_file(name: str, raw: bytes) -> ParsedFile:
    text = _read_text(raw)
    samsung = _parse_samsung(name, text)
    if samsung is not None:
        return samsung
    try:
        df = pd.read_csv(io.StringIO(text), low_memory=False)
    except (pd.errors.ParserError, csv.Error) as exc:
        raise ImportFormatError(f"{name}: could not read CSV ({exc})") from exc
    df.columns = [str(c).strip() for c in df.columns]
    for parser in (_parse_fitbit, _parse_google_fit, _parse_generic):
        parsed = parser(name, df)
        if parsed is not None:
            return parsed
    raise ImportFormatError(
        f"{name}: format not recognised. Columns were: {', '.join(df.columns[:8])}. "
        "Use a Fitbit, Samsung Health or Google Fit export, or the generic template."
    )


# ------------------------------------------------------------------ merging
def build_observations(files: list[ParsedFile], utc_offset_hours: float, source: str) -> ImportResult:
    """Merge parsed files onto one grid and convert local clock -> UTC."""
    samples = [f.samples for f in files if f.samples is not None and len(f.samples)]
    if not samples:
        raise ImportFormatError("no heart-rate or activity readings found in the uploaded files")
    long = pd.concat(samples, ignore_index=True)
    if "heart_rate" not in set(long["field"]):
        raise ImportFormatError("heart rate is required: include a heart-rate file (e.g. heartrate_seconds_merged.csv)")

    wide = long.pivot_table(index="t", columns="field", values="value", aggfunc="mean")
    steps = long[long["field"] == "steps"].groupby("t")["value"].sum()
    span = wide.index.max() - wide.index.min()
    interval_s = 60 if span <= pd.Timedelta(days=31) else 300
    rule = f"{interval_s}s"

    grid = wide.drop(columns=[c for c in ("steps",) if c in wide.columns]).resample(rule).mean()
    grid["steps"] = (steps.resample(rule).sum().reindex(grid.index) if len(steps) else 0.0)
    grid["steps"] = grid["steps"].fillna(0.0)
    grid = grid[grid["heart_rate"].notna()]
    grid = grid[(grid["heart_rate"] >= 25) & (grid["heart_rate"] <= 230)]
    if grid.empty:
        raise ImportFormatError("no time windows with a valid heart rate")

    sleep_intervals = [iv for f in files for iv in f.sleep]
    asleep = pd.Series(False, index=grid.index)
    if sleep_intervals:
        minutes = pd.DatetimeIndex(sorted({pd.Timestamp(a).floor(rule) for a, _ in sleep_intervals}))
        long_ivs = [(a, b) for a, b in sleep_intervals if (b - a) > timedelta(minutes=2)]
        asleep = pd.Series(grid.index.isin(minutes), index=grid.index)
        for a, b in long_ivs:
            asleep |= (grid.index >= a) & (grid.index < b)

    estimated = "activity_intensity" not in grid.columns
    per_min = grid["steps"].fillna(0) * 60.0 / interval_s
    intensity = per_min.map(intensity_from_cadence) if estimated else grid["activity_intensity"].clip(0, 1).fillna(0.0)

    if len(grid) > MAX_ROWS:
        grid, intensity, asleep = grid.iloc[-MAX_ROWS:], intensity.iloc[-MAX_ROWS:], asleep.iloc[-MAX_ROWS:]

    offset = timedelta(hours=utc_offset_hours)

    def opt(row, name, lo, hi, digits):
        v = row.get(name)
        if v is None or pd.isna(v) or not (lo <= v <= hi):
            return None
        return round(float(v), digits)

    observations = []
    for (t, row), inten, sl in zip(grid.iterrows(), intensity, asleep):
        observations.append(
            Observation(
                timestamp=(t.to_pydatetime() - offset).replace(microsecond=0),
                heart_rate=round(float(row["heart_rate"]), 1),
                spo2=opt(row, "spo2", 50, 100, 1),
                temperature=opt(row, "temperature", 30, 43, 2),
                respiratory_rate=opt(row, "respiratory_rate", 3, 70, 1),
                steps=int(min(max(row.get("steps", 0) or 0, 0), 2000 * interval_s / 60)),
                activity_intensity=0.0 if sl else round(float(inten), 3),
                is_asleep=bool(sl),
                source=source,
            )
        )
    metrics = ["heart_rate"] + [m for m in ("spo2", "temperature", "respiratory_rate") if m in grid.columns and grid[m].notna().any()]
    notes = []
    if estimated:
        notes.append(
            "Movement intensity was estimated from step cadence (the export has no intensity field). "
            "Workouts without steps (cycling, gym, swimming) look like rest to the twin, so their high heart "
            "rate can be flagged as unusual."
        )
    if not sleep_intervals:
        notes.append("No sleep data in the upload: sleep-related features are unavailable.")
    missing = [m for m in ("spo2", "temperature", "respiratory_rate") if m not in metrics]
    if missing:
        notes.append("Not measured by this device, so not monitored: " + ", ".join(missing) + ".")
    return ImportResult(
        observations=observations,
        files=[{"name": f.name, "format": f.format, "rows": f.rows} for f in files],
        interval_s=interval_s,
        metrics=metrics,
        start=observations[0].timestamp,
        end=observations[-1].timestamp,
        sleep_minutes=int(sum(o.is_asleep for o in observations) * interval_s / 60),
        intensity_estimated=estimated,
        notes=notes,
    )


def import_files(uploads: list[tuple[str, bytes]], utc_offset_hours: float, source: str) -> ImportResult:
    parsed = [parse_file(name, raw) for name, raw in uploads]
    return build_observations(parsed, utc_offset_hours, source)


__all__ = ["ImportFormatError", "ImportResult", "import_files", "intensity_from_cadence", "parse_file"]
_ = np  # numpy is used implicitly by pandas operations above
