"""Simplified physiological response model shared across the project.

The same equations are used in three places, which keeps the system
internally consistent:

* the **data simulator** uses them to generate correlated synthetic data;
* the **twin engine** uses them to compute what a vital *should* be given the
  current activity context (so exercise is not mistaken for an anomaly);
* the **what-if scenario engine** uses them to project trajectories.

Model (intentionally simple and explainable):

* Maximum heart rate is estimated with the Tanaka formula (208 - 0.7 x age),
  a population estimate.
* Target heart rate scales linearly with activity intensity across the
  heart-rate reserve (Karvonen-style): hr_rest + intensity x (hr_max - hr_rest).
* Heart rate approaches its target with first-order dynamics, faster going up
  than coming down (recovery).

These are *scenario-model* assumptions for a prototype, not validated
physiology. They are documented in docs/simulation.md.
"""

from __future__ import annotations

import math

# First-order time constants (seconds).
HR_TAU_UP_S = 30.0
HR_TAU_DOWN_S = 110.0
RR_TAU_S = 25.0
TEMP_TAU_S = 900.0
SPO2_TAU_S = 40.0

# The engine's "effective intensity" filter decays more slowly than real HR
# recovery, so the expected value stays above the actual value while the
# subject is recovering. This prevents normal recovery from being flagged.
EFFECTIVE_INTENSITY_TAU_UP_S = 20.0
EFFECTIVE_INTENSITY_TAU_DOWN_S = 180.0
# Mirror-image filter for the lower edge of the expected band: rises slowly
# (heart rate lags a sudden start of exercise) and falls quickly.
LAGGING_INTENSITY_TAU_UP_S = 60.0
LAGGING_INTENSITY_TAU_DOWN_S = 15.0

RR_GAIN_PER_INTENSITY = 22.0  # breaths/min added at full intensity
TEMP_GAIN_PER_INTENSITY = 0.8  # °C added by sustained full intensity
SPO2_DROP_PER_INTENSITY = 1.0  # small desaturation during hard effort


def hr_max_estimate(age_years: float) -> float:
    """Population estimate of maximum heart rate (Tanaka et al.)."""
    return 208.0 - 0.7 * age_years


def target_heart_rate(hr_rest: float, hr_max: float, intensity: float) -> float:
    intensity = min(max(intensity, 0.0), 1.0)
    return hr_rest + intensity * (hr_max - hr_rest)


def target_respiratory_rate(rr_rest: float, intensity: float) -> float:
    return rr_rest + RR_GAIN_PER_INTENSITY * min(max(intensity, 0.0), 1.0)


def first_order_step(current: float, target: float, dt_s: float, tau_s: float) -> float:
    """Advance a first-order system towards ``target`` by ``dt_s`` seconds."""
    if tau_s <= 0 or dt_s <= 0:
        return target if dt_s > 0 else current
    alpha = 1.0 - math.exp(-dt_s / tau_s)
    return current + alpha * (target - current)


def asymmetric_step(
    current: float, target: float, dt_s: float, tau_up_s: float, tau_down_s: float
) -> float:
    tau = tau_up_s if target > current else tau_down_s
    return first_order_step(current, target, dt_s, tau)


def update_effective_intensity(previous: float, intensity: float, dt_s: float) -> float:
    """Activity context used by the engine to compute expected vitals."""
    return asymmetric_step(
        previous,
        intensity,
        dt_s,
        EFFECTIVE_INTENSITY_TAU_UP_S,
        EFFECTIVE_INTENSITY_TAU_DOWN_S,
    )


def update_lagging_intensity(previous: float, intensity: float, dt_s: float) -> float:
    """Lower-edge activity context: the least exertion the vitals could reflect."""
    return asymmetric_step(
        previous,
        intensity,
        dt_s,
        LAGGING_INTENSITY_TAU_UP_S,
        LAGGING_INTENSITY_TAU_DOWN_S,
    )


def cadence_steps_per_min(intensity: float) -> float:
    """Approximate step cadence for a given movement intensity."""
    if intensity < 0.08:
        return 0.0
    if intensity < 0.5:
        return 60.0 + 100.0 * intensity  # strolling -> brisk walk (~110 spm)
    return 110.0 + 80.0 * (intensity - 0.5)  # jogging -> running (~150 spm)
