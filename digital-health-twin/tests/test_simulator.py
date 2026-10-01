"""Synthetic data generator: reproducibility and physiological correlation."""

from datetime import datetime

import numpy as np

from simulator.generator import ActivityInput, PhysiologySimulator, SubjectProfile, generate_history
from simulator.scenarios import GUIDED_DEMO, SCENARIOS, ScenarioRunner

START = datetime(2026, 3, 1, 4, 30)  # 10:00 local (UTC+5:30)


def _run(scenario: str, ticks: int, seed: int = 42):
    runner = ScenarioRunner(PhysiologySimulator(SubjectProfile(), seed=seed, start=START), scenario)
    return [runner.next(15.0) for _ in range(ticks)]


def test_same_seed_same_data():
    assert _run("NORMAL", 30, seed=1) == _run("NORMAL", 30, seed=1)
    assert _run("NORMAL", 30, seed=1) != _run("NORMAL", 30, seed=2)


def test_history_is_reproducible():
    a = generate_history(SubjectProfile(), end=START, days=1, seed=5)
    b = generate_history(SubjectProfile(), end=START, days=1, seed=5)
    assert a == b and len(a) == 288


def test_exercise_raises_correlated_signals():
    rest = _run("NORMAL", 20)
    run = _run("EXERCISE", 40)[-10:]
    assert np.mean([o.heart_rate for o in run]) > np.mean([o.heart_rate for o in rest]) + 50
    assert np.mean([o.respiratory_rate for o in run]) > np.mean([o.respiratory_rate for o in rest]) + 8
    assert sum(o.steps for o in run) > 200
    assert np.mean([o.spo2 for o in run]) < np.mean([o.spo2 for o in rest])


def test_recovery_decays_towards_baseline():
    sim = PhysiologySimulator(SubjectProfile(), seed=1, start=START, noise_scale=0.0)
    for _ in range(40):
        sim.step(15.0, ActivityInput(intensity=0.8))
    peak = sim.hr
    hrs = [sim.step(15.0, ActivityInput(intensity=0.02)).heart_rate for _ in range(40)]
    assert hrs[0] < peak and hrs[-1] < hrs[0] and all(b <= a + 1e-6 for a, b in zip(hrs, hrs[1:]))


def test_sleep_lowers_heart_rate():
    sleep = _run("SLEEP", 40)[-10:]
    assert np.mean([o.heart_rate for o in sleep]) < SubjectProfile().hr_rest
    assert all(o.is_asleep and o.steps == 0 for o in sleep)


def test_anomaly_deviates_without_activity():
    anomaly = _run("ANOMALY", 40)[-10:]
    p = SubjectProfile()
    assert np.mean([o.heart_rate for o in anomaly]) > p.hr_rest * 1.2
    assert np.mean([o.spo2 for o in anomaly]) < p.spo2 - 2
    assert max(o.activity_intensity for o in anomaly) < 0.1


def test_guided_demo_walks_through_all_phases():
    runner = ScenarioRunner(PhysiologySimulator(SubjectProfile(), seed=1, start=START))
    runner.start_guided()
    seen = []
    for _ in range(int(sum(d for _, d in GUIDED_DEMO) / 15) + 2):
        runner.next(15.0)
        if not seen or seen[-1] != runner.scenario.key:
            seen.append(runner.scenario.key)
    assert seen == [k for k, _ in GUIDED_DEMO]
    assert set(seen) <= set(SCENARIOS)
