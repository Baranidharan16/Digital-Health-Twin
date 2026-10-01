# Testing

## How to run

```bash
pip install -r requirements-dev.txt
pytest                              # backend: 52 tests, about 6 s
cd frontend && npm ci && npm test   # frontend: 5 tests
python -m digital_twin.evaluation   # validation report
```

Every API test creates its own temporary SQLite database and seeds 3 days of history, so tests are independent and need no running server. The suite has been run from a fresh virtualenv with only `requirements-dev.txt` installed.

## What is covered

| File | Tests | What they prove |
|---|---|---|
| `test_ingestion.py` | 9 | Field aliases, °F → °C, SpO₂ fraction → %, epoch-ms timestamps, implausible values rejected (HR 400, SpO₂ 30, temperature 50, RR 0, negative steps), missing timestamp, per-line CSV errors |
| `test_baseline.py` | 4 | Learned resting HR within 2 bpm of the simulator's truth; sleeping HR below resting; robust to 5% corrupted readings; spread floors; insufficient-history errors |
| `test_anomaly.py` | 6 | A resting HR rise is "watch" until 4 readings, then "anomalous"; explanation text contains %, context and consecutive count; 150 bpm while running is **not** flagged; hysteresis clears after 3 normal readings; a one-off glitch is never flagged; SpO₂ reference-range flag |
| `test_state_engine.py` | 8 | Initial state; debounce; ANOMALOUS immediate; exercise → HIGH_ACTIVITY → RECOVERY → STABLE with reasons; SLEEPING; anomaly priority over activity; out-of-order readings rejected; determinism |
| `test_simulator.py` | 7 | Same seed gives identical data and different seeds differ; history reproducible; exercise raises HR, RR and steps and lowers SpO₂; monotonic recovery; sleep lowers HR with no steps; anomaly deviates without activity; guided demo runs through all phases |
| `test_whatif.py` | 5 | Results labelled as simulation with assumptions; higher intensity gives a higher peak capped by max HR; deterministic; short sleep raises resting HR and slows recovery; no sleep deficit gives no effect |
| `test_api.py` | 11 | Health; identity has no PII fields; state and vitals; every history range including custom (and an invalid custom range returns 400); baseline, events and wellness; ingestion 200/409/422 including rejection of unknown fields; CSV adapter; simulation endpoint and validation; live start, switch, stop and the WebSocket push; system info and OpenAPI; replay backup demo |
| `test_integration.py` | 2 | **End to end:** a seeded simulator stream is posted through the public REST endpoint; the twin goes HIGH_ACTIVITY → RECOVERY → ANOMALOUS in order; `/state` and `/events` return the anomaly with explanations. **Validation guard:** recall ≥ 0.7, ≤ 0.5 false alarms/day, fewer false alarms than population thresholds, baseline error < 2 bpm |
| `frontend/src/lib/twinVisuals.test.ts` | 5 | Heart and lung rates follow live vitals; still at rest and moving when running; lying down when asleep; each flagged vital lights its body region; heartbeat waveform periodic |

## Manual checks done

- Production build served by FastAPI and inspected with headless Chromium at 1440 px and 390 px wide (no horizontal scroll at phone width).
- Guided demo observed via the API: STABLE → ACTIVE → HIGH_ACTIVITY → RECOVERY → STABLE → ANOMALOUS in about 70 s.
- Replay mode streams the recorded session through ingestion.
- Blender script run headless (Blender 4.2 `bpy`), exporting 9 named parts (about 5.3k vertices, 0.13 MB GLB).

## Not covered (known gaps)

- No browser end-to-end test in CI. The UI was checked manually with screenshots.
- The Docker image build could not be run in the development sandbox because the Docker Hub registry was blocked. Build it once with `docker compose up --build` before the demo.
- No load testing; the prototype targets one twin at 1 reading per second.
