"""Daily wellness summaries derived from the twin's history.

All scores here are transparent heuristics for a prototype. They are
documented in docs/digital-twin-model.md and labelled as heuristics in the UI.
They are not clinical scores.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from digital_twin.baseline import sleep_episodes
from digital_twin.types import Baseline, Observation

ACTIVE_INTENSITY = 0.2
MIN_EPISODE = timedelta(hours=1)


@dataclass
class SleepSummary:
    start: datetime
    end: datetime
    duration_hours: float
    baseline_hours: float
    restless_fraction: float
    mean_sleep_hr: float
    hr_dip_pct: float  # how far sleeping HR sits below resting baseline
    quality_score: int  # heuristic 0-100

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["start"], d["end"] = self.start.isoformat(), self.end.isoformat()
        return d


@dataclass
class ActivitySummary:
    day: str
    steps: int
    baseline_daily_steps: float
    active_minutes: float
    current_intensity: float
    activity_level: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def activity_level_label(intensity: float) -> str:
    if intensity < 0.08:
        return "Still"
    if intensity < 0.2:
        return "Light"
    if intensity < 0.55:
        return "Moderate"
    return "Vigorous"


def sleep_quality_score(duration_h: float, baseline_h: float, restless: float, hr_dip_pct: float) -> int:
    """Heuristic: 60 pts duration vs personal norm, 25 pts calmness, 15 pts HR dip."""
    duration_part = 60.0 * min(duration_h / max(baseline_h, 1.0), 1.0)
    calm_part = 25.0 * (1.0 - min(max(restless, 0.0), 1.0))
    dip_part = 15.0 * min(max(hr_dip_pct / 10.0, 0.0), 1.0)
    return int(round(duration_part + calm_part + dip_part))


def last_sleep(observations: Sequence[Observation], baseline: Baseline) -> SleepSummary | None:
    """Summary of the most recent *completed* sleep episode.

    If the subject is asleep right now, the ongoing episode is skipped so a
    half-finished night is not reported (or penalised) as a short night.
    """
    episodes = sleep_episodes(observations)
    if episodes and observations and observations[-1].is_asleep:
        episodes = episodes[:-1]
    episodes = [e for e in episodes if e[1].timestamp - e[0].timestamp >= MIN_EPISODE]
    if not episodes:
        return None
    first, last = episodes[-1]
    during = [o for o in observations if first.timestamp <= o.timestamp <= last.timestamp]
    asleep = [o for o in during if o.is_asleep]
    duration_h = (last.timestamp - first.timestamp).total_seconds() / 3600.0
    restless = 1.0 - len(asleep) / max(len(during), 1)
    mean_hr = float(np.mean([o.heart_rate for o in asleep])) if asleep else baseline.hr_sleep
    dip = 100.0 * (baseline.hr_rest - mean_hr) / baseline.hr_rest
    return SleepSummary(
        start=first.timestamp,
        end=last.timestamp,
        duration_hours=round(duration_h, 2),
        baseline_hours=baseline.sleep_hours,
        restless_fraction=round(restless, 3),
        mean_sleep_hr=round(mean_hr, 1),
        hr_dip_pct=round(dip, 1),
        quality_score=sleep_quality_score(duration_h, baseline.sleep_hours, restless, dip),
    )


def activity_today(
    observations: Sequence[Observation], baseline: Baseline, utc_offset_hours: float = 0.0
) -> ActivitySummary | None:
    """Steps and active minutes since local midnight (subject's time zone)."""
    if not observations:
        return None
    offset = timedelta(hours=utc_offset_hours)
    latest = observations[-1]
    day = (latest.timestamp + offset).date()
    today = [o for o in observations if (o.timestamp + offset).date() == day]
    active_s = 0.0
    for prev, cur in zip(today, today[1:]):
        if cur.activity_intensity >= ACTIVE_INTENSITY:
            active_s += min((cur.timestamp - prev.timestamp).total_seconds(), 600.0)
    return ActivitySummary(
        day=day.isoformat(),
        steps=int(sum(o.steps for o in today)),
        baseline_daily_steps=baseline.daily_steps,
        active_minutes=round(active_s / 60.0, 1),
        current_intensity=latest.activity_intensity,
        activity_level=activity_level_label(latest.activity_intensity),
    )


def recent_resting_hr(observations: Sequence[Observation], window: timedelta = timedelta(hours=12)) -> float | None:
    if not observations:
        return None
    cutoff = observations[-1].timestamp - window
    rest = [o.heart_rate for o in observations if o.timestamp >= cutoff and not o.is_asleep and o.activity_intensity < 0.1]
    return round(float(np.median(rest)), 1) if len(rest) >= 3 else None


def recovery_index(
    sleep: SleepSummary | None,
    resting_hr: float | None,
    baseline: Baseline,
    active_anomaly: bool,
) -> dict[str, Any]:
    """Heuristic 0-100 readiness indicator with an itemised explanation."""
    score = 100.0
    factors: list[str] = []
    if sleep is not None:
        deficit = max(baseline.sleep_hours - sleep.duration_hours, 0.0)
        penalty = min(10.0 * deficit, 40.0)
        if penalty:
            factors.append(f"-{penalty:.0f}: slept {deficit:.1f} h less than usual")
        score -= penalty
    if resting_hr is not None:
        pct_above = 100.0 * (resting_hr - baseline.hr_rest) / baseline.hr_rest
        penalty = min(max(2.0 * pct_above, 0.0), 30.0)
        if penalty >= 1:
            factors.append(f"-{penalty:.0f}: resting heart rate {pct_above:.0f}% above baseline")
        score -= penalty
    if active_anomaly:
        factors.append("-20: an anomaly flag is currently active")
        score -= 20.0
    if not factors:
        factors.append("No penalties: sleep and resting heart rate are in line with baseline")
    return {"score": int(round(max(score, 0.0))), "factors": factors, "heuristic": True}
