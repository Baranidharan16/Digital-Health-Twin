"""Ingestion layer: every data source is converted to one normalized format.

    Simulator ─┐
    CSV file  ─┤
    Wearable  ─┼─► source adapter ─► normalize() ─► ObservationIn (validated) ─► TwinService
    REST API  ─┤
    Replay    ─┘

Adapters only translate *shape and units*. They never contain twin logic,
so a real wearable can replace the simulator without touching the engine.

``normalize_raw`` accepts common vendor variations:

* field aliases (``hr``/``bpm``, ``spo2``/``oxygen_saturation``, ``rr``, ...)
* SpO2 given as a fraction (0.97) instead of a percentage
* temperature in °F (``temperature_f``/``temp_f`` or ``temperature_unit: "F"``)
* timestamps as ISO-8601 strings or Unix epoch seconds/milliseconds
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.app.schemas import ObservationIn
from digital_twin.types import Observation

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "time", "ts", "datetime", "recorded_at"),
    "heart_rate": ("heart_rate", "hr", "bpm", "pulse"),
    "spo2": ("spo2", "oxygen_saturation", "sp_o2", "o2sat"),
    "temperature": ("temperature", "temp", "temperature_c", "skin_temp"),
    "respiratory_rate": ("respiratory_rate", "rr", "resp_rate", "breathing_rate"),
    "steps": ("steps", "step_count"),
    "activity_intensity": ("activity_intensity", "intensity", "activity"),
    "is_asleep": ("is_asleep", "asleep", "sleep"),
}


class NormalizationError(ValueError):
    pass


def _first(raw: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in raw and raw[name] not in (None, ""):
            return raw[name]
    return None


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.replace(".", "", 1).isdigit()):
        number = float(value)
        if number > 1e11:  # epoch milliseconds
            number /= 1000.0
        return datetime.fromtimestamp(number, tz=timezone.utc)
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise NormalizationError(f"unrecognized timestamp {value!r}")


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "asleep"}


def normalize_raw(raw: dict[str, Any], source: str) -> ObservationIn:
    """Translate a raw reading from any adapter into a validated ObservationIn."""
    raw = {str(k).strip().lower(): v for k, v in raw.items()}
    data: dict[str, Any] = {"source": source}

    ts = _first(raw, FIELD_ALIASES["timestamp"])
    if ts is None:
        raise NormalizationError("missing timestamp")
    data["timestamp"] = _parse_timestamp(ts)

    for field in ("heart_rate", "respiratory_rate", "steps", "activity_intensity"):
        value = _first(raw, FIELD_ALIASES[field])
        if value is not None:
            data[field] = value

    spo2 = _first(raw, FIELD_ALIASES["spo2"])
    if spo2 is not None:
        spo2 = float(spo2)
        data["spo2"] = spo2 * 100.0 if spo2 <= 1.0 else spo2

    temp_f = _first(raw, ("temperature_f", "temp_f"))
    temp = _first(raw, FIELD_ALIASES["temperature"])
    if temp_f is not None:
        data["temperature"] = (float(temp_f) - 32.0) * 5.0 / 9.0
    elif temp is not None:
        temp = float(temp)
        unit = str(raw.get("temperature_unit", "C")).upper()
        data["temperature"] = (temp - 32.0) * 5.0 / 9.0 if unit == "F" else temp

    data["is_asleep"] = _parse_bool(_first(raw, FIELD_ALIASES["is_asleep"]))
    if "steps" in data:
        data["steps"] = int(float(data["steps"]))

    try:
        return ObservationIn(**data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        raise NormalizationError(problems) from exc


def to_observation(item: ObservationIn) -> Observation:
    return Observation(
        timestamp=item.timestamp,
        heart_rate=item.heart_rate,
        spo2=item.spo2,
        temperature=round(item.temperature, 2),
        respiratory_rate=item.respiratory_rate,
        steps=item.steps,
        activity_intensity=item.activity_intensity,
        is_asleep=item.is_asleep,
        source=item.source,
    )


def to_observation_in(obs: Observation) -> ObservationIn:
    return ObservationIn(
        timestamp=obs.timestamp,
        heart_rate=obs.heart_rate,
        spo2=obs.spo2,
        temperature=obs.temperature,
        respiratory_rate=obs.respiratory_rate,
        steps=obs.steps,
        activity_intensity=obs.activity_intensity,
        is_asleep=obs.is_asleep,
        source=obs.source,
    )


# ---------------------------------------------------------------- CSV adapter
def parse_csv(text: str, source: str = "csv") -> Iterator[tuple[int, ObservationIn | None, str | None]]:
    """Yield (line_number, observation, error) for each CSV data row."""
    reader = csv.DictReader(io.StringIO(text))
    for line_no, row in enumerate(reader, start=2):
        try:
            yield line_no, normalize_raw(row, source), None
        except (NormalizationError, ValueError) as exc:
            yield line_no, None, str(exc)


# ------------------------------------------------------------- replay adapter
@dataclass
class ReplayRecord:
    dt_s: float  # seconds after the previous reading
    reading: dict[str, Any]
    scenario: str


class ReplaySource:
    """Replays a pre-recorded demo session (backup demo if live simulation fails).

    The recording stores the time *step* between readings, so replayed
    readings are re-timed to continue from the twin's current clock. At the
    end of the recording it loops.
    """

    def __init__(self, path: str | Path) -> None:
        self.records: list[ReplayRecord] = []
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    item = json.loads(line)
                    self.records.append(
                        ReplayRecord(item["dt_s"], item["reading"], item.get("scenario", "REPLAY"))
                    )
        if not self.records:
            raise ValueError(f"replay file {path} is empty")
        self.index = 0

    def next(self, anchor: datetime) -> tuple[Observation, str]:
        """Return the next reading, timed ``dt_s`` after ``anchor`` (the last reading)."""
        record = self.records[self.index % len(self.records)]
        self.index += 1
        base = dict(record.reading)
        base["timestamp"] = anchor + timedelta(seconds=max(record.dt_s, 1.0))
        return to_observation(normalize_raw(base, "replay")), record.scenario
