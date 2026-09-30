"""Reusable, deterministic baseline engine for signal detection.

A baseline answers: "compared to what?". Every baseline is explicit, versioned
and states its own formula so a signal's deviation is never a black box.

Supported baseline types (no statistical forecasting here — only deterministic
ladders over data Orbit already has):

    CURRENT_PERIOD, PREVIOUS_PERIOD, ROLLING_MEAN, ROLLING_MEDIAN,
    TREND, EXPECTED_RANGE, THRESHOLD, SEASONAL_BASELINE

Invariant: when there is not enough data to build a baseline, the result is
``available=False``. Detectors MUST emit an insufficient-data signal in that
case rather than comparing a period against itself or against zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import median, pstdev
from typing import Optional, Sequence

BASELINE_ENGINE_VERSION = "baseline-v1"


class BaselineType(str, Enum):
    CURRENT_PERIOD = "CURRENT_PERIOD"
    PREVIOUS_PERIOD = "PREVIOUS_PERIOD"
    ROLLING_MEAN = "ROLLING_MEAN"
    ROLLING_MEDIAN = "ROLLING_MEDIAN"
    TREND = "TREND"
    EXPECTED_RANGE = "EXPECTED_RANGE"
    THRESHOLD = "THRESHOLD"
    SEASONAL_BASELINE = "SEASONAL_BASELINE"


@dataclass(frozen=True)
class Baseline:
    """An explicit, inspectable baseline.

    ``available=False`` means the baseline could not be constructed. ``reason``
    carries the deterministic explanation (e.g. "no_prior_periods") so the
    resulting signal is self-documenting.
    """

    baseline_type: BaselineType
    value: Optional[float]
    available: bool
    reason: str = ""
    formula: str = ""
    sample_size: int = 0
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    version: str = BASELINE_ENGINE_VERSION

    def describe(self) -> str:
        if not self.available:
            return f"{self.baseline_type.value}: unavailable ({self.reason})"
        return (
            f"{self.baseline_type.value}={self.value:.4f} "
            f"via {self.formula} (n={self.sample_size})"
        )


def unavailable(baseline_type: BaselineType, reason: str) -> Baseline:
    return Baseline(
        baseline_type=baseline_type,
        value=None,
        available=False,
        reason=reason,
        formula="",
        sample_size=0,
    )


def previous_period(observations: Sequence[float]) -> Baseline:
    """Baseline = the most recent prior observation."""
    if not observations:
        return unavailable(BaselineType.PREVIOUS_PERIOD, "no_prior_periods")
    return Baseline(
        baseline_type=BaselineType.PREVIOUS_PERIOD,
        value=float(observations[-1]),
        available=True,
        formula="most recent prior Orbit audit",
        sample_size=1,
    )


def rolling_mean(observations: Sequence[float], window: int = 3) -> Baseline:
    if not observations:
        return unavailable(BaselineType.ROLLING_MEAN, "no_history")
    sample = [float(v) for v in observations[-window:]]
    return Baseline(
        baseline_type=BaselineType.ROLLING_MEAN,
        value=sum(sample) / len(sample),
        available=True,
        formula=f"mean of last {len(sample)} Orbit audits",
        sample_size=len(sample),
    )


def rolling_median(observations: Sequence[float], window: int = 3) -> Baseline:
    if not observations:
        return unavailable(BaselineType.ROLLING_MEDIAN, "no_history")
    sample = [float(v) for v in observations[-window:]]
    return Baseline(
        baseline_type=BaselineType.ROLLING_MEDIAN,
        value=float(median(sample)),
        available=True,
        formula=f"median of last {len(sample)} Orbit audits",
        sample_size=len(sample),
    )


def trend(observations: Sequence[float], min_points: int = 3) -> Baseline:
    """Least-squares slope per period, expressed as a baseline value.

    With fewer than ``min_points`` observations a trend is not defensible, so the
    baseline is unavailable rather than approximated.
    """
    if len(observations) < min_points:
        return unavailable(
            BaselineType.TREND,
            f"insufficient_history({len(observations)}<{min_points})",
        )
    n = len(observations)
    xs = list(range(n))
    ys = [float(v) for v in observations]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return unavailable(BaselineType.TREND, "degenerate_history")
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    return Baseline(
        baseline_type=BaselineType.TREND,
        value=slope,
        available=True,
        formula=f"least-squares slope over {n} Orbit audits (units/audit)",
        sample_size=n,
    )


def expected_range(
    observations: Sequence[float],
    *,
    window: int = 5,
    sigma: float = 2.0,
) -> Baseline:
    """Expected band as mean ± sigma·(population stdev).

    A single observation has zero dispersion, which would make any deviation
    look extreme; we require at least two points and say so otherwise.
    """
    if len(observations) < 2:
        return unavailable(
            BaselineType.EXPECTED_RANGE,
            f"insufficient_history({len(observations)}<2)",
        )
    sample = [float(v) for v in observations[-window:]]
    mean = sum(sample) / len(sample)
    spread = pstdev(sample)
    return Baseline(
        baseline_type=BaselineType.EXPECTED_RANGE,
        value=mean,
        available=True,
        formula=f"mean ± {sigma:g}·σ over last {len(sample)} audits",
        sample_size=len(sample),
        lower_bound=mean - sigma * spread,
        upper_bound=mean + sigma * spread,
    )


def threshold(value: float, *, rule: str) -> Baseline:
    """Fixed deterministic threshold baseline."""
    return Baseline(
        baseline_type=BaselineType.THRESHOLD,
        value=float(value),
        available=True,
        formula=rule,
        sample_size=0,
    )


def seasonal_baseline(
    observations: Sequence[float],
    *,
    period: int = 7,
) -> Baseline:
    """Seasonal baseline: mean of observations at the same phase of the period.

    Requires at least a full period of history; otherwise unavailable.
    """
    if len(observations) < period:
        return unavailable(
            BaselineType.SEASONAL_BASELINE,
            f"insufficient_history({len(observations)}<{period})",
        )
    obs = [float(v) for v in observations]
    phase = len(obs) % period
    same_phase = obs[phase::period]
    if not same_phase:
        return unavailable(BaselineType.SEASONAL_BASELINE, "no_matching_phase")
    return Baseline(
        baseline_type=BaselineType.SEASONAL_BASELINE,
        value=sum(same_phase) / len(same_phase),
        available=True,
        formula=f"mean of {len(same_phase)} observations at phase {phase} of {period}",
        sample_size=len(same_phase),
    )


def deviation(observed: Optional[float], baseline: Baseline) -> tuple[float, float, bool]:
    """Return ``(deviation, deviation_percent, computable)``.

    ``computable=False`` means the caller must not claim a deviation. A zero
    baseline yields absolute deviation only (percent is undefined, not 0%).
    """
    if observed is None or not baseline.available or baseline.value is None:
        return 0.0, 0.0, False
    diff = float(observed) - float(baseline.value)
    if baseline.value == 0:
        return diff, 0.0, True
    return diff, (diff / abs(float(baseline.value))) * 100.0, True
