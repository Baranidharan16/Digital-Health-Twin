"""Correlated physiological signal simulator.

The simulator produces *correlated* signals rather than independent random
numbers. A single activity input drives every channel through the shared
physiology model (digital_twin.physiology):

* exercise raises heart rate, breathing rate and (slowly) temperature,
  slightly lowers SpO2 and produces steps;
* stopping exercise gives an exponential recovery back to baseline;
* sleep lowers heart rate, breathing rate and temperature;
* an "anomaly" input raises resting heart rate, temperature and breathing
  rate and lowers SpO2, a pattern that is *not* explained by activity.

Measurement noise is an AR(1) process so consecutive readings are
correlated like real sensor data. All randomness comes from one seeded
``numpy.random.Generator``, so every run with the same seed is identical.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from digital_twin.physiology import (
    HR_TAU_DOWN_S,
    HR_TAU_UP_S,
    RR_TAU_S,
    SPO2_DROP_PER_INTENSITY,
    SPO2_TAU_S,
    TEMP_GAIN_PER_INTENSITY,
    TEMP_TAU_S,
    asymmetric_step,
    cadence_steps_per_min,
    first_order_step,
    hr_max_estimate,
    target_heart_rate,
    target_respiratory_rate,
)
from digital_twin.types import Observation

ANOMALY_TAU_S = 45.0


@dataclass(frozen=True)
class SubjectProfile:
    """Synthetic subject. No real personal data: an age band and physiology only."""

    age_years: float = 29.0
    hr_rest: float = 62.0
    hr_sleep_drop: float = 8.0
    rr_rest: float = 13.5
    spo2: float = 97.8
    temp: float = 36.65
    temp_circadian_amp: float = 0.25
    # Local time zone of the synthetic subject (daily routine, circadian rhythm).
    utc_offset_hours: float = 5.5

    @property
    def hr_max(self) -> float:
        return hr_max_estimate(self.age_years)


@dataclass(frozen=True)
class ActivityInput:
    """What the simulated person is doing during one time step."""

    intensity: float = 0.0
    asleep: bool = False
    anomaly: bool = False
    anomaly_magnitude: float = 1.0  # 1.0 = full demo-strength deviation
    # Optional modifiers used by scenario simulation (e.g. after poor sleep).
    hr_rest_offset: float = 0.0
    recovery_tau_scale: float = 1.0


class _AR1:
    """First-order autoregressive noise: x_t = phi * x_{t-1} + e_t."""

    def __init__(self, rng: np.random.Generator, sigma: float, corr_time_s: float) -> None:
        self.rng, self.sigma, self.corr_time_s, self.value = rng, sigma, corr_time_s, 0.0

    def step(self, dt_s: float) -> float:
        phi = math.exp(-dt_s / self.corr_time_s) if dt_s > 0 else 1.0
        innovation_sd = self.sigma * math.sqrt(max(1.0 - phi * phi, 0.0))
        self.value = phi * self.value + float(self.rng.normal(0.0, innovation_sd))
        return self.value


class PhysiologySimulator:
    """Integrates the physiology model forward in time for one subject."""

    def __init__(
        self,
        profile: SubjectProfile,
        seed: int = 42,
        start: datetime | None = None,
        noise_scale: float = 1.0,
    ) -> None:
        self.profile = profile
        self.noise_scale = noise_scale
        self.rng = np.random.default_rng(seed)
        self.time = start or datetime(2026, 1, 1)
        self.hr = profile.hr_rest
        self.rr = profile.rr_rest
        self.spo2 = profile.spo2
        self.temp_offset = 0.0
        self.anomaly_level = 0.0
        self._step_remainder = 0.0
        self._pending_steps = 0
        self._noise = {
            "hr": _AR1(self.rng, 1.8 * noise_scale, 40.0),
            "rr": _AR1(self.rng, 0.6 * noise_scale, 30.0),
            "spo2": _AR1(self.rng, 0.35 * noise_scale, 60.0),
            "temp": _AR1(self.rng, 0.05 * noise_scale, 300.0),
        }

    # -------------------------------------------------------------- dynamics
    def _circadian_temp(self) -> float:
        local = self.time + timedelta(hours=self.profile.utc_offset_hours)
        hours = local.hour + local.minute / 60.0
        # Minimum around 04:00, maximum around 16:00.
        return self.profile.temp_circadian_amp * math.sin(2 * math.pi * (hours - 10.0) / 24.0)

    def advance(self, dt_s: float, activity: ActivityInput) -> None:
        """Advance internal physiology by ``dt_s`` seconds without emitting."""
        p = self.profile
        intensity = 0.0 if activity.asleep else min(max(activity.intensity, 0.0), 1.0)

        self.anomaly_level = first_order_step(
            self.anomaly_level,
            activity.anomaly_magnitude if activity.anomaly else 0.0,
            dt_s,
            ANOMALY_TAU_S,
        )
        a = self.anomaly_level

        hr_rest = p.hr_rest + activity.hr_rest_offset
        if activity.asleep:
            hr_target = hr_rest - p.hr_sleep_drop
            rr_target = p.rr_rest - 1.5
        else:
            hr_target = target_heart_rate(hr_rest, p.hr_max, intensity)
            rr_target = target_respiratory_rate(p.rr_rest, intensity)
        hr_target = hr_target * (1.0 + 0.32 * a)
        rr_target += 6.0 * a

        self.hr = asymmetric_step(
            self.hr, hr_target, dt_s, HR_TAU_UP_S, HR_TAU_DOWN_S * activity.recovery_tau_scale
        )
        self.rr = first_order_step(self.rr, rr_target, dt_s, RR_TAU_S)
        spo2_target = p.spo2 - SPO2_DROP_PER_INTENSITY * intensity - 3.5 * a
        self.spo2 = first_order_step(self.spo2, spo2_target, dt_s, SPO2_TAU_S)
        temp_target = TEMP_GAIN_PER_INTENSITY * intensity + (-0.25 if activity.asleep else 0.0) + 1.3 * a
        self.temp_offset = first_order_step(self.temp_offset, temp_target, dt_s, TEMP_TAU_S / (1 + 4 * a))

        # Steps (carry fractional steps so short intervals still add up).
        steps_float = cadence_steps_per_min(intensity) * dt_s / 60.0 + self._step_remainder
        self._pending_steps += int(steps_float)
        self._step_remainder = steps_float - int(steps_float)

        for noise in self._noise.values():
            noise.step(dt_s)
        self.time += timedelta(seconds=dt_s)

    def emit(self, activity: ActivityInput, source: str = "simulator") -> Observation:
        """Produce a sensor reading of the current physiology."""
        p = self.profile
        n = self._noise
        intensity = 0.0 if activity.asleep else activity.intensity
        jitter = float(self.rng.normal(0.0, 0.02 * self.noise_scale)) if self.noise_scale else 0.0
        measured_intensity = min(max(intensity + jitter, 0.0), 1.0)
        steps = self._pending_steps
        self._pending_steps = 0
        return Observation(
            timestamp=self.time,
            heart_rate=round(max(self.hr + n["hr"].value, 30.0), 1),
            spo2=round(min(max(self.spo2 + n["spo2"].value, 80.0), 100.0), 1),
            temperature=round(p.temp + self._circadian_temp() + self.temp_offset + n["temp"].value, 2),
            respiratory_rate=round(max(self.rr + n["rr"].value, 6.0), 1),
            steps=int(steps),
            activity_intensity=round(measured_intensity, 3),
            is_asleep=activity.asleep,
            source=source,
        )

    def step(self, dt_s: float, activity: ActivityInput, source: str = "simulator") -> Observation:
        """Advance ``dt_s`` seconds (in sub-steps of at most 15 s) and emit a reading."""
        remaining = dt_s
        while remaining > 1e-9:
            chunk = min(15.0, remaining)
            self.advance(chunk, activity)
            remaining -= chunk
        return self.emit(activity, source)


# ------------------------------------------------------------------ history
def _daily_plan(
    day_index: int, rng: np.random.Generator, include_planned_anomaly: bool = True
) -> list[tuple[float, float, ActivityInput]]:
    """Activity blocks for one day as (start_hour, end_hour, activity)."""
    wake = 6.75 + float(rng.uniform(-0.3, 0.3))
    bed = 23.25 + float(rng.uniform(-0.3, 0.4))
    blocks: list[tuple[float, float, ActivityInput]] = [
        (0.0, wake, ActivityInput(asleep=True)),
        (wake + 0.6, wake + 0.95, ActivityInput(intensity=0.35)),  # morning walk
        (8.6, 8.85, ActivityInput(intensity=0.4)),  # commute walk
        (13.0, 13.2, ActivityInput(intensity=0.3)),  # lunch walk
        (17.8, 18.05, ActivityInput(intensity=0.4)),  # commute home
    ]
    if day_index % 2 == 0:  # workout days: warm-up, run, cool-down walk
        blocks += [
            (18.6, 18.75, ActivityInput(intensity=0.4)),
            (18.75, 19.3, ActivityInput(intensity=0.78)),
            (19.3, 19.4, ActivityInput(intensity=0.25)),
        ]
    else:
        blocks.append((19.0, 19.5, ActivityInput(intensity=0.33)))
    if include_planned_anomaly and day_index == 4:  # one unexplained evening episode, to populate history
        blocks.append((20.5, 23.0, ActivityInput(intensity=0.03, anomaly=True)))
    blocks.append((bed, 24.0, ActivityInput(asleep=True)))
    return blocks


def _activity_at(hour: float, blocks: list[tuple[float, float, ActivityInput]], rng: np.random.Generator) -> ActivityInput:
    for start, end, activity in blocks:
        if start <= hour < end:
            return activity
    # Unscheduled awake time: mostly seated with small movements.
    return ActivityInput(intensity=0.12 if rng.random() < 0.04 else 0.03)


def generate_history(
    profile: SubjectProfile,
    end: datetime,
    days: int = 7,
    interval_s: float = 300.0,
    seed: int = 7,
    anomaly_windows: list[tuple[datetime, datetime] | tuple[datetime, datetime, float]] | None = None,
    include_planned_anomaly: bool = True,
) -> list[Observation]:
    """Generate ``days`` of daily-routine history ending at ``end`` (naive UTC).

    The daily routine follows the subject's *local* clock
    (``profile.utc_offset_hours``). Physiology is integrated at 60-second
    resolution and sampled every ``interval_s`` seconds; steps are accumulated
    over each interval.

    ``anomaly_windows`` (UTC ``(start, end)`` or ``(start, end, magnitude)``)
    inject labelled anomalous periods; this is how the evaluation harness
    creates ground truth for detector validation.
    """
    rng = np.random.default_rng(seed)
    offset = timedelta(hours=profile.utc_offset_hours)
    start = (end - timedelta(days=days)).replace(second=0, microsecond=0)
    sim = PhysiologySimulator(profile, seed=seed + 1, start=start)
    plans: dict = {}
    windows = [(w[0], w[1], w[2] if len(w) > 2 else 1.0) for w in (anomaly_windows or [])]
    observations: list[Observation] = []
    sub_dt = 60.0
    subs_per_sample = max(int(round(interval_s / sub_dt)), 1)
    current = ActivityInput()
    t = start
    first_local_day = (start + offset).date()
    while t < end:
        for _ in range(subs_per_sample):
            local = sim.time + offset
            day = (local.date() - first_local_day).days
            if day not in plans:
                plans[day] = _daily_plan(day, rng, include_planned_anomaly)
            hour = local.hour + local.minute / 60.0
            current = _activity_at(hour, plans[day], rng)
            if current.asleep and rng.random() < 0.01:
                current = ActivityInput(intensity=0.1)  # brief night-time awakening
            active = next((w for w in windows if w[0] <= sim.time < w[1]), None)
            if active is not None:
                current = ActivityInput(
                    intensity=0.0 if current.asleep else 0.03,
                    asleep=current.asleep,
                    anomaly=True,
                    anomaly_magnitude=active[2],
                )
            sim.advance(sub_dt, current)
        t = sim.time
        if t <= end:
            observations.append(sim.emit(current, source="simulator-history"))
    return observations
