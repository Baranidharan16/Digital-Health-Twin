"""Pretend to be the Android app: test the phone connection without a phone.

1. On the website open **My data → Connect your Android phone → Show pairing code**.
2. Run::

       python scripts/fake_phone.py --code 123456
       python scripts/fake_phone.py --code 123456 --live      # keep syncing every 10 s

It claims the code exactly like the app, sends 3 days of Health Connect-shaped
records (simulated, clearly labelled "fake phone"), and with ``--live`` keeps
sending one new minute of readings per sync, so you can watch the twin update.
Only the Python standard library and this repo's simulator are used.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulator.generator import ActivityInput, PhysiologySimulator, SubjectProfile, generate_history  # noqa: E402
from simulator.health_connect import to_health_connect  # noqa: E402


def call(server: str, path: str, body: dict, token: str | None = None) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(server.rstrip("/") + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{path} failed: HTTP {exc.code} {exc.read().decode(errors='replace')}") from None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--code", help="6-digit pairing code shown on the website")
    ap.add_argument("--token", help="reuse a token from an earlier run instead of pairing")
    ap.add_argument("--days", type=float, default=3)
    ap.add_argument("--live", action="store_true", help="keep sending new minutes")
    ap.add_argument("--every", type=float, default=10, help="seconds between live syncs")
    ap.add_argument("--scenario", choices=["rest", "walk", "run", "unusual"], default="rest",
                    help="what the fake person does during --live")
    args = ap.parse_args()

    if not args.token and not args.code:
        ap.error("give --code (from the website) or --token")
    token = args.token
    if not token:
        claim = call(args.server, "/api/devices/claim", {"code": args.code, "device_name": "Fake phone (simulator)"})
        token = claim["token"]
        print(f"paired: twin {claim['twin_id']}  (reuse with --token {token})")

    profile = SubjectProfile()
    now = datetime.now(timezone.utc).replace(tzinfo=None, second=0, microsecond=0)
    history = generate_history(profile, end=now, days=args.days, interval_s=60.0, seed=21, include_planned_anomaly=False)
    offset = -time.timezone / 3600 if time.daylight == 0 else -time.altzone / 3600
    out = call(args.server, "/api/devices/sync", to_health_connect(history, offset, window_end=now + timedelta(minutes=1)), token)
    print(f"history sync: {out['status']}, +{out['readings_ingested']} minutes, measured {', '.join(out['metrics'])}")

    if not args.live:
        return
    intensity = {"rest": 0.03, "walk": 0.35, "run": 0.75, "unusual": 0.03}[args.scenario]
    sim = PhysiologySimulator(profile, seed=5, start=history[-1].timestamp)
    sim.hr = history[-1].heart_rate
    activity = ActivityInput(intensity=intensity, anomaly=args.scenario == "unusual")
    print(f"live: one new minute every {args.every:g} s ({args.scenario}); Ctrl+C to stop")
    try:
        while True:
            obs = sim.step(60.0, activity, source="fake-phone")
            body = to_health_connect([obs], offset, window_end=obs.timestamp + timedelta(minutes=1), spo2_every=1)
            out = call(args.server, "/api/devices/sync", body, token)
            print(f"{obs.timestamp:%H:%M} HR {obs.heart_rate:5.1f}  steps {obs.steps:3d}  -> {out['status']} +{out['readings_ingested']}")
            time.sleep(args.every)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
