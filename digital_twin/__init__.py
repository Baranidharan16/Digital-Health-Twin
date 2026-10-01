"""Core Digital Twin engine.

This package is deliberately free of web-framework and database code.
It contains the deterministic logic that turns a stream of normalized
observations into an evolving twin state:

    observation -> features -> anomaly assessment -> state engine -> snapshot

Because it is pure Python, every rule here is unit-testable in isolation and
the same engine is reused by the live pipeline, the history backfill and the
what-if scenario simulator.
"""

from digital_twin.types import (
    Baseline,
    MetricAssessment,
    Observation,
    TwinSnapshot,
    TwinState,
)
from digital_twin.engine import TwinEngine

__all__ = [
    "Baseline",
    "MetricAssessment",
    "Observation",
    "TwinEngine",
    "TwinSnapshot",
    "TwinState",
]
