"""Deterministic Digital Twin state engine.

The state engine converts the current reading, its anomaly assessment and
the activity context into one of a small set of descriptive states. These
states describe *what the data shows*; they are not medical diagnoses.

Rules are evaluated in priority order; the first that matches is the
*candidate* state:

1. ANOMALOUS     any vital has a persistent, confirmed anomaly flag
2. ELEVATED      any vital is unusual but not yet persistent ("watch")
3. SLEEPING      the source reports the subject asleep
4. HIGH_ACTIVITY movement intensity >= 0.55 (jogging/running level)
5. ACTIVE        movement intensity >= 0.20 (walking level)
6. RECOVERY      activity has just stopped and heart rate is still more than
                 10% above the resting baseline
7. STABLE        none of the above

To avoid flicker, the twin only moves to a new non-anomalous candidate after
it has been the candidate for ``CONFIRM_READINGS`` consecutive readings.
ANOMALOUS is entered immediately because the anomaly layer has already
required persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from digital_twin.types import Baseline, MetricAssessment, Observation, TwinState

HIGH_ACTIVITY_INTENSITY = 0.55
ACTIVE_INTENSITY = 0.20
RECOVERY_HR_MARGIN = 0.10  # fraction above resting baseline
CONFIRM_READINGS = 2

STATE_PRIORITY: tuple[TwinState, ...] = (
    TwinState.ANOMALOUS,
    TwinState.ELEVATED,
    TwinState.SLEEPING,
    TwinState.HIGH_ACTIVITY,
    TwinState.ACTIVE,
    TwinState.RECOVERY,
    TwinState.STABLE,
)

STATE_DESCRIPTIONS: dict[TwinState, str] = {
    TwinState.STABLE: "Vitals are close to the subject's personal baseline for their current activity.",
    TwinState.ACTIVE: "Walking-level movement with vitals rising as expected.",
    TwinState.HIGH_ACTIVITY: "Vigorous movement; elevated heart and breathing rates are expected.",
    TwinState.RECOVERY: "Activity has stopped and vitals are returning towards baseline.",
    TwinState.SLEEPING: "The source reports sleep; vitals are compared with the sleeping baseline.",
    TwinState.ELEVATED: "One or more vitals are unusual for this subject but not yet persistent.",
    TwinState.ANOMALOUS: "One or more vitals have deviated persistently from what is expected for this subject.",
}

ACTIVE_STATES = {TwinState.HIGH_ACTIVITY, TwinState.ACTIVE}


@dataclass
class StateDecision:
    state: TwinState
    reason: str


def candidate_state(
    obs: Observation,
    assessments: dict[str, MetricAssessment],
    baseline: Baseline,
    current_state: TwinState | None,
) -> StateDecision:
    anomalous = [a for a in assessments.values() if a.status == "anomalous"]
    if anomalous:
        return StateDecision(TwinState.ANOMALOUS, " ".join(a.reason or "" for a in anomalous).strip())

    watch = [a for a in assessments.values() if a.status == "watch"]
    if watch:
        return StateDecision(
            TwinState.ELEVATED, "Watch: " + " ".join(a.reason or "" for a in watch).strip()
        )

    if obs.is_asleep:
        return StateDecision(
            TwinState.SLEEPING,
            f"Source reports sleep; heart rate {obs.heart_rate:.0f} bpm vs sleeping baseline "
            f"{baseline.hr_sleep:.0f} bpm.",
        )

    intensity = obs.activity_intensity
    if intensity >= HIGH_ACTIVITY_INTENSITY:
        return StateDecision(
            TwinState.HIGH_ACTIVITY,
            f"Movement intensity {intensity:.2f} (running level) with heart rate "
            f"{obs.heart_rate:.0f} bpm, consistent with vigorous activity.",
        )
    if intensity >= ACTIVE_INTENSITY:
        return StateDecision(
            TwinState.ACTIVE,
            f"Movement intensity {intensity:.2f} (walking level); heart rate "
            f"{obs.heart_rate:.0f} bpm.",
        )

    hr_margin = (obs.heart_rate - baseline.hr_rest) / baseline.hr_rest
    recently_active = current_state in ACTIVE_STATES or current_state == TwinState.RECOVERY
    if recently_active and hr_margin > RECOVERY_HR_MARGIN:
        return StateDecision(
            TwinState.RECOVERY,
            f"Activity stopped; heart rate {obs.heart_rate:.0f} bpm is still "
            f"{100 * hr_margin:.0f}% above resting baseline {baseline.hr_rest:.0f} bpm and returning.",
        )

    return StateDecision(
        TwinState.STABLE,
        f"Vitals within personal baseline (heart rate {obs.heart_rate:.0f} bpm vs resting "
        f"baseline {baseline.hr_rest:.0f} bpm).",
    )


class StateMachine:
    """Holds the current state and applies debounced transitions."""

    def __init__(self) -> None:
        self.state: TwinState | None = None
        self.previous_state: TwinState | None = None
        self.state_since: datetime | None = None
        self.reason: str = ""
        self._pending: TwinState | None = None
        self._pending_count = 0

    def restore(self, state: TwinState, since: datetime, reason: str, previous: TwinState | None) -> None:
        self.state, self.state_since, self.reason, self.previous_state = state, since, reason, previous
        self._pending, self._pending_count = None, 0

    def update(self, decision: StateDecision, timestamp: datetime) -> bool:
        """Apply a candidate decision. Returns True if a transition happened."""
        if self.state is None:
            self.state, self.state_since, self.reason = decision.state, timestamp, decision.reason
            return True

        if decision.state == self.state:
            self._pending, self._pending_count = None, 0
            self.reason = decision.reason  # keep the explanation current
            return False

        if decision.state == self._pending:
            self._pending_count += 1
        else:
            self._pending, self._pending_count = decision.state, 1

        required = 1 if decision.state == TwinState.ANOMALOUS else CONFIRM_READINGS
        if self._pending_count >= required:
            self.previous_state = self.state
            self.state, self.state_since, self.reason = decision.state, timestamp, decision.reason
            self._pending, self._pending_count = None, 0
            return True
        return False
