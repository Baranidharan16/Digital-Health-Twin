"""Pydantic request/response schemas (these also generate the OpenAPI docs)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator

from digital_twin.types import TwinState


def to_utc_iso(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat(timespec="seconds") + "Z"


# All datetimes are stored as naive UTC and serialized with an explicit "Z".
UTCDateTime = Annotated[datetime, PlainSerializer(to_utc_iso, return_type=str)]


def to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


# ---------------------------------------------------------------- ingestion
class ObservationIn(BaseModel):
    """Normalized observation accepted by the ingestion layer.

    Ranges reject physically implausible readings (sensor faults), not
    unusual-but-possible values, which are the anomaly layer's job.
    """

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    heart_rate: float = Field(ge=25, le=230, description="beats per minute")
    spo2: float | None = Field(default=None, ge=50, le=100, description="peripheral oxygen saturation, % (optional)")
    temperature: float | None = Field(default=None, ge=30, le=43, description="°C (optional)")
    respiratory_rate: float | None = Field(default=None, ge=3, le=70, description="breaths per minute (optional)")
    steps: int = Field(default=0, ge=0, le=2000, description="steps since previous reading")
    activity_intensity: float = Field(default=0.0, ge=0, le=1, description="normalized movement intensity 0–1")
    is_asleep: bool = False
    source: str = Field(default="api", max_length=40, pattern=r"^[A-Za-z0-9_.\-]+$")

    @field_validator("timestamp")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return to_naive_utc(value)


class IngestResult(BaseModel):
    accepted: bool
    state: TwinState
    transitioned: bool
    new_anomalies: list[str]


class CsvIngestResult(BaseModel):
    accepted: int
    rejected: int
    errors: list[str]


# ------------------------------------------------------------------ outputs
class MetricAssessmentOut(BaseModel):
    metric: str
    value: float
    expected: float
    expected_low: float
    expected_high: float
    deviation: float
    deviation_pct: float
    robust_z: float
    status: Literal["normal", "watch", "anomalous"]
    consecutive: int
    context: str
    reason: str | None = None
    reference_flag: str | None = None


class ObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: UTCDateTime
    heart_rate: float
    spo2: float | None
    temperature: float | None
    respiratory_rate: float | None
    steps: int
    activity_intensity: float
    is_asleep: bool
    source: str


class SubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pseudonym: str
    age_years: float
    is_synthetic: bool
    utc_offset_hours: float
    data_source: str | None = None


class TwinOut(BaseModel):
    id: str
    name: str
    subject: SubjectOut
    created_at: UTCDateTime
    updated_at: UTCDateTime
    current_state: TwinState | None
    state_since: UTCDateTime | None
    observation_count: int
    last_observation_at: UTCDateTime | None
    last_received_at: UTCDateTime | None


class TwinStateOut(BaseModel):
    twin_id: str
    state: TwinState
    previous_state: TwinState | None
    state_since: UTCDateTime
    state_reason: str
    state_description: str
    twin_time: UTCDateTime
    received_at: UTCDateTime | None
    data_age_seconds: float | None = Field(description="seconds since the last reading was received")
    observation: ObservationOut
    assessments: dict[str, MetricAssessmentOut]
    effective_intensity: float
    activity_level: str
    rolling: dict[str, float]
    last_hr_recovery_bpm: float | None


class EventOut(BaseModel):
    id: int
    kind: Literal["transition", "anomaly"]
    timestamp: UTCDateTime
    title: str
    detail: str
    from_state: str | None = None
    to_state: str | None = None
    metric: str | None = None
    ended_at: UTCDateTime | None = None
    active: bool | None = None


class HistoryPoint(BaseModel):
    t: UTCDateTime
    heart_rate: float
    spo2: float | None
    temperature: float | None
    respiratory_rate: float | None
    steps: int
    activity_intensity: float
    is_asleep: bool
    state: str
    anomalous: list[str]


class HistoryOut(BaseModel):
    twin_id: str
    start: UTCDateTime
    end: UTCDateTime
    resolution_seconds: float
    raw_points: int
    points: list[HistoryPoint]
    state_segments: list[dict[str, Any]]
    anomaly_markers: list[dict[str, Any]]


class BaselineOut(BaseModel):
    twin_id: str
    computed_at: UTCDateTime
    data: dict[str, Any]
    comparison: list[dict[str, Any]]


# --------------------------------------------------------------- simulation
class ExerciseScenarioIn(BaseModel):
    scenario: Literal["exercise"] = "exercise"
    twin_id: str
    intensity: float = Field(0.7, ge=0.1, le=1.0)
    duration_min: float = Field(30, ge=2, le=120)
    prior_sleep_hours: float | None = Field(None, ge=2, le=12)
    recovery_min: float = Field(20, ge=5, le=60)


class SleepScenarioIn(BaseModel):
    scenario: Literal["sleep_restriction"] = "sleep_restriction"
    twin_id: str
    sleep_hours: float = Field(5.0, ge=2, le=12)
    nights: int = Field(3, ge=1, le=7)


ScenarioIn = Annotated[ExerciseScenarioIn | SleepScenarioIn, Field(discriminator="scenario")]


class LiveStartIn(BaseModel):
    twin_id: str = "twin-001"
    scenario: str = "NORMAL"
    guided: bool = False
    mode: Literal["simulator", "replay"] = "simulator"


class LiveScenarioIn(BaseModel):
    scenario: str
