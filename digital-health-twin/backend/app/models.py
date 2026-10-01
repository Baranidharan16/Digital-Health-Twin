"""ORM models.

Entity overview (see docs/data-model.md for the ER diagram):

* ``subjects``          the (synthetic) person the twin represents; no PII
* ``twins``             the digital twin, holding its *current* state
* ``observations``      every normalized reading + the twin state after it
* ``baselines``         versioned personal baselines (one active per twin)
* ``state_transitions`` every change of twin state, with its reason
* ``anomaly_events``    anomaly episodes per metric (start, end, explanation)
* ``simulation_runs``   saved what-if scenario runs
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    pseudonym: Mapped[str] = mapped_column(String(80))
    age_years: Mapped[float] = mapped_column(Float)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    # Subject's local time zone offset; defines "today" and daily summaries.
    utc_offset_hours: Mapped[float] = mapped_column(Float, default=0.0)
    # Physiology parameters used by the simulator for synthetic subjects only.
    simulation_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    twins: Mapped[list[Twin]] = relationship(back_populates="subject")


class Twin(Base):
    __tablename__ = "twins"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id"))
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    current_state: Mapped[str | None] = mapped_column(String(24), nullable=True)
    previous_state: Mapped[str | None] = mapped_column(String(24), nullable=True)
    state_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    state_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_observation_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_hr_recovery_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    observation_count: Mapped[int] = mapped_column(Integer, default=0)

    subject: Mapped[Subject] = relationship(back_populates="twins")


class ObservationRow(Base):
    __tablename__ = "observations"
    __table_args__ = (UniqueConstraint("twin_id", "timestamp", name="uq_observation_twin_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    twin_id: Mapped[str] = mapped_column(ForeignKey("twins.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(40))

    heart_rate: Mapped[float] = mapped_column(Float)
    spo2: Mapped[float] = mapped_column(Float)
    temperature: Mapped[float] = mapped_column(Float)
    respiratory_rate: Mapped[float] = mapped_column(Float)
    steps: Mapped[int] = mapped_column(Integer, default=0)
    activity_intensity: Mapped[float] = mapped_column(Float, default=0.0)
    is_asleep: Mapped[bool] = mapped_column(Boolean, default=False)

    # Twin state after ingesting this observation (enables state history charts).
    state: Mapped[str] = mapped_column(String(24))
    anomalous_metrics: Mapped[str] = mapped_column(String(120), default="")
    watch_metrics: Mapped[str] = mapped_column(String(120), default="")


class BaselineRow(Base):
    __tablename__ = "baselines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    twin_id: Mapped[str] = mapped_column(ForeignKey("twins.id"), index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    data: Mapped[dict] = mapped_column(JSON)


class StateTransitionRow(Base):
    __tablename__ = "state_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    twin_id: Mapped[str] = mapped_column(ForeignKey("twins.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    from_state: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_state: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(Text)


class AnomalyEventRow(Base):
    __tablename__ = "anomaly_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    twin_id: Mapped[str] = mapped_column(ForeignKey("twins.id"), index=True)
    metric: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    value: Mapped[float] = mapped_column(Float)
    expected: Mapped[float] = mapped_column(Float)
    peak_deviation_pct: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)


class SimulationRunRow(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    twin_id: Mapped[str] = mapped_column(ForeignKey("twins.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    scenario: Mapped[str] = mapped_column(String(40))
    inputs: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[dict] = mapped_column(JSON)
