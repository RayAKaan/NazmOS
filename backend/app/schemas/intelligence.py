"""Pydantic API schemas for the canonical Intelligence API.

The API layer maps the canonical domain contracts (``app.services.intelligence.contracts``)
onto wire types. Mapping happens here, once, so routers/services/tests never
redefine the same object with subtly different fields.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Context ──────────────────────────────────────────────────────────────────

class BusinessContextOut(_Base):
    business_id: UUID
    state_version: str
    snapshot_timestamp: datetime
    data_freshness: str
    data_quality_score: Optional[float] = None
    business_type: str
    health_score: int
    health_breakdown: dict[str, Any] = Field(default_factory=dict)
    exposures: dict[str, Any] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    opportunities: list[dict[str, Any]] = Field(default_factory=list)
    limitations: dict[str, Any] = Field(default_factory=dict)
    historical_metrics: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    contract_version: str


# ── Signal ───────────────────────────────────────────────────────────────────

class SignalOut(_Base):
    signal_id: UUID
    business_id: UUID
    state_version: str
    signal_type: str
    domain: str
    metric: str
    observed_value: float
    baseline_value: float
    baseline_type: str
    baseline_formula: str
    deviation: float
    deviation_percent: float
    severity: str
    confidence: float
    detected_at: datetime
    evidence_ids: list[str] = Field(default_factory=list)
    freshness: str
    status: str
    detector_version: str
    detector_name: str
    fingerprint: str


class SignalListOut(_Base):
    items: list[SignalOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


# ── Root cause ───────────────────────────────────────────────────────────────

class RootCauseOut(_Base):
    root_cause_id: UUID
    signal_id: UUID
    cause_type: str
    description: str
    confidence: float
    support_level: str
    evidence_ids: list[str] = Field(default_factory=list)
    contributing_factors: list[str] = Field(default_factory=list)
    contradictory_evidence: list[str] = Field(default_factory=list)
    analysis_version: str
    analyzed_at: datetime


class RootCauseListOut(_Base):
    items: list[RootCauseOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


# ── Impact ───────────────────────────────────────────────────────────────────

class ImpactOut(_Base):
    impact_id: UUID
    signal_id: UUID
    kind: str
    amount_sar: float
    lower_bound_sar: float
    upper_bound_sar: float
    formula: str
    assumptions: list[str] = Field(default_factory=list)
    confidence: float
    evidence_ids: list[str] = Field(default_factory=list)
    currency: str
    period: str
    calculation_version: str
    calculated_at: datetime


class ImpactListOut(_Base):
    items: list[ImpactOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


# ── Advisory ─────────────────────────────────────────────────────────────────

class AdvisoryOut(_Base):
    source: str
    confidence: float
    reasoning: str
    suggested_action: Optional[str] = None
    alternative_action: Optional[str] = None
    challenge: bool = False
    risk_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    jev_consulted: bool = False


# ── Recommendation ───────────────────────────────────────────────────────────

class ImpactRef(BaseModel):
    amount_sar: float
    kind: str
    formula: str = ""
    assumptions: list[str] = Field(default_factory=list)


class RecommendationOut(_Base):
    recommendation_id: UUID
    business_id: UUID
    state_version: str
    signal_ids: list[UUID] = Field(default_factory=list)
    root_cause_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    action_type: str
    rationale: str
    potential_impact: Optional[ImpactRef] = None
    expected_impact: Optional[ImpactRef] = None
    confidence: float
    urgency: str
    risk: str
    reversibility: str
    affected_resources: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    approval_required: bool
    governance_requirements: list[str] = Field(default_factory=list)
    expires_at: Optional[datetime] = None
    recommendation_version: str
    created_at: datetime
    status: str


class RecommendationListOut(_Base):
    items: list[RecommendationOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


# ── Decision candidate ───────────────────────────────────────────────────────

class DecisionCandidateOut(_Base):
    decision_id: UUID
    business_id: UUID
    state_version: str
    recommendation_id: UUID
    action_type: str
    deterministic_basis: dict[str, Any] = Field(default_factory=dict)
    advisory: Optional[AdvisoryOut] = None
    expected_impact: Optional[ImpactOut] = None
    risk: float
    urgency: float
    confidence: float
    evidence_ids: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    governance_status: str
    approval_required: bool
    status: str
    created_at: datetime
    expires_at: Optional[datetime] = None


class DecisionCandidateListOut(_Base):
    items: list[DecisionCandidateOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


# ── Alert ────────────────────────────────────────────────────────────────────

class AlertOut(_Base):
    alert_id: UUID
    business_id: UUID
    severity: str
    alert_type: str
    title: str
    description: str
    signal_id: Optional[UUID] = None
    recommendation_id: Optional[UUID] = None
    decision_id: Optional[UUID] = None
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    expires_at: Optional[datetime] = None
    status: str
    fingerprint: str


class AlertListOut(_Base):
    items: list[AlertOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


# ── Copilot ──────────────────────────────────────────────────────────────────

class CopilotRequest(BaseModel):
    business_id: UUID
    question: str = Field(min_length=1, max_length=2000)
    state_version: Optional[str] = None
    enable_advisory: bool = False


class CopilotAnswerOut(_Base):
    answer: str
    sources: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    related_signal_ids: list[UUID] = Field(default_factory=list)
    related_recommendation_ids: list[UUID] = Field(default_factory=list)
    confidence: float
    freshness: str
    limitations: list[str] = Field(default_factory=list)
    generated_at: datetime


# ── Run / analyze / monitor ──────────────────────────────────────────────────

class RunRequest(BaseModel):
    business_id: UUID
    state_version: Optional[str] = None
    trigger: Optional[str] = Field(default=None, max_length=64)
    enable_advisory: bool = False
    shariah_approved: bool = False
    detectors: Optional[list[str]] = None


class IntelligenceRunOut(_Base):
    run_id: UUID
    business_id: UUID
    state_version: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    signals: list[SignalOut] = Field(default_factory=list)
    root_causes: list[RootCauseOut] = Field(default_factory=list)
    impacts: list[ImpactOut] = Field(default_factory=list)
    recommendations: list[RecommendationOut] = Field(default_factory=list)
    decision_candidates: list[DecisionCandidateOut] = Field(default_factory=list)
    alerts: list[AlertOut] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failed_detectors: list[str] = Field(default_factory=list)
    detector_errors: dict[str, str] = Field(default_factory=dict)
