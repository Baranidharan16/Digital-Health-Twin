"""Twin endpoints: identity, live state, vitals, history, events, baseline, ingestion."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import asyncio

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select

from backend.app.api.deps import Container, get_container, map_errors
from backend.app.importers import ImportFormatError
from backend.app.ingestion import parse_csv
from backend.app.services.imports import ImportError_, create_twin_from_upload, delete_twin, import_sample
from backend.app.models import Subject, Twin
from backend.app.schemas import (
    BaselineOut,
    CsvIngestResult,
    EventOut,
    HistoryOut,
    IngestResult,
    ObservationIn,
    SubjectOut,
    TwinOut,
    TwinStateOut,
    to_naive_utc,
)
from digital_twin.engine import OutOfOrderObservationError

router = APIRouter(prefix="/api", tags=["twin"])

MAX_CSV_BYTES = 5 * 1024 * 1024
MAX_IMPORT_BYTES = 80 * 1024 * 1024


def _twin_out(twin: Twin, subject: Subject) -> TwinOut:
    return TwinOut(
        id=twin.id,
        name=twin.name,
        subject=SubjectOut.model_validate(subject),
        created_at=twin.created_at,
        updated_at=twin.updated_at,
        current_state=twin.current_state,
        state_since=twin.state_since,
        observation_count=twin.observation_count,
        last_observation_at=twin.last_observation_at,
        last_received_at=twin.last_received_at,
    )


@router.get("/twins", response_model=list[TwinOut], summary="List digital twins")
def list_twins(c: Container = Depends(get_container)) -> list[TwinOut]:
    with c.db.session_scope() as session:
        return [_twin_out(t, t.subject) for t in session.scalars(select(Twin)).all()]


@router.post(
    "/twins/import",
    tags=["ingestion"],
    summary="Create a personal twin from real wearable exports (Fitbit, Samsung Health, Google Fit, generic CSV)",
)
async def import_twin(
    files: list[UploadFile] = File(..., description="One or more CSV exports"),
    display_name: str = Form("My twin", max_length=60, description="A nickname; avoid your real name"),
    age_years: float = Form(30, ge=10, le=100),
    utc_offset_hours: float = Form(0, ge=-12, le=14, description="Time zone of the device clock"),
    data_source: str = Form("Wearable export", max_length=80),
    c: Container = Depends(get_container),
) -> dict[str, Any]:
    uploads, total = [], 0
    for f in files:
        raw = await f.read(MAX_IMPORT_BYTES + 1)
        total += len(raw)
        if total > MAX_IMPORT_BYTES:
            raise HTTPException(413, "uploads larger than 80 MB in total")
        uploads.append((f.filename or "upload.csv", raw))
    try:
        return await asyncio.to_thread(
            create_twin_from_upload, c.twins, uploads, display_name, age_years, utc_offset_hours, data_source
        )
    except (ImportFormatError, ImportError_) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/twins/import-sample", tags=["ingestion"], summary="Load the bundled real Fitbit sample (CC0) as a twin")
async def import_sample_twin(c: Container = Depends(get_container)) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(import_sample, c.twins)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/twin/{twin_id}", summary="Permanently delete a twin and all of its data")
def remove_twin(twin_id: str, c: Container = Depends(get_container)) -> dict[str, Any]:
    try:
        delete_twin(c.twins, twin_id)
    except Exception as exc:
        raise map_errors(exc) from exc
    return {"deleted": twin_id}


@router.get("/twin/{twin_id}", response_model=TwinOut, summary="Twin identity and summary")
def get_twin(twin_id: str, c: Container = Depends(get_container)) -> TwinOut:
    with c.db.session_scope() as session:
        twin = session.get(Twin, twin_id)
        if twin is None:
            raise HTTPException(404, f"twin {twin_id} not found")
        return _twin_out(twin, twin.subject)


@router.get("/twin/{twin_id}/state", response_model=TwinStateOut, summary="Current twin state with explanations")
def get_state(twin_id: str, c: Container = Depends(get_container)) -> dict[str, Any]:
    try:
        return c.twins.state_payload(twin_id)
    except Exception as exc:
        raise map_errors(exc) from exc


@router.get("/twin/{twin_id}/vitals", summary="Latest vitals with expected values and status")
def get_vitals(twin_id: str, c: Container = Depends(get_container)) -> dict[str, Any]:
    try:
        payload = c.twins.state_payload(twin_id)
    except Exception as exc:
        raise map_errors(exc) from exc
    return {
        "twin_id": twin_id,
        "timestamp": payload["observation"]["timestamp"],
        "vitals": {
            metric: {
                "value": a["value"],
                "expected": a["expected"],
                "status": a["status"],
                "reason": a["reason"],
            }
            for metric, a in payload["assessments"].items()
        },
        "activity": {
            "steps": payload["observation"]["steps"],
            "intensity": payload["observation"]["activity_intensity"],
            "level": payload["activity_level"],
            "is_asleep": payload["observation"]["is_asleep"],
        },
    }


@router.get("/twin/{twin_id}/history", response_model=HistoryOut, summary="Time series with state and anomaly overlays")
def get_history(
    twin_id: str,
    range: Literal["1h", "6h", "24h", "today", "7d", "custom"] = "1h",
    start: datetime | None = None,
    end: datetime | None = None,
    max_points: int = Query(600, ge=10, le=5000),
    c: Container = Depends(get_container),
) -> dict[str, Any]:
    try:
        return c.queries.history(
            twin_id,
            range,
            to_naive_utc(start) if start else None,
            to_naive_utc(end) if end else None,
            max_points,
        )
    except Exception as exc:
        raise map_errors(exc) from exc


@router.get("/twin/{twin_id}/events", response_model=list[EventOut], summary="State transitions and anomaly episodes")
def get_events(
    twin_id: str,
    limit: int = Query(50, ge=1, le=500),
    kind: Literal["transition", "anomaly"] | None = None,
    c: Container = Depends(get_container),
) -> list[dict[str, Any]]:
    try:
        return c.queries.events(twin_id, limit, kind)
    except Exception as exc:
        raise map_errors(exc) from exc


@router.get("/twin/{twin_id}/baseline", response_model=BaselineOut, summary="Personal baseline and current comparison")
def get_baseline(twin_id: str, c: Container = Depends(get_container)) -> dict[str, Any]:
    try:
        return c.queries.baseline(twin_id)
    except Exception as exc:
        raise map_errors(exc) from exc


@router.post("/twin/{twin_id}/baseline/recompute", summary="Re-learn the personal baseline from recent history")
def recompute_baseline(twin_id: str, c: Container = Depends(get_container)) -> dict[str, Any]:
    try:
        baseline = c.twins.recompute_baseline(twin_id)
    except Exception as exc:
        raise map_errors(exc) from exc
    return {"twin_id": twin_id, "baseline": baseline.to_dict()}


@router.get("/twin/{twin_id}/wellness", summary="Sleep, activity and recovery summaries (heuristic)")
def get_wellness(twin_id: str, c: Container = Depends(get_container)) -> dict[str, Any]:
    try:
        return c.queries.wellness(twin_id)
    except Exception as exc:
        raise map_errors(exc) from exc


@router.get("/twin/{twin_id}/analytics", summary="Aggregate analytics over a time range")
def get_analytics(
    twin_id: str,
    range: Literal["1h", "6h", "24h", "today", "7d"] = "7d",
    c: Container = Depends(get_container),
) -> dict[str, Any]:
    try:
        return c.queries.analytics(twin_id, range)
    except Exception as exc:
        raise map_errors(exc) from exc


@router.post(
    "/twin/{twin_id}/observations",
    response_model=IngestResult,
    tags=["ingestion"],
    summary="Ingest one normalized observation (wearable/API adapter)",
)
def ingest_observation(twin_id: str, body: ObservationIn, c: Container = Depends(get_container)) -> IngestResult:
    try:
        snap = c.twins.ingest(twin_id, body)
    except OutOfOrderObservationError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise map_errors(exc) from exc
    return IngestResult(
        accepted=True,
        state=snap.state,
        transitioned=snap.transitioned,
        new_anomalies=[a.metric for a in snap.new_anomalies],
    )


@router.post(
    "/twin/{twin_id}/observations/csv",
    response_model=CsvIngestResult,
    tags=["ingestion"],
    summary="Ingest a CSV file (CSV adapter; aliases and unit conversion supported)",
)
async def ingest_csv(twin_id: str, file: UploadFile = File(...), c: Container = Depends(get_container)) -> CsvIngestResult:
    content = await file.read(MAX_CSV_BYTES + 1)
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(413, "CSV larger than 5 MB")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "CSV must be UTF-8") from exc
    accepted, rejected, errors = 0, 0, []
    for line_no, item, error in parse_csv(text):
        if item is None:
            rejected += 1
            errors.append(f"line {line_no}: {error}")
            continue
        try:
            c.twins.ingest(twin_id, item)
            accepted += 1
        except OutOfOrderObservationError as exc:
            rejected += 1
            errors.append(f"line {line_no}: {exc}")
        except Exception as exc:
            raise map_errors(exc) from exc
    return CsvIngestResult(accepted=accepted, rejected=rejected, errors=errors[:50])
