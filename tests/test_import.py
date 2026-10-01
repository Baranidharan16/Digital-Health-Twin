"""Importing real wearable exports into a personal twin."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from backend.app.importers import ImportFormatError, import_files, intensity_from_cadence, parse_file

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample_real" / "fitbit_user_5553957443"


def _uploads():
    return [(p.name, p.read_bytes()) for p in sorted(SAMPLE.glob("*.csv"))]


def test_fitbit_files_are_detected():
    formats = {parse_file(n, b).format for n, b in _uploads()}
    assert formats == {"Fitbit heart rate (seconds)", "Fitbit steps (minute)", "Fitbit sleep (minute)"}


def test_real_fitbit_export_is_merged_honestly():
    r = import_files(_uploads(), utc_offset_hours=-5, source="fitbit")
    assert r.interval_s == 60 and len(r.observations) > 10_000
    assert r.metrics == ["heart_rate"]  # Fitbit export has no SpO2 / temperature / breathing
    assert all(o.spo2 is None and o.temperature is None and o.respiratory_rate is None for o in r.observations)
    assert r.sleep_minutes > 3000 and r.intensity_estimated
    # Local device clock (UTC-5) is converted to UTC.
    assert r.start == datetime(2016, 4, 12, 5, 0)


def test_cadence_to_intensity_is_monotonic():
    values = [intensity_from_cadence(s) for s in (0, 30, 60, 90, 110, 140, 200)]
    assert values == sorted(values) and values[0] < 0.05 and 0.4 < intensity_from_cadence(110) < 0.6


def test_generic_csv_with_optional_vitals():
    t0 = datetime(2026, 1, 5, 8, 0)
    lines = ["timestamp,heart_rate,spo2,steps"] + [
        f"{(t0 + timedelta(minutes=i)).isoformat()},{62 + i % 3},{0.97},{0}" for i in range(90)
    ]
    r = import_files([("my_watch.csv", "\n".join(lines).encode())], 0, "generic")
    assert r.metrics == ["heart_rate", "spo2"]
    assert r.observations[0].spo2 == pytest.approx(97.0)
    assert r.observations[0].temperature is None


def test_samsung_health_heart_rate():
    text = (
        "com.samsung.health.heart_rate,6313005,1\n"
        "com.samsung.health.heart_rate.start_time,com.samsung.health.heart_rate.time_offset,com.samsung.health.heart_rate.heart_rate\n"
        + "\n".join(f"2024-03-01 0{h}:00:00.000,UTC+0530,{60 + h}" for h in range(5))
    )
    p = parse_file("com.samsung.health.heart_rate.20240301.csv", text.encode())
    assert p.format == "Samsung Health heart rate"
    assert p.samples["t"].iloc[0] == datetime(2024, 3, 1, 5, 30)  # UTC + 05:30 -> local clock


def test_unknown_format_and_missing_heart_rate_are_rejected():
    with pytest.raises(ImportFormatError, match="not recognised"):
        parse_file("x.csv", b"foo,bar\n1,2\n")
    with pytest.raises(ImportFormatError, match="heart rate is required"):
        import_files([("steps.csv", b"timestamp,steps\n2026-01-01T00:00:00,10\n")], 0, "x")


def test_import_api_creates_and_deletes_a_personal_twin(client):
    r = client.post("/api/twins/import-sample")
    assert r.status_code == 200, r.text
    twin_id = r.json()["twin_id"]
    state = client.get(f"/api/twin/{twin_id}/state").json()
    assert set(state["assessments"]) == {"heart_rate"}
    twin = client.get(f"/api/twin/{twin_id}").json()
    assert twin["subject"]["is_synthetic"] is False and "Fitbit" in twin["subject"]["data_source"]
    # Live simulator refuses to drive a twin built from real data.
    assert client.post("/api/simulator/start", json={"twin_id": twin_id}).status_code == 400
    # What-if still works on the personal baseline.
    assert client.post("/api/simulation", json={"scenario": "exercise", "twin_id": twin_id}).status_code == 200
    # Right to erasure; the demo twin is protected.
    assert client.delete(f"/api/twin/{twin_id}").status_code == 200
    assert client.get(f"/api/twin/{twin_id}").status_code == 404
    assert client.delete("/api/twin/twin-001").status_code == 400


def test_upload_endpoint_rejects_bad_files(client):
    r = client.post("/api/twins/import", files={"files": ("bad.csv", b"a,b\n1,2\n", "text/csv")})
    assert r.status_code == 400 and "not recognised" in r.json()["detail"]
