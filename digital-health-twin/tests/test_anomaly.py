"""Context-aware, explainable anomaly detection."""

from datetime import timedelta

from digital_twin.anomaly import CLEAR_READINGS, PERSISTENCE_READINGS, AnomalyDetector
from digital_twin.engine import TwinEngine
from tests.conftest import T0, make_obs, series


def _assess(detector, obs, baseline, intensity=0.03):
    return detector.assess(obs, baseline, intensity, intensity, intensity)


def test_resting_tachycardia_requires_persistence(baseline):
    detector = AnomalyDetector()
    high = baseline.hr_rest * 1.4
    statuses = []
    for obs in series(T0, PERSISTENCE_READINGS + 1, heart_rate=high):
        statuses.append(_assess(detector, obs, baseline)["heart_rate"].status)
    # Watch while not yet persistent, anomalous once the streak is long enough.
    assert statuses[: PERSISTENCE_READINGS - 1] == ["watch"] * (PERSISTENCE_READINGS - 1)
    assert statuses[PERSISTENCE_READINGS - 1] == "anomalous"


def test_explanation_says_why(baseline):
    detector = AnomalyDetector()
    result = None
    for obs in series(T0, PERSISTENCE_READINGS, heart_rate=baseline.hr_rest * 1.4):
        result = _assess(detector, obs, baseline)["heart_rate"]
    assert result.status == "anomalous"
    assert "% above" in result.reason
    assert "expected for this subject at rest" in result.reason
    assert f"{PERSISTENCE_READINGS} consecutive readings" in result.reason


def test_exercise_heart_rate_is_not_anomalous(baseline):
    """150 bpm during a run is expected; the same value at rest would not be."""
    engine = TwinEngine(baseline)
    snap = None
    for i in range(60):  # 15 minutes of steady running
        snap = engine.ingest(make_obs(T0 + timedelta(seconds=15 * i), heart_rate=150.0, activity_intensity=0.75,
                                      respiratory_rate=30.0, steps=35))
    assert snap is not None
    assert snap.assessments["heart_rate"].status == "normal"
    assert not snap.active_anomalies


def test_anomaly_clears_with_hysteresis(baseline):
    detector = AnomalyDetector()
    for obs in series(T0, PERSISTENCE_READINGS, heart_rate=baseline.hr_rest * 1.4):
        _assess(detector, obs, baseline)
    start = T0 + timedelta(minutes=10)
    statuses = [
        _assess(detector, obs, baseline)["heart_rate"].status
        for obs in series(start, CLEAR_READINGS, heart_rate=baseline.hr_rest)
    ]
    assert statuses[:-1] == ["anomalous"] * (CLEAR_READINGS - 1)
    assert statuses[-1] == "normal"


def test_single_glitch_is_not_flagged(baseline):
    detector = AnomalyDetector()
    readings = series(T0, 6)
    readings[2] = make_obs(readings[2].timestamp, heart_rate=140.0)
    statuses = [_assess(detector, o, baseline)["heart_rate"].status for o in readings]
    assert "anomalous" not in statuses


def test_low_spo2_reference_flag(baseline):
    detector = AnomalyDetector()
    result = None
    for obs in series(T0, PERSISTENCE_READINGS, spo2=90.5):
        result = _assess(detector, obs, baseline)["spo2"]
    assert result.status == "anomalous"
    assert result.reference_flag and "92%" in result.reference_flag
