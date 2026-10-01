# Real data

The demo twin is synthetic so the demo is controllable and reproducible. To show that the twin is not "just fake numbers", the same engine also builds twins from **real wearable exports**.

## Try it

**My data → Load real Fitbit sample → Open this twin**, or `POST /api/twins/import-sample`.

The sample is 14 days (12–25 April 2016) of participant **5553957443** from the public *Crowd-sourced Fitbit datasets* (Furberg et al., 2016, Zenodo doi:10.5281/zenodo.53894, **CC0**). Thirty consenting Amazon Mechanical Turk users shared their Fitbit data for research. The files are unmodified Fitbit/Fitabase exports, filtered to one participant and 14 days:

| File | Content | Rows |
|---|---|---|
| `heartrate_seconds_merged.csv` | heart rate every ~5 s | 115,263 |
| `minuteStepsNarrow_merged.csv` | steps per minute | 20,160 |
| `minuteSleep_merged.csv` | sleep state per minute (1 = asleep) | 7,104 |

What the twin learns from them: resting heart rate about 65 bpm, sleeping about 59 bpm, typical sleep about 6.1 h, about 7,400 steps a day. Over 7 days it spends about 61% of the time Stable, 34% Sleeping and 3% Active, and raises a handful of heart-rate flags that are explained below.

## Upload your own

**My data → Upload your own export**, or `POST /api/twins/import` (multipart). Several files can be uploaded together; they are merged by time.

| Source | How to export | Files the importer reads |
|---|---|---|
| Samsung Health | App → Settings → Download personal data | `com.samsung.health.heart_rate.*.csv`, `com.samsung.shealth.tracker.pedometer_step_count.*.csv`, `com.samsung.health.sleep.*.csv` (SpO₂ files too) |
| Google Fit | takeout.google.com → Fit → *Daily activity metrics* | day files `YYYY-MM-DD.csv` (15-min average heart rate and step count) |
| Fitbit / Fitabase | research exports | `heartrate_seconds_merged.csv`, `minuteStepsNarrow_merged.csv`, `minuteSleep_merged.csv` |
| Any device | your own CSV | `timestamp` + any of `heart_rate, spo2, temperature, respiratory_rate, steps, activity_intensity, is_asleep` (aliases such as `hr`, `bpm`, `temp_f` accepted) |

## How an upload becomes a twin (`backend/app/importers.py`, `services/imports.py`)

1. **Detect** each file's format from its header.
2. **Merge** all files on one time grid: 1-minute buckets, or 5-minute buckets for histories over 31 days. Vitals are averaged, steps are summed, and sleep minutes mark a bucket as asleep.
3. **Keep honest gaps.** Buckets without heart rate are dropped. SpO₂, temperature and breathing stay empty if the device did not record them; the twin never assesses or animates a vital it does not have.
4. **Estimate movement intensity from step cadence** when the export lacks it (0 steps/min → still, ~100 → brisk walk, ~140 → running). This is an approximation and is reported as such.
5. **Convert the device's local clock to UTC** with the chosen time zone. The dashboard shows times on the twin's own clock.
6. Create a pseudonymous subject and twin, learn the baseline, **replay every reading through the engine** (states, anomaly episodes), then re-learn the baseline excluding flagged readings. This is the same lifecycle as the demo twin.

## Honest limitations on real data

- **No ground truth.** Detection accuracy is validated on synthetic data, where injected anomalies are known. On real data, flags are explained but cannot be scored.
- **Workouts without steps.** Cycling, gym work or swimming produce few steps, so the twin thinks the person is resting and may flag the high heart rate. In the Fitbit sample, the four flagged peaks around 120 bpm look like such sessions.
- **Consumer heart-rate accuracy** varies with fit, skin and motion; the twin uses the data as given.
- **Wearables observe only part of the body.** See the "What drives each part of the body" table on the Twin page.

## Privacy

Uploads are processed by the local backend and stored in the local SQLite database: a nickname, age, time zone and the readings, with no names, emails or device IDs. **Delete data** removes the twin, its subject and every reading. The demo twin cannot be deleted, only reset.
