"""Owner Copilot — a read/explanation layer over Intelligence artifacts.

The Copilot does NOT reason about the business independently. It answers
questions *by reading* what Orbit, the detectors, the root-cause engine, the
impact engine, the recommendation engine and the Loop already produced, and
cites the artifact ids it used.

Hard rules:
- Every answer carries sources, evidence ids and freshness.
- When the artifacts do not support an answer, the Copilot says
  "insufficient data" instead of inventing a number.
- Copilot never fabricates financial figures. Amounts are copied from Impact
  estimates and always labelled POTENTIAL or EXPECTED.
- Jev may be used to *phrase* an explanation, never to manufacture business truth.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.services.intelligence.contracts import (
    BusinessContext,
    CopilotAnswer,
    FreshnessStatus,
    IntelligenceRun,
    ImpactEstimate,
    ImpactKind,
    Recommendation,
    RootCause,
    Signal,
)

INSUFFICIENT = "insufficient data"

# Deterministic intent classification. Keyword routing only — no model required,
# so the Copilot works with zero AI availability.
_INTENTS: list[tuple[str, tuple[str, ...]]] = [
    ("what_changed", ("what changed", "changed", "difference", "since last", "trend")),
    ("why", ("why", "reason", "cause", "root cause", "because")),
    ("attention", ("attention", "urgent", "critical", "worst", "biggest", "risk")),
    ("costing_money", ("costing", "cost me", "losing money", "where is the money", "at risk", "exposure")),
    ("review", ("review", "approve", "approval", "should i", "what should")),
    ("confidence", ("confidence", "sure", "how confident", "reliable")),
    ("do_nothing", ("if i do nothing", "do nothing", "no action", "wait")),
]


def classify_intent(question: str) -> str:
    """Classify the owner question into a deterministic intent."""
    text = (question or "").strip().lower()
    if not text:
        return "unknown"
    for intent, keywords in _INTENTS:
        if any(keyword in text for keyword in keywords):
            return intent
    return "unknown"


def _format_amount(kind: ImpactKind, amount: float) -> str:
    label = "potential" if kind is ImpactKind.POTENTIAL else kind.value
    return f"SAR {amount:,.0f} ({label} only — not approved, executed or verified)"


def _impact_lines(impacts: list[ImpactEstimate], *, kind: ImpactKind) -> list[str]:
    lines: list[str] = []
    for impact in impacts:
        if impact.kind is not kind:
            continue
        lines.append(_format_amount(kind, impact.amount_sar))
    return lines


def answer_from_run(
    question: str,
    run: IntelligenceRun,
    context: Optional[BusinessContext] = None,
) -> CopilotAnswer:
    """Answer an owner question strictly from existing Intelligence artifacts."""
    intent = classify_intent(question)
    signals = run.signals
    causes = run.root_causes
    recs = run.recommendations
    impacts = run.impacts

    if not signals and not recs:
        return CopilotAnswer(
            answer=(
                f"{INSUFFICIENT}: no intelligence artifacts exist for this business "
                f"state. Run an Orbit audit and monitoring first."
            ),
            sources=[],
            evidence_ids=[],
            confidence=0.0,
            freshness=FreshnessStatus.MISSING,
            limitations=[
                w for w in run.warnings
            ] or ["no signals or recommendations available"],
        )

    limitations: list[str] = list(run.warnings)
    if run.status.value == "partial":
        limitations.insert(0, "run was PARTIAL: some detectors could not judge")
    if context is not None:
        if context.data_freshness is not FreshnessStatus.FRESH:
            limitations.append(f"Orbit data freshness is {context.data_freshness.value}")
        if context.data_quality_score is not None and context.data_quality_score < 0.6:
            limitations.append(
                f"Orbit data quality is {context.data_quality_score:.0%}; "
                "conclusions are limited"
            )
        dont_know = (context.limitations or {}).get("we_dont_know") or []
        if dont_know:
            limitations.append(
                f"Orbit reported {len(dont_know)} inputs as unknown"
            )

    answer_parts: list[str] = []
    sources: list[str] = []
    evidence_ids: list[str] = []
    related_signals: list[Any] = []
    related_recs: list[Any] = []
    confidence = 0.0

    if intent == "what_changed":
        if context is not None and context.historical_metrics:
            series = context.historical_metrics.get("health_score_series") or []
            if len(series) >= 2:
                first, last = series[0], series[-1]
                delta = (last.get("health_score") or 0) - (first.get("health_score") or 0)
                answer_parts.append(
                    f"Overall health moved {delta:+d} points across "
                    f"{len(series)} Orbit audits "
                    f"(first {first.get('health_score')}, latest {last.get('health_score')})."
                )
                sources.append("orbit.health_score_series")
                confidence = max(confidence, 0.8)
        if not answer_parts:
            answer_parts.append(
                f"{INSUFFICIENT}: only one Orbit audit exists, so no change can be determined."
            )
        for signal in sorted(signals, key=lambda s: s.severity.value)[:5]:
            answer_parts.append(
                f"- {signal.signal_type} ({signal.domain}, {signal.severity.value}): "
                f"{signal.metric}={signal.observed_value:g}"
            )
            related_signals.append(signal.signal_id)
            evidence_ids.extend(signal.evidence_ids)
        if related_signals:
            confidence = max(confidence, 0.7)

    elif intent == "why":
        for cause in causes[:5]:
            signal = next((s for s in signals if s.signal_id == cause.signal_id), None)
            metric_ctx = f" for {signal.signal_type}" if signal else ""
            answer_parts.append(
                f"- {cause.cause_type} is a {cause.support_level.value} contributor"
                f"{metric_ctx} (confidence {cause.confidence:.2f})."
            )
            if cause.contradictory_evidence:
                answer_parts.append(
                    f"  Counter-evidence: {'; '.join(cause.contradictory_evidence)}"
                )
                limitations.append("some root causes have counter-evidence")
            related_signals.append(cause.signal_id)
            evidence_ids.extend(cause.evidence_ids)
            sources.append(f"root_cause:{cause.cause_type}")
            confidence = max(confidence, cause.confidence)
        if not answer_parts:
            answer_parts.append(
                f"{INSUFFICIENT}: no root-cause analysis is available yet."
            )

    elif intent == "attention":
        critical = [s for s in signals if s.severity.value == "critical"]
        warnings = [s for s in signals if s.severity.value == "warning"]
        if critical:
            answer_parts.append(
                f"{len(critical)} critical issue(s) need attention:"
            )
            for signal in critical:
                answer_parts.append(
                    f"- {signal.signal_type}: {signal.metric}={signal.observed_value:g} "
                    f"({signal.baseline_formula})"
                )
                related_signals.append(signal.signal_id)
                evidence_ids.extend(signal.evidence_ids)
            confidence = max(confidence, 0.85)
        if warnings:
            answer_parts.append(f"{len(warnings)} warning-level issue(s):")
            for signal in warnings[:5]:
                answer_parts.append(f"- {signal.signal_type} in {signal.domain}")
                related_signals.append(signal.signal_id)
            confidence = max(confidence, 0.6)
        if not answer_parts:
            answer_parts.append("Nothing critical requires attention right now.")

    elif intent == "costing_money":
        potential = _impact_lines(impacts, kind=ImpactKind.POTENTIAL)
        expected = _impact_lines(impacts, kind=ImpactKind.EXPECTED)
        if potential:
            answer_parts.append("Potential exposure identified by Orbit/Impact engine:")
            answer_parts.extend(f"- {line}" for line in potential)
            for est in impacts:
                if est.kind is ImpactKind.POTENTIAL:
                    evidence_ids.extend(est.evidence_ids)
            sources.append("impact.potential")
            confidence = max(confidence, 0.6)
        if expected:
            answer_parts.append("Planning estimate (expected):")
            answer_parts.extend(f"- {line}" for line in expected)
            sources.append("impact.expected")
        if not potential:
            answer_parts.append(
                f"{INSUFFICIENT}: no monetary impact could be quantified from Orbit data."
            )

    elif intent == "review":
        approval = [r for r in recs if r.approval_required and r.action_type not in ("REVIEW", "INFO_ONLY")]
        advisory = [r for r in recs if not r.approval_required]
        if approval:
            answer_parts.append("These require your approval:")
            for rec in approval:
                answer_parts.append(f"- {rec.action_type} (confidence {rec.confidence:.2f})")
                related_recs.append(rec.recommendation_id)
                evidence_ids.extend(rec.evidence_ids)
            confidence = max(confidence, 0.75)
        if advisory:
            answer_parts.append("These are informational:")
            for rec in advisory[:5]:
                answer_parts.append(f"- {rec.action_type}")
                related_recs.append(rec.recommendation_id)
        if not recs:
            answer_parts.append(f"{INSUFFICIENT}: no recommendations available.")

    elif intent == "confidence":
        if recs:
            best = recs[0]
            answer_parts.append(
                f"Top recommendation {best.action_type} has confidence "
                f"{best.confidence:.2f}, urgency {best.urgency}, risk {best.risk}."
            )
            if best.potential_impact:
                answer_parts.append(
                    f"Its impact is {_format_amount(ImpactKind.POTENTIAL, best.potential_impact.amount_sar)}."
                )
            related_recs.append(best.recommendation_id)
            confidence = best.confidence
            sources.append(f"recommendation:{best.action_type}")
        else:
            answer_parts.append(f"{INSUFFICIENT}: nothing to be confident about yet.")

    elif intent == "do_nothing":
        totals = [
            i for i in impacts if i.kind is ImpactKind.POTENTIAL
        ]
        if totals:
            combined = sum(i.amount_sar for i in totals)
            answer_parts.append(
                f"If you take no action, the potential exposure identified remains "
                f"{_format_amount(ImpactKind.POTENTIAL, combined)}."
            )
            answer_parts.append(
                "This is a potential estimate only; nothing has been approved, "
                "executed or verified."
            )
            for est in totals:
                evidence_ids.extend(est.evidence_ids)
            confidence = max(confidence, 0.5)
        else:
            answer_parts.append(
                f"{INSUFFICIENT}: no potential impact is quantified, so the cost of "
                "doing nothing cannot be stated."
            )

    else:
        # Unknown intent: summarise rather than guess.
        answer_parts.append(
            f"I can explain what changed, why, what needs attention, what is costing "
            f"money, what needs approval, and my confidence. "
            f"Currently {len(signals)} signal(s) and {len(recs)} recommendation(s) exist."
        )
        confidence = 0.4
        limitations.append("question intent was not recognised; returned a summary")

    return CopilotAnswer(
        answer="\n".join(answer_parts),
        sources=sorted(set(sources)),
        evidence_ids=sorted(set(evidence_ids)),
        related_signal_ids=related_signals,
        related_recommendation_ids=related_recs,
        confidence=round(confidence, 4),
        freshness=(
            context.data_freshness if context is not None else FreshnessStatus.UNKNOWN
        ),
        limitations=sorted(set(limitations)),
    )
