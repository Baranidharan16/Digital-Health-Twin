"""TwinEngine: the stateful core that keeps a digital twin synchronized.

One engine instance exists per twin. Each call to :meth:`TwinEngine.ingest`
performs the full synchronization cycle for one observation:

1. update the activity context (effective intensity filters);
2. assess every vital against the personal baseline (anomaly layer);
3. derive the candidate state and apply a debounced transition;
4. update rolling features and recovery indicators;
5. return a :class:`TwinSnapshot` describing the new twin state.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from digital_twin.anomaly import AnomalyDetector
from digital_twin.physiology import (
    TEMP_TAU_S,
    first_order_step,
    update_effective_intensity,
    update_lagging_intensity,
)
from digital_twin.state_engine import ACTIVE_STATES, StateMachine, candidate_state
from digital_twin.types import Baseline, Observation, TwinSnapshot, TwinState

MAX_DT_S = 600.0  # cap the time step across data gaps
ROLLING_WINDOW = timedelta(minutes=5)
STEP_WINDOW = timedelta(minutes=10)
HR_RECOVERY_WINDOW_S = 60.0


class OutOfOrderObservationError(ValueError):
    """Raised when an observation is not newer than the previous one."""


class TwinEngine:
    def __init__(self, baseline: Baseline) -> None:
        self.baseline = baseline
        self.detector = AnomalyDetector()
        self.machine = StateMachine()
        self.effective_intensity = 0.0
        self.lagging_intensity = 0.0
        self.slow_intensity = 0.0
        self.last_timestamp: datetime | None = None
        self._window: deque[Observation] = deque()
        self._active_anomalies: set[str] = set()
        self._activity_end: tuple[datetime, float] | None = None
        self.last_hr_recovery_bpm: float | None = None

    # ------------------------------------------------------------------ public
    def set_baseline(self, baseline: Baseline) -> None:
        self.baseline = baseline

    def restore_state(
        self, state: TwinState, since: datetime, reason: str, previous: TwinState | None
    ) -> None:
        self.machine.restore(state, since, reason, previous)

    def ingest(self, obs: Observation) -> TwinSnapshot:
        if self.last_timestamp is not None and obs.timestamp <= self.last_timestamp:
            raise OutOfOrderObservationError(
                f"observation at {obs.timestamp.isoformat()} is not newer than "
                f"{self.last_timestamp.isoformat()}"
            )
        dt_s = 0.0 if self.last_timestamp is None else (obs.timestamp - self.last_timestamp).total_seconds()
        dt_s = min(dt_s, MAX_DT_S)
        self.last_timestamp = obs.timestamp

        # 1. activity context
        if dt_s == 0.0:
            self.effective_intensity = obs.activity_intensity
            self.lagging_intensity = obs.activity_intensity
            self.slow_intensity = obs.activity_intensity
        else:
            self.effective_intensity = update_effective_intensity(
                self.effective_intensity, obs.activity_intensity, dt_s
            )
            self.lagging_intensity = update_lagging_intensity(
                self.lagging_intensity, obs.activity_intensity, dt_s
            )
            self.slow_intensity = first_order_step(
                self.slow_intensity, obs.activity_intensity, dt_s, TEMP_TAU_S
            )

        # 2. anomaly assessment
        assessments = self.detector.assess(
            obs, self.baseline, self.effective_intensity, self.slow_intensity, self.lagging_intensity
        )
        now_anomalous = {m for m, a in assessments.items() if a.status == "anomalous"}
        new_anomalies = [assessments[m] for m in sorted(now_anomalous - self._active_anomalies)]
        resolved = sorted(self._active_anomalies - now_anomalous)
        self._active_anomalies = now_anomalous

        # 3. state
        previous = self.machine.state
        decision = candidate_state(obs, assessments, self.baseline, previous)
        transitioned = self.machine.update(decision, obs.timestamp)

        # 4. rolling features and recovery indicator
        self._window.append(obs)
        while self._window and obs.timestamp - self._window[0].timestamp > STEP_WINDOW:
            self._window.popleft()
        hr_recovery = self._update_hr_recovery(obs, previous, transitioned)

        assert self.machine.state is not None and self.machine.state_since is not None
        return TwinSnapshot(
            timestamp=obs.timestamp,
            state=self.machine.state,
            previous_state=self.machine.previous_state,
            state_since=self.machine.state_since,
            state_reason=self.machine.reason,
            transitioned=transitioned,
            observation=obs,
            assessments=assessments,
            effective_intensity=round(self.effective_intensity, 3),
            rolling=self._rolling(obs.timestamp),
            new_anomalies=new_anomalies,
            resolved_anomalies=resolved,
            hr_recovery_bpm=hr_recovery,
        )

    # ----------------------------------------------------------------- helpers
    def _rolling(self, now: datetime) -> dict[str, float]:
        recent = [o for o in self._window if now - o.timestamp <= ROLLING_WINDOW]
        out: dict[str, float] = {}
        for metric, digits in (("heart_rate", 1), ("respiratory_rate", 1), ("spo2", 2), ("temperature", 2)):
            values = [v for v in (getattr(o, metric) for o in recent) if v is not None]
            if values:
                out[f"{metric}_5min"] = round(sum(values) / len(values), digits)
        out["intensity_5min"] = round(sum(o.activity_intensity for o in recent) / len(recent), 3)
        out["steps_10min"] = float(sum(o.steps for o in self._window))
        return out

    def _update_hr_recovery(
        self, obs: Observation, previous: TwinState | None, transitioned: bool
    ) -> float | None:
        """Heart-rate recovery: HR drop in the first minute after activity stops.

        A faster drop is commonly used in fitness contexts as an indicator of
        good cardiovascular recovery. Here it is reported as a trend feature.
        """
        state = self.machine.state
        if transitioned and previous in ACTIVE_STATES and state not in ACTIVE_STATES:
            # Use the last active reading's heart rate as the starting point.
            last_active = next(
                (o for o in reversed(list(self._window)[:-1]) if o.activity_intensity >= 0.2), None
            )
            if last_active is not None:
                self._activity_end = (last_active.timestamp, last_active.heart_rate)
        if self._activity_end is None:
            return None
        end_ts, end_hr = self._activity_end
        elapsed = (obs.timestamp - end_ts).total_seconds()
        if elapsed < HR_RECOVERY_WINDOW_S:
            return None
        self._activity_end = None
        if elapsed > 2 * HR_RECOVERY_WINDOW_S:
            return None  # data too sparse for a one-minute measurement
        self.last_hr_recovery_bpm = round(end_hr - obs.heart_rate, 1)
        return self.last_hr_recovery_bpm
