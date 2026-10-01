"""Record the deterministic guided demo to a replay file (backup demo).

The replay file stores each reading plus the time step since the previous
reading, so the backend can replay it through the normal ingestion path
(``POST /api/simulator/start`` with ``{"mode": "replay"}``) if the live
simulator misbehaves during a presentation.

Usage (from the repository root):

    python scripts/record_demo.py                 # writes data/demo_recording.jsonl
    python scripts/record_demo.py --out my.jsonl --seed 7
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simulator.generator import PhysiologySimulator, SubjectProfile  # noqa: E402
from simulator.scenarios import GUIDED_DEMO, ScenarioRunner  # noqa: E402

TICK_S = 15.0


def record(out: Path, seed: int) -> int:
    runner = ScenarioRunner(PhysiologySimulator(SubjectProfile(), seed=seed, start=datetime(2026, 1, 1, 4, 30)))
    runner.start_guided()
    ticks = int(sum(d for _, d in GUIDED_DEMO) / TICK_S) + 1
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for _ in range(ticks):
            obs = runner.next(TICK_S, source="replay")
            reading = {
                "heart_rate": obs.heart_rate,
                "spo2": obs.spo2,
                "temperature": obs.temperature,
                "respiratory_rate": obs.respiratory_rate,
                "steps": obs.steps,
                "activity_intensity": obs.activity_intensity,
                "is_asleep": obs.is_asleep,
            }
            handle.write(json.dumps({"dt_s": TICK_S, "scenario": runner.scenario.key, "reading": reading}) + "\n")
    return ticks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "demo_recording.jsonl")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    n = record(args.out, args.seed)
    print(f"wrote {n} readings to {args.out}")
