"""FastAPI application factory (imported by main.py and by the tests)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from backend.app.api import simulation, system, twins
from backend.app.api.deps import Container
from backend.app.config import Settings, get_settings
from backend.app.db import Database
from backend.app.services.hub import Hub
from backend.app.services.live import LiveRunner
from backend.app.services.queries import QueryService
from backend.app.services.seed import DEFAULT_TWIN_ID, seed_database
from backend.app.services.twin_service import TwinService

log = logging.getLogger("digital_twin")

DESCRIPTION = """
**Human Health Digital Twin — research/demo prototype.**

A software-only digital twin of a (synthetic) person: observations are
ingested and validated, a deterministic engine keeps the twin's state in
sync, anomalies are explained against a *personal* baseline, and what-if
scenarios are simulated with a model calibrated to that baseline.

⚠️ Synthetic data only. Not a medical device. No diagnosis or treatment advice.
"""


def build_container(settings: Settings) -> Container:
    db = Database(settings.database_url)
    db.create_all()
    twins_service = TwinService(db)
    hub = Hub()
    live = LiveRunner(twins_service, settings, on_status=lambda s: hub.publish_all({"type": "live", "data": s}))
    twins_service.add_listener(lambda twin_id, payload: hub.publish(twin_id, {"type": "state", "data": payload}))
    return Container(
        settings=settings, db=db, twins=twins_service, queries=QueryService(twins_service), live=live, hub=hub
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        container: Container = app.state.container
        container.hub.bind(asyncio.get_running_loop())
        if settings.seed_on_startup:
            await asyncio.to_thread(seed_database, container.twins, settings)
        if settings.autostart_live:
            try:
                await container.live.start(DEFAULT_TWIN_ID, "NORMAL")
            except Exception:
                log.exception("could not autostart live simulator")
        yield
        await container.live.stop()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.container = build_container(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(twins.router)
    app.include_router(simulation.router)
    app.include_router(system.router)

    dist = Path(settings.frontend_dist)
    if dist.is_dir() and (dist / "index.html").exists():
        index = dist / "index.html"

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith(("api/", "ws/")):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(index)

    return app

