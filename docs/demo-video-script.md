# Demo video script (15–20 minutes)

Record the screen and your voice. OBS Studio and the Windows Game Bar (Win + G) are both free. Upload the video to YouTube as **Unlisted** and paste the link into the README's [Demo video](../README.md#demo-video) section.

**Before recording:**
- Start the app with `run.bat`, or open the deployed website.
- Open http://localhost:8000.
- Go to **System → Reset demo data**.
- Set the browser zoom to 90% and close other tabs.
- Have the phone with the Health Twin app ready, or the fallback `scripts/fake_phone.py`.
- Keep `docs/submission/presentation.pdf` open in another window.

| # | Time | Show | Say (key points) |
|---|---|---|---|
| 1 | 0:00–1:30 | Presentation slides 1–2 | Team and college. The problem: wearables judge everyone against the same thresholds, so they give false alarms during exercise and miss changes that are large *for you*. |
| 2 | 1:30–3:00 | Slides 3–4 and `architecture-diagram.pdf` | What a digital twin is: a live model kept in sync with data, not just a 3D picture. Walk through the 5 columns: sources → ingestion → twin engine → store & sync → interfaces. |
| 3 | 3:00–5:00 | Website **Overview** | The demo twin: a synthetic person with 7 days of history. Point to the personal baseline (resting HR 66, not a population 70). Explain the 5-step strip at the top and the state panel. |
| 4 | 5:00–7:30 | **Run guided demo** | Normal → Exercise: HR 160 is *inside* the expected band, so no alarm. Recovery: the 1-minute heart-rate recovery. Anomaly at rest: Elevated, then Anomalous after 4 readings. Read the "Why" sentence aloud. Show the event feed. |
| 5 | 7:30–9:00 | **Twin** page | The 3D anatomy from scan data: toggle layers, click the heart and lungs to see what drives them. Point out that unmonitored organs never animate. Switch to Sleep: the body lies down. |
| 6 | 9:00–10:30 | **History** and **Analytics** | 7-day history with states and anomaly spans. Validation panel: 77% caught with 0 false alarms a day, vs 43% and 4.6 a day for thresholds. Be honest that subtle changes are only 17%. |
| 7 | 10:30–12:00 | **Simulation** | Exercise after a 5-hour night vs a normal night: recovery 9.0 vs 5.5 min. Assumptions are listed, and it is labelled a scenario, not a prediction. |
| 8 | 12:00–13:30 | **My data → Load real Fitbit sample** | A real person's 14 days (public CC0 dataset). The twin learned resting HR 65 and sleep 6.1 h. SpO₂ and temperature show as "not measured", never invented. Twin page → play back a real night. |
| 9 | 13:30–16:00 | **My data → Connect your Android phone** + the phone (screen-record the phone, or film it) | Show the pairing code → Scan QR in the app → allow Health Connect permissions → Sync now. The phone twin appears and updates. Explain: Health Connect covers Samsung, Fitbit and Pixel watches, and only a hash of the device token is stored. (No phone? Run `python scripts/fake_phone.py --code <code> --live --scenario run` and explain that it uses the app's exact API.) |
| 10 | 16:00–17:30 | GitHub repo, **Actions** tab, `/docs` (API docs) | Engineering: tests run on every push (72 backend + 7 frontend), the APK is built automatically, OpenAPI docs, Docker, and free deployment on Render. |
| 11 | 17:30–19:00 | Slides 13–15 | Outcomes, honest limitations (synthetic validation, Android only, not a medical device), roadmap (pilot with consenting users, iPhone, BLE sensors). Thank the panel. |

**Tips:**
- Speak slowly and keep the mouse still while you talk.
- If something fails, use **System → Play recorded session**, which is the backup demo.
- Keep the total between **15 and 20 minutes**. The form requires this.
