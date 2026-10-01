# Presentation outline (10 slides, about 6 minutes plus demo)

Use the screenshots in `/screenshots`. Keep each slide to one idea and one visual.

| # | Title | Content | Visual |
|---|---|---|---|
| 1 | **The problem** | Wearables stream vitals, but apps use one-size-fits-all thresholds, so they raise false alarms during exercise and miss changes that are large *for you*. | Two lines: "150 bpm while running → alarm"; "85 bpm at rest for someone whose normal is 66 → silence" |
| 2 | **Our digital twin** | A live model of one person: learns their baseline, follows every reading in context, explains changes, simulates what-ifs. Synthetic data; not a medical device. | `01-overview-stable.png` |
| 3 | **Architecture** | Adapters → normalised observation → TwinEngine (context, anomaly, state) → DB and WebSocket → dashboard and 3D twin. Same engine for live, history and what-if. | Mermaid architecture diagram (README §6) |
| 4 | **Live digital twin** | Every reading updates the state machine. The 3D body is bound to data: heart = HR, lungs = RR, limbs = activity, posture = sleep, region glow = flags. | `02-overview-exercise.png`, `04-twin-mapping.png` |
| 5 | **Explainable anomaly detection** | Personal baseline (median/MAD) + activity-aware expected band + robust z + persistence/hysteresis. Example explanation sentence. | `03-overview-anomaly.png` |
| 6 | **Measured, not claimed** | 35 unseen synthetic days, 30 injected episodes: twin 77% caught with 0.0 false alarms/day vs thresholds 43% with 4.6/day. By strength: 17/82/100% vs 0/9/92%. | Table from `06-analytics-validation.png` |
| 7 | **What-if simulation** | Personal model + the same state engine; exercise after a short night recovers more slowly (9.0 vs 5.5 min). Assumptions listed; "scenario simulation, not prediction". | `07-simulation.png` |
| 8 | **Technical implementation** | FastAPI · Pydantic · SQLAlchemy/SQLite · NumPy/pandas · React/TS/Vite · Three.js/R3F · Blender GLB · Docker. Why each was chosen (README §8). | Stack strip |
| 9 | **Validation and testing** | 52 backend + 5 frontend tests: ingestion, baseline, anomaly, states, simulator, what-if, API, WebSocket, an end-to-end integration test, and a validation guard. Reproducible seeds. | Test table (docs/testing.md) |
| 10 | **Limitations, roadmap, demo** | Synthetic data, simplified physiology, illustrative sleep coefficients, subtle-change recall. Roadmap: CSV (done) → wearable APIs → BLE (0x180D/0x1822/0x1809) → ESP32 prototype. Then the live demo. | Roadmap table (README §21) |

**Claims to avoid**: diagnosis, disease prediction, clinical accuracy, patient safety. **Words to use**: wellness monitoring, anomaly flag, personal baseline, scenario simulation, research prototype.
