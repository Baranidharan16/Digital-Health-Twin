"""Live demo runner: feeds observations into the twin at a fixed tick.

Two data sources are supported, both entering through the same ingestion
path as any external device:

* ``simulator``: the physiology simulator driven by a named scenario
  (NORMAL, EXERCISE, RECOVERY, ANOMALY, SLEEP) or the guided demo sequence;
* ``replay``: a pre-recorded session (the backup demo).

Demo time is accelerated: every real ``tick_seconds`` the twin clock advances
``twin_seconds_per_tick`` (default 15 s per 1 s), so exercise, recovery and an
anomaly unfold within a few minutes of presentation time.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.config import Settings
from backend.app.ingestion import ReplaySource
from backend.app.models import ObservationRow, Subject, Twin
from backend.app.services.twin_service import TwinService, utcnow
from digital_twin.engine import OutOfOrderObservationError
from simulator.generator import PhysiologySimulator, SubjectProfile
from simulator.scenarios import GUIDED_DEMO, SCENARIOS, ScenarioRunner

log = logging.getLogger(__name__)

MAX_CONSECUTIVE_ERRORS = 5


@dataclass
class LiveStatus:
    running: bool = False
    twin_id: str | None = None
    mode: str = "simulator"
    scenario: str | None = None
    guided: bool = False
    guided_step: str | None = None
    ticks: int = 0
    started_at: datetime | None = None
    last_error: str | None = None
    tick_seconds: float = 1.0
    twin_seconds_per_tick: float = 15.0
    scenarios: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "twin_id": self.twin_id,
            "mode": self.mode,
            "scenario": self.scenario,
            "guided": self.guided,
            "guided_step": self.guided_step,
            "guided_sequence": [{"scenario": k, "twin_seconds": d} for k, d in GUIDED_DEMO],
            "ticks": self.ticks,
            "started_at": self.started_at.isoformat() + "Z" if self.started_at else None,
            "last_error": self.last_error,
            "tick_seconds": self.tick_seconds,
            "twin_seconds_per_tick": self.twin_seconds_per_tick,
            "time_acceleration": round(self.twin_seconds_per_tick / self.tick_seconds, 1),
            "scenarios": self.scenarios,
        }


class LiveRunner:
    def __init__(self, service: TwinService, settings: Settings, on_status=None) -> None:
        self.service = service
        self.settings = settings
        self.on_status = on_status
        self.status = LiveStatus(
            tick_seconds=settings.tick_seconds,
            twin_seconds_per_tick=settings.twin_seconds_per_tick,
            scenarios=[{"key": s.key, "label": s.label, "description": s.description} for s in SCENARIOS.values()],
        )
        self._task: asyncio.Task | None = None
        self._runner: ScenarioRunner | None = None
        self._replay: ReplaySource | None = None

    # ------------------------------------------------------------- control
    def _build_simulator(self, twin_id: str) -> PhysiologySimulator:
        with self.service.db.session_scope() as session:
            twin = session.get(Twin, twin_id)
            if twin is None:
                raise KeyError(twin_id)
            subject = session.get(Subject, twin.subject_id)
            profile = SubjectProfile(**(subject.simulation_profile or {})) if subject else SubjectProfile()
            last = twin.last_observation_at or utcnow()
            last_row = (
                session.query(ObservationRow)
                .filter(ObservationRow.twin_id == twin_id, ObservationRow.timestamp == last)
                .first()
            )
        sim = PhysiologySimulator(profile, seed=self.settings.demo_seed, start=last)
        if last_row is not None:  # continue smoothly from the twin's last reading
            sim.hr, sim.rr, sim.spo2 = last_row.heart_rate, last_row.respiratory_rate, last_row.spo2
        return sim

    async def start(self, twin_id: str, scenario: str = "NORMAL", guided: bool = False, mode: str = "simulator") -> dict[str, Any]:
        await self.stop()
        self.service.engine(twin_id)  # fail fast if the twin does not exist
        if mode == "replay":
            path = Path(self.settings.replay_file)
            if not path.exists():
                raise FileNotFoundError(f"replay file not found: {path}")
            self._replay = ReplaySource(path)
            self._runner = None
            self.status.scenario = "REPLAY"
        else:
            if scenario not in SCENARIOS:
                raise KeyError(f"unknown scenario {scenario!r}")
            self._runner = ScenarioRunner(self._build_simulator(twin_id), scenario)
            if guided:
                self._runner.start_guided()
            self._replay = None
            self.status.scenario = self._runner.scenario.key
        self.status.running = True
        self.status.twin_id = twin_id
        self.status.mode = mode
        self.status.guided = guided and mode == "simulator"
        self.status.guided_step = self._runner.guided_step if self._runner else None
        self.status.ticks = 0
        self.status.started_at = utcnow()
        self.status.last_error = None
        self._task = asyncio.create_task(self._loop(twin_id))
        self._notify()
        return self.status.to_dict()

    async def stop(self) -> dict[str, Any]:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        was_running = self.status.running
        self.status.running = False
        self.status.guided = False
        self.status.guided_step = None
        if was_running:
            self._notify()
        return self.status.to_dict()

    def set_scenario(self, scenario: str) -> dict[str, Any]:
        if self._runner is None or not self.status.running:
            raise RuntimeError("live simulator is not running")
        self._runner.set_scenario(scenario)
        self.status.scenario = scenario
        self.status.guided = False
        self.status.guided_step = None
        self._notify()
        return self.status.to_dict()

    # ---------------------------------------------------------------- loop
    def _next_observation(self, twin_id: str):
        dt = self.settings.twin_seconds_per_tick
        if self._replay is not None:
            anchor = self.service.engine(twin_id).last_timestamp or utcnow()
            obs, label = self._replay.next(anchor)
            self.status.scenario = label
            return obs
        assert self._runner is not None
        obs = self._runner.next(dt, source="simulator-live")
        scenario_changed = self._runner.scenario.key != self.status.scenario
        self.status.scenario = self._runner.scenario.key
        self.status.guided_step = self._runner.guided_step
        if scenario_changed:
            self._notify()
        return obs

    async def _loop(self, twin_id: str) -> None:
        errors = 0
        while True:
            started = asyncio.get_running_loop().time()
            try:
                obs = self._next_observation(twin_id)
                await asyncio.to_thread(self.service.ingest, twin_id, obs)
                self.status.ticks += 1
                errors = 0
            except asyncio.CancelledError:
                raise
            except OutOfOrderObservationError as exc:
                log.warning("skipping out-of-order observation: %s", exc)
            except Exception as exc:
                errors += 1
                self.status.last_error = str(exc)
                log.exception("live tick failed (%d/%d)", errors, MAX_CONSECUTIVE_ERRORS)
                if errors >= MAX_CONSECUTIVE_ERRORS:
                    self.status.running = False
                    self._notify()
                    return
            elapsed = asyncio.get_running_loop().time() - started
            await asyncio.sleep(max(self.settings.tick_seconds - elapsed, 0.0))

    def _notify(self) -> None:
        if self.on_status:
            try:
                self.on_status(self.status.to_dict())
            except Exception:
                log.exception("status listener failed")
