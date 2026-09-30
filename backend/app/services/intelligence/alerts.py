"""Alert generation with deterministic deduplication.

An unresolved signal must **update** its existing alert rather than create a new
one on every monitoring cycle. Identity is a deterministic fingerprint over:

    business + alert_type + signal_type + affected resource + detector_version

Fingerprinting deliberately excludes ``state_version`` so the same underlying
business issue stays one alert across Orbit re-audits, while a genuinely different
issue (different signal type / resource / detector) produces a distinct alert.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.services.intelligence.contracts import (
    Alert,
    AlertSeverity,
    AlertStatus,
    Recommendation,
    Signal,
    SignalSeverity,
    make_alert_fingerprint,
)

ALERT_VERSION = "alerts-v1"

ALERT_TTL_HOURS = 168  # 7 days

SEVERITY_FROM_SIGNAL: dict[SignalSeverity, AlertSeverity] = {
    SignalSeverity.CRITICAL: AlertSeverity.CRITICAL,
    SignalSeverity.WARNING: AlertSeverity.WARNING,
    SignalSeverity.INFO: AlertSeverity.INFO,
}

# Human-readable signal titles. Kept explicit (no fabricated narrative).
SIGNAL_TITLES: dict[str, str] = {
    "excess_inventory": "Excess inventory is tying up capital",
    "stockout_risk": "Stockout risk detected",
    "margin_health_erosion": "Margin health is eroding",
    "margin_health_low": "Margin health is low",
    "procurement_health_low": "Procurement health is low",
    "sales_health_decline": "Sales health is declining",
    "health_deterioration": "Overall business health is deteriorating",
    "gross_profit_at_risk": "Gross profit is at risk",
    "revenue_at_risk_observed": "Revenue at risk (level observed)",
    "data_quality_gap": "Data quality is limiting analysis",
}


def alert_for_signal(signal: Signal) -> Optional[Alert]:
    """Derive an alert from a signal, or ``None`` for info-only signals.

    INFO signals do not raise alerts — an alert system that fires on everything
    is noise, not intelligence.
    """
    if signal.severity is SignalSeverity.INFO:
        return None

    resource = signal.domain
    alert_type = str(signal.severity.value).upper()
    title = SIGNAL_TITLES.get(signal.signal_type, signal.signal_type.replace("_", " ").title())
    description = (
        f"{signal.signal_type} detected in {signal.domain} by "
        f"{signal.detector_name} ({signal.detector_version}). "
        f"{signal.metric}={signal.observed_value:g}; {signal.baseline_formula}."
    )
    if signal.freshness.value != "fresh":
        description += f" Data freshness is {signal.freshness.value}."

    from datetime import timedelta

    return Alert(
        business_id=signal.business_id,
        severity=SEVERITY_FROM_SIGNAL[signal.severity],
        alert_type=alert_type,
        title=title,
        description=description,
        signal_id=signal.signal_id,
        evidence_ids=list(signal.evidence_ids),
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=ALERT_TTL_HOURS),
        status=AlertStatus.OPEN,
        fingerprint=make_alert_fingerprint(
            signal.business_id,
            alert_type,
            signal.signal_type,
            resource,
            signal.detector_version,
        ),
    )


def alert_for_approval(recommendation: Recommendation) -> Optional[Alert]:
    """Alert that a recommendation requires owner approval."""
    if not recommendation.approval_required:
        return None
    if recommendation.action_type in ("REVIEW", "INFO_ONLY"):
        return None

    from datetime import timedelta

    return Alert(
        business_id=recommendation.business_id,
        severity=AlertSeverity.APPROVAL_REQUIRED,
        alert_type="APPROVAL_REQUIRED",
        title=f"Approval required: {recommendation.action_type}",
        description=recommendation.rationale,
        recommendation_id=recommendation.recommendation_id,
        evidence_ids=list(recommendation.evidence_ids),
        created_at=datetime.utcnow(),
        expires_at=recommendation.expires_at
        or (datetime.utcnow() + timedelta(hours=ALERT_TTL_HOURS)),
        status=AlertStatus.OPEN,
        fingerprint=make_alert_fingerprint(
            recommendation.business_id,
            "APPROVAL_REQUIRED",
            recommendation.action_type,
            str(recommendation.affected_resources[0] if recommendation.affected_resources else "business"),
            recommendation.recommendation_version,
        ),
    )


def alert_for_data_quality(signal: Signal) -> Optional[Alert]:
    """Data-quality alerts are always surfaced, even when the signal is INFO."""
    if signal.signal_type != "data_quality_gap":
        return None
    alert = alert_for_signal(signal)
    if alert is None:
        from datetime import timedelta

        return Alert(
            business_id=signal.business_id,
            severity=AlertSeverity.DATA_QUALITY,
            alert_type="DATA_QUALITY",
            title=SIGNAL_TITLES["data_quality_gap"],
            description=(
                f"{signal.observed_value:g} unknown/estimated Orbit inputs limit analysis. "
                "Recommendations are marked low confidence."
            ),
            signal_id=signal.signal_id,
            evidence_ids=list(signal.evidence_ids),
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=ALERT_TTL_HOURS),
            status=AlertStatus.OPEN,
            fingerprint=make_alert_fingerprint(
                signal.business_id,
                "DATA_QUALITY",
                signal.signal_type,
                "business",
                signal.detector_version,
            ),
        )
    # Re-type the alert so data quality is always visible under its own type.
    from dataclasses import replace

    return replace(
        alert,
        severity=AlertSeverity.DATA_QUALITY,
        alert_type="DATA_QUALITY",
    )


def dedupe(alerts: list[Alert]) -> list[Alert]:
    """Collapse alerts sharing a fingerprint, keeping the newest.

    Deterministic: within a single run the first occurrence of a fingerprint is
    kept, so repeated monitoring cycles converge instead of multiplying.
    """
    seen: dict[str, Alert] = {}
    for alert in alerts:
        key = alert.fingerprint or f"{alert.business_id}:{alert.alert_type}:{alert.title}"
        existing = seen.get(key)
        if existing is None:
            seen[key] = alert
            continue
        # Keep the most severe, then the most recent.
        if (alert.severity.value, alert.created_at) > (existing.severity.value, existing.created_at):
            seen[key] = alert
    return list(seen.values())


def build_alerts(
    signals: list[Signal],
    recommendations: list[Recommendation],
    *,
    max_alerts: int = 50,
) -> list[Alert]:
    """Build the alert set for one Intelligence run, deduplicated and bounded."""
    alerts: list[Alert] = []
    for signal in signals:
        data_quality = alert_for_data_quality(signal)
        if data_quality is not None:
            alerts.append(data_quality)
            continue
        alert = alert_for_signal(signal)
        if alert is not None:
            alerts.append(alert)
    for rec in recommendations:
        alert = alert_for_approval(rec)
        if alert is not None:
            alerts.append(alert)

    deduped = dedupe(alerts)
    # Deterministic ordering: severity, then creation time.
    order = {AlertSeverity.CRITICAL: 0, AlertSeverity.APPROVAL_REQUIRED: 1,
             AlertSeverity.EXECUTION_FAILED: 2, AlertSeverity.WARNING: 3,
             AlertSeverity.DATA_QUALITY: 4, AlertSeverity.OUTCOME_READY: 5,
             AlertSeverity.DECISION_REQUIRED: 6, AlertSeverity.INFO: 7}
    deduped.sort(key=lambda a: (order.get(a.severity, 9), -a.created_at.timestamp()))
    return deduped[:max_alerts]
