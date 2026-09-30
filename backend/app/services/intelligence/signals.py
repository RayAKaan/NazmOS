"""Deterministic signal detection.

Every detector is a pure function of a :class:`BusinessContext` (which is itself
a projection of canonical Orbit state). Detectors:

- never call Jev / any AI provider
- never mutate business state
- never execute anything
- are independently testable
- carry a ``version`` so historical signals remain distinguishable
- return evidence ids and an evidence-based confidence
- emit an explicit insufficient-data signal when the required Orbit metric is
  absent (never substitute zero)

Detected entirely from Orbit's canonical output:
    health_breakdown.{sales,inventory,margins,procurement,data_quality}
    exposures.{capital_exposed,revenue_at_risk,gross_profit_at_risk,recoverable}
    findings[] / opportunities[] / limitations[] / evidence{}
    historical health_score series (for baselines)
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional
from uuid import UUID

from app.services.intelligence import baseline as bl
from app.services.intelligence.contracts import (
    BusinessContext,
    FreshnessStatus,
    Signal,
    SignalSeverity,
    SignalStatus,
    make_signal_fingerprint,
)

DETECTOR_VERSION = "detectors-v1"

# Deterministic severity ladders. Thresholds are business policy, not tuning.
REVENUE_DECLINE_WARNING_PCT = -15.0
REVENUE_DECLINE_CRITICAL_PCT = -30.0
REVENUE_SPIKE_CRITICAL_PCT = 40.0
HEALTH_DROP_WARNING = 10
HEALTH_DROP_CRITICAL = 20
EXPOSURE_SPIKE_WARNING_PCT = 25.0
EXPOSURE_SPIKE_CRITICAL_PCT = 60.0
DOMAIN_SCORE_WARNING = 60
DOMAIN_SCORE_CRITICAL = 40
DATA_QUALITY_WARNING = 0.6
RECOVERABLE_CONFIDENCE_FLOOR = 0.2

# Domain -> the Orbit health_breakdown key it is derived from.
DOMAIN_BREAKDOWN_KEY = {
    "sales": "sales",
    "margin": "margins",
    "inventory": "inventory",
    "procurement": "procurement",
    "data_quality": "data_quality",
}


class SignalInsufficientData:
    """Marker for a detector that cannot judge because Orbit data is absent.

    Detectors return one of these instead of a Signal when the required canonical
    Orbit metric is missing, so "missing" can never be silently rendered as zero.
    """

    __slots__ = ("domain", "metric", "reason", "detector_name")

    def __init__(self, domain: str, metric: str, reason: str, detector_name: str) -> None:
        self.domain = domain
        self.metric = metric
        self.reason = reason
        self.detector_name = detector_name

    @property
    def sufficient(self) -> bool:
        return False

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"SignalInsufficientData(domain={self.domain!r}, metric={self.metric!r}, "
            f"reason={self.reason!r}, detector={self.detector_name!r})"
        )


def insufficient(domain: str, metric: str, reason: str, detector: str) -> SignalInsufficientData:
    return SignalInsufficientData(domain, metric, reason, detector)


def _domain_score(context: BusinessContext, key: str) -> tuple[Optional[int], list[str], str]:
    """Read a domain score from Orbit's health_breakdown.

    Returns ``(score, evidence_ids, confidence)``; ``score is None`` when Orbit did
    not produce that domain score.
    """
    breakdown = context.health_breakdown or {}
    if not isinstance(breakdown, dict):
        return None, [], "UNKNOWN"
    raw = breakdown.get(key)
    if raw is None:
        return None, [], "UNKNOWN"
    if isinstance(raw, dict):
        score = raw.get("score")
        confidence = str(raw.get("confidence") or "MEDIUM")
        evidence = raw.get("evidence_ids") or []
    else:
        score = raw
        confidence = "MEDIUM"
        evidence = []
    if score is None:
        return None, [], "UNKNOWN"
    try:
        return int(score), [str(e) for e in evidence], confidence
    except (TypeError, ValueError):
        return None, [], "UNKNOWN"


def _exposure_value(context: BusinessContext, key: str) -> tuple[Optional[float], list[str]]:
    """Read one of Orbit's exposure metrics. ``None`` when unavailable."""
    exposures = context.exposures or {}
    if not isinstance(exposures, dict):
        return None, []
    raw = exposures.get(key)
    if raw is None:
        return None, []
    if isinstance(raw, (int, float)):
        return float(raw), []
    if isinstance(raw, dict):
        value = raw.get("value")
        evidence = raw.get("evidence_ids") or []
        if value is None:
            return None, []
        try:
            return float(value), [str(e) for e in evidence]
        except (TypeError, ValueError):
            return None, []
    return None, []


def _health_series(context: BusinessContext) -> list[float]:
    series = (context.historical_metrics or {}).get("health_score_series") or []
    values: list[float] = []
    for row in series:
        if row.get("audit_id") == context.state_version:
            continue  # exclude current audit from its own baseline
        score = row.get("health_score")
        if score is None:
            continue
        try:
            values.append(float(score))
        except (TypeError, ValueError):
            continue
    return values


def _domain_series(context: BusinessContext, key: str) -> list[float]:
    """Historical series for a single Orbit domain score, if Orbit stored it."""
    series = (context.historical_metrics or {}).get("domain_score_series") or {}
    values: list[float] = []
    for row in series.get(key, []) or []:
        if row.get("audit_id") == context.state_version:
            continue
        score = row.get("score")
        if score is None:
            continue
        try:
            values.append(float(score))
        except (TypeError, ValueError):
            continue
    return values


def _base_signal(
    context: BusinessContext,
    *,
    signal_type: str,
    domain: str,
    metric: str,
    observed: float,
    baseline: bl.Baseline,
    severity: SignalSeverity,
    confidence: float,
    resource: str,
    detector_name: str,
) -> Signal:
    dev, dev_pct, computable = bl.deviation(observed, baseline)
    return Signal(
        business_id=context.business_id,
        state_version=context.state_version,
        signal_type=signal_type,
        domain=domain,
        metric=metric,
        observed_value=observed,
        baseline_value=baseline.value if baseline.value is not None else 0.0,
        baseline_type=baseline.baseline_type.value,
        baseline_formula=baseline.describe(),
        deviation=round(dev, 6),
        deviation_percent=round(dev_pct, 4),
        severity=severity,
        confidence=round(confidence, 4),
        detected_at=datetime.utcnow(),
        evidence_ids=list(context.evidence_ids),
        freshness=context.data_freshness,
        status=SignalStatus.DETECTED,
        detector_version=DETECTOR_VERSION,
        detector_name=detector_name,
        fingerprint=make_signal_fingerprint(
            context.business_id, signal_type, resource, DETECTOR_VERSION, context.state_version
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# SALES
# ─────────────────────────────────────────────────────────────────────────────

def detect_sales_trend(context: BusinessContext) -> list[Signal]:
    """Detect sales-health regression using Orbit's sales domain score."""
    score, evidence, orbit_conf = _domain_score(context, DOMAIN_BREAKDOWN_KEY["sales"])
    if score is None:
        return [insufficient("sales", "health_breakdown.sales.score", "orbit_domain_score_absent", "sales_trend")]  # type: ignore[list-item]

    prior = _domain_series(context, "sales")
    base = bl.rolling_mean(prior, window=3) if prior else bl.threshold(
        DOMAIN_SCORE_WARNING, rule="fixed domain health floor (no history)"
    )
    if not base.available:
        return [insufficient("sales", "health_breakdown.sales.score", base.reason, "sales_trend")]  # type: ignore[list-item]

    severity = (
        SignalSeverity.CRITICAL if score <= DOMAIN_SCORE_CRITICAL
        else SignalSeverity.WARNING if score <= DOMAIN_SCORE_WARNING
        else SignalSeverity.INFO
    )
    if base.baseline_type is bl.BaselineType.THRESHOLD:
        return []

    # Only emit when the current score is materially below the baseline.
    dev, dev_pct, computable = bl.deviation(float(score), base)
    if not computable or dev >= 0:
        return []

    drop = abs(dev)
    severity = (
        SignalSeverity.CRITICAL if drop >= HEALTH_DROP_CRITICAL
        else SignalSeverity.WARNING if drop >= HEALTH_DROP_WARNING
        else SignalSeverity.INFO
    )
    if severity is SignalSeverity.INFO:
        return []

    confidence = 0.8 if len(prior) >= 3 else 0.6
    return [
        _base_signal(
            context,
            signal_type="sales_health_decline",
            domain="sales",
            metric="health_breakdown.sales.score",
            observed=float(score),
            baseline=base,
            severity=severity,
            confidence=confidence,
            resource="business",
            detector_name="sales_trend",
        )
    ]


def detect_revenue_decline(context: BusinessContext) -> list[Signal]:
    """Detect revenue decline when Orbit recorded a revenue exposure baseline."""
    observed, evidence = _exposure_value(context, "revenue_at_risk_sar")
    if observed is None:
        return [insufficient("sales", "exposures.revenue_at_risk_sar", "orbit_exposure_absent", "revenue_decline")]  # type: ignore[list-item]
    # Without a prior-period revenue exposure we cannot assert a *decline*; we
    # report the level as info-only rather than inventing a comparison.
    return [
        Signal(
            business_id=context.business_id,
            state_version=context.state_version,
            signal_type="revenue_at_risk_observed",
            domain="sales",
            metric="exposures.revenue_at_risk_sar",
            observed_value=observed,
            baseline_value=observed,
            baseline_type=bl.BaselineType.CURRENT_PERIOD.value,
            baseline_formula="current Orbit exposure level (no prior period available)",
            deviation=0.0,
            deviation_percent=0.0,
            severity=SignalSeverity.INFO,
            confidence=0.5,
            detected_at=datetime.utcnow(),
            evidence_ids=evidence or list(context.evidence_ids),
            freshness=context.data_freshness,
            status=SignalStatus.DETECTED,
            detector_version=DETECTOR_VERSION,
            detector_name="revenue_decline",
            fingerprint=make_signal_fingerprint(
                context.business_id, "revenue_at_risk_observed", "business", DETECTOR_VERSION, context.state_version
            ),
        )
    ]


# ─────────────────────────────────────────────────────────────────────────────
# MARGIN
# ─────────────────────────────────────────────────────────────────────────────

def detect_margin_erosion(context: BusinessContext) -> list[Signal]:
    """Detect margin-health regression using Orbit's margins domain score."""
    score, evidence, orbit_conf = _domain_score(context, DOMAIN_BREAKDOWN_KEY["margin"])
    if score is None:
        return [insufficient("margin", "health_breakdown.margins.score", "orbit_domain_score_absent", "margin_erosion")]  # type: ignore[list-item]

    prior = _domain_series(context, "margins")
    base = bl.rolling_mean(prior, window=3) if prior else bl.unavailable(
        bl.BaselineType.ROLLING_MEAN, "no_prior_domain_scores"
    )
    if not base.available:
        level = (
            SignalSeverity.CRITICAL if score <= DOMAIN_SCORE_CRITICAL
            else SignalSeverity.WARNING if score <= DOMAIN_SCORE_WARNING
            else SignalSeverity.INFO
        )
        if level is SignalSeverity.INFO:
            return []
        # No baseline: report the *level* honestly, flagging the missing baseline.
        return [
            _base_signal(
                context,
                signal_type="margin_health_low",
                domain="margin",
                metric="health_breakdown.margins.score",
                observed=float(score),
                baseline=bl.threshold(DOMAIN_SCORE_WARNING, rule="fixed domain health floor"),
                severity=level,
                confidence=0.5,
                resource="business",
                detector_name="margin_erosion",
            )
        ]

    dev, dev_pct, computable = bl.deviation(float(score), base)
    if not computable or dev >= 0:
        return []
    drop = abs(dev)
    if drop < HEALTH_DROP_WARNING / 2:
        return []
    severity = (
        SignalSeverity.CRITICAL if drop >= HEALTH_DROP_CRITICAL
        else SignalSeverity.WARNING
    )
    return [
        _base_signal(
            context,
            signal_type="margin_health_erosion",
            domain="margin",
            metric="health_breakdown.margins.score",
            observed=float(score),
            baseline=base,
            severity=severity,
            confidence=0.75 if len(prior) >= 3 else 0.55,
            resource="business",
            detector_name="margin_erosion",
        )
    ]


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY
# ─────────────────────────────────────────────────────────────────────────────

def detect_excess_inventory(context: BusinessContext) -> list[Signal]:
    """Detect trapped capital from Orbit's capital exposure + recoverable range."""
    capital, capital_evidence = _exposure_value(context, "capital_exposed_sar")
    if capital is None:
        return [insufficient("inventory", "exposures.capital_exposed_sar", "orbit_exposure_absent", "excess_inventory")]  # type: ignore[list-item]

    prior = _exposure_series(context, "capital_exposed_sar")
    base = bl.rolling_mean(prior, window=3) if prior else bl.unavailable(
        bl.BaselineType.ROLLING_MEAN, "no_prior_exposures"
    )

    severity = SignalSeverity.WARNING
    if base.available:
        dev, dev_pct, computable = bl.deviation(capital, base)
        if computable and dev_pct >= EXPOSURE_SPIKE_CRITICAL_PCT:
            severity = SignalSeverity.CRITICAL
        elif computable and dev_pct >= EXPOSURE_SPIKE_WARNING_PCT:
            severity = SignalSeverity.WARNING
        else:
            return []
        confidence = 0.8 if len(prior) >= 3 else 0.6
    else:
        # Absolute level only, with explicitly lower confidence.
        confidence = 0.5
        if capital >= 100_000:
            severity = SignalSeverity.CRITICAL
        elif capital >= 10_000:
            severity = SignalSeverity.WARNING
        else:
            return []

    return [
        _base_signal(
            context,
            signal_type="excess_inventory",
            domain="inventory",
            metric="exposures.capital_exposed_sar",
            observed=capital,
            baseline=base if base.available else bl.threshold(10_000.0, rule="fixed capital-exposure floor"),
            severity=severity,
            confidence=confidence,
            resource="business",
            detector_name="excess_inventory",
        )
    ]


def _exposure_series(context: BusinessContext, key: str) -> list[float]:
    series = (context.historical_metrics or {}).get("exposure_series") or {}
    values: list[float] = []
    for row in series.get(key, []) or []:
        if row.get("audit_id") == context.state_version:
            continue
        value = row.get("value")
        if value is None:
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return values


def detect_stockout_risk(context: BusinessContext) -> list[Signal]:
    """Detect stockout risk via Orbit's inventory domain score."""
    score, evidence, orbit_conf = _domain_score(context, DOMAIN_BREAKDOWN_KEY["inventory"])
    if score is None:
        return [insufficient("inventory", "health_breakdown.inventory.score", "orbit_domain_score_absent", "stockout_risk")]  # type: ignore[list-item]
    if score > DOMAIN_SCORE_WARNING:
        return []
    severity = SignalSeverity.CRITICAL if score <= DOMAIN_SCORE_CRITICAL else SignalSeverity.WARNING
    return [
        _base_signal(
            context,
            signal_type="stockout_risk",
            domain="inventory",
            metric="health_breakdown.inventory.score",
            observed=float(score),
            baseline=bl.threshold(DOMAIN_SCORE_WARNING, rule="fixed domain health ceiling"),
            severity=severity,
            confidence=0.7,
            resource="business",
            detector_name="stockout_risk",
        )
    ]


# ─────────────────────────────────────────────────────────────────────────────
# PROCUREMENT
# ─────────────────────────────────────────────────────────────────────────────

def detect_procurement_health(context: BusinessContext) -> list[Signal]:
    score, evidence, orbit_conf = _domain_score(context, DOMAIN_BREAKDOWN_KEY["procurement"])
    if score is None:
        return [insufficient("procurement", "health_breakdown.procurement.score", "orbit_domain_score_absent", "procurement_health")]  # type: ignore[list-item]
    if score > DOMAIN_SCORE_WARNING:
        return []
    severity = SignalSeverity.CRITICAL if score <= DOMAIN_SCORE_CRITICAL else SignalSeverity.WARNING
    return [
        _base_signal(
            context,
            signal_type="procurement_health_low",
            domain="procurement",
            metric="health_breakdown.procurement.score",
            observed=float(score),
            baseline=bl.threshold(DOMAIN_SCORE_WARNING, rule="fixed domain health ceiling"),
            severity=severity,
            confidence=0.65,
            resource="business",
            detector_name="procurement_health",
        )
    ]


# ─────────────────────────────────────────────────────────────────────────────
# FINANCIAL
# ─────────────────────────────────────────────────────────────────────────────

def detect_profit_at_risk(context: BusinessContext) -> list[Signal]:
    gpar, evidence = _exposure_value(context, "gross_profit_at_risk_sar")
    if gpar is None:
        return [insufficient("financial", "exposures.gross_profit_at_risk_sar", "orbit_exposure_absent", "profit_at_risk")]  # type: ignore[list-item]
    if gpar < 1:
        return []
    severity = SignalSeverity.CRITICAL if gpar >= 25_000 else SignalSeverity.WARNING
    return [
        _base_signal(
            context,
            signal_type="gross_profit_at_risk",
            domain="financial",
            metric="exposures.gross_profit_at_risk_sar",
            observed=gpar,
            baseline=bl.threshold(1.0, rule="non-zero gross profit at risk"),
            severity=severity,
            confidence=0.7,
            resource="business",
            detector_name="profit_at_risk",
        )
    ]


# ─────────────────────────────────────────────────────────────────────────────
# DATA QUALITY
# ─────────────────────────────────────────────────────────────────────────────

def detect_data_quality_gaps(context: BusinessContext) -> list[Signal]:
    """Emit an explicit data-quality signal from Orbit's own limitations."""
    limitations = context.limitations or {}
    dont_know = limitations.get("we_dont_know") or []
    estimate = limitations.get("we_estimate") or []
    if not isinstance(dont_know, list) or not isinstance(estimate, list):
        return [
            insufficient("data_quality", "limitations.we_dont_know", "malformed_limitations", "data_quality")  # type: ignore[list-item]
        ]

    gap = len(dont_know) + len(estimate)
    if gap == 0:
        return []

    observed = float(gap)
    severity = SignalSeverity.WARNING if gap < 3 else SignalSeverity.CRITICAL
    detail = (
        f"{len(dont_know)} unknown and {len(estimate)} estimated Orbit inputs"
    )
    return [
        Signal(
            business_id=context.business_id,
            state_version=context.state_version,
            signal_type="data_quality_gap",
            domain="data_quality",
            metric="limitations.we_dont_know+we_estimate",
            observed_value=observed,
            baseline_value=0.0,
            baseline_type=bl.BaselineType.THRESHOLD.value,
            baseline_formula="target: zero unknown/estimated Orbit inputs",
            deviation=observed,
            deviation_percent=0.0,
            severity=severity,
            confidence=0.9,
            detected_at=datetime.utcnow(),
            evidence_ids=list(context.evidence_ids),
            freshness=context.data_freshness,
            status=SignalStatus.DETECTED,
            detector_version=DETECTOR_VERSION,
            detector_name="data_quality_gap",
            fingerprint=make_signal_fingerprint(
                context.business_id, "data_quality_gap", "business", DETECTOR_VERSION, context.state_version
            ),
        )
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Overall health
# ─────────────────────────────────────────────────────────────────────────────

def detect_health_deterioration(context: BusinessContext) -> list[Signal]:
    """Detect overall business-health regression against Orbit history."""
    if context.health_score is None:
        return [insufficient("financial", "health_score", "orbit_health_score_absent", "health_deterioration")]  # type: ignore[list-item]
    prior = _health_series(context)
    if len(prior) < 2:
        return [insufficient("financial", "health_score", f"insufficient_history({len(prior)}<2)", "health_deterioration")]  # type: ignore[list-item]
    base = bl.rolling_mean(prior, window=3)
    dev, dev_pct, computable = bl.deviation(float(context.health_score), base)
    if not computable or dev >= 0:
        return []
    drop = abs(dev)
    if drop < HEALTH_DROP_WARNING / 2:
        return []
    severity = SignalSeverity.CRITICAL if drop >= HEALTH_DROP_CRITICAL else SignalSeverity.WARNING
    return [
        _base_signal(
            context,
            signal_type="health_deterioration",
            domain="financial",
            metric="health_score",
            observed=float(context.health_score),
            baseline=base,
            severity=severity,
            confidence=0.75,
            resource="business",
            detector_name="health_deterioration",
        )
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

DetectorFn = Callable[[BusinessContext], list]

DETECTOR_REGISTRY: dict[str, DetectorFn] = {
    "health_deterioration": detect_health_deterioration,
    "sales_trend": detect_sales_trend,
    "revenue_decline": detect_revenue_decline,
    "margin_erosion": detect_margin_erosion,
    "excess_inventory": detect_excess_inventory,
    "stockout_risk": detect_stockout_risk,
    "procurement_health": detect_procurement_health,
    "profit_at_risk": detect_profit_at_risk,
    "data_quality_gap": detect_data_quality_gaps,
}

DETECTOR_VERSION_CONSTANT = DETECTOR_VERSION


def run_detectors(
    context: BusinessContext,
    *,
    only: Optional[list[str]] = None,
) -> tuple[list[Signal], list[SignalInsufficientData]]:
    """Run the detector registry against a context.

    Failure isolation: one detector raising must not corrupt the run. The failing
    detector is reported to the caller and the run continues. A detector that
    cannot judge returns a :class:`SignalInsufficientData` marker instead of a
    fabricated signal.
    """
    signals: list[Signal] = []
    insufficients: list[SignalInsufficientData] = []
    names = only or list(DETECTOR_REGISTRY)
    for name in names:
        fn = DETECTOR_REGISTRY.get(name)
        if fn is None:
            continue
        try:
            results = fn(context) or []
        except Exception as exc:  # pragma: no cover - defensive isolation
            raise DetectorFailure(name, str(exc)) from exc
        for item in results:
            if isinstance(item, SignalInsufficientData):
                insufficients.append(item)
            elif isinstance(item, Signal):
                signals.append(item)
    return signals, insufficients


class DetectorFailure(RuntimeError):
    """Raised when a detector itself fails (bug or unexpected data shape)."""

    def __init__(self, detector: str, message: str) -> None:
        super().__init__(f"detector {detector} failed: {message}")
        self.detector = detector
        self.message = message
