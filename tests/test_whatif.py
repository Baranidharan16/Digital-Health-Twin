"""What-if scenario simulation engine."""

from digital_twin.whatif import simulate_exercise, simulate_sleep_restriction, sleep_effect


def test_exercise_scenario_shape_and_labels(baseline):
    r = simulate_exercise(baseline, 29, intensity=0.7, duration_min=20)
    assert r["label"].startswith("Scenario simulation")
    assert any("not a medical prediction" in a for a in r["assumptions"])
    assert len(r["series"]) == len(r["reference_series"])
    states = [t["state"] for t in r["state_transitions"]]
    assert "HIGH_ACTIVITY" in states and "RECOVERY" in states


def test_higher_intensity_gives_higher_peak(baseline):
    easy = simulate_exercise(baseline, 29, intensity=0.4, duration_min=20)["metrics"]
    hard = simulate_exercise(baseline, 29, intensity=0.9, duration_min=20)["metrics"]
    assert hard["peak_heart_rate"] > easy["peak_heart_rate"] + 30
    assert hard["peak_heart_rate"] <= baseline.hr_max_est + 1


def test_scenario_is_deterministic(baseline):
    assert simulate_exercise(baseline, 29, 0.6, 15) == simulate_exercise(baseline, 29, 0.6, 15)


def test_sleep_restriction_raises_resting_hr_and_slows_recovery(baseline):
    r = simulate_sleep_restriction(baseline, 29, sleep_hours=4.5, nights=3)
    assert r["nights"][-1]["resting_hr"] > baseline.hr_rest
    assert r["nights"][-1]["resting_hr"] >= r["nights"][0]["resting_hr"]
    m, ref = r["metrics"], r["reference_metrics"]
    assert m["heart_rate_recovery_1min"] < ref["heart_rate_recovery_1min"]


def test_no_deficit_no_effect(baseline):
    effect = sleep_effect(baseline, baseline.sleep_hours + 1, nights=3)
    assert effect.hr_rest_offset == 0 and effect.recovery_tau_scale == 1.0
