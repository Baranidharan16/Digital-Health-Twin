"""Personal baseline calculation.

Why a personal baseline? Population thresholds treat a resting heart rate of
78 bpm as "normal" for everyone. For a subject whose own resting rate is
58 bpm, 78 bpm at rest is a 34% change and is worth noticing. The twin
therefore learns each subject's typical values from their own history and
measures deviations against them.

Robust statistics (median, MAD) are used so a few bad readings or an
anomalous day inside the history window do not distort the baseline.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

import numpy as np

from digital_twin.physiology import hr_max_estimate
from digital_twin.types import Baseline, Observation

MAD_SCALE = 1.4826  # makes MAD comparable to a standard deviation for normal data

# Minimum spreads prevent a very quiet history from making the detector
# hypersensitive (a z-score of 4 on a 0.2 bpm spread is meaningless).
SPREAD_FLOOR = {
    "heart_rate": 3.5,
    "respiratory_rate": 1.2,
    "spo2": 0.6,
    "temperature": 0.12,
}

REST_INTENSITY_MAX = 0.1
MIN_REST_SAMPLES = 12
SLEEP_EPISODE_GAP = timedelta(minutes=30)
MIN_SLEEP_EPISODE = timedelta(hours=3)

# Fallbacks used only when history is too short; clearly population-level.
POPULATION_DEFAULTS = {
    "hr_rest": 68.0,
    "hr_sleep": 60.0,
    "rr_rest": 14.0,
    "rr_sleep": 12.5,
    "spo2": 97.5,
    "temp_awake": 36.7,
    "temp_sleep": 36.4,
    "daily_steps": 7000.0,
    "sleep_hours": 7.5,
}


class InsufficientHistoryError(ValueError):
    """Raised when there is not enough data to learn a personal baseline."""


def robust_center_spread(values: Sequence[float], floor: float) -> tuple[float, float]:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise InsufficientHistoryError("no values")
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median)))
    return median, max(MAD_SCALE * mad, floor)


def _median_or(values: Sequence[float], default: float) -> float:
    return float(np.median(values)) if len(values) else default


def sleep_episodes(observations: Sequence[Observation]) -> list[tuple[Observation, Observation]]:
    """Group consecutive asleep readings into (first, last) sleep episodes."""
    episodes: list[tuple[Observation, Observation]] = []
    start: Observation | None = None
    last: Observation | None = None
    for obs in observations:
        if not obs.is_asleep:
            continue
        if start is None:
            start = last = obs
            continue
        assert last is not None
        if obs.timestamp - last.timestamp > SLEEP_EPISODE_GAP:
            episodes.append((start, last))
            start = obs
        last = obs
    if start is not None and last is not None:
        episodes.append((start, last))
    return episodes


def daily_step_totals(observations: Sequence[Observation], utc_offset_hours: float = 0.0) -> list[float]:
    """Step totals for each *complete* local calendar day in the window."""
    if not observations:
        return []
    offset = timedelta(hours=utc_offset_hours)
    totals: dict = {}
    for obs in observations:
        day = (obs.timestamp + offset).date()
        totals[day] = totals.get(day, 0) + obs.steps
    days = sorted(totals)
    # Drop the first and last day: they are usually partial.
    complete = days[1:-1] if len(days) > 2 else []
    return [float(totals[d]) for d in complete]


def compute_baseline(
    observations: Sequence[Observation], age_years: float, utc_offset_hours: float = 0.0
) -> Baseline:
    """Learn a personal baseline from historical observations.

    ``observations`` must be sorted by timestamp. Callers should exclude
    readings that were flagged anomalous so the baseline reflects typical
    behaviour.
    """
    if not observations:
        raise InsufficientHistoryError("cannot compute a baseline without observations")

    rest = [o for o in observations if not o.is_asleep and o.activity_intensity < REST_INTENSITY_MAX]
    asleep = [o for o in observations if o.is_asleep]
    awake = [o for o in observations if not o.is_asleep]

    if len(rest) < MIN_REST_SAMPLES:
        raise InsufficientHistoryError(
            f"need at least {MIN_REST_SAMPLES} resting readings, got {len(rest)}"
        )

    hr_rest, hr_spread = robust_center_spread([o.heart_rate for o in rest], SPREAD_FLOOR["heart_rate"])
    rr_rest, rr_spread = robust_center_spread(
        [o.respiratory_rate for o in rest], SPREAD_FLOOR["respiratory_rate"]
    )
    spo2, spo2_spread = robust_center_spread([o.spo2 for o in awake or rest], SPREAD_FLOOR["spo2"])
    temp_awake, temp_spread = robust_center_spread(
        [o.temperature for o in rest], SPREAD_FLOOR["temperature"]
    )

    episodes = sleep_episodes(observations)
    night_hours = [
        (last.timestamp - first.timestamp).total_seconds() / 3600.0
        for first, last in episodes
        if last.timestamp - first.timestamp >= MIN_SLEEP_EPISODE
    ]
    step_days = daily_step_totals(observations, utc_offset_hours)

    return Baseline(
        hr_rest=round(hr_rest, 2),
        hr_rest_spread=round(hr_spread, 3),
        hr_sleep=round(_median_or([o.heart_rate for o in asleep], hr_rest - 7.0), 2),
        rr_rest=round(rr_rest, 2),
        rr_rest_spread=round(rr_spread, 3),
        rr_sleep=round(_median_or([o.respiratory_rate for o in asleep], rr_rest - 1.5), 2),
        spo2=round(spo2, 2),
        spo2_spread=round(spo2_spread, 3),
        temp_awake=round(temp_awake, 3),
        temp_spread=round(temp_spread, 3),
        temp_sleep=round(_median_or([o.temperature for o in asleep], temp_awake - 0.3), 3),
        hr_max_est=round(hr_max_estimate(age_years), 1),
        daily_steps=round(_median_or(step_days, POPULATION_DEFAULTS["daily_steps"]), 0),
        sleep_hours=round(_median_or(night_hours, POPULATION_DEFAULTS["sleep_hours"]), 2),
        sample_count=len(observations),
        window_start=observations[0].timestamp,
        window_end=observations[-1].timestamp,
    )
