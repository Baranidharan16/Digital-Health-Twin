"""End-to-end: simulated observation -> ingestion -> twin update -> state -> API.

Uses the public REST ingestion endpoint (the same path a wearable adapter
would use), not internal shortcuts.
"""

from datetime import datetime

from digital_twin.evaluation import evaluate
from simulator.generator import PhysiologySimulator, SubjectProfile
from simulator.scenarios import ScenarioRunner

TWIN = "twin-001"


def _post(client, obs):
    payload = {
        "timestamp": obs.timestamp.isoformat(),
        "heart_rate": obs.heart_rate,
        "spo2": obs.spo2,
        "temperature": obs.temperature,
        "respiratory_rate": obs.respiratory_rate,
        "steps": obs.steps,
        "activity_intensity": obs.activity_intensity,
        "is_asleep": obs.is_asleep,
        "source": "integration-test",
    }
    r = client.post(f"/api/twin/{TWIN}/observations", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_simulated_stream_drives_twin_through_states(client):
    last = datetime.fromisoformat(client.get(f"/api/twin/{TWIN}/state").json()["twin_time"].rstrip("Z"))
    runner = ScenarioRunner(PhysiologySimulator(SubjectProfile(), seed=99, start=last), "NORMAL")

    seen = []
    for scenario, ticks in (("NORMAL", 10), ("EXERCISE", 30), ("RECOVERY", 25), ("ANOMALY", 30)):
        runner.set_scenario(scenario)
        for _ in range(ticks):
            result = _post(client, runner.next(15.0))
            if not seen or seen[-1] != result["state"]:
                seen.append(result["state"])

    assert "HIGH_ACTIVITY" in seen
    assert "RECOVERY" in seen
    assert seen[-1] == "ANOMALOUS"
    assert seen.index("HIGH_ACTIVITY") < seen.index("RECOVERY") < seen.index("ANOMALOUS")

    state = client.get(f"/api/twin/{TWIN}/state").json()
    assert state["state"] == "ANOMALOUS"
    assert state["observation"]["source"] == "integration-test"
    flagged = [a for a in state["assessments"].values() if a["status"] == "anomalous"]
    assert flagged and all("expected for this subject" in a["reason"] for a in flagged)

    events = client.get(f"/api/twin/{TWIN}/events", params={"kind": "anomaly"}).json()
    assert any(e["active"] for e in events)
    transitions = client.get(f"/api/twin/{TWIN}/events", params={"kind": "transition"}).json()
    assert transitions[0]["to_state"] == "ANOMALOUS"


def test_engine_validation_metrics():
    """Guards the validation numbers reported in the README (same 5 seeds as the README table)."""
    result = evaluate()
    assert result["twin"]["false_alarms_per_day"] <= 0.5
    assert result["twin"]["event_recall"] >= 0.7
    assert result["population_threshold_rule"]["false_alarms_per_day"] > result["twin"]["false_alarms_per_day"]
    assert result["baseline_learning"]["mean_abs_error_resting_hr_bpm"] < 2.0
