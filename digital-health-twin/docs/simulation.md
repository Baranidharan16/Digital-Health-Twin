# Simulation

There are two different "simulations" in this project. They share the same equations:

| | Data simulator (`simulator/`) | What-if engine (`digital_twin/whatif.py`) |
|---|---|---|
| Purpose | Stand-in for a real person and wearable | Answer "what would happen if…" for **this** twin |
| Parameters | Hidden ground-truth `SubjectProfile` | The twin's **learned** baseline |
| Noise | Seeded AR(1) sensor noise | None (deterministic) |
| Output | Observations into the ingestion pipeline | Trajectories, metrics and a state sequence, compared with a reference |

## Shared physiology model (`digital_twin/physiology.py`)

| Quantity | Model | Parameter |
|---|---|---|
| Max HR | 208 − 0.7 × age (Tanaka) | population estimate |
| Target HR | rest + intensity × (max − rest) | Karvonen-style, linear in intensity |
| HR dynamics | first-order, asymmetric | τ up 30 s, τ down 110 s |
| Breathing | rest + 22 × intensity | τ 25 s |
| SpO₂ | base − 1.0 × intensity | τ 40 s |
| Temperature | base + circadian ±0.25 °C + 0.8 × intensity | τ 900 s |
| Sleep | HR −8 bpm, RR −1.5, temperature −0.25 °C | |
| Steps | 0 below intensity 0.08; 60–110 spm walking; 110–150 spm running | |

These are scenario-model assumptions chosen to be explainable, not validated physiology.

## Data simulator

**Correlated signals.** One activity input drives every channel, so exercise raises heart rate, breathing, steps and (slowly) temperature and slightly lowers SpO₂. Stopping gives an exponential recovery. Sleep lowers heart rate, breathing and temperature. Tests check each of these.

**Anomaly pattern.** At rest, the anomaly level rises with τ 45 s and adds HR × (1 + 0.32a), RR + 6a, SpO₂ − 3.5a and temperature + 1.3a, where `a` ≤ magnitude (0–1). This is a pattern activity cannot explain, which is exactly what the detector should flag.

**History** (`generate_history`). Seven days of a daily routine on the subject's local clock (UTC+5:30 by default), integrated at 60 s and sampled every 5 min:
wake about 06:45; a morning walk; commute walks; a lunch walk; a run (warm-up, about 33 min at intensity 0.78, cool-down) every other evening, otherwise an evening walk; bed about 23:15; occasional night-time awakenings; one unexplained evening episode on day 4. `anomaly_windows=[(start, end, magnitude)]` injects labelled episodes for validation.

**Live scenarios** (`simulator/scenarios.py`), at 15 s of twin time per 1 s tick:

| Scenario | Activity input |
|---|---|
| NORMAL | seated (0.04) with a small fidget (0.12) every 90 s |
| EXERCISE | 45 s brisk walk (0.38), then running (0.8) |
| RECOVERY | still (0.02); vitals decay towards baseline |
| ANOMALY | still (0.03) with the anomaly input on |
| SLEEP | asleep |
| Guided demo | NORMAL 2 min → EXERCISE 5 min → RECOVERY 5 min → ANOMALY 6.5 min (twin time), about 70 s on screen |

**Reproducibility.** Every random draw comes from one `numpy.random.Generator` seeded from configuration (`DHT_HISTORY_SEED`, `DHT_DEMO_SEED`). The same seed gives identical data (tested).

## What-if engine

1. Build a `SubjectProfile` from the twin's **learned** baseline (resting and sleeping HR, breathing, SpO₂, awake temperature, age) with no circadian swing.
2. Run the physiology noise-free at 30 s steps through a schedule of activity blocks.
3. Feed the trajectory through a fresh `TwinEngine` with the same baseline. The output includes the **states and reasons** the twin would show.
4. Run a **reference** schedule (same activity after a normal night) and return both, with metrics.

### Scenario 1: exercise session

Inputs: intensity (0.1–1.0), duration (2–120 min), recovery period (5–60 min), optional prior-night sleep (2–12 h). The schedule is 5 min rest, then the session, then recovery.

Outputs: peak and mean exercise HR, peak as % of HR reserve, 1-minute HR recovery, minutes until HR is within 10% of resting, temperature rise, estimated steps, minutes in each state, and transitions with reasons.

### Scenario 2: short sleep

Inputs: hours per night (2–12), nights in a row (1–7). Outputs: projected resting HR after each night and recovery slow-down, plus a standard 10-minute brisk walk (intensity 0.4) compared with the same walk after a normal night.

**Illustrative coefficients**, returned with every result:

- each hour below the personal sleep norm adds **1.2 bpm** to resting HR (cap 8 bpm);
- each additional short night adds **50%** carry-over;
- recovery slows by **6% per deficit-hour-night** (cap 1.5×).

Sleep restriction is commonly associated with a higher resting heart rate and slower recovery, but these magnitudes are chosen for demonstration and are not fitted to data. That is why the feature is called a scenario simulation and not a prediction.

## Example

Exercise at intensity 0.7 for 30 min, after a 5 h night vs a normal night (the twin learned resting HR 66 bpm and max HR about 188 bpm):

| Outcome | After 5 h sleep | Normal night |
|---|---|---|
| Peak HR | 152 bpm | 151 bpm |
| HR drop in first minute after | 31 bpm | 35 bpm |
| Minutes to settle near resting | 9.0 | 5.5 |
| States | STABLE → HIGH_ACTIVITY (6 min) → RECOVERY (36 min) → STABLE (45 min) | |
