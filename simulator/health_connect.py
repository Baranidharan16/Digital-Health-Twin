"""Shape simulated readings like the records Android Health Connect returns.

Used by ``scripts/fake_phone.py`` (test the phone connection without a phone)
and by the tests. The JSON matches what the Android app sends to
``POST /api/devices/sync``: heart-rate samples, step-count intervals, SpO2,
respiratory-rate and body-temperature samples, and sleep sessions, all in UTC.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from digital_twin.types import Observation


def _iso(t: datetime) -> str:
    return t.replace(microsecond=0).isoformat() + "Z"


def to_health_connect(
    observations: Sequence[Observation],
    utc_offset_hours: float = 0.0,
    window_end: datetime | None = None,
    include: Sequence[str] = ("heart_rate", "steps", "spo2", "respiratory_rate", "temperature", "sleep"),
    spo2_every: int = 5,
) -> dict[str, Any]:
    """Convert observations (sorted, UTC) into a ``DeviceSyncIn`` JSON body.

    Phones measure SpO2 and temperature far less often than heart rate, so by
    default only every ``spo2_every``-th reading carries those values.
    """
    body: dict[str, Any] = {
        "utc_offset_hours": utc_offset_hours,
        "window_start": _iso(observations[0].timestamp) if observations else None,
        "window_end": _iso(window_end or (observations[-1].timestamp + timedelta(minutes=1))) if observations else None,
        "heart_rate": [],
        "steps": [],
        "spo2": [],
        "respiratory_rate": [],
        "temperature": [],
        "sleep": [],
    }
    prev: datetime | None = None
    sleep_start: datetime | None = None
    for i, o in enumerate(observations):
        t = o.timestamp
        if "heart_rate" in include:
            body["heart_rate"].append({"t": _iso(t), "bpm": o.heart_rate})
        if "steps" in include and o.steps:
            dt = (t - prev) if prev is not None else timedelta(minutes=1)
            body["steps"].append({"start": _iso(t), "end": _iso(t + dt), "count": int(o.steps)})
        sparse = i % max(spo2_every, 1) == 0
        if "spo2" in include and sparse and o.spo2 is not None:
            body["spo2"].append({"t": _iso(t), "pct": o.spo2})
        if "respiratory_rate" in include and o.respiratory_rate is not None:
            body["respiratory_rate"].append({"t": _iso(t), "rate": o.respiratory_rate})
        if "temperature" in include and sparse and o.temperature is not None:
            body["temperature"].append({"t": _iso(t), "celsius": o.temperature})
        if "sleep" in include:
            if o.is_asleep and sleep_start is None:
                sleep_start = t
            elif not o.is_asleep and sleep_start is not None:
                body["sleep"].append({"start": _iso(sleep_start), "end": _iso(t)})
                sleep_start = None
        prev = t
    if "sleep" in include and sleep_start is not None and prev is not None:
        body["sleep"].append({"start": _iso(sleep_start), "end": _iso(prev + timedelta(minutes=1))})
    return body
