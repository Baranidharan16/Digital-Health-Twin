"""Deterministic state engine and transitions."""

from datetime import timedelta

from digital_twin.engine import OutOfOrderObservationError, TwinEngine
from digital_twin.state_engine import CONFIRM_READINGS, StateDecision, StateMachine
from digital_twin.types import TwinState
from tests.conftest import T0, make_obs

import pytest


def _run(engine, start, n, **kw):
    snaps = []
    for i in range(n):
        snaps.append(engine.ingest(make_obs(start + timedelta(seconds=15 * i), **kw)))
    return snaps


def test_first_reading_sets_state(baseline):
    engine = TwinEngine(baseline)
    snap = engine.ingest(make_obs(T0, heart_rate=baseline.hr_rest))
    assert snap.state == TwinState.STABLE
    assert snap.transitioned


def test_debounce_requires_confirmation():
    machine = StateMachine()
    machine.update(StateDecision(TwinState.STABLE, "start"), T0)
    changed = [
        machine.update(StateDecision(TwinState.ACTIVE, "walking"), T0 + timedelta(seconds=i + 1))
        for i in range(CONFIRM_READINGS)
    ]
    assert changed == [False] * (CONFIRM_READINGS - 1) + [True]
    assert machine.state == TwinState.ACTIVE
    assert machine.previous_state == TwinState.STABLE


def test_anomalous_is_entered_immediately():
    machine = StateMachine()
    machine.update(StateDecision(TwinState.STABLE, "start"), T0)
    assert machine.update(StateDecision(TwinState.ANOMALOUS, "persistent"), T0 + timedelta(seconds=1))


def test_exercise_then_recovery_then_stable(baseline):
    engine = TwinEngine(baseline)
    _run(engine, T0, 4, heart_rate=baseline.hr_rest)
    run = _run(engine, T0 + timedelta(minutes=1), 40, heart_rate=150.0, activity_intensity=0.75,
               respiratory_rate=30.0, steps=35)
    assert run[-1].state == TwinState.HIGH_ACTIVITY
    # Activity stops while heart rate is still high -> RECOVERY.
    after = _run(engine, T0 + timedelta(minutes=12), 3, heart_rate=110.0, activity_intensity=0.02,
                 respiratory_rate=18.0)
    assert after[-1].state == TwinState.RECOVERY
    assert "returning" in after[-1].state_reason
    settled = _run(engine, T0 + timedelta(minutes=13), 4, heart_rate=baseline.hr_rest, activity_intensity=0.02)
    assert settled[-1].state == TwinState.STABLE
    assert settled[-1].previous_state == TwinState.RECOVERY


def test_sleep_state(baseline):
    engine = TwinEngine(baseline)
    snaps = _run(engine, T0, 4, heart_rate=baseline.hr_sleep, is_asleep=True, respiratory_rate=baseline.rr_sleep,
                 temperature=baseline.temp_sleep, activity_intensity=0.0)
    assert snaps[-1].state == TwinState.SLEEPING


def test_anomalous_has_priority_over_activity(baseline):
    engine = TwinEngine(baseline)
    snaps = _run(engine, T0, 8, heart_rate=baseline.hr_rest, spo2=89.0)
    assert snaps[-1].state == TwinState.ANOMALOUS
    assert "SpO₂" in snaps[-1].state_reason


def test_out_of_order_observation_rejected(baseline):
    engine = TwinEngine(baseline)
    engine.ingest(make_obs(T0))
    with pytest.raises(OutOfOrderObservationError):
        engine.ingest(make_obs(T0))


def test_engine_is_deterministic(baseline):
    readings = [make_obs(T0 + timedelta(seconds=15 * i), heart_rate=66 + (i % 7) * 6, activity_intensity=(i % 5) / 6)
                for i in range(80)]
    a = [TwinEngine(baseline).ingest(r).state for r in readings[:1]]
    e1, e2 = TwinEngine(baseline), TwinEngine(baseline)
    s1 = [e1.ingest(r).state for r in readings]
    s2 = [e2.ingest(r).state for r in readings]
    assert s1 == s2 and a
