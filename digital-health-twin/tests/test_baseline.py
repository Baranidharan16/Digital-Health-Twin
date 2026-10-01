"""Personal baseline calculation."""

from dataclasses import replace

import pytest

from digital_twin.baseline import InsufficientHistoryError, SPREAD_FLOOR, compute_baseline
from digital_twin.physiology import target_heart_rate
from tests.conftest import T0, series


def test_baseline_learns_subject_resting_heart_rate(baseline, profile):
    true_rest = target_heart_rate(profile.hr_rest, profile.hr_max, 0.03)
    assert baseline.hr_rest == pytest.approx(true_rest, abs=2.0)
    assert baseline.hr_sleep < baseline.hr_rest  # heart rate dips during sleep
    assert 6.0 < baseline.sleep_hours < 8.5
    assert baseline.daily_steps > 3000


def test_baseline_is_robust_to_outliers(history, profile, baseline):
    # Corrupt 5% of resting readings with a wildly high heart rate.
    corrupted = [
        replace(o, heart_rate=180.0) if (i % 20 == 0 and o.activity_intensity < 0.1 and not o.is_asleep) else o
        for i, o in enumerate(history)
    ]
    robust = compute_baseline(corrupted, profile.age_years)
    assert robust.hr_rest == pytest.approx(baseline.hr_rest, abs=1.5)


def test_spread_has_a_floor():
    flat = series(T0, 40, heart_rate=60.0)  # perfectly constant signal
    b = compute_baseline(flat, 30)
    assert b.hr_rest_spread == SPREAD_FLOOR["heart_rate"]


def test_insufficient_history_raises():
    with pytest.raises(InsufficientHistoryError):
        compute_baseline(series(T0, 5), 30)
    with pytest.raises(InsufficientHistoryError):
        compute_baseline([], 30)
