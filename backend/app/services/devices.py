"""Phone companion app: pairing, device tokens and Health Connect sync.

Flow
----
1. The website asks for a pairing code (``POST /api/devices/pairing``) and
   shows it with a QR code and the laptop's network address.
2. The Android app sends the code (``POST /api/devices/claim``). The server
   creates a personal twin for that phone and returns a random access token.
   Only the SHA-256 hash of the token is stored.
3. The app reads Health Connect (heart rate, steps, SpO2, respiratory rate,
   body temperature, sleep) and posts it to ``POST /api/devices/sync`` with
   ``Authorization: Bearer <token>``.
4. The server merges the records onto the same 1-minute grid used for file
   imports, ingests every reading newer than the twin's last one through the
   normal twin engine, and pushes the new state to the dashboard over the
   WebSocket.

The first sync must contain enough history to learn a personal baseline
(at least an hour of heart rate including some rest); until then the server
replies ``waiting_for_more_data`` and the app keeps the window open.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.app.importers import ImportFormatError, ParsedFile, build_observations
from backend.app.models import DeviceRow, Subject, Twin
from backend.app.services.twin_service import TwinNotFoundError, TwinService, utcnow
from digital_twin.baseline import InsufficientHistoryError

log = logging.getLogger(__name__)

PAIRING_TTL = timedelta(minutes=10)
MAX_ITEMS_PER_TYPE = 250_000


# ------------------------------------------------------------------ schemas
class HeartRateSample(BaseModel):
    t: datetime
    bpm: float = Field(ge=20, le=250)


class StepsInterval(BaseModel):
    start: datetime
    end: datetime
    count: int = Field(ge=0, le=100_000)


class Spo2Sample(BaseModel):
    t: datetime
    pct: float = Field(ge=50, le=100)


class RespiratorySample(BaseModel):
    t: datetime
    rate: float = Field(ge=3, le=70)


class TemperatureSample(BaseModel):
    t: datetime
    celsius: float = Field(ge=30, le=43)


class SleepSession(BaseModel):
    start: datetime
    end: datetime


class DeviceSyncIn(BaseModel):
    """Records read from Android Health Connect (times in UTC / ISO-8601)."""

    utc_offset_hours: float = Field(0, ge=-12, le=14)
    window_start: datetime | None = None
    window_end: datetime | None = None
    heart_rate: list[HeartRateSample] = Field(default_factory=list, max_length=MAX_ITEMS_PER_TYPE)
    steps: list[StepsInterval] = Field(default_factory=list, max_length=MAX_ITEMS_PER_TYPE)
    spo2: list[Spo2Sample] = Field(default_factory=list, max_length=MAX_ITEMS_PER_TYPE)
    respiratory_rate: list[RespiratorySample] = Field(default_factory=list, max_length=MAX_ITEMS_PER_TYPE)
    temperature: list[TemperatureSample] = Field(default_factory=list, max_length=MAX_ITEMS_PER_TYPE)
    sleep: list[SleepSession] = Field(default_factory=list, max_length=10_000)


class ClaimIn(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    device_name: str = Field("Android phone", max_length=80)


class PairingIn(BaseModel):
    display_name: str = Field("My phone", max_length=60)
    age_years: float = Field(30, ge=10, le=100)


# ------------------------------------------------------------------ helpers
def _naive_utc(t: datetime) -> datetime:
    if t.tzinfo is not None:
        t = t.astimezone(timezone.utc).replace(tzinfo=None)
    return t


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class DeviceAuthError(PermissionError):
    pass


@dataclass
class _Pairing:
    display_name: str
    age_years: float
    expires: datetime


def to_parsed(body: DeviceSyncIn) -> list[ParsedFile]:
    """Convert Health Connect records into the importer's long format (UTC clock)."""
    parts: list[pd.DataFrame] = []

    def frame(times, field, values) -> pd.DataFrame:
        return pd.DataFrame({"t": [_naive_utc(t) for t in times], "field": field, "value": values})

    if body.heart_rate:
        parts.append(frame([s.t for s in body.heart_rate], "heart_rate", [s.bpm for s in body.heart_rate]))
    if body.spo2:
        parts.append(frame([s.t for s in body.spo2], "spo2", [s.pct for s in body.spo2]))
    if body.respiratory_rate:
        parts.append(frame([s.t for s in body.respiratory_rate], "respiratory_rate", [s.rate for s in body.respiratory_rate]))
    if body.temperature:
        parts.append(frame([s.t for s in body.temperature], "temperature", [s.celsius for s in body.temperature]))
    if body.steps:
        # Spread each steps interval evenly over the minutes it covers.
        times, values = [], []
        for iv in body.steps:
            a, b = _naive_utc(iv.start), _naive_utc(iv.end)
            minutes = max(int((b - a).total_seconds() // 60), 1)
            per = iv.count / minutes
            for i in range(minutes):
                times.append(a + timedelta(minutes=i))
                values.append(per)
        parts.append(pd.DataFrame({"t": times, "field": "steps", "value": values}))
    sleep = [(_naive_utc(s.start), _naive_utc(s.end)) for s in body.sleep if s.end > s.start]
    samples = pd.concat(parts, ignore_index=True) if parts else None
    return [ParsedFile("health-connect", "Android Health Connect", samples, sleep=sleep, rows=sum(len(p) for p in parts))]


class DeviceService:
    def __init__(self, twins: TwinService) -> None:
        self.twins = twins
        self.db = twins.db
        self._pairings: dict[str, _Pairing] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------- pairing
    def create_pairing(self, display_name: str, age_years: float) -> dict:
        now = utcnow()
        with self._lock:
            self._pairings = {c: p for c, p in self._pairings.items() if p.expires > now}
            code = f"{secrets.randbelow(10**6):06d}"
            while code in self._pairings:
                code = f"{secrets.randbelow(10**6):06d}"
            self._pairings[code] = _Pairing(display_name.strip() or "My phone", age_years, now + PAIRING_TTL)
        return {"code": code, "expires_at": (now + PAIRING_TTL).isoformat() + "Z", "ttl_seconds": int(PAIRING_TTL.total_seconds())}

    def claim(self, code: str, device_name: str) -> dict:
        now = utcnow()
        with self._lock:
            pairing = self._pairings.pop(code, None)
        if pairing is None or pairing.expires <= now:
            raise DeviceAuthError("pairing code is wrong or expired; create a new one on the website")
        token = secrets.token_urlsafe(32)
        twin_id = f"twin-{uuid.uuid4().hex[:8]}"
        subject_id = f"subj-{twin_id.removeprefix('twin-')}"
        with self.db.session_scope() as session:
            session.add(
                Subject(id=subject_id, pseudonym=pairing.display_name[:60], age_years=pairing.age_years,
                        is_synthetic=False, utc_offset_hours=0.0, data_source="Android phone (Health Connect)",
                        created_at=now)
            )
            session.add(Twin(id=twin_id, subject_id=subject_id, name=f"Health Twin · {pairing.display_name[:60]}",
                             created_at=now, updated_at=now, observation_count=0))
            session.flush()
            device = DeviceRow(twin_id=twin_id, name=device_name[:80], token_hash=hash_token(token), created_at=now)
            session.add(device)
            session.flush()
            device_id = device.id
        log.info("paired device %s to %s", device_id, twin_id)
        return {"token": token, "twin_id": twin_id, "device_id": device_id, "display_name": pairing.display_name}

    def authenticate(self, token: str | None) -> DeviceRow:
        if not token:
            raise DeviceAuthError("missing device token")
        with self.db.session_scope() as session:
            row = session.scalars(select(DeviceRow).where(DeviceRow.token_hash == hash_token(token))).first()
            if row is None:
                raise DeviceAuthError("unknown or revoked device token; pair the phone again")
            session.expunge(row)
            return row

    # ---------------------------------------------------------------- sync
    def sync(self, device: DeviceRow, body: DeviceSyncIn) -> dict:
        twin_id = device.twin_id
        with self.db.session_scope() as session:
            twin = session.get(Twin, twin_id)
            if twin is None:
                raise TwinNotFoundError(twin_id)
            subject = session.get(Subject, twin.subject_id)
            subject.utc_offset_hours = body.utc_offset_hours  # phone's current time zone
            age = subject.age_years
            last = twin.last_observation_at
        counts = {k: len(getattr(body, k)) for k in ("heart_rate", "steps", "spo2", "respiratory_rate", "temperature", "sleep")}

        try:
            result = build_observations(to_parsed(body), utc_offset_hours=0.0, source="health-connect")
            observations = result.observations
            metrics = result.metrics
        except ImportFormatError as exc:
            observations, metrics = [], []
            reason = str(exc)
        else:
            reason = None
        new = [o for o in observations if last is None or o.timestamp > last]
        if body.window_end is not None and new:
            # Only complete minutes: the minute still in progress is sent again next time.
            cutoff = _naive_utc(body.window_end).replace(second=0, microsecond=0)
            new = [o for o in new if o.timestamp < cutoff]

        status = "synced"
        ingested = 0
        if new:
            if last is None:  # first data for this twin: learn the baseline first
                try:
                    self.twins.set_initial_baseline(twin_id, new, age, body.utc_offset_hours)
                except InsufficientHistoryError as exc:
                    status, reason, new = "waiting_for_more_data", f"not enough history for a baseline yet ({exc})", []
            if new:
                ingested = self.twins.ingest_many(twin_id, new)
                if last is None:
                    self.twins.recompute_baseline(twin_id)
                self.twins.notify(twin_id)
        elif reason:
            status = "no_heart_rate"
        else:
            status = "nothing_new"

        summary = {
            "status": status,
            "received": counts,
            "readings_ingested": ingested,
            "metrics": metrics,
            "twin_id": twin_id,
            "detail": reason,
            "synced_at": utcnow().isoformat() + "Z",
        }
        with self.db.session_scope() as session:
            row = session.get(DeviceRow, device.id)
            if row is not None:
                row.last_seen_at = utcnow()
                row.last_sync = summary
        return summary

    # ------------------------------------------------------------- listing
    def list_devices(self) -> list[dict]:
        with self.db.session_scope() as session:
            rows = session.scalars(select(DeviceRow).order_by(DeviceRow.created_at.desc())).all()
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "twin_id": r.twin_id,
                    "created_at": r.created_at.isoformat() + "Z",
                    "last_seen_at": r.last_seen_at.isoformat() + "Z" if r.last_seen_at else None,
                    "last_sync": r.last_sync,
                }
                for r in rows
            ]

    def revoke(self, device_id: int) -> None:
        with self.db.session_scope() as session:
            row = session.get(DeviceRow, device_id)
            if row is None:
                raise KeyError(f"device {device_id} not found")
            session.delete(row)
