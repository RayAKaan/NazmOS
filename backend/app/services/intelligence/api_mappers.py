"""Explicit mapping from canonical Intelligence contracts to API schemas.

The domain contracts are frozen dataclasses with ``str``-valued Enums. Rather
than relying on implicit Pydantic coercion, each contract is mapped explicitly
here so the wire shape is intentional and reviewable in one place.
"""
from __future__ import annotations

from typing import Any, Optional

from app.schemas.intelligence import (
    AdvisoryOut,
    AlertOut,
    BusinessContextOut,
    CopilotAnswerOut,
    DecisionCandidateOut,
    ImpactOut,
    ImpactRef,
    RecommendationOut,
    RootCauseOut,
    SignalOut,
)
from app.services.intelligence.contracts import (
    AdvisoryResult,
    Alert,
    BusinessContext,
    CopilotAnswer,
    DecisionCandidate,
    ImpactEstimate,
    Recommendation,
    RootCause,
    Signal,
)


def _enum(value: Any) -> str:
    return getattr(value, "value", str(value))


def signal_out(signal: Signal) -> SignalOut:
    return SignalOut(
        signal_id=signal.signal_id,
        business_id=signal.business_id,
        state_version=signal.state_version,
        signal_type=signal.signal_type,
        domain=signal.domain,
        metric=signal.metric,
        observed_value=signal.observed_value,
        baseline_value=signal.baseline_value,
        baseline_type=signal.baseline_type,
        baseline_formula=signal.baseline_formula,
        deviation=signal.deviation,
        deviation_percent=signal.deviation_percent,
        severity=_enum(signal.severity),
        confidence=signal.confidence,
        detected_at=signal.detected_at,
        evidence_ids=list(signal.evidence_ids),
        freshness=_enum(signal.freshness),
        status=_enum(signal.status),
        detector_version=signal.detector_version,
        detector_name=signal.detector_name,
        fingerprint=signal.fingerprint,
    )


def root_cause_out(cause: RootCause) -> RootCauseOut:
    return RootCauseOut(
        root_cause_id=cause.root_cause_id,
        signal_id=cause.signal_id,
        cause_type=cause.cause_type,
        description=cause.description,
        confidence=cause.confidence,
        support_level=_enum(cause.support_level),
        evidence_ids=list(cause.evidence_ids),
        contributing_factors=list(cause.contributing_factors),
        contradictory_evidence=list(cause.contradictory_evidence),
        analysis_version=cause.analysis_version,
        analyzed_at=cause.analyzed_at,
    )


def impact_out(impact: ImpactEstimate) -> ImpactOut:
    return ImpactOut(
        impact_id=impact.impact_id,
        signal_id=impact.signal_id,
        kind=_enum(impact.kind),
        amount_sar=impact.amount_sar,
        lower_bound_sar=impact.lower_bound_sar,
        upper_bound_sar=impact.upper_bound_sar,
        formula=impact.formula,
        assumptions=list(impact.assumptions),
        confidence=impact.confidence,
        evidence_ids=list(impact.evidence_ids),
        currency=impact.currency,
        period=impact.period,
        calculation_version=impact.calculation_version,
        calculated_at=impact.calculated_at,
    )


def _impact_ref(impact: Optional[ImpactEstimate]) -> Optional[ImpactRef]:
    if impact is None:
        return None
    return ImpactRef(
        amount_sar=impact.amount_sar,
        kind=_enum(impact.kind),
        formula=impact.formula,
        assumptions=list(impact.assumptions),
    )


def advisory_out(advisory: Optional[AdvisoryResult]) -> Optional[AdvisoryOut]:
    if advisory is None:
        return None
    return AdvisoryOut(
        source=_enum(advisory.source),
        confidence=advisory.confidence,
        reasoning=advisory.reasoning,
        suggested_action=advisory.suggested_action,
        alternative_action=advisory.alternative_action,
        challenge=advisory.challenge,
        risk_flags=list(advisory.risk_flags),
        evidence_ids=list(advisory.evidence_ids),
        latency_ms=advisory.latency_ms,
        jev_consulted=advisory.jev_consulted,
    )


def recommendation_out(rec: Recommendation) -> RecommendationOut:
    return RecommendationOut(
        recommendation_id=rec.recommendation_id,
        business_id=rec.business_id,
        state_version=rec.state_version,
        signal_ids=list(rec.signal_ids),
        root_cause_ids=list(rec.root_cause_ids),
        evidence_ids=list(rec.evidence_ids),
        action_type=rec.action_type,
        rationale=rec.rationale,
        potential_impact=_impact_ref(rec.potential_impact),
        expected_impact=_impact_ref(rec.expected_impact),
        confidence=rec.confidence,
        urgency=rec.urgency,
        risk=rec.risk,
        reversibility=rec.reversibility,
        affected_resources=list(rec.affected_resources),
        constraints=dict(rec.constraints),
        approval_required=rec.approval_required,
        governance_requirements=list(rec.governance_requirements),
        expires_at=rec.expires_at,
        recommendation_version=rec.recommendation_version,
        created_at=rec.created_at,
        status=_enum(rec.status),
    )


def decision_candidate_out(candidate: DecisionCandidate) -> DecisionCandidateOut:
    return DecisionCandidateOut(
        decision_id=candidate.decision_id,
        business_id=candidate.business_id,
        state_version=candidate.state_version,
        recommendation_id=candidate.recommendation_id,
        action_type=candidate.action_type,
        deterministic_basis=dict(candidate.deterministic_basis),
        advisory=advisory_out(candidate.advisory),
        expected_impact=impact_out(candidate.expected_impact) if candidate.expected_impact else None,
        risk=candidate.risk,
        urgency=candidate.urgency,
        confidence=candidate.confidence,
        evidence_ids=list(candidate.evidence_ids),
        constraints=dict(candidate.constraints),
        governance_status=candidate.governance_status,
        approval_required=candidate.approval_required,
        status=_enum(candidate.status),
        created_at=candidate.created_at,
        expires_at=candidate.expires_at,
    )


def alert_out(alert: Alert) -> AlertOut:
    return AlertOut(
        alert_id=alert.alert_id,
        business_id=alert.business_id,
        severity=_enum(alert.severity),
        alert_type=alert.alert_type,
        title=alert.title,
        description=alert.description,
        signal_id=alert.signal_id,
        recommendation_id=alert.recommendation_id,
        decision_id=alert.decision_id,
        evidence_ids=list(alert.evidence_ids),
        created_at=alert.created_at,
        expires_at=alert.expires_at,
        status=_enum(alert.status),
        fingerprint=alert.fingerprint,
    )


def context_out(context: BusinessContext) -> BusinessContextOut:
    return BusinessContextOut(
        business_id=context.business_id,
        state_version=context.state_version,
        snapshot_timestamp=context.snapshot_timestamp,
        data_freshness=_enum(context.data_freshness),
        data_quality_score=context.data_quality_score,
        business_type=context.business_type,
        health_score=context.health_score,
        health_breakdown=dict(context.health_breakdown),
        exposures=dict(context.exposures),
        findings=list(context.findings),
        opportunities=list(context.opportunities),
        limitations=dict(context.limitations),
        historical_metrics=dict(context.historical_metrics),
        evidence_ids=list(context.evidence_ids),
        contract_version=context.contract_version,
    )


def copilot_answer_out(answer: CopilotAnswer) -> CopilotAnswerOut:
    return CopilotAnswerOut(
        answer=answer.answer,
        sources=list(answer.sources),
        evidence_ids=list(answer.evidence_ids),
        related_signal_ids=list(answer.related_signal_ids),
        related_recommendation_ids=list(answer.related_recommendation_ids),
        confidence=answer.confidence,
        freshness=_enum(answer.freshness),
        limitations=list(answer.limitations),
        generated_at=answer.generated_at,
    )
