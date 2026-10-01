"""Context-aware, explainable anomaly detection.

For every vital sign the detector asks: *given this subject's personal
baseline and what they are doing right now, what value would we expect?*
It then measures how far the reading is from that expectation.

    deviation  = value - expected
    robust_z   = deviation / personal_spread     (spread = 1.4826 x MAD)

A reading becomes a *candidate* when it is both statistically unusual
(|robust_z| above a threshold) and practically meaningful (the absolute or
relative change is large enough to matter). It is only flagged as
*anomalous* when the candidate condition persists for several consecutive
readings, and it only clears after several consecutive normal readings
(hysteresis). This suppresses one-off sensor glitches and avoids flicker.

Because the expected value tracks activity, a heart rate of 150 bpm during a
run is normal, while 95 bpm at rest for a subject whose baseline is 62 bpm is
flagged, and the explanation says exactly why.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from digital_twin.physiology import (
    SPO2_DROP_PER_INTENSITY,
    TEMP_GAIN_PER_INTENSITY,
    target_heart_rate,
    target_respiratory_rate,
)
from digital_twin.types import METRIC_LABELS, METRIC_UNITS, Baseline, MetricAssessment, Observation


@dataclass(frozen=True)
class MetricRule:
    metric: str
    direction: str  # "high", "low" or "both"
    z_anomalous: float
    z_watch: float
    min_abs_change: float  # minimum absolute deviation for an anomaly candidate
    min_pct_change: float  # minimum relative deviation (%) for an anomaly candidate


RULES: dict[str, MetricRule] = {
    # Heart rate is flagged when HIGHER than expected. Lower-than-expected heart
    # rate during movement is usually an activity-estimate artefact (e.g. arm
    # movement counted as steps); dangerously low values are still caught by the
    # reference-range check (< 40 bpm).
    "heart_rate": MetricRule("heart_rate", "high", 3.5, 3.0, 10.0, 15.0),
    "respiratory_rate": MetricRule("respiratory_rate", "high", 3.5, 2.5, 4.0, 20.0),
    "spo2": MetricRule("spo2", "low", 3.5, 2.5, 2.0, 2.0),
    "temperature": MetricRule("temperature", "both", 3.5, 3.0, 0.5, 1.2),
}

PERSISTENCE_READINGS = 4  # consecutive candidate readings before flagging
CLEAR_READINGS = 3  # consecutive normal readings before clearing


def activity_context(effective_intensity: float, is_asleep: bool) -> str:
    if is_asleep:
        return "asleep"
    if effective_intensity < 0.1:
        return "at rest"
    if effective_intensity < 0.3:
        return "during light activity"
    if effective_intensity < 0.55:
        return "during moderate activity"
    return "during high activity"


@dataclass(frozen=True)
class Expectation:
    low: float
    high: float
    spread: float


def expected_values(
    baseline: Baseline,
    effective_intensity: float,
    lagging_intensity: float,
    slow_intensity: float,
    is_asleep: bool,
) -> dict[str, Expectation]:
    """Expected band and personal spread for each vital in the current context.

    The band spans the vital's value at the *lagging* activity context (how
    little exertion the body may still be reflecting) and at the *effective*
    context (how much). While activity is steady the band collapses to a
    single value; when activity starts or stops it widens, so the normal lag
    of heart rate behind movement is not treated as an anomaly.
    """
    if is_asleep:
        return {
            "heart_rate": Expectation(baseline.hr_sleep, baseline.hr_sleep, baseline.hr_rest_spread),
            "respiratory_rate": Expectation(baseline.rr_sleep, baseline.rr_sleep, baseline.rr_rest_spread),
            "spo2": Expectation(baseline.spo2, baseline.spo2, baseline.spo2_spread),
            "temperature": Expectation(baseline.temp_sleep, baseline.temp_sleep, baseline.temp_spread),
        }
    lo_i, hi_i = sorted((lagging_intensity, effective_intensity))
    # Variability grows with exertion, so widen the tolerance with intensity.
    widen = 1.0 + 2.0 * hi_i
    hr = [target_heart_rate(baseline.hr_rest, baseline.hr_max_est, i) for i in (lo_i, hi_i)]
    rr = [target_respiratory_rate(baseline.rr_rest, i) for i in (lo_i, hi_i)]
    spo2 = [baseline.spo2 - SPO2_DROP_PER_INTENSITY * i for i in (hi_i, lo_i)]
    temp = baseline.temp_awake + TEMP_GAIN_PER_INTENSITY * slow_intensity
    return {
        "heart_rate": Expectation(hr[0], hr[1], baseline.hr_rest_spread * widen),
        "respiratory_rate": Expectation(rr[0], rr[1], baseline.rr_rest_spread * widen),
        "spo2": Expectation(spo2[0], spo2[1], baseline.spo2_spread * widen),
        "temperature": Expectation(temp, temp, baseline.temp_spread * (1.0 + slow_intensity)),
    }


def reference_range_flag(metric: str, value: float, context: str) -> str | None:
    """General adult reference ranges, used as a secondary, population-level check.

    These are *not* diagnostic thresholds; they simply mark values that are
    unusual for most adults regardless of personal baseline.
    """
    at_rest = context in ("at rest", "asleep")
    if metric == "spo2" and value < 92.0:
        return "below 92%, outside the typical adult range"
    if metric == "temperature" and value >= 38.0:
        return "at or above 38.0 °C, outside the typical adult range"
    if metric == "temperature" and value <= 35.0:
        return "at or below 35.0 °C, outside the typical adult range"
    if metric == "heart_rate" and at_rest and value > 120.0:
        return "above 120 bpm while at rest, outside the typical adult range"
    if metric == "heart_rate" and value < 40.0:
        return "below 40 bpm, outside the typical adult range"
    if metric == "respiratory_rate" and at_rest and value > 25.0:
        return "above 25 br/min while at rest, outside the typical adult range"
    return None


def _fmt(metric: str, value: float) -> str:
    unit = METRIC_UNITS[metric]
    if metric == "temperature":
        return f"{value:.1f} {unit}"
    if metric == "spo2":
        return f"{value:.1f}{unit}"
    return f"{value:.0f} {unit}"


def _duration_text(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {sec} s" if sec else f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min"


@dataclass
class _MetricTracker:
    status: str = "normal"
    candidate_count: int = 0
    normal_count: int = 0
    streak_start: datetime | None = None


class AnomalyDetector:
    """Stateful per-twin detector (keeps persistence counters between readings)."""

    def __init__(self) -> None:
        self._trackers: dict[str, _MetricTracker] = {m: _MetricTracker() for m in RULES}

    def reset(self) -> None:
        self._trackers = {m: _MetricTracker() for m in RULES}

    def assess(
        self,
        obs: Observation,
        baseline: Baseline,
        effective_intensity: float,
        slow_intensity: float,
        lagging_intensity: float | None = None,
    ) -> dict[str, MetricAssessment]:
        if lagging_intensity is None:
            lagging_intensity = effective_intensity
        context = activity_context(effective_intensity, obs.is_asleep)
        expectations = expected_values(
            baseline, effective_intensity, lagging_intensity, slow_intensity, obs.is_asleep
        )
        results: dict[str, MetricAssessment] = {}
        for metric, rule in RULES.items():
            raw = getattr(obs, metric)
            if raw is None:  # not measured by this source: never assessed
                continue
            value = float(raw)
            results[metric] = self._assess_metric(
                obs.timestamp, rule, value, expectations[metric], context
            )
        return results

    def _assess_metric(
        self,
        timestamp: datetime,
        rule: MetricRule,
        value: float,
        band: Expectation,
        context: str,
    ) -> MetricAssessment:
        if value > band.high:
            expected = band.high
        elif value < band.low:
            expected = band.low
        else:
            expected = (band.low + band.high) / 2.0
        deviation = value - expected if (value > band.high or value < band.low) else 0.0
        deviation_pct = 100.0 * deviation / expected if expected else 0.0
        z = deviation / band.spread if band.spread > 0 else 0.0

        # Only count deviations in the direction this metric cares about.
        if rule.direction == "high":
            directed_z, directed_abs, directed_pct = z, deviation, deviation_pct
        elif rule.direction == "low":
            directed_z, directed_abs, directed_pct = -z, -deviation, -deviation_pct
        else:
            directed_z, directed_abs, directed_pct = abs(z), abs(deviation), abs(deviation_pct)

        reference = reference_range_flag(rule.metric, value, context)
        candidate = (
            directed_z >= rule.z_anomalous
            and directed_abs >= rule.min_abs_change
            and directed_pct >= rule.min_pct_change
        ) or reference is not None
        watch = directed_z >= rule.z_watch and directed_abs >= rule.min_abs_change / 2

        tracker = self._trackers[rule.metric]
        if candidate:
            if tracker.candidate_count == 0:
                tracker.streak_start = timestamp
            tracker.candidate_count += 1
            tracker.normal_count = 0
        else:
            tracker.candidate_count = 0
            if tracker.status == "anomalous" and not watch:
                tracker.normal_count += 1
            elif tracker.status != "anomalous":
                tracker.streak_start = None

        if tracker.status == "anomalous":
            if tracker.normal_count >= CLEAR_READINGS:
                tracker.status = "normal"
                tracker.normal_count = 0
                tracker.streak_start = None
        elif tracker.candidate_count >= PERSISTENCE_READINGS:
            tracker.status = "anomalous"

        if tracker.status == "anomalous":
            status = "anomalous"
        elif watch or candidate:
            status = "watch"
        else:
            status = "normal"

        reason = None
        if status != "normal":
            reason = self._explain(
                rule.metric, status, value, expected, deviation_pct, context, tracker, timestamp, reference
            )

        return MetricAssessment(
            metric=rule.metric,
            value=round(value, 2),
            expected=round(expected, 2),
            expected_low=round(band.low, 2),
            expected_high=round(band.high, 2),
            deviation=round(deviation, 2),
            deviation_pct=round(deviation_pct, 1),
            robust_z=round(z, 2),
            status=status,
            consecutive=tracker.candidate_count,
            context=context,
            reason=reason,
            reference_flag=reference,
        )

    @staticmethod
    def _explain(
        metric: str,
        status: str,
        value: float,
        expected: float,
        deviation_pct: float,
        context: str,
        tracker: _MetricTracker,
        timestamp: datetime,
        reference: str | None,
    ) -> str:
        label = METRIC_LABELS[metric]
        direction = "above" if deviation_pct >= 0 else "below"
        core = (
            f"{label} {_fmt(metric, value)} is {abs(deviation_pct):.0f}% {direction} the "
            f"{_fmt(metric, expected)} expected for this subject {context}"
        )
        if status == "anomalous":
            if tracker.streak_start is not None and tracker.candidate_count > 0:
                elapsed = (timestamp - tracker.streak_start).total_seconds()
                core += (
                    f", for {tracker.candidate_count} consecutive readings"
                    f" ({_duration_text(elapsed)})"
                )
            else:
                core += " (persisting; returning towards normal)"
        else:
            core += " (monitoring; not yet persistent)"
        if reference:
            core += f"; value is {reference}"
        return core + "."
