"""System endpoints: health, architecture/engine info, demo reset, WebSocket."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy import func, select

from backend.app.api.deps import Container, get_container
from backend.app.models import AnomalyEventRow, ObservationRow, SimulationRunRow, StateTransitionRow, Twin
from backend.app.services.seed import reset_and_seed
from backend.app.services.twin_service import NoBaselineError
from digital_twin.anomaly import CLEAR_READINGS, PERSISTENCE_READINGS, RULES
from digital_twin.baseline import SPREAD_FLOOR
from digital_twin.evaluation import evaluate
from digital_twin.state_engine import CONFIRM_READINGS, STATE_DESCRIPTIONS, STATE_PRIORITY

router = APIRouter(tags=["system"])


@router.get("/api/health", summary="Liveness and basic status")
def health(c: Container = Depends(get_container)) -> dict[str, Any]:
    with c.db.session_scope() as session:
        twins = session.scalar(select(func.count()).select_from(Twin))
    return {"status": "ok", "twins": twins, "live_running": c.live.status.running}


@router.get("/api/system/info", summary="Pipeline, adapters, engine rules and data volumes")
def system_info(c: Container = Depends(get_container)) -> dict[str, Any]:
    with c.db.session_scope() as session:
        counts = {
            name: session.scalar(select(func.count()).select_from(model))
            for name, model in {
                "observations": ObservationRow,
                "state_transitions": StateTransitionRow,
                "anomaly_events": AnomalyEventRow,
                "simulation_runs": SimulationRunRow,
            }.items()
        }
    db_url = c.settings.database_url
    return {
        "app": c.settings.app_name,
        "database": db_url.split(":", 1)[0],
        "counts": counts,
        "websocket_clients": c.hub.client_count,
        "live": c.live.status.to_dict(),
        "pipeline": [
            {"step": "Source", "detail": "Simulator · Replay · CSV · REST · wearable exports · Android phone (Health Connect)"},
            {"step": "Ingestion", "detail": "Aliases, unit conversion, plausibility validation"},
            {"step": "Twin engine", "detail": "Context-aware expectations, anomaly persistence, state machine"},
            {"step": "Persistence", "detail": "Observations, states, transitions, anomaly episodes"},
            {"step": "Analytics", "detail": "Baseline, rolling features, trends, wellness indices"},
            {"step": "Simulation", "detail": "What-if scenarios calibrated to the personal baseline"},
            {"step": "Interface", "detail": "REST + WebSocket → React dashboard and 3D twin"},
        ],
        "adapters": [
            {"name": "simulator", "status": "active", "detail": "Seeded physiology simulator (live scenarios)"},
            {"name": "replay", "status": "available", "detail": "Pre-recorded session — backup demo"},
            {"name": "csv", "status": "available", "detail": "POST /api/twin/{id}/observations/csv"},
            {"name": "rest", "status": "available", "detail": "POST /api/twin/{id}/observations"},
            {"name": "file import", "status": "available", "detail": "Fitbit · Samsung Health · Google Fit · generic CSV"},
            {"name": "android phone", "status": "available", "detail": "Health Twin app → Health Connect → POST /api/devices/sync"},
            {"name": "ble / iot", "status": "planned", "detail": "BLE heart-rate/SpO2 services, ESP32 → same normalized format"},
        ],
        "engine": {
            "anomaly_rules": {
                m: {
                    "direction": r.direction,
                    "z_anomalous": r.z_anomalous,
                    "z_watch": r.z_watch,
                    "min_abs_change": r.min_abs_change,
                    "min_pct_change": r.min_pct_change,
                    "spread_floor": SPREAD_FLOOR[m],
                }
                for m, r in RULES.items()
            },
            "persistence_readings": PERSISTENCE_READINGS,
            "clear_readings": CLEAR_READINGS,
            "state_confirm_readings": CONFIRM_READINGS,
            "state_priority": [s.value for s in STATE_PRIORITY],
            "state_descriptions": {s.value: d for s, d in STATE_DESCRIPTIONS.items()},
        },
        "disclaimer": "Research/demo prototype using synthetic data. Not a medical device; no diagnosis.",
    }


_evaluation_cache: dict[str, Any] = {}


@router.get("/api/system/evaluation", summary="Validation of the twin engine against simulator ground truth")
async def system_evaluation() -> dict[str, Any]:
    """Anomaly recall, false alarms/day, latency and baseline error (cached after first call)."""
    if "result" not in _evaluation_cache:
        _evaluation_cache["result"] = await asyncio.to_thread(evaluate)
    return _evaluation_cache["result"]


@router.post("/api/demo/reset", summary="Stop live data and re-seed deterministic demo data")
async def demo_reset(c: Container = Depends(get_container)) -> dict[str, Any]:
    await c.live.stop()
    reset_and_seed(c.twins, c.settings)
    return {"status": "reset", "twin_id": "twin-001"}


@router.websocket("/ws/twin/{twin_id}")
async def twin_socket(websocket: WebSocket, twin_id: str) -> None:
    c: Container = websocket.app.state.container
    await websocket.accept()
    initial: list[dict[str, Any]] = [{"type": "live", "data": c.live.status.to_dict()}]
    try:
        initial.append({"type": "state", "data": c.twins.state_payload(twin_id)})
    except NoBaselineError:
        pass  # twin exists but has no readings yet (e.g. a phone that hasn't synced): stay subscribed
    except Exception as exc:
        await websocket.send_json({"type": "error", "detail": str(exc)})
        await websocket.close()
        return
    await c.hub.serve(websocket, twin_id, initial)
