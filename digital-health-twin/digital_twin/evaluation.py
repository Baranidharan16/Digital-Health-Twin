"""Validation harness: measure the twin against simulator ground truth.

Because the simulator knows exactly when it injected an anomaly and what the
subject's true physiology is, we can measure the twin engine objectively:

* **Event recall**: share of injected anomaly episodes that the twin flagged
  while the episode was happening (any metric), overall and by severity.
  Episode magnitude is drawn between 0.3 (subtle) and 1.0 (demo strength,
  about +32 % heart rate, +1.3 °C, -3.5 SpO2 points, +6 br/min).
* **False-alarm rate**: anomaly episodes flagged per day *outside* injected
  windows, including exercise days (the hard case for population thresholds).
* **Detection latency**: minutes from injection start to the first flag.
* **Baseline error**: learned resting heart rate vs the simulator's true
  steady-state resting heart rate.
* **Ablation**: the same data scored with a population-only rule
  (heart rate > 100 bpm, SpO2 < 94 %, temperature >= 37.8 °C,
  respiratory rate > 20 br/min) to show what personal, activity-aware
  baselines add.

This validates the *engine against its own simulator*. It does not validate
anything clinically. Run it with:

    python -m digital_twin.evaluation
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

import numpy as np

from digital_twin.baseline import compute_baseline
from digital_twin.engine import TwinEngine
from digital_twin.physiology import target_heart_rate
from digital_twin.types import Observation
from simulator.generator import SubjectProfile, generate_history

DEFAULT_SEEDS = (11, 23, 37, 41, 59)
TRAIN_DAYS = 7
TEST_DAYS = 7
INTERVAL_S = 300.0
EPISODES_PER_SEED = 6
POPULATION_RULE = "HR>100 or SpO2<94 or Temp>=37.8 or RR>20 (no activity context)"


SEVERITY_BANDS = (("subtle", 0.3, 0.5), ("moderate", 0.5, 0.75), ("strong", 0.75, 1.01))


@dataclass
class SeedResult:
    seed: int
    episodes: int
    detected: int
    magnitudes: list[float]
    detected_mask: list[bool]
    population_detected_mask: list[bool]
    latencies_min: list[float]
    false_alarm_episodes: int
    test_days: float
    population_detected: int
    population_false_alarm_episodes: int
    learned_hr_rest: float
    true_hr_rest: float


def _random_windows(
    rng: np.random.Generator, start: datetime, days: int, n: int
) -> list[tuple[datetime, datetime, float]]:
    """Non-overlapping episodes of 40-120 min at random times (awake or asleep)."""
    windows: list[tuple[datetime, datetime, float]] = []
    attempts = 0
    while len(windows) < n and attempts < 500:
        attempts += 1
        offset_h = float(rng.uniform(6, days * 24 - 4))
        length = timedelta(minutes=float(rng.uniform(40, 120)))
        w0 = start + timedelta(hours=offset_h)
        w1 = w0 + length
        if all(w1 + timedelta(hours=2) < a or w0 > b + timedelta(hours=2) for a, b, _ in windows):
            windows.append((w0, w1, round(float(rng.uniform(0.3, 1.0)), 2)))
    return sorted(windows)


def _flag_episodes(times: list[datetime], flags: list[bool]) -> list[tuple[datetime, datetime]]:
    episodes: list[tuple[datetime, datetime]] = []
    start = None
    for t, f in zip(times, flags):
        if f and start is None:
            start = t
        elif not f and start is not None:
            episodes.append((start, t))
            start = None
    if start is not None:
        episodes.append((start, times[-1]))
    return episodes


def _population_flag(o: Observation) -> bool:
    return o.heart_rate > 100 or o.spo2 < 94 or o.temperature >= 37.8 or o.respiratory_rate > 20


def _score(
    times: list[datetime],
    flags: list[bool],
    windows: list[tuple[datetime, datetime, float]],
) -> tuple[list[bool], list[float], int]:
    """(detected mask per episode, latencies, false-alarm flag episodes)."""
    mask, latencies = [], []
    for w0, w1, _ in windows:
        hits = [t for t, f in zip(times, flags) if f and w0 <= t <= w1 + timedelta(minutes=10)]
        mask.append(bool(hits))
        if hits:
            latencies.append((hits[0] - w0).total_seconds() / 60.0)
    grace = timedelta(minutes=30)  # flags clearing shortly after an episode are not false alarms
    false_alarms = sum(
        1
        for e0, e1 in _flag_episodes(times, flags)
        if not any(w0 - timedelta(minutes=5) <= e1 and e0 <= w1 + grace for w0, w1, _ in windows)
    )
    return mask, latencies, false_alarms


def evaluate_seed(seed: int, profile: SubjectProfile | None = None) -> SeedResult:
    profile = profile or SubjectProfile()
    end = datetime(2026, 3, 1, 0, 0)
    test_start = end - timedelta(days=TEST_DAYS)

    # 1. Learn the baseline from a clean training week (no injected anomalies).
    train = generate_history(
        profile, end=test_start, days=TRAIN_DAYS, interval_s=INTERVAL_S, seed=seed, include_planned_anomaly=False
    )
    baseline = compute_baseline(train, profile.age_years, profile.utc_offset_hours)

    # 2. Generate an unseen test week with labelled anomaly episodes.
    rng = np.random.default_rng(seed + 1000)
    windows = _random_windows(rng, test_start, TEST_DAYS, EPISODES_PER_SEED)
    test = generate_history(
        profile,
        end=end,
        days=TEST_DAYS,
        interval_s=INTERVAL_S,
        seed=seed + 500,
        anomaly_windows=windows,
        include_planned_anomaly=False,
    )

    engine = TwinEngine(baseline)
    times, twin_flags, pop_flags = [], [], []
    for obs in test:
        snap = engine.ingest(obs)
        times.append(obs.timestamp)
        twin_flags.append(bool(snap.active_anomalies))
        pop_flags.append(_population_flag(obs))

    mask, latencies, false_alarms = _score(times, twin_flags, windows)
    pop_mask, _, pop_false = _score(times, pop_flags, windows)
    true_rest = target_heart_rate(profile.hr_rest, profile.hr_max, 0.03)
    return SeedResult(
        seed=seed,
        episodes=len(windows),
        detected=sum(mask),
        magnitudes=[w[2] for w in windows],
        detected_mask=mask,
        population_detected_mask=pop_mask,
        latencies_min=[round(x, 1) for x in latencies],
        false_alarm_episodes=false_alarms,
        test_days=float(TEST_DAYS),
        population_detected=sum(pop_mask),
        population_false_alarm_episodes=pop_false,
        learned_hr_rest=baseline.hr_rest,
        true_hr_rest=round(true_rest, 2),
    )


def evaluate(seeds: tuple[int, ...] = DEFAULT_SEEDS) -> dict:
    results = [evaluate_seed(s) for s in seeds]
    episodes = sum(r.episodes for r in results)
    days = sum(r.test_days for r in results)
    latencies = [x for r in results for x in r.latencies_min]
    hr_errors = [abs(r.learned_hr_rest - r.true_hr_rest) for r in results]
    by_severity = {}
    for name, lo, hi in SEVERITY_BANDS:
        twin_hits = [d for r in results for m, d in zip(r.magnitudes, r.detected_mask) if lo <= m < hi]
        pop_hits = [d for r in results for m, d in zip(r.magnitudes, r.population_detected_mask) if lo <= m < hi]
        by_severity[name] = {
            "magnitude_range": [lo, min(hi, 1.0)],
            "episodes": len(twin_hits),
            "twin_recall": round(sum(twin_hits) / len(twin_hits), 3) if twin_hits else None,
            "population_rule_recall": round(sum(pop_hits) / len(pop_hits), 3) if pop_hits else None,
        }
    return {
        "description": "Twin engine vs simulator ground truth (synthetic data; not clinical validation).",
        "seeds": list(seeds),
        "sampling_interval_s": INTERVAL_S,
        "test_days_total": days,
        "injected_episodes": episodes,
        "twin": {
            "event_recall": round(sum(r.detected for r in results) / episodes, 3),
            "false_alarms_per_day": round(sum(r.false_alarm_episodes for r in results) / days, 3),
            "median_detection_latency_min": round(float(np.median(latencies)), 1) if latencies else None,
        },
        "population_threshold_rule": {
            "rule": POPULATION_RULE,
            "event_recall": round(sum(r.population_detected for r in results) / episodes, 3),
            "false_alarms_per_day": round(sum(r.population_false_alarm_episodes for r in results) / days, 3),
        },
        "recall_by_severity": by_severity,
        "baseline_learning": {
            "mean_abs_error_resting_hr_bpm": round(float(np.mean(hr_errors)), 2),
            "max_abs_error_resting_hr_bpm": round(float(np.max(hr_errors)), 2),
        },
        "per_seed": [asdict(r) for r in results],
    }


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(evaluate(), indent=2, default=str))
