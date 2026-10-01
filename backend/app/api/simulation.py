"""What-if scenario simulation and live simulator control."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select

from backend.app.api.deps import Container, get_container, map_errors
from backend.app.models import SimulationRunRow, Twin
from backend.app.schemas import ExerciseScenarioIn, LiveScenarioIn, LiveStartIn, ScenarioIn, to_utc_iso
from backend.app.services.twin_service import utcnow
from digital_twin.whatif import simulate_exercise, simulate_sleep_restriction

router = APIRouter(prefix="/api", tags=["simulation"])


@router.post("/simulation", summary="Run a what-if scenario simulation calibrated to the twin")
def run_simulation(body: ScenarioIn = Body(...), c: Container = Depends(get_container)) -> dict[str, Any]:
    with c.db.session_scope() as session:
        twin = session.get(Twin, body.twin_id)
        if twin is None:
            raise HTTPException(404, f"twin {body.twin_id} not found")
        age = twin.subject.age_years
        try:
            baseline = c.twins.active_baseline(session, body.twin_id)
        except Exception as exc:
            raise map_errors(exc) from exc

    if isinstance(body, ExerciseScenarioIn):
        result = simulate_exercise(
            baseline, age, body.intensity, body.duration_min, body.prior_sleep_hours, body.recovery_min
        )
    else:
        result = simulate_sleep_restriction(baseline, age, body.sleep_hours, body.nights)

    with c.db.session_scope() as session:
        run = SimulationRunRow(
            twin_id=body.twin_id,
            created_at=utcnow(),
            scenario=result["scenario"],
            inputs=result["inputs"],
            summary={"metrics": result["metrics"], "reference_metrics": result["reference_metrics"]},
        )
        session.add(run)
        session.flush()
        result["run_id"] = run.id
    return result


@router.get("/simulation/runs", summary="Previously run scenario simulations")
def list_runs(
    twin_id: str = "twin-001", limit: int = Query(20, ge=1, le=100), c: Container = Depends(get_container)
) -> list[dict[str, Any]]:
    with c.db.session_scope() as session:
        rows = session.scalars(
            select(SimulationRunRow)
            .where(SimulationRunRow.twin_id == twin_id)
            .order_by(SimulationRunRow.created_at.desc())
            .limit(limit)
        ).all()
        return [
            {
                "id": r.id,
                "created_at": to_utc_iso(r.created_at),
                "scenario": r.scenario,
                "inputs": r.inputs,
                "summary": r.summary,
            }
            for r in rows
        ]


# --------------------------------------------------------------- live demo
@router.get("/scenarios", tags=["live"], summary="Live demo scenarios")
def list_scenarios(c: Container = Depends(get_container)) -> dict[str, Any]:
    return {"scenarios": c.live.status.scenarios, "guided": c.live.status.to_dict()["guided_sequence"]}


@router.get("/simulator/status", tags=["live"], summary="Live simulator status")
def live_status(c: Container = Depends(get_container)) -> dict[str, Any]:
    return c.live.status.to_dict()


@router.post("/simulator/start", tags=["live"], summary="Start live data (simulator or replay backup)")
async def live_start(body: LiveStartIn = Body(default_factory=LiveStartIn), c: Container = Depends(get_container)) -> dict[str, Any]:
    try:
        return await c.live.start(body.twin_id, body.scenario, body.guided, body.mode)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise map_errors(exc) from exc


@router.post("/simulator/stop", tags=["live"], summary="Stop live data")
async def live_stop(c: Container = Depends(get_container)) -> dict[str, Any]:
    return await c.live.stop()


@router.post("/simulator/scenario", tags=["live"], summary="Switch the running live scenario")
def live_scenario(body: LiveScenarioIn, c: Container = Depends(get_container)) -> dict[str, Any]:
    try:
        return c.live.set_scenario(body.scenario)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(400, str(exc)) from exc
