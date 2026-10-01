"""Seed the database with one synthetic subject, its twin and 7 days of history.

No real person is represented. The subject has a pseudonym, an age and
simulator physiology parameters only.
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from sqlalchemy import select

from backend.app.config import Settings
from backend.app.models import Subject, Twin
from backend.app.services.twin_service import TwinService, utcnow
from simulator.generator import SubjectProfile, generate_history

log = logging.getLogger(__name__)

DEFAULT_SUBJECT_ID = "subj-001"
DEFAULT_TWIN_ID = "twin-001"
DEFAULT_PROFILE = SubjectProfile()


def seed_database(service: TwinService, settings: Settings) -> bool:
    """Create the demo subject/twin with history if missing. Returns True if seeded."""
    with service.db.session_scope() as session:
        if session.scalars(select(Twin).where(Twin.id == DEFAULT_TWIN_ID)).first() is not None:
            return False
        now = utcnow()
        session.add(
            Subject(
                id=DEFAULT_SUBJECT_ID,
                pseudonym="Synthetic Subject A",
                age_years=DEFAULT_PROFILE.age_years,
                is_synthetic=True,
                utc_offset_hours=DEFAULT_PROFILE.utc_offset_hours,
                simulation_profile=asdict(DEFAULT_PROFILE),
                created_at=now,
            )
        )
        session.add(
            Twin(
                id=DEFAULT_TWIN_ID,
                subject_id=DEFAULT_SUBJECT_ID,
                name="Health Twin · Subject A",
                created_at=now,
                updated_at=now,
                observation_count=0,
            )
        )

    end = utcnow().replace(second=0, microsecond=0)
    history = generate_history(
        DEFAULT_PROFILE,
        end=end,
        days=settings.history_days,
        interval_s=settings.history_interval_s,
        seed=settings.history_seed,
    )
    # Bootstrap: learn an initial baseline from the raw history, replay the
    # history through the twin, then re-learn the baseline excluding readings
    # the twin flagged as anomalous.
    service.set_initial_baseline(
        DEFAULT_TWIN_ID, history, DEFAULT_PROFILE.age_years, DEFAULT_PROFILE.utc_offset_hours
    )
    count = service.ingest_many(DEFAULT_TWIN_ID, history)
    service.recompute_baseline(DEFAULT_TWIN_ID)
    log.info("seeded %s with %d historical observations", DEFAULT_TWIN_ID, count)
    return True


def reset_and_seed(service: TwinService, settings: Settings) -> None:
    service.reset()
    service.db.drop_all()
    service.db.create_all()
    seed_database(service, settings)
