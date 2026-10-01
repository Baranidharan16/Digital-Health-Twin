"""TwinService: orchestrates ingestion, the twin engine and persistence.

This is the synchronization loop of the Digital Twin. For every incoming
observation it:

1. validates and normalizes it (ingestion layer, before this service);
2. updates the in-memory :class:`TwinEngine` (state, anomalies, features);
3. persists the observation, the new twin state, any state transition and
   any anomaly episode;
4. notifies listeners (WebSocket clients) so the UI and 3D twin update.

One engine per twin is kept in memory for speed. On startup it is rebuilt by
replaying recent observations from the database, so the service can restart
without losing the twin's persistence counters or current state.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.db import Database
from backend.app.ingestion import to_observation
from backend.app.models import (
    AnomalyEventRow,
    BaselineRow,
    ObservationRow,
    StateTransitionRow,
    Twin,
)
from backend.app.schemas import ObservationIn, to_utc_iso
from digital_twin.baseline import compute_baseline
from digital_twin.engine import TwinEngine
from digital_twin.state_engine import STATE_DESCRIPTIONS
from digital_twin.types import Baseline, Observation, TwinSnapshot, TwinState
from digital_twin.wellness import activity_level_label

log = logging.getLogger(__name__)

RESTORE_WINDOW = timedelta(hours=2)
BASELINE_WINDOW = timedelta(days=7)

Listener = Callable[[str, dict[str, Any]], None]


class TwinNotFoundError(KeyError):
    pass


class NoBaselineError(RuntimeError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def row_to_observation(row: ObservationRow) -> Observation:
    return Observation(
        timestamp=row.timestamp,
        heart_rate=row.heart_rate,
        spo2=row.spo2,
        temperature=row.temperature,
        respiratory_rate=row.respiratory_rate,
        steps=row.steps,
        activity_intensity=row.activity_intensity,
        is_asleep=row.is_asleep,
        source=row.source,
    )


class TwinService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._engines: dict[str, TwinEngine] = {}
        self._snapshots: dict[str, TwinSnapshot] = {}
        self._open_anomalies: dict[str, dict[str, int]] = {}
        self._listeners: list[Listener] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------- listeners
    def add_listener(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: Listener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    # ---------------------------------------------------------------- engines
    def has_engine(self, twin_id: str) -> bool:
        return twin_id in self._engines

    def engine(self, twin_id: str) -> TwinEngine:
        with self._lock:
            if twin_id not in self._engines:
                self._restore_engine(twin_id)
            return self._engines[twin_id]

    def reset(self) -> None:
        with self._lock:
            self._engines.clear()
            self._snapshots.clear()
            self._open_anomalies.clear()

    def active_baseline(self, session: Session, twin_id: str) -> Baseline:
        row = session.scalars(
            select(BaselineRow)
            .where(BaselineRow.twin_id == twin_id, BaselineRow.is_active.is_(True))
            .order_by(BaselineRow.computed_at.desc())
        ).first()
        if row is None:
            raise NoBaselineError(f"twin {twin_id} has no baseline yet")
        return Baseline.from_dict(row.data)

    def _restore_engine(self, twin_id: str) -> None:
        with self.db.session_scope() as session:
            twin = session.get(Twin, twin_id)
            if twin is None:
                raise TwinNotFoundError(twin_id)
            baseline = self.active_baseline(session, twin_id)
            engine = TwinEngine(baseline)
            snapshot = None
            replayed = 0
            if twin.last_observation_at is not None:
                rows = session.scalars(
                    select(ObservationRow)
                    .where(
                        ObservationRow.twin_id == twin_id,
                        ObservationRow.timestamp >= twin.last_observation_at - RESTORE_WINDOW,
                    )
                    .order_by(ObservationRow.timestamp)
                ).all()
                for row in rows:
                    snapshot = engine.ingest(row_to_observation(row))
                replayed = len(rows)
            if twin.current_state and twin.state_since:
                engine.restore_state(
                    TwinState(twin.current_state),
                    twin.state_since,
                    twin.state_reason or "",
                    TwinState(twin.previous_state) if twin.previous_state else None,
                )
                if snapshot is not None:
                    snapshot.state = TwinState(twin.current_state)
                    snapshot.state_since = twin.state_since
                    snapshot.state_reason = twin.state_reason or snapshot.state_reason
            engine.last_hr_recovery_bpm = twin.last_hr_recovery_bpm
            open_rows = session.scalars(
                select(AnomalyEventRow).where(
                    AnomalyEventRow.twin_id == twin_id, AnomalyEventRow.ended_at.is_(None)
                )
            ).all()
            self._open_anomalies[twin_id] = {r.metric: r.id for r in open_rows}
            self._engines[twin_id] = engine
            if snapshot is not None:
                self._snapshots[twin_id] = snapshot
            log.info("restored engine for %s by replaying %d observations", twin_id, replayed)

    # --------------------------------------------------------------- baseline
    def recompute_baseline(self, twin_id: str, window: timedelta = BASELINE_WINDOW) -> Baseline:
        """Learn the personal baseline from recent, non-anomalous history."""
        with self._lock, self.db.session_scope() as session:
            twin = session.get(Twin, twin_id)
            if twin is None:
                raise TwinNotFoundError(twin_id)
            end = twin.last_observation_at
            if end is None:
                raise NoBaselineError("no observations to learn a baseline from")
            rows = session.scalars(
                select(ObservationRow)
                .where(
                    ObservationRow.twin_id == twin_id,
                    ObservationRow.timestamp >= end - window,
                    ObservationRow.anomalous_metrics == "",
                )
                .order_by(ObservationRow.timestamp)
            ).all()
            baseline = compute_baseline(
                [row_to_observation(r) for r in rows], twin.subject.age_years, twin.subject.utc_offset_hours
            )
            self._store_baseline(session, twin_id, baseline)
        if twin_id in self._engines:
            self._engines[twin_id].set_baseline(baseline)
        return baseline

    def _store_baseline(self, session: Session, twin_id: str, baseline: Baseline) -> None:
        session.execute(
            update(BaselineRow).where(BaselineRow.twin_id == twin_id).values(is_active=False)
        )
        session.add(BaselineRow(twin_id=twin_id, computed_at=utcnow(), is_active=True, data=baseline.to_dict()))

    def set_initial_baseline(
        self, twin_id: str, observations: Sequence[Observation], age_years: float, utc_offset_hours: float = 0.0
    ) -> Baseline:
        baseline = compute_baseline(observations, age_years, utc_offset_hours)
        with self.db.session_scope() as session:
            self._store_baseline(session, twin_id, baseline)
        return baseline

    # ---------------------------------------------------------------- ingest
    def ingest(
        self,
        twin_id: str,
        item: ObservationIn | Observation,
        received_at: datetime | None = None,
        notify: bool = True,
    ) -> TwinSnapshot:
        """Run one full synchronization cycle for one observation."""
        obs = to_observation(item) if isinstance(item, ObservationIn) else item
        with self._lock:
            engine = self.engine(twin_id)
            snapshot = engine.ingest(obs)  # raises OutOfOrderObservationError
            with self.db.session_scope() as session:
                self._persist(session, twin_id, snapshot, received_at or utcnow())
            self._snapshots[twin_id] = snapshot
        if notify and self._listeners:
            payload = self.state_payload(twin_id)
            for listener in list(self._listeners):
                try:
                    listener(twin_id, payload)
                except Exception:  # a broken client must not break ingestion
                    log.exception("listener failed")
        return snapshot

    def ingest_many(self, twin_id: str, observations: Iterable[Observation]) -> int:
        """Bulk ingestion (history backfill): one transaction, no notifications."""
        count = 0
        with self._lock:
            engine = self.engine(twin_id)
            with self.db.session_scope() as session:
                received = utcnow()
                last = None
                for obs in observations:
                    last = engine.ingest(obs)
                    self._persist(session, twin_id, last, received)
                    count += 1
            if last is not None:
                self._snapshots[twin_id] = last
        return count

    def _persist(self, session: Session, twin_id: str, snap: TwinSnapshot, received_at: datetime) -> None:
        obs = snap.observation
        anomalous = [m for m, a in snap.assessments.items() if a.status == "anomalous"]
        watch = [m for m, a in snap.assessments.items() if a.status == "watch"]
        session.add(
            ObservationRow(
                twin_id=twin_id,
                timestamp=obs.timestamp,
                received_at=received_at,
                source=obs.source,
                heart_rate=obs.heart_rate,
                spo2=obs.spo2,
                temperature=obs.temperature,
                respiratory_rate=obs.respiratory_rate,
                steps=obs.steps,
                activity_intensity=obs.activity_intensity,
                is_asleep=obs.is_asleep,
                state=snap.state.value,
                anomalous_metrics=",".join(anomalous),
                watch_metrics=",".join(watch),
            )
        )
        if snap.transitioned:
            session.add(
                StateTransitionRow(
                    twin_id=twin_id,
                    timestamp=snap.timestamp,
                    from_state=snap.previous_state.value if snap.previous_state else None,
                    to_state=snap.state.value,
                    reason=snap.state_reason,
                )
            )

        open_map = self._open_anomalies.setdefault(twin_id, {})
        for assessment in snap.new_anomalies:
            row = AnomalyEventRow(
                twin_id=twin_id,
                metric=assessment.metric,
                started_at=snap.timestamp,
                value=assessment.value,
                expected=assessment.expected,
                peak_deviation_pct=assessment.deviation_pct,
                reason=assessment.reason or "",
            )
            session.add(row)
            session.flush()
            open_map[assessment.metric] = row.id
        for metric in snap.resolved_anomalies:
            row_id = open_map.pop(metric, None)
            if row_id is not None:
                session.execute(
                    update(AnomalyEventRow).where(AnomalyEventRow.id == row_id).values(ended_at=snap.timestamp)
                )
        for assessment in snap.active_anomalies:
            row_id = open_map.get(assessment.metric)
            if row_id is None:
                continue
            row = session.get(AnomalyEventRow, row_id)
            if row is not None and abs(assessment.deviation_pct) > abs(row.peak_deviation_pct):
                row.peak_deviation_pct = assessment.deviation_pct
                row.value = assessment.value
                row.expected = assessment.expected

        twin = session.get(Twin, twin_id)
        assert twin is not None
        twin.current_state = snap.state.value
        twin.previous_state = snap.previous_state.value if snap.previous_state else None
        twin.state_since = snap.state_since
        twin.state_reason = snap.state_reason
        twin.last_observation_at = obs.timestamp
        twin.last_received_at = received_at
        twin.updated_at = received_at
        twin.observation_count = (twin.observation_count or 0) + 1
        if snap.hr_recovery_bpm is not None:
            twin.last_hr_recovery_bpm = snap.hr_recovery_bpm

    # ------------------------------------------------------------------ state
    def snapshot(self, twin_id: str) -> TwinSnapshot | None:
        self.engine(twin_id)  # ensure restored
        return self._snapshots.get(twin_id)

    def state_payload(self, twin_id: str) -> dict[str, Any]:
        snap = self.snapshot(twin_id)
        if snap is None:
            raise NoBaselineError(f"twin {twin_id} has no observations yet")
        with self.db.session_scope() as session:
            twin = session.get(Twin, twin_id)
            received_at = twin.last_received_at if twin else None
            hrr = twin.last_hr_recovery_bpm if twin else None
        obs = snap.observation
        age = (utcnow() - received_at).total_seconds() if received_at else None
        return {
            "twin_id": twin_id,
            "state": snap.state.value,
            "previous_state": snap.previous_state.value if snap.previous_state else None,
            "state_since": to_utc_iso(snap.state_since),
            "state_reason": snap.state_reason,
            "state_description": STATE_DESCRIPTIONS[snap.state],
            "twin_time": to_utc_iso(snap.timestamp),
            "received_at": to_utc_iso(received_at) if received_at else None,
            "data_age_seconds": round(age, 1) if age is not None else None,
            "observation": {
                "timestamp": to_utc_iso(obs.timestamp),
                "heart_rate": obs.heart_rate,
                "spo2": obs.spo2,
                "temperature": obs.temperature,
                "respiratory_rate": obs.respiratory_rate,
                "steps": obs.steps,
                "activity_intensity": obs.activity_intensity,
                "is_asleep": obs.is_asleep,
                "source": obs.source,
            },
            "assessments": {m: a.to_dict() for m, a in snap.assessments.items()},
            "effective_intensity": snap.effective_intensity,
            "activity_level": activity_level_label(obs.activity_intensity if not obs.is_asleep else 0.0),
            "rolling": snap.rolling,
            "last_hr_recovery_bpm": hrr,
        }
