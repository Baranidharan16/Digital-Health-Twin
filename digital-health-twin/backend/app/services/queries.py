"""Read-side queries: history, events, baseline comparison, wellness, analytics.

Time ranges are anchored on the *twin clock* (the timestamp of the latest
observation), so "last hour" means the last hour of the twin's data. This
keeps the views correct both for live data and for accelerated demo time.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.models import AnomalyEventRow, BaselineRow, ObservationRow, StateTransitionRow, Twin
from backend.app.schemas import to_utc_iso
from backend.app.services.twin_service import TwinNotFoundError, TwinService, row_to_observation, utcnow
from digital_twin.state_engine import STATE_PRIORITY
from digital_twin.types import METRIC_LABELS, METRIC_UNITS, VITAL_METRICS, Baseline, TwinState
from digital_twin.wellness import activity_today, last_sleep, recent_resting_hr, recovery_index

RANGES = {"1h": timedelta(hours=1), "6h": timedelta(hours=6), "24h": timedelta(hours=24), "7d": timedelta(days=7)}
_PRIORITY = {state.value: i for i, state in enumerate(STATE_PRIORITY)}


def _twin(session: Session, twin_id: str) -> Twin:
    twin = session.get(Twin, twin_id)
    if twin is None:
        raise TwinNotFoundError(twin_id)
    return twin


def resolve_range(
    anchor: datetime,
    range_key: str,
    start: datetime | None,
    end: datetime | None,
    utc_offset_hours: float = 0.0,
) -> tuple[datetime, datetime]:
    if range_key == "custom":
        if start is None or end is None or start >= end:
            raise ValueError("custom range needs start < end")
        return start, end
    if range_key == "today":
        offset = timedelta(hours=utc_offset_hours)
        local_midnight = (anchor + offset).replace(hour=0, minute=0, second=0, microsecond=0)
        return local_midnight - offset, anchor
    if range_key not in RANGES:
        raise ValueError(f"range must be one of {sorted(RANGES) + ['today', 'custom']}")
    return anchor - RANGES[range_key], anchor


def _rows(session: Session, twin_id: str, start: datetime, end: datetime) -> list[ObservationRow]:
    return list(
        session.scalars(
            select(ObservationRow)
            .where(ObservationRow.twin_id == twin_id, ObservationRow.timestamp >= start, ObservationRow.timestamp <= end)
            .order_by(ObservationRow.timestamp)
        ).all()
    )


def _worst_state(states: list[str]) -> str:
    return min(states, key=lambda s: _PRIORITY.get(s, 99))


class QueryService:
    def __init__(self, twins: TwinService) -> None:
        self.twins = twins
        self.db = twins.db

    # ---------------------------------------------------------------- history
    def history(
        self,
        twin_id: str,
        range_key: str = "1h",
        start: datetime | None = None,
        end: datetime | None = None,
        max_points: int = 600,
    ) -> dict[str, Any]:
        with self.db.session_scope() as session:
            twin = _twin(session, twin_id)
            anchor = twin.last_observation_at or utcnow()
            start, end = resolve_range(anchor, range_key, start, end, twin.subject.utc_offset_hours)
            rows = _rows(session, twin_id, start, end)
            anomalies = session.scalars(
                select(AnomalyEventRow).where(
                    AnomalyEventRow.twin_id == twin_id,
                    AnomalyEventRow.started_at <= end,
                    or_(AnomalyEventRow.ended_at.is_(None), AnomalyEventRow.ended_at >= start),
                )
            ).all()

        span = max((end - start).total_seconds(), 1.0)
        bucket_s = 0.0
        if len(rows) > max_points:
            bucket_s = math.ceil(span / max_points)
        points = self._bucket(rows, start, bucket_s)

        segments: list[dict[str, Any]] = []
        for row in rows:
            if segments and segments[-1]["state"] == row.state:
                segments[-1]["end"] = to_utc_iso(row.timestamp)
            else:
                segments.append({"state": row.state, "start": to_utc_iso(row.timestamp), "end": to_utc_iso(row.timestamp)})

        markers = [
            {
                "id": a.id,
                "metric": a.metric,
                "start": to_utc_iso(max(a.started_at, start)),
                "end": to_utc_iso(min(a.ended_at, end)) if a.ended_at else to_utc_iso(end),
                "active": a.ended_at is None,
                "reason": a.reason,
            }
            for a in anomalies
        ]
        return {
            "twin_id": twin_id,
            "start": start,
            "end": end,
            "resolution_seconds": bucket_s,
            "raw_points": len(rows),
            "points": points,
            "state_segments": segments,
            "anomaly_markers": markers,
        }

    @staticmethod
    def _bucket(rows: list[ObservationRow], start: datetime, bucket_s: float) -> list[dict[str, Any]]:
        def point(group: list[ObservationRow], t: datetime) -> dict[str, Any]:
            n = len(group)
            anomalous = sorted({m for r in group for m in r.anomalous_metrics.split(",") if m})
            return {
                "t": t,
                "heart_rate": round(sum(r.heart_rate for r in group) / n, 1),
                "spo2": round(sum(r.spo2 for r in group) / n, 2),
                "temperature": round(sum(r.temperature for r in group) / n, 2),
                "respiratory_rate": round(sum(r.respiratory_rate for r in group) / n, 1),
                "steps": sum(r.steps for r in group),
                "activity_intensity": round(sum(r.activity_intensity for r in group) / n, 3),
                "is_asleep": sum(r.is_asleep for r in group) * 2 >= n,
                "state": _worst_state([r.state for r in group]),
                "anomalous": anomalous,
            }

        if bucket_s <= 0:
            return [point([r], r.timestamp) for r in rows]
        buckets: dict[int, list[ObservationRow]] = {}
        for r in rows:
            buckets.setdefault(int((r.timestamp - start).total_seconds() // bucket_s), []).append(r)
        return [point(group, group[-1].timestamp) for _, group in sorted(buckets.items())]

    # ----------------------------------------------------------------- events
    def events(self, twin_id: str, limit: int = 50, kind: str | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        with self.db.session_scope() as session:
            _twin(session, twin_id)
            if kind in (None, "transition"):
                for t in session.scalars(
                    select(StateTransitionRow)
                    .where(StateTransitionRow.twin_id == twin_id)
                    .order_by(StateTransitionRow.timestamp.desc())
                    .limit(limit)
                ):
                    out.append(
                        {
                            "id": t.id,
                            "kind": "transition",
                            "timestamp": t.timestamp,
                            "title": f"{t.from_state or 'START'} → {t.to_state}",
                            "detail": t.reason,
                            "from_state": t.from_state,
                            "to_state": t.to_state,
                        }
                    )
            if kind in (None, "anomaly"):
                for a in session.scalars(
                    select(AnomalyEventRow)
                    .where(AnomalyEventRow.twin_id == twin_id)
                    .order_by(AnomalyEventRow.started_at.desc())
                    .limit(limit)
                ):
                    out.append(
                        {
                            "id": a.id,
                            "kind": "anomaly",
                            "timestamp": a.started_at,
                            "title": f"{METRIC_LABELS.get(a.metric, a.metric)} anomaly flagged",
                            "detail": a.reason,
                            "metric": a.metric,
                            "ended_at": a.ended_at,
                            "active": a.ended_at is None,
                        }
                    )
        out.sort(key=lambda e: (e["timestamp"], e["kind"] == "anomaly"), reverse=True)
        return out[:limit]

    # --------------------------------------------------------------- baseline
    def baseline(self, twin_id: str) -> dict[str, Any]:
        with self.db.session_scope() as session:
            _twin(session, twin_id)
            row = session.scalars(
                select(BaselineRow)
                .where(BaselineRow.twin_id == twin_id, BaselineRow.is_active.is_(True))
                .order_by(BaselineRow.computed_at.desc())
            ).first()
            if row is None:
                raise TwinNotFoundError(f"{twin_id} has no baseline")
            computed_at, data = row.computed_at, row.data
        baseline = Baseline.from_dict(data)
        snap = self.twins.snapshot(twin_id)
        comparison = []
        if snap is not None:
            asleep = snap.observation.is_asleep
            personal = {
                "heart_rate": baseline.hr_sleep if asleep else baseline.hr_rest,
                "respiratory_rate": baseline.rr_sleep if asleep else baseline.rr_rest,
                "spo2": baseline.spo2,
                "temperature": baseline.temp_sleep if asleep else baseline.temp_awake,
            }
            for metric in VITAL_METRICS:
                a = snap.assessments[metric]
                base = personal[metric]
                comparison.append(
                    {
                        "metric": metric,
                        "label": METRIC_LABELS[metric],
                        "unit": METRIC_UNITS[metric],
                        "current": a.value,
                        "rolling_5min": snap.rolling.get(f"{metric}_5min"),
                        "baseline": base,
                        "baseline_context": "asleep" if asleep else "resting",
                        "diff_from_baseline": round(a.value - base, 2),
                        "diff_from_baseline_pct": round(100 * (a.value - base) / base, 1),
                        "expected": a.expected,
                        "expected_low": a.expected_low,
                        "expected_high": a.expected_high,
                        "context": a.context,
                        "status": a.status,
                    }
                )
        return {"twin_id": twin_id, "computed_at": computed_at, "data": data, "comparison": comparison}

    # --------------------------------------------------------------- wellness
    def wellness(self, twin_id: str) -> dict[str, Any]:
        with self.db.session_scope() as session:
            twin = _twin(session, twin_id)
            anchor = twin.last_observation_at
            if anchor is None:
                return {}
            rows = _rows(session, twin_id, anchor - timedelta(hours=36), anchor)
            hrr = twin.last_hr_recovery_bpm
            offset_h = twin.subject.utc_offset_hours
            baseline = self.twins.active_baseline(session, twin_id)
        observations = [row_to_observation(r) for r in rows]
        sleep = last_sleep(observations, baseline)
        activity = activity_today(observations, baseline, offset_h)
        resting = recent_resting_hr(observations)
        snap = self.twins.snapshot(twin_id)
        active_anomaly = bool(snap and snap.active_anomalies)
        return {
            "sleep": sleep.to_dict() if sleep else None,
            "activity": activity.to_dict() if activity else None,
            "resting_hr_recent": resting,
            "resting_hr_baseline": baseline.hr_rest,
            "hr_recovery_1min": hrr,
            "recovery_index": recovery_index(sleep, resting, baseline, active_anomaly),
        }

    # -------------------------------------------------------------- analytics
    def analytics(self, twin_id: str, range_key: str = "7d") -> dict[str, Any]:
        with self.db.session_scope() as session:
            twin = _twin(session, twin_id)
            anchor = twin.last_observation_at or utcnow()
            offset_h = twin.subject.utc_offset_hours
            start, end = resolve_range(anchor, range_key, None, None, offset_h)
            rows = _rows(session, twin_id, start, end)
            anomaly_rows = session.scalars(
                select(AnomalyEventRow).where(AnomalyEventRow.twin_id == twin_id, AnomalyEventRow.started_at >= start)
            ).all()
            transitions = session.scalars(
                select(StateTransitionRow).where(
                    StateTransitionRow.twin_id == twin_id, StateTransitionRow.timestamp >= start
                )
            ).all()
            baseline = self.twins.active_baseline(session, twin_id)
        if not rows:
            return {"twin_id": twin_id, "range": range_key, "empty": True}

        df = pd.DataFrame(
            {
                "t": [r.timestamp for r in rows],
                "heart_rate": [r.heart_rate for r in rows],
                "spo2": [r.spo2 for r in rows],
                "temperature": [r.temperature for r in rows],
                "respiratory_rate": [r.respiratory_rate for r in rows],
                "steps": [r.steps for r in rows],
                "intensity": [r.activity_intensity for r in rows],
                "asleep": [r.is_asleep for r in rows],
                "state": [r.state for r in rows],
                "anomalous": [bool(r.anomalous_metrics) for r in rows],
            }
        )
        df["dt_s"] = df["t"].diff().dt.total_seconds().shift(-1).fillna(0).clip(upper=600)
        hours = (df["t"] - df["t"].iloc[0]).dt.total_seconds() / 3600.0
        resting = (~df["asleep"]) & (df["intensity"] < 0.1)

        metrics = {}
        for metric in VITAL_METRICS:
            series = df[metric]
            rest_series = series[resting]
            slope = None
            if len(rest_series) >= 3 and hours[resting].nunique() > 1:
                slope = float(np.polyfit(hours[resting], rest_series, 1)[0])
            metrics[metric] = {
                "label": METRIC_LABELS[metric],
                "unit": METRIC_UNITS[metric],
                "mean": round(float(series.mean()), 2),
                "min": round(float(series.min()), 2),
                "max": round(float(series.max()), 2),
                "p95": round(float(series.quantile(0.95)), 2),
                "resting_median": round(float(rest_series.median()), 2) if len(rest_series) else None,
                "resting_trend_per_day": round(slope * 24, 3) if slope is not None else None,
            }

        state_minutes = df.groupby("state")["dt_s"].sum().div(60).round(1).to_dict()
        total_minutes = max(sum(state_minutes.values()), 1e-9)
        daily = None
        if range_key == "7d":
            day_groups = df.groupby((df["t"] + pd.Timedelta(hours=offset_h)).dt.date)
            daily = []
            for day, g in day_groups:
                rest_g = g[(~g["asleep"]) & (g["intensity"] < 0.1)]
                sleep_minutes = float(g.loc[g["asleep"], "dt_s"].sum() / 60.0)
                daily.append(
                    {
                        "day": day.isoformat(),
                        "steps": int(g["steps"].sum()),
                        "resting_hr": round(float(rest_g["heart_rate"].median()), 1) if len(rest_g) else None,
                        "active_minutes": round(float(g.loc[g["intensity"] >= 0.2, "dt_s"].sum() / 60.0), 1),
                        "sleep_hours": round(sleep_minutes / 60.0, 2),
                        "anomalous_readings": int(g["anomalous"].sum()),
                    }
                )
        corr = df["heart_rate"].corr(df["intensity"]) if df["intensity"].std() > 0 else None
        return {
            "twin_id": twin_id,
            "range": range_key,
            "start": to_utc_iso(start),
            "end": to_utc_iso(end),
            "observations": len(df),
            "metrics": metrics,
            "time_in_state_minutes": state_minutes,
            "time_in_state_pct": {k: round(100 * v / total_minutes, 1) for k, v in state_minutes.items()},
            "transitions": len(transitions),
            "transition_counts": dict(Counter(f"{t.from_state}→{t.to_state}" for t in transitions).most_common(8)),
            "anomaly_episodes": len(anomaly_rows),
            "anomalies_by_metric": dict(Counter(a.metric for a in anomaly_rows)),
            "hr_intensity_correlation": round(float(corr), 3) if corr is not None and not math.isnan(corr) else None,
            "baseline_hr_rest": baseline.hr_rest,
            "daily": daily,
            "states": [s.value for s in TwinState],
        }
