# One container: FastAPI serves the API, WebSocket and the built React app.
# ---- 1. build the frontend --------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. runtime -------------------------------------------------------------
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DHT_DATABASE_URL=sqlite:////app/var/twin.db
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY digital_twin/ digital_twin/
COPY simulator/ simulator/
COPY scripts/ scripts/
COPY data/demo_recording.jsonl data/demo_recording.jsonl
COPY data/sample_real/ data/sample_real/
COPY --from=frontend /src/frontend/dist frontend/dist
RUN mkdir -p /app/var && useradd --create-home twin && chown -R twin /app/var
USER twin
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
