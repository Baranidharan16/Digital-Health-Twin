#!/usr/bin/env bash
# One-click start for macOS/Linux:  ./run.sh   -> http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")"
PY=python3; command -v python3 >/dev/null || PY=python
[ -x .venv/bin/python ] || { echo "[1/3] Creating Python environment..."; $PY -m venv .venv; }
# shellcheck disable=SC1091
source .venv/bin/activate
echo "[2/3] Installing Python packages..."
python -m pip install -q --disable-pip-version-check -r requirements-dev.txt
if [ ! -f frontend/dist/index.html ]; then
  echo "Building the website (needs Node.js)..."
  (cd frontend && npm install && npm run build)
fi
echo "[3/3] Starting at http://localhost:8000 (Ctrl+C to stop)"
echo "      Phones on the same Wi-Fi can connect: My data -> Connect your Android phone."
( sleep 6; (command -v open >/dev/null && open http://localhost:8000) || (command -v xdg-open >/dev/null && xdg-open http://localhost:8000) || true ) &
exec python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
