"""ASGI entry point.

Run locally:   uvicorn backend.app.main:app --reload
OpenAPI docs:  http://localhost:8000/docs
"""

from backend.app.factory import create_app

app = create_app()
