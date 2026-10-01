"""Data validation and normalization (ingestion layer)."""

from datetime import datetime

import pytest

from backend.app.ingestion import NormalizationError, normalize_raw, parse_csv


def test_aliases_and_unit_conversion():
    obs = normalize_raw(
        {"time": "2026-03-01T10:00:00Z", "bpm": 72, "oxygen_saturation": 0.975, "temperature_f": 98.6, "rr": 15},
        source="wearable",
    )
    assert obs.heart_rate == 72
    assert obs.spo2 == pytest.approx(97.5)
    assert obs.temperature == pytest.approx(37.0, abs=0.01)
    assert obs.respiratory_rate == 15
    assert obs.source == "wearable"
    assert obs.timestamp == datetime(2026, 3, 1, 10, 0)  # stored as naive UTC


def test_epoch_milliseconds_timestamp():
    obs = normalize_raw(
        {"ts": 1772359200000, "hr": 60, "spo2": 98, "temp": 36.5, "resp_rate": 12}, source="api"
    )
    assert obs.timestamp == datetime(2026, 3, 1, 10, 0)


@pytest.mark.parametrize(
    "field,value",
    [("hr", 400), ("spo2", 30), ("temp", 50), ("rr", 0), ("steps", -1)],
)
def test_physically_implausible_values_rejected(field, value):
    raw = {"timestamp": "2026-03-01T10:00:00", "hr": 70, "spo2": 98, "temp": 36.6, "rr": 14, "steps": 5}
    raw[field] = value
    with pytest.raises(NormalizationError):
        normalize_raw(raw, source="api")


def test_missing_timestamp_rejected():
    with pytest.raises(NormalizationError, match="timestamp"):
        normalize_raw({"hr": 70, "spo2": 98, "temp": 36.6, "rr": 14}, source="api")


def test_csv_reports_bad_rows_with_line_numbers():
    text = (
        "timestamp,hr,spo2,temp,rr,steps\n"
        "2026-03-01T10:00:00,70,98,36.6,14,10\n"
        "2026-03-01T10:00:15,999,98,36.6,14,10\n"
    )
    rows = list(parse_csv(text))
    assert rows[0][1] is not None and rows[0][2] is None
    assert rows[1][0] == 3 and rows[1][1] is None and "heart_rate" in rows[1][2]
