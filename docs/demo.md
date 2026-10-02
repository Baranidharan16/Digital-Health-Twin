# Demo script (4–5 minutes)

## Before you present (5 minutes earlier)

1. `docker compose up --build` (or `uvicorn backend.app.main:app --port 8000`). Open <http://localhost:8000>, set the browser to full screen and zoom to 90% on a laptop.
2. **System → Reset demo data**, then **Resume data**. The twin starts at STABLE with a fresh 7-day history.
3. Open the **Analytics** page once so the validation report is computed and cached (about 2 s).
4. Keep a second tab on <http://localhost:8000/docs> in case a judge asks about the API.
5. Have the backup ready (see the end of this page).

## Script

| Time | Do this | Say this |
|---|---|---|
| **0:00–0:30** Problem | Overview page, at rest | "Wearables give us heart rate, SpO₂, temperature and movement, but apps compare everyone to the same thresholds. That gives false alarms when you exercise and misses changes that are big *for you*. We built a digital twin of one person: a live model that knows their normal." |
| **0:30–1:00** What the twin is | Point along the five-step strip at the top | "Readings arrive, the twin updates, its state changes, analytics explain why, and we can simulate what-ifs. The person is synthetic, with 7 days of history the twin learned a personal baseline from: resting heart rate 66, not a population 70." |
| **1:00–2:00** Live twin | Click **Run guided demo**. Watch the body and the state panel | "Every second a new reading arrives, 15 seconds of twin time. The heart beats at the live heart rate and the lungs at the breathing rate. Now the person starts running: the muscles light up, the state goes Active, then High activity. Heart rate is 160, and the gauge shows it is *inside* the expected band for running, so no alarm. A threshold rule would have fired here." |
| | When it reaches **Recovering** | "Activity stopped. The twin calls this Recovery, not an anomaly, and measures the heart-rate drop in the first minute." |
| **2:00–2:45** Anomaly | When the anomaly phase starts (about 45 s in) | "Now the person is sitting still, but heart rate, breathing and temperature rise and SpO₂ dips. Watch: Elevated first, then after 4 consecutive readings, Anomaly flagged. The heart, lungs and head light up. And it says *why*:" read the Why panel, e.g. "Heart rate 88 is 24% above the 71 expected for this person at rest, for 4 consecutive readings." "Every change is logged with its reason: here in the event feed." |
| **2:45–3:30** What-if | **Simulation** → Exercise session, intensity Run, 30 min, tick *After a short night* (5 h) → **Run simulation** | "The twin can also look ahead. This runs the person's own model, with their learned baseline, through a 30-minute run after a 5-hour night, compared with a normal night. Recovery is slower: 9 minutes to settle instead of 5.5. The same state engine classifies the simulated future. It's labelled as a scenario simulation, and the assumptions are listed. We don't claim it's a medical prediction." |
| **3:30–4:10** Evidence | **Analytics** → validation panel | "How do we know the detector works? The simulator knows when it injected anomalies, so we measured it on 35 unseen days: the twin catches 77% of episodes with zero false alarms per day. Population thresholds catch 43% and raise 4.6 false alarms a day. Subtle episodes are still hard: we catch 17%. That's the honest trade-off." |
| **4:10–4:40** Engineering and future | **System** page | "Any source becomes one normalised observation: simulator, replay, CSV or REST today, with a wearable next. The engine doesn't change. FastAPI, SQLAlchemy, React and Three.js; the anatomy is real scan data (BodyParts3D) assembled in Blender. 72 backend tests including an end-to-end test, real-data import and phone-sync tests, and one-click start. Next: a real-data pilot, BLE devices, and learning each person's time constants." |
| **(optional, +45 s)** Real data | **My data → Load real Fitbit sample → Open this twin**, then **Twin → Load day → Play** | "Is the data fake? The demo is simulated so we can control it, but here is a real person: 14 days of a public Fitbit dataset. Same engine: it learned this person's resting heart rate of 65, their sleep, their steps. SpO₂ and temperature are greyed out because that watch never measured them, and we never invent data. Now the anatomy is replaying their real night, minute by minute." |
| **(optional, +60 s)** Your phone | **My data → Connect your Android phone → Show pairing code**; scan it with the Health Twin app, allow access, **Sync now**; switch to the phone twin | "And this is my own phone. The app reads Health Connect, so it works with Samsung, Fitbit, Pixel and most watches. Pairing is a one-time code; the server stores only a hash of the phone's token. The first sync sends a week so the twin learns my baseline; after that it syncs every minute and the body follows." (No phone or Wi-Fi blocked? Run `python scripts/fake_phone.py --code <code> --live --scenario run`.) |
| **4:40–5:00** Close | Back to Overview | "A twin that knows your normal, says what changed and why, and lets you ask what-if. Synthetic data, not a medical device, built to plug into real wearables. Thank you." |

## Manual control (if asked or for Q&A)

Use the **Simulated person is** buttons: Normal, Exercise, Recovery, Anomaly, Sleep. Sleep lays the body down and switches to the sleeping baseline. Switching from Anomaly to Normal clears the flags after 3 normal readings.

## Likely judge questions

- **Is this a medical device?** No. It is a research prototype on synthetic data; states describe data, not diagnoses.
- **Why not deep learning?** No real labelled data, and explanations matter for health. A few interpretable rules with measured recall and false-alarm rate beat an opaque model trained on synthetic data.
- **How does real data come in?** The Android app (Health Connect: phone and most watches), file exports, or `POST /api/twin/{id}/observations`. Next: iPhone (HealthKit), BLE heart-rate/SpO₂ services.
- **Why a phone app and not each watch's API?** Health Connect already aggregates Samsung, Fitbit, Google and others on the phone, so one app covers most watches, with the user's explicit per-type permission.
- **Is the phone link secure?** Single-use 10-minute code, then a random token (only its hash is stored); revocable from the website. A prototype on the local network over HTTP; a deployment would add TLS and accounts.
- **What makes it a twin and not a dashboard?** A persistent per-person model (baseline and context filters), state with transitions, and simulation on that model, kept in sync by every reading.
- **Why 4 readings?** It trades latency (about 1 min live, about 20 min at 5-minute sampling) for zero false alarms in validation. It's configurable.

## Backup demo (if live simulation misbehaves)

Choose whichever option is quickest:

1. **Replay the recorded session**: System → **Play recorded session (backup demo)**. It streams `data/demo_recording.jsonl` (the guided demo recorded with seed 42) through the normal ingestion path, so the whole UI behaves exactly as live.
   CLI: `curl -X POST localhost:8000/api/simulator/start -H "Content-Type: application/json" -d '{"mode":"replay"}'`
2. **Reset**: System → **Reset demo data** reseeds the deterministic history in about 1 s.
3. **Screenshots**: `screenshots/` covers every step of the script.
4. **Video**: record a 5-minute screen capture of this script beforehand (for example with OBS) and keep it on the desktop.

To re-record the replay file: `python scripts/record_demo.py`.
