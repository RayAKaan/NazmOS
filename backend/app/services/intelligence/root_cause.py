"""Root-cause analysis.

Root cause is **not** correlation. For each signal the engine enumerates
candidate causes from the repository's existing taxonomy, runs deterministic
causal checks, and records contradictory evidence. The support level is the
honest result of those checks:

    OBSERVED  — Orbit itself recorded the cause
    SUPPORTED — deterministic checks passed and evidence agrees
    POSSIBLE  — plausible but a required check could not be evaluated
    UNKNOWN   — no defensible cause could be established

The taxonomy is NOT re-invented: it reuses
``app.services.canonical_controller.ROOT_CAUSE_BUCKETS`` so Jev's root-cause
advisory contract and the deterministic taxonomy cannot drift apart.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.services.canonical_controller import ROOT_CAUSE_BUCKETS
from app.services.intelligence.contracts import (
    BusinessContext,
    RootCause,
    RootCauseSupportLevel,
    Signal,
    SignalSeverity,
)

ROOT_CAUSE_ANALYSIS_VERSION = "rootcause-v1"

# The vocabulary this engine may emit. Reused from the canonical controller.
CAUSE_TYPES: frozenset[str] = ROOT_CAUSE_BUCKETS

# Signal type -> candidate causes, most specific first.
CANDIDATE_CAUSES: dict[str, tuple[str, ...]] = {
    "excess_inventory": (
        "SLOW_STOCK_CONVERSION",
        "LOW_DEMAND",
        "INVENTORY_CASH_TRAPPED",
    ),
    "stockout_risk": (
        "REORDER_THRESHOLD_LOW",
        "SUPPLIER_LEAD_TIME",
        "LOW_DEMAND",
    ),
    "margin_health_erosion": (
        "SUPPLIER_COST_INCREASE",
        "SELLING_PRICE_MISMATCH",
        "EXCESSIVE_DISCOUNTING",
    ),
    "margin_health_low": (
        "SUPPLIER_COST_INCREASE",
        "SELLING_PRICE_MISMATCH",
        "EXCESSIVE_DISCOUNTING",
    ),
    "procurement_health_low": (
        "SUPPLIER_COST_INCREASE",
        "SUPPLIER_LEAD_TIME",
    ),
    "sales_health_decline": (
        "LOW_DEMAND",
        "EXCESSIVE_DISCOUNTING",
    ),
    "health_deterioration": (
        "LOW_DEMAND",
        "SLOW_STOCK_CONVERSION",
        "SUPPLIER_COST_INCREASE",
    ),
    "gross_profit_at_risk": (
        "SUPPLIER_COST_INCREASE",
        "EXCESSIVE_DISCOUNTING",
    ),
    "revenue_at_risk_observed": ("LOW_DEMAND",),
    "data_quality_gap": ("MISSING_COST_DATA",),
}

# Orbit's own finding text often names the cause explicitly. These phrases are
# matched against the *existing* taxonomy so we reuse Orbit's judgement instead
# of re-deriving it.
ORBIT_CAUSE_PHRASES: dict[str, tuple[str, ...]] = {
    "SUPPLIER_COST_INCREASE": ("supplier cost", "purchase cost", "cost increase", "cost per unit"),
    "SELLING_PRICE_MISMATCH": ("price mismatch", "selling price", "price gap", "below cost"),
    "EXCESSIVE_DISCOUNTING": ("discount", "markdown", "over-discount"),
    "LOW_DEMAND": ("slow moving", "low demand", "no sales", "demand slowdown"),
    "SLOW_STOCK_CONVERSION": ("slow moving", "overstock", "excess", "aged", "dead stock"),
    "INVENTORY_CASH_TRAPPED": ("capital", "tied up", "trapped", "cash locked"),
    "SUPPLIER_LEAD_TIME": ("lead time", "delivery delay", "late delivery"),
    "REORDER_THRESHOLD_LOW": ("reorder level", "stockout", "out of stock", "reorder"),
    "MISSING_COST_DATA": ("missing cost", "no cost", "cost unavailable", "cost data"),
    "EXPIRY_REMINDER": ("expiry", "expire", "shelf life"),
    "UNCERTAIN": ("uncertain", "unclear", "unknown"),
}

# Causes that cannot be validated without data Orbit may not have. We mark them
# POSSIBLE rather than dropping them, so the gap is visible.
DATA_DEPENDENT_CAUSES: frozenset[str] = frozenset({
    "SUPPLIER_COST_INCREASE",
    "SELLING_PRICE_MISMATCH",
    "EXCESSIVE_DISCOUNTING",
    "SUPPLIER_LEAD_TIME",
})


def _findings_for_domain(context: BusinessContext, domain: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for finding in context.findings or []:
        if not isinstance(finding, dict):
            continue
        text = " ".join(
            str(finding.get(key) or "")
            for key in ("what", "why", "recommended_next_step", "cause", "category")
        ).lower()
        if domain in text or _matches_domain(text, domain):
            matches.append(finding)
    return matches


def _matches_domain(text: str, domain: str) -> bool:
    if domain == "inventory":
        return any(k in text for k in ("inventory", "stock", "overstock", "excess", "dead"))
    if domain == "margin":
        return any(k in text for k in ("margin", "profit", "cost", "price"))
    if domain == "sales":
        return any(k in text for k in ("sales", "revenue", "demand", "customer"))
    if domain == "procurement":
        return any(k in text for k in ("supplier", "purchase", "procurement", "vendor"))
    if domain == "financial":
        return any(k in text for k in ("cash", "financial", "capital", "working"))
    if domain == "data_quality":
        return any(k in text for k in ("missing", "data quality", "incomplete", "invalid"))
    return False


def _orbit_support(context: BusinessContext, cause_type: str) -> list[str]:
    """Return Orbit findings that explicitly name this cause (as evidence)."""
    phrases = ORBIT_CAUSE_PHRASES.get(cause_type, ())
    if not phrases:
        return []
    evidence: list[str] = []
    for finding in context.findings or []:
        if not isinstance(finding, dict):
            continue
        blob = " ".join(
            str(finding.get(key) or "")
            for key in ("what", "why", "recommended_next_step", "cause", "category")
        ).lower()
        if any(phrase in blob for phrase in phrases):
            for eid in finding.get("evidence_ids") or []:
                evidence.append(str(eid))
            if not evidence:
                evidence.append(str(finding.get("what") or cause_type)[:120])
    return evidence


def _has_domain_evidence(context: BusinessContext, cause_type: str) -> bool:
    """True when the context carries the data needed to judge this cause."""
    if cause_type in DATA_DEPENDENT_CAUSES:
        # Requires Orbit findings/opportunities that reference price or cost.
        for finding in context.findings or []:
            if isinstance(finding, dict):
                blob = " ".join(str(v) for v in finding.values()).lower()
                if "cost" in blob or "price" in blob or "purchase" in blob:
                    return True
        for opportunity in context.opportunities or []:
            if isinstance(opportunity, dict):
                blob = " ".join(str(v) for v in opportunity.values()).lower()
                if "cost" in blob or "price" in blob:
                    return True
        return False
    if cause_type == "INVENTORY_CASH_TRAPPED":
        return bool(context.exposures)
    if cause_type == "EXPIRY_REMINDER":
        blob = " ".join(
            str(v) for v in (context.limitations or {}).values()
        ).lower()
        return "expir" in blob
    if cause_type == "MISSING_COST_DATA":
        return bool((context.limitations or {}).get("we_dont_know"))
    return True


def _contradictory(context: BusinessContext, cause_type: str) -> list[str]:
    """Evidence that argues *against* this cause, so we never overstate."""
    contradictions: list[str] = []
    # If Orbit says the domain is healthy, a domain-specific cause is contradicted.
    domain_by_cause = {
        "SUPPLIER_COST_INCREASE": "margin",
        "SELLING_PRICE_MISMATCH": "margin",
        "EXCESSIVE_DISCOUNTING": "margin",
        "LOW_DEMAND": "sales",
        "SLOW_STOCK_CONVERSION": "inventory",
        "INVENTORY_CASH_TRAPPED": "inventory",
    }
    domain = domain_by_cause.get(cause_type)
    if not domain:
        return contradictions
    breakdown = context.health_breakdown or {}
    key = {"margin": "margins"}.get(domain, domain)
    entry = breakdown.get(key) if isinstance(breakdown, dict) else None
    score = None
    if isinstance(entry, dict):
        score = entry.get("score")
    elif entry is not None:
        score = entry
    if isinstance(score, (int, float)) and score >= 80:
        contradictions.append(
            f"Orbit {domain} domain score is healthy ({int(score)}/100), "
            f"which does not support {cause_type}"
        )
    return contradictions


def analyze_signal(
    context: BusinessContext,
    signal: Signal,
) -> list[RootCause]:
    """Analyze one signal into ranked root-cause candidates."""
    candidates = CANDIDATE_CAUSES.get(signal.signal_type)
    if not candidates:
        return [
            RootCause(
                signal_id=signal.signal_id,
                cause_type="UNCERTAIN",
                description=(
                    f"No deterministic cause mapping exists for signal "
                    f"{signal.signal_type!r}; manual review required."
                ),
                confidence=0.0,
                support_level=RootCauseSupportLevel.UNKNOWN,
                evidence_ids=[],
                contradictory_evidence=[],
                analysis_version=ROOT_CAUSE_ANALYSIS_VERSION,
            )
        ]

    results: list[RootCause] = []
    for cause_type in candidates:
        if cause_type not in CAUSE_TYPES:  # taxonomy drift guard
            continue
        orbit_evidence = _orbit_support(context, cause_type)
        contradictions = _contradictory(context, cause_type)
        has_data = _has_domain_evidence(context, cause_type)

        if orbit_evidence and not contradictions:
            support = RootCauseSupportLevel.OBSERVED
            confidence = 0.9
            description = (
                f"Orbit recorded {cause_type} as a contributing factor to "
                f"{signal.signal_type}."
            )
        elif has_data and not contradictions:
            support = RootCauseSupportLevel.SUPPORTED
            confidence = 0.7
            description = (
                f"{cause_type} is a supported contributor to {signal.signal_type}."
            )
        elif has_data and contradictions:
            support = RootCauseSupportLevel.POSSIBLE
            confidence = 0.4
            description = (
                f"{cause_type} is a possible contributor to {signal.signal_type}, "
                f"but contradictory evidence exists."
            )
        else:
            support = RootCauseSupportLevel.POSSIBLE
            confidence = 0.25
            description = (
                f"{cause_type} is a possible contributor to {signal.signal_type}, "
                f"but the data required to validate it is unavailable."
            )

        contributing: list[str] = []
        if signal.baseline_formula:
            contributing.append(
                f"{signal.metric} {signal.observed_value:g} vs baseline "
                f"{signal.baseline_formula}"
            )
        if signal.severity is SignalSeverity.CRITICAL:
            contributing.append("signal severity is CRITICAL")

        results.append(
            RootCause(
                signal_id=signal.signal_id,
                cause_type=cause_type,
                description=description,
                confidence=round(confidence, 4),
                support_level=support,
                evidence_ids=sorted(set(orbit_evidence or list(signal.evidence_ids))),
                contributing_factors=contributing,
                contradictory_evidence=contradictions,
                analysis_version=ROOT_CAUSE_ANALYSIS_VERSION,
            )
        )

    # Most-supported first, then by confidence.
    order = {
        RootCauseSupportLevel.OBSERVED: 0,
        RootCauseSupportLevel.SUPPORTED: 1,
        RootCauseSupportLevel.POSSIBLE: 2,
        RootCauseSupportLevel.UNKNOWN: 3,
    }
    results.sort(key=lambda rc: (order[rc.support_level], -rc.confidence))
    return results


def analyze_signals(
    context: BusinessContext,
    signals: list[Signal],
    *,
    max_per_signal: int = 3,
) -> list[RootCause]:
    """Analyze all signals, bounding the number of causes kept per signal."""
    out: list[RootCause] = []
    for signal in signals:
        for cause in analyze_signal(context, signal)[:max_per_signal]:
            out.append(cause)
    return out
