"""Named live-demo scenarios and a deterministic guided demo sequence.

Each scenario maps elapsed scenario time (seconds of *twin time*) to an
:class:`ActivityInput`. The live runner steps the simulator forward and emits
one observation per tick.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from digital_twin.types import Observation
from simulator.generator import ActivityInput, PhysiologySimulator


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    description: str
    activity: Callable[[float], ActivityInput]


def _normal(t: float) -> ActivityInput:
    # Seated with a small fidget every 90 s.
    return ActivityInput(intensity=0.12 if (t % 90.0) < 15.0 else 0.04)


def _exercise(t: float) -> ActivityInput:
    return ActivityInput(intensity=0.38 if t < 45.0 else 0.8)


def _recovery(t: float) -> ActivityInput:
    return ActivityInput(intensity=0.02)


def _anomaly(t: float) -> ActivityInput:
    return ActivityInput(intensity=0.03, anomaly=True)


def _sleep(t: float) -> ActivityInput:
    return ActivityInput(asleep=True)


SCENARIOS: dict[str, Scenario] = {
    s.key: s
    for s in (
        Scenario("NORMAL", "Normal", "Seated, everyday activity. Vitals near personal baseline.", _normal),
        Scenario("EXERCISE", "Exercise", "45 s brisk-walk warm-up, then running.", _exercise),
        Scenario("RECOVERY", "Recovery", "Activity stops; vitals return towards baseline.", _recovery),
        Scenario(
            "ANOMALY",
            "Anomaly",
            "At rest, but heart rate, temperature and breathing rise and SpO₂ dips — "
            "a pattern not explained by activity.",
            _anomaly,
        ),
        Scenario("SLEEP", "Sleep", "Asleep; vitals compared with the sleeping baseline.", _sleep),
    )
}

# Guided demo: (scenario key, twin-time duration in seconds). With the default
# 15 s of twin time per tick this runs in roughly 70 ticks.
GUIDED_DEMO: list[tuple[str, float]] = [
    ("NORMAL", 120.0),
    ("EXERCISE", 300.0),
    ("RECOVERY", 300.0),
    ("ANOMALY", 390.0),
]


class ScenarioRunner:
    """Steps a :class:`PhysiologySimulator` through scenarios, one tick at a time."""

    def __init__(self, simulator: PhysiologySimulator, scenario: str = "NORMAL") -> None:
        self.simulator = simulator
        self.scenario = SCENARIOS[scenario]
        self.elapsed_s = 0.0
        self.guided_index: int | None = None
        self.guided_elapsed_s = 0.0

    def set_scenario(self, key: str) -> None:
        if key not in SCENARIOS:
            raise KeyError(f"unknown scenario {key!r}; choose one of {sorted(SCENARIOS)}")
        self.scenario = SCENARIOS[key]
        self.elapsed_s = 0.0
        self.guided_index = None

    def start_guided(self) -> None:
        self.set_scenario(GUIDED_DEMO[0][0])
        self.guided_index = 0
        self.guided_elapsed_s = 0.0

    @property
    def guided_step(self) -> str | None:
        if self.guided_index is None:
            return None
        return f"{self.guided_index + 1}/{len(GUIDED_DEMO)}"

    def next(self, dt_s: float, source: str = "simulator") -> Observation:
        if self.guided_index is not None:
            key, duration = GUIDED_DEMO[self.guided_index]
            if self.guided_elapsed_s >= duration and self.guided_index + 1 < len(GUIDED_DEMO):
                self.guided_index += 1
                self.guided_elapsed_s = 0.0
                self.scenario = SCENARIOS[GUIDED_DEMO[self.guided_index][0]]
                self.elapsed_s = 0.0
        activity = self.scenario.activity(self.elapsed_s)
        obs = self.simulator.step(dt_s, activity, source=source)
        self.elapsed_s += dt_s
        self.guided_elapsed_s += dt_s
        return obs
