"""Reproducible synthetic physiological data generator."""

from simulator.generator import (
    ActivityInput,
    PhysiologySimulator,
    SubjectProfile,
    generate_history,
)
from simulator.scenarios import SCENARIOS, GUIDED_DEMO, ScenarioRunner

__all__ = [
    "ActivityInput",
    "GUIDED_DEMO",
    "PhysiologySimulator",
    "SCENARIOS",
    "ScenarioRunner",
    "SubjectProfile",
    "generate_history",
]
