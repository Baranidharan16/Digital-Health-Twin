"""Phone connection: pairing, device tokens and Health Connect sync."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from simulator.generator import SubjectProfile, generate_history
from simulator.health_connect import to_health_connect

END = datetime(2026, 3, 4, 9, 0, 0)


@pytest.fixture(scope="module")
def phone_history():
    return generate_history(SubjectProfile(), end=END, days=2, interval_s=60.0, seed=11, include_planned_anomaly=False)


def _pair(client, name="Test phone"):
    r = client.post("/api/devices/pairing", json={"display_name": name, "age_years": 31})
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    assert len(code) == 6 and code.isdigit()
    assert r.json()["deep_link"].startswith("healthtwin://pair?")
    r = client.post("/api/devices/claim", json={"code": code, "device_name": "Pixel test"})
    assert r.status_code == 200, r.text
    return r.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_pairing_creates_twin_and_code_is_single_use(client):
    r = client.post("/api/devices/pairing", json={"display_name": "Asha"})
    code = r.json()["code"]
    claim = client.post("/api/devices/claim", json={"code": code})
    assert claim.status_code == 200
    body = claim.json()
    assert body["twin_id"].startswith("twin-") and len(body["token"]) > 30
    twins = {t["id"]: t for t in client.get("/api/twins").json()}
    assert body["twin_id"] in twins
    assert twins[body["twin_id"]]["subject"]["data_source"] == "Android phone (Health Connect)"
    again = client.post("/api/devices/claim", json={"code": code})
    assert again.status_code == 401


def test_wrong_code_and_bad_token_are_rejected(client):
    assert client.post("/api/devices/claim", json={"code": "000000"}).status_code in (401,)
    assert client.post("/api/devices/claim", json={"code": "12ab"}).status_code == 422
    r = client.post("/api/devices/sync", json={}, headers=_auth("not-a-real-token"))
    assert r.status_code == 401
    assert client.post("/api/devices/sync", json={}).status_code == 401


def test_first_sync_learns_baseline_and_updates_twin(client, phone_history):
    paired = _pair(client)
    body = to_health_connect(phone_history, utc_offset_hours=5.5)
    r = client.post("/api/devices/sync", json=body, headers=_auth(paired["token"]))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "synced"
    assert out["readings_ingested"] > 2000
    assert out["received"]["heart_rate"] == len(phone_history)
    assert "spo2" in out["metrics"] and "heart_rate" in out["metrics"]

    state = client.get(f"/api/twin/{paired['twin_id']}/state")
    assert state.status_code == 200
    baseline = client.get(f"/api/twin/{paired['twin_id']}/baseline").json()
    assert 50 < baseline["data"]["hr_rest"] < 75

    devices = client.get("/api/devices").json()
    mine = [d for d in devices if d["id"] == paired["device_id"]][0]
    assert mine["last_sync"]["status"] == "synced" and mine["last_seen_at"]


def test_incremental_sync_only_adds_new_minutes(client, phone_history):
    paired = _pair(client)
    first, later = phone_history[:-120], phone_history[-180:]  # 60 min overlap
    r1 = client.post("/api/devices/sync", json=to_health_connect(first), headers=_auth(paired["token"])).json()
    r2 = client.post("/api/devices/sync", json=to_health_connect(later), headers=_auth(paired["token"])).json()
    assert r1["status"] == "synced" and r2["status"] == "synced"
    assert 110 <= r2["readings_ingested"] <= 121
    r3 = client.post("/api/devices/sync", json=to_health_connect(later), headers=_auth(paired["token"])).json()
    assert r3["status"] == "nothing_new" and r3["readings_ingested"] == 0


def test_short_history_waits_for_more_data(client, phone_history):
    paired = _pair(client)
    body = to_health_connect(phone_history[-10:])
    out = client.post("/api/devices/sync", json=body, headers=_auth(paired["token"])).json()
    assert out["status"] == "waiting_for_more_data"
    assert out["readings_ingested"] == 0
    # The full history later still works.
    out = client.post("/api/devices/sync", json=to_health_connect(phone_history), headers=_auth(paired["token"])).json()
    assert out["status"] == "synced"


def test_sync_without_heart_rate_is_reported(client, phone_history):
    paired = _pair(client)
    body = to_health_connect(phone_history[:200], include=("steps",))
    out = client.post("/api/devices/sync", json=body, headers=_auth(paired["token"])).json()
    assert out["status"] == "no_heart_rate"
    assert "heart rate" in out["detail"]


def test_only_heart_rate_and_steps_leaves_other_vitals_unmeasured(client, phone_history):
    paired = _pair(client)
    body = to_health_connect(phone_history, include=("heart_rate", "steps"))
    out = client.post("/api/devices/sync", json=body, headers=_auth(paired["token"])).json()
    assert out["status"] == "synced"
    assert "spo2" not in out["metrics"]
    state = client.get(f"/api/twin/{paired['twin_id']}/state").json()
    assert state["observation"]["spo2"] is None


def test_revoke_and_delete(client, phone_history):
    paired = _pair(client)
    assert client.get("/api/devices/me", headers=_auth(paired["token"])).status_code == 200
    assert client.delete(f"/api/devices/{paired['device_id']}").status_code == 200
    assert client.post("/api/devices/sync", json={}, headers=_auth(paired["token"])).status_code == 401
    assert client.delete(f"/api/devices/{paired['device_id']}").status_code == 404

    other = _pair(client)
    assert client.delete(f"/api/twin/{other['twin_id']}").status_code in (200, 204)
    assert client.post("/api/devices/sync", json={}, headers=_auth(other["token"])).status_code == 401


def test_network_endpoint(client):
    r = client.get("/api/system/network")
    assert r.status_code == 200 and isinstance(r.json()["server_urls"], list)


def test_window_end_drops_unfinished_minute(client, phone_history):
    paired = _pair(client)
    hist = phone_history
    body = to_health_connect(hist, window_end=hist[-1].timestamp + timedelta(seconds=20))
    out = client.post("/api/devices/sync", json=body, headers=_auth(paired["token"])).json()
    assert out["status"] == "synced"
    twin = [t for t in client.get("/api/twins").json() if t["id"] == paired["twin_id"]][0]
    assert twin["last_observation_at"] < (hist[-1].timestamp.replace(second=0)).isoformat()


def test_deployed_site_gives_its_own_https_address(client):
    r = client.get("https://twin.example.com/api/system/network")
    body = r.json()
    assert body["server_urls"] == ["https://twin.example.com"] and body["public"] is True
    p = client.post("https://twin.example.com/api/devices/pairing", json={"display_name": "x"}).json()
    assert p["deep_link"].startswith("healthtwin://pair?server=https://twin.example.com&code=")


def test_empty_phone_twin_is_safe_to_open(client):
    paired = _pair(client)
    tid = paired["twin_id"]
    assert client.get(f"/api/twin/{tid}").json()["observation_count"] == 0
    assert client.get(f"/api/twin/{tid}/state").status_code == 409
    assert client.get(f"/api/twin/{tid}/events").status_code == 200
    assert client.get(f"/api/twin/{tid}/history?range=24h").status_code == 200
