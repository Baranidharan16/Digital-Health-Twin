"""What-if scenario simulation, calibrated to the twin's personal baseline.

This is a *scenario model*, not a medical prediction. It answers questions
such as "what would this subject's heart rate look like during a 30-minute run
at this intensity, and how long would it take to settle afterwards?" by running
the project's documented physiology model with the subject's own baseline
(resting heart rate, breathing rate, SpO2, temperature, estimated max HR).

The simulated trajectory is then fed through a fresh :class:`TwinEngine`, so
the same deterministic state and anomaly rules used for live data also describe
the simulated future. Every run is noise-free and fully reproducible.

Assumptions that are *illustrative* (not validated) are listed in
``SLEEP_ASSUMPTIONS`` and returned with every result.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from digital_twin.engine import TwinEngine
from digital_twin.types import Baseline, Observation
from simulator.generator import ActivityInput, PhysiologySimulator, SubjectProfile

STEP_S = 30.0
SETTLE_MARGIN = 0.10  # "settled" = within 10% of resting baseline

# Illustrative coefficients for the sleep scenario. Sleep restriction is
# commonly associated with a modestly higher resting heart rate and slower
# recovery; the magnitudes below are assumptions chosen for demonstration.
HR_REST_BPM_PER_DEFICIT_HOUR = 1.2
CARRYOVER_PER_EXTRA_NIGHT = 0.5
MAX_HR_REST_OFFSET = 8.0
RECOVERY_SLOWDOWN_PER_DEFICIT_HOUR_NIGHT = 0.06
MAX_RECOVERY_SLOWDOWN = 1.5

GENERAL_ASSUMPTIONS = [
    "Scenario model, not a medical prediction: shows how this model responds, not what will happen.",
    "Maximum heart rate uses the population Tanaka estimate (208 − 0.7 × age).",
    "Target heart rate scales linearly with intensity across the heart-rate reserve.",
    "Heart rate follows first-order dynamics: ~30 s time constant rising, ~110 s recovering.",
    "Calibrated with this subject's personal baseline; simulated values are noise-free.",
]
SLEEP_ASSUMPTIONS = [
    f"Illustrative: each hour of sleep below the personal norm raises resting heart rate by "
    f"{HR_REST_BPM_PER_DEFICIT_HOUR} bpm, capped at {MAX_HR_REST_OFFSET:.0f} bpm.",
    f"Illustrative: each additional short night adds {int(CARRYOVER_PER_EXTRA_NIGHT * 100)}% carry-over.",
    f"Illustrative: recovery slows by {int(RECOVERY_SLOWDOWN_PER_DEFICIT_HOUR_NIGHT * 100)}% per "
    f"deficit-hour-night, capped at {MAX_RECOVERY_SLOWDOWN:.1f}×.",
]


@dataclass(frozen=True)
class SleepEffect:
    hr_rest_offset: float
    recovery_tau_scale: float
    deficit_hours: float


def sleep_effect(baseline: Baseline, sleep_hours: float, nights: int = 1) -> SleepEffect:
    deficit = max(baseline.sleep_hours - sleep_hours, 0.0)
    carry = 1.0 + CARRYOVER_PER_EXTRA_NIGHT * max(nights - 1, 0)
    offset = min(HR_REST_BPM_PER_DEFICIT_HOUR * deficit * carry, MAX_HR_REST_OFFSET)
    slowdown = min(1.0 + RECOVERY_SLOWDOWN_PER_DEFICIT_HOUR_NIGHT * deficit * nights, MAX_RECOVERY_SLOWDOWN)
    return SleepEffect(round(offset, 2), round(slowdown, 3), round(deficit, 2))


def _profile(baseline: Baseline, age_years: float) -> SubjectProfile:
    return SubjectProfile(
        age_years=age_years,
        hr_rest=baseline.hr_rest,
        hr_sleep_drop=max(baseline.hr_rest - baseline.hr_sleep, 0.0),
        rr_rest=baseline.rr_rest,
        spo2=baseline.spo2,
        temp=baseline.temp_awake,
        temp_circadian_amp=0.0,
    )


def _simulate(
    baseline: Baseline,
    age_years: float,
    schedule: list[tuple[float, ActivityInput]],
    start: datetime,
) -> list[Observation]:
    """Run a noise-free simulation of (duration_s, activity) blocks."""
    sim = PhysiologySimulator(_profile(baseline, age_years), seed=0, start=start, noise_scale=0.0)
    first_offset = schedule[0][1].hr_rest_offset if schedule else 0.0
    sim.hr = baseline.hr_rest + first_offset
    out = [sim.emit(schedule[0][1], source="scenario-model")] if schedule else []
    for duration_s, activity in schedule:
        elapsed = 0.0
        while elapsed < duration_s - 1e-9:
            out.append(sim.step(STEP_S, activity, source="scenario-model"))
            elapsed += STEP_S
    return out


def _run_engine(baseline: Baseline, observations: list[Observation]) -> tuple[list[str], list[dict[str, Any]]]:
    engine = TwinEngine(baseline)
    states: list[str] = []
    transitions: list[dict[str, Any]] = []
    t0 = observations[0].timestamp
    for obs in observations:
        snap = engine.ingest(obs)
        states.append(snap.state.value)
        if snap.transitioned:
            transitions.append(
                {
                    "t_min": round((obs.timestamp - t0).total_seconds() / 60.0, 1),
                    "state": snap.state.value,
                    "reason": snap.state_reason,
                }
            )
    return states, transitions


def _series(observations: list[Observation]) -> list[dict[str, float]]:
    t0 = observations[0].timestamp
    return [
        {
            "t_min": round((o.timestamp - t0).total_seconds() / 60.0, 2),
            "heart_rate": o.heart_rate,
            "respiratory_rate": o.respiratory_rate,
            "temperature": o.temperature,
            "spo2": o.spo2,
            "intensity": o.activity_intensity,
        }
        for o in observations
    ]


def _settle_minutes(observations: list[Observation], stop_index: int, hr_rest: float) -> float | None:
    """Minutes after exercise stops until heart rate is within 10% of resting baseline."""
    stop_time = observations[stop_index].timestamp
    for obs in observations[stop_index:]:
        if obs.heart_rate <= hr_rest * (1 + SETTLE_MARGIN):
            return round((obs.timestamp - stop_time).total_seconds() / 60.0, 1)
    return None


def _one_minute_recovery(observations: list[Observation], stop_index: int) -> float | None:
    stop = observations[stop_index]
    for obs in observations[stop_index:]:
        if (obs.timestamp - stop.timestamp).total_seconds() >= 60.0:
            return round(stop.heart_rate - obs.heart_rate, 1)
    return None


def _exercise_metrics(
    observations: list[Observation], warmup_steps: int, stop_index: int, baseline: Baseline, states: list[str]
) -> dict[str, Any]:
    active = observations[warmup_steps: stop_index + 1] or observations[: stop_index + 1]
    peak = max(o.heart_rate for o in active)
    reserve = baseline.hr_max_est - baseline.hr_rest
    counts = Counter(states)
    minutes_per_sample = STEP_S / 60.0
    return {
        "peak_heart_rate": round(peak, 1),
        "mean_exercise_heart_rate": round(sum(o.heart_rate for o in active) / len(active), 1),
        "peak_pct_heart_rate_reserve": round(100.0 * (peak - baseline.hr_rest) / reserve, 1),
        "heart_rate_recovery_1min": _one_minute_recovery(observations, stop_index),
        "minutes_to_settle": _settle_minutes(observations, stop_index, baseline.hr_rest),
        "temperature_rise": round(max(o.temperature for o in observations) - observations[0].temperature, 2),
        "estimated_steps": int(sum(o.steps for o in observations)),
        "minutes_in_state": {k: round(v * minutes_per_sample, 1) for k, v in counts.items()},
    }


def simulate_exercise(
    baseline: Baseline,
    age_years: float,
    intensity: float,
    duration_min: float,
    prior_sleep_hours: float | None = None,
    recovery_min: float = 20.0,
    start: datetime | None = None,
) -> dict[str, Any]:
    """Exercise session: 5 min rest, the session, then a recovery period."""
    start = start or datetime(2026, 1, 1, 9, 0)
    sleep = prior_sleep_hours if prior_sleep_hours is not None else baseline.sleep_hours
    effect = sleep_effect(baseline, sleep)

    def schedule(offset: float, tau_scale: float) -> list[tuple[float, ActivityInput]]:
        return [
            (300.0, ActivityInput(intensity=0.03, hr_rest_offset=offset, recovery_tau_scale=tau_scale)),
            (duration_min * 60.0, ActivityInput(intensity=intensity, hr_rest_offset=offset, recovery_tau_scale=tau_scale)),
            (recovery_min * 60.0, ActivityInput(intensity=0.02, hr_rest_offset=offset, recovery_tau_scale=tau_scale)),
        ]

    warmup_steps = int(300.0 / STEP_S)
    stop_index = warmup_steps + int(duration_min * 60.0 / STEP_S)

    scenario = _simulate(baseline, age_years, schedule(effect.hr_rest_offset, effect.recovery_tau_scale), start)
    reference = _simulate(baseline, age_years, schedule(0.0, 1.0), start)
    scenario_states, scenario_transitions = _run_engine(baseline, scenario)
    reference_states, _ = _run_engine(baseline, reference)

    assumptions = list(GENERAL_ASSUMPTIONS)
    if effect.deficit_hours > 0:
        assumptions += SLEEP_ASSUMPTIONS
    return {
        "scenario": "exercise",
        "label": "Scenario simulation (model output, not a prediction)",
        "inputs": {
            "intensity": intensity,
            "duration_min": duration_min,
            "prior_sleep_hours": sleep,
            "recovery_min": recovery_min,
        },
        "phases": [
            {"name": "Rest", "start_min": 0.0, "end_min": 5.0},
            {"name": "Exercise", "start_min": 5.0, "end_min": 5.0 + duration_min},
            {"name": "Recovery", "start_min": 5.0 + duration_min, "end_min": 5.0 + duration_min + recovery_min},
        ],
        "baseline": {"heart_rate": baseline.hr_rest, "hr_max_est": baseline.hr_max_est},
        "sleep_effect": effect.__dict__,
        "series": _series(scenario),
        "reference_series": _series(reference),
        "metrics": _exercise_metrics(scenario, warmup_steps, stop_index, baseline, scenario_states),
        "reference_metrics": _exercise_metrics(reference, warmup_steps, stop_index, baseline, reference_states),
        "state_transitions": scenario_transitions,
        "assumptions": assumptions,
    }


def simulate_sleep_restriction(
    baseline: Baseline,
    age_years: float,
    sleep_hours: float,
    nights: int,
    test_intensity: float = 0.4,
    test_duration_min: float = 10.0,
) -> dict[str, Any]:
    """Several short nights, then a standard brisk walk to compare recovery."""
    per_night = []
    for n in range(1, nights + 1):
        eff = sleep_effect(baseline, sleep_hours, n)
        per_night.append(
            {
                "night": n,
                "sleep_hours": sleep_hours,
                "resting_hr": round(baseline.hr_rest + eff.hr_rest_offset, 1),
                "recovery_slowdown": eff.recovery_tau_scale,
            }
        )
    effect = sleep_effect(baseline, sleep_hours, nights)
    test = simulate_exercise(
        baseline,
        age_years,
        test_intensity,
        test_duration_min,
        prior_sleep_hours=baseline.sleep_hours,
        recovery_min=15.0,
    )
    # Re-run the standard test with the cumulative multi-night effect applied.
    start = datetime(2026, 1, 1, 9, 0)
    blocks = [
        (300.0, 0.03),
        (test_duration_min * 60.0, test_intensity),
        (15 * 60.0, 0.02),
    ]
    restricted = _simulate(
        baseline,
        age_years,
        [
            (d, ActivityInput(intensity=i, hr_rest_offset=effect.hr_rest_offset, recovery_tau_scale=effect.recovery_tau_scale))
            for d, i in blocks
        ],
        start,
    )
    warmup_steps = int(300.0 / STEP_S)
    stop_index = warmup_steps + int(test_duration_min * 60.0 / STEP_S)
    restricted_states, transitions = _run_engine(baseline, restricted)
    return {
        "scenario": "sleep_restriction",
        "label": "Scenario simulation (model output, not a prediction)",
        "inputs": {"sleep_hours": sleep_hours, "nights": nights, "baseline_sleep_hours": baseline.sleep_hours},
        "sleep_effect": effect.__dict__,
        "nights": per_night,
        "phases": test["phases"],
        "baseline": test["baseline"],
        "series": _series(restricted),
        "reference_series": test["reference_series"],
        "metrics": _exercise_metrics(restricted, warmup_steps, stop_index, baseline, restricted_states),
        "reference_metrics": test["reference_metrics"],
        "state_transitions": transitions,
        "assumptions": GENERAL_ASSUMPTIONS + SLEEP_ASSUMPTIONS,
    }


__all__ = [
    "GENERAL_ASSUMPTIONS",
    "SLEEP_ASSUMPTIONS",
    "simulate_exercise",
    "simulate_sleep_restriction",
    "sleep_effect",
]
