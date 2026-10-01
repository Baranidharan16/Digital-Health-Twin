"""Create a personal digital twin from uploaded real wearable data.

Flow (same lifecycle as the demo twin, but with real readings):

    files -> importers.import_files (parse, merge, resample, local->UTC)
          -> new Subject + Twin (pseudonymous; no names or device IDs stored)
          -> initial baseline from the data -> replay every reading through the
             twin engine (states, anomaly episodes) -> re-learn baseline
             excluding flagged readings
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from sqlalchemy import delete

from backend.app.config import REPO_ROOT
from backend.app.importers import ImportResult, import_files
from backend.app.models import (
    AnomalyEventRow,
    DeviceRow,
    BaselineRow,
    ObservationRow,
    SimulationRunRow,
    StateTransitionRow,
    Subject,
    Twin,
)
from backend.app.services.seed import DEFAULT_SUBJECT_ID, DEFAULT_TWIN_ID
from backend.app.services.twin_service import TwinNotFoundError, TwinService, utcnow
from digital_twin.baseline import InsufficientHistoryError

log = logging.getLogger(__name__)

SAMPLE_DIR = REPO_ROOT / "data" / "sample_real" / "fitbit_user_5553957443"
SAMPLE_TWIN_ID = "twin-fitbit-sample"
SAMPLE_OFFSET_HOURS = -5.0  # participants' local clock; US Eastern assumed for display


class ImportError_(ValueError):
    pass


def _summary(result: ImportResult, twin_id: str, replayed: int) -> dict:
    return {
        "twin_id": twin_id,
        "observations": replayed,
        "interval_seconds": result.interval_s,
        "start": result.start.isoformat() + "Z",
        "end": result.end.isoformat() + "Z",
        "metrics_measured": result.metrics,
        "sleep_minutes": result.sleep_minutes,
        "intensity_estimated": result.intensity_estimated,
        "files": result.files,
        "notes": result.notes,
    }


def create_twin_from_upload(
    service: TwinService,
    uploads: list[tuple[str, bytes]],
    display_name: str,
    age_years: float,
    utc_offset_hours: float,
    data_source: str,
    twin_id: str | None = None,
) -> dict:
    slug = re.sub(r"[^a-z0-9]+", "-", data_source.lower()).strip("-")[:40] or "upload"
    result = import_files(uploads, utc_offset_hours, source=slug)
    if len(result.observations) < 60:
        raise ImportError_("need at least an hour of heart-rate readings to learn a personal baseline")

    twin_id = twin_id or f"twin-{uuid.uuid4().hex[:8]}"
    subject_id = f"subj-{twin_id.removeprefix('twin-')}"
    now = utcnow()
    with service.db.session_scope() as session:
        session.add(
            Subject(
                id=subject_id,
                pseudonym=display_name.strip()[:60] or "My twin",
                age_years=age_years,
                is_synthetic=False,
                utc_offset_hours=utc_offset_hours,
                data_source=data_source[:80],
                created_at=now,
            )
        )
        session.add(
            Twin(id=twin_id, subject_id=subject_id, name=f"Health Twin · {display_name.strip()[:60] or 'My twin'}",
                 created_at=now, updated_at=now, observation_count=0)
        )
    try:
        service.set_initial_baseline(twin_id, result.observations, age_years, utc_offset_hours)
        replayed = service.ingest_many(twin_id, result.observations)
        service.recompute_baseline(twin_id)
    except InsufficientHistoryError as exc:
        delete_twin(service, twin_id)
        raise ImportError_(
            f"not enough resting readings to learn a baseline ({exc}). Upload a longer period that includes rest."
        ) from exc
    except Exception:
        delete_twin(service, twin_id)
        raise
    log.info("created %s from %d uploaded readings", twin_id, replayed)
    return _summary(result, twin_id, replayed)


def import_sample(service: TwinService) -> dict:
    """Load the bundled real Fitbit sample (CC0) as its own twin, replacing any previous copy."""
    if not SAMPLE_DIR.is_dir():
        raise FileNotFoundError(f"sample data not found at {SAMPLE_DIR}")
    try:
        delete_twin(service, SAMPLE_TWIN_ID)
    except TwinNotFoundError:
        pass
    uploads = [(p.name, p.read_bytes()) for p in sorted(Path(SAMPLE_DIR).glob("*.csv"))]
    return create_twin_from_upload(
        service, uploads, "Fitbit user 5553957443 (public dataset)", 30.0, SAMPLE_OFFSET_HOURS,
        "Fitbit export (real, CC0 dataset)", twin_id=SAMPLE_TWIN_ID,
    )


def delete_twin(service: TwinService, twin_id: str) -> None:
    """Permanently delete a twin and all its data (right to erasure)."""
    if twin_id == DEFAULT_TWIN_ID:
        raise ValueError("the demo twin cannot be deleted; use demo reset instead")
    with service.db.session_scope() as session:
        twin = session.get(Twin, twin_id)
        if twin is None:
            raise TwinNotFoundError(twin_id)
        subject_id = twin.subject_id
        for model in (ObservationRow, BaselineRow, StateTransitionRow, AnomalyEventRow, SimulationRunRow, DeviceRow):
            session.execute(delete(model).where(model.twin_id == twin_id))
        session.delete(twin)
        session.flush()
        if subject_id != DEFAULT_SUBJECT_ID:
            subject = session.get(Subject, subject_id)
            if subject is not None:
                session.delete(subject)
    service.forget(twin_id)
