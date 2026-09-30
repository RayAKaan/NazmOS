"""Canonical Intelligence contracts — single source of truth for all Intelligence artifacts.

This module defines the typed contracts that flow through the Intelligence pipeline:
OrbitAuditResult → BusinessContext → Signals → RootCauses → Impacts → Recommendations
→ Jev Advisory → DecisionCandidates → Governance → Loop

All contracts preserve:
- business_id / tenant boundary
- state_version (Orbit audit_id or BusinessSnapshot version)
- evidence_ids (traceable to Orbit evidence)
- freshness (FRESH/STALE/PARTIAL/MISSING/CONFLICT/UNKNOWN)
- confidence (evidence-based, not fabricated)
- timestamps, provenance, contract version
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

D = Decimal
ZERO = D("0")

INTELLIGENCE_CONTRACT_VERSION = "v1"


class FreshnessStatus(str, Enum):
    """Explicit freshness — never treat missing as zero, stale as current."""
    FRESH = "fresh"
    STALE = "stale"
    PARTIAL = "partial"
    MISSING = "missing"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


class SignalSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SignalStatus(str, Enum):
    DETECTED = "detected"
    CONFIRMED = "confirmed"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class RootCauseSupportLevel(str, Enum):
    OBSERVED = "observed"
    SUPPORTED = "supported"
    POSSIBLE = "possible"
    UNKNOWN = "unknown"


class ImpactKind(str, Enum):
    POTENTIAL = "potential"
    EXPECTED = "expected"
    APPROVED = "approved"
    EXECUTED = "executed"
    VERIFIED = "verified"


class RecommendationStatus(str, Enum):
    DETECTED = "detected"
    QUANTIFIED = "quantified"
    ADVISORY_PENDING = "advisory_pending"
    VALIDATED = "validated"
    POLICY_EVALUATED = "policy_evaluated"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    RECONCILING = "reconciling"
    VERIFYING = "verifying"
    CLOSED = "closed"
    PARTIAL = "partial"
    DISPUTED = "disputed"
    UNVERIFIED = "unverified"
    DENIED = "denied"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class DecisionCandidateStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    GOVERNANCE_PENDING = "governance_pending"
    APPROVAL_REQUIRED = "approval_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    HANDED_TO_LOOP = "handed_to_loop"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    DECISION_REQUIRED = "decision_required"
    APPROVAL_REQUIRED = "approval_required"
    EXECUTION_FAILED = "execution_failed"
    OUTCOME_READY = "outcome_ready"
    DATA_QUALITY = "data_quality"


class AlertStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class AdvisorySource(str, Enum):
    JEV = "jev"
    LLM_API = "llm_api"
    DETERMINISTIC_ONLY = "deterministic_only"
    MOCKED = "mocked"


class IntelligenceRunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


# ─────────────────────────────────────────────────────────────────────────────
# Business Context — projection of authoritative Orbit state
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BusinessContext:
    """Canonical business context assembled from Orbit + Loop state.
    
    This is the single entry point for all Intelligence processing.
    It does NOT invent values — it projects existing authoritative data.
    """
    business_id: UUID
    state_version: str  # Orbit audit_id or BusinessSnapshot version
    snapshot_timestamp: datetime
    data_freshness: FreshnessStatus
    data_quality_score: float  # 0.0-1.0
    business_type: str
    
    # Current metrics from Orbit
    health_score: int
    health_breakdown: dict[str, Any]
    exposures: dict[str, Any]
    metrics: dict[str, Any]
    findings: list[dict[str, Any]]
    opportunities: list[dict[str, Any]]
    limitations: dict[str, Any]
    
    # Historical context
    historical_metrics: dict[str, Any] = field(default_factory=dict)
    
    # Active state from Loop
    active_signals: list[UUID] = field(default_factory=list)
    active_recommendations: list[UUID] = field(default_factory=list)
    active_alerts: list[UUID] = field(default_factory=list)
    recent_outcomes: list[dict[str, Any]] = field(default_factory=list)
    
    # Existing Intelligence/Governance state. These are projections of what the
    # repository already stores (IntelligenceDecision, agent_actions, ...); the
    # Intelligence layer never becomes a second authority for them.
    existing_decisions: list[dict[str, Any]] = field(default_factory=list)
    open_recommendations: list[dict[str, Any]] = field(default_factory=list)
    previous_outcomes: list[dict[str, Any]] = field(default_factory=list)
    
    # Constraints & goals
    active_constraints: dict[str, Any] = field(default_factory=dict)
    active_goals: dict[str, Any] = field(default_factory=dict)
    
    # Context enrichments
    supplier_context: dict[str, Any] = field(default_factory=dict)
    inventory_context: dict[str, Any] = field(default_factory=dict)
    financial_context: dict[str, Any] = field(default_factory=dict)
    operational_context: dict[str, Any] = field(default_factory=dict)
    external_context: dict[str, Any] = field(default_factory=dict)
    
    evidence_ids: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)
    contract_version: str = INTELLIGENCE_CONTRACT_VERSION


# ─────────────────────────────────────────────────────────────────────────────
# Signal System — deterministic detection with full provenance
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Signal:
    """A deterministic signal detected from business context.
    
    Every signal must state HOW its baseline was calculated.
    """
    signal_id: UUID = field(default_factory=uuid4)
    business_id: UUID = field(default_factory=lambda: UUID(int=0))
    state_version: str = ""
    signal_type: str = ""  # e.g., "revenue_decline", "excess_inventory", "margin_erosion"
    domain: str = ""  # sales, margin, inventory, procurement, financial, data_quality
    metric: str = ""  # the metric name from Orbit (e.g., "revenue_30d", "gross_margin_pct")
    observed_value: float = 0.0
    baseline_value: float = 0.0
    baseline_type: str = ""  # CURRENT_PERIOD, PREVIOUS_PERIOD, ROLLING_MEAN, etc.
    baseline_formula: str = ""  # human-readable: "30-day rolling mean ending 2026-09-15"
    deviation: float = 0.0
    deviation_percent: float = 0.0
    severity: SignalSeverity = SignalSeverity.INFO
    confidence: float = 0.0  # evidence-based
    detected_at: datetime = field(default_factory=datetime.utcnow)
    evidence_ids: list[str] = field(default_factory=list)
    freshness: FreshnessStatus = FreshnessStatus.FRESH
    status: SignalStatus = SignalStatus.DETECTED
    detector_version: str = "1.0"
    detector_name: str = ""
    
    # For deduplication
    fingerprint: str = ""  # deterministic: business_id + signal_type + resource + detector_version


# ─────────────────────────────────────────────────────────────────────────────
# Root Cause — evidence-based, not correlation
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RootCause:
    """A hypothesized root cause with evidence validation.
    
    Distinguishes: OBSERVED | SUPPORTED | POSSIBLE | UNKNOWN
    Never represents correlation as certainty.
    """
    root_cause_id: UUID = field(default_factory=uuid4)
    signal_id: UUID = field(default_factory=lambda: UUID(int=0))
    cause_type: str = ""  # from taxonomy: SUPPLIER_COST_INCREASE, etc.
    description: str = ""
    confidence: float = 0.0
    support_level: RootCauseSupportLevel = RootCauseSupportLevel.UNKNOWN
    evidence_ids: list[str] = field(default_factory=list)
    contributing_factors: list[str] = field(default_factory=list)
    contradictory_evidence: list[str] = field(default_factory=list)
    analysis_version: str = "1.0"
    analyzed_at: datetime = field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Impact — never conflate potential with verified
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ImpactEstimate:
    """Quantified impact — MUST expose formula and assumptions.
    
    Separates: POTENTIAL | EXPECTED | APPROVED | EXECUTED | VERIFIED
    """
    impact_id: UUID = field(default_factory=uuid4)
    signal_id: UUID = field(default_factory=lambda: UUID(int=0))
    recommendation_id: Optional[UUID] = None
    kind: ImpactKind = ImpactKind.POTENTIAL
    amount_sar: float = 0.0
    lower_bound_sar: float = 0.0
    upper_bound_sar: float = 0.0
    formula: str = ""  # e.g., "eligible_stock × recoverable_fraction"
    assumptions: list[str] = field(default_factory=list)
    confidence: float = 0.0
    evidence_ids: list[str] = field(default_factory=list)
    currency: str = "SAR"
    period: str = ""
    calculation_version: str = "1.0"
    calculated_at: datetime = field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Recommendation — deterministic action candidate
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Recommendation:
    """A deterministic recommendation with full traceability.
    
    Uses ONLY canonical action vocabulary from orchestration.contracts.CANONICAL_ACTION_TYPES
    """
    recommendation_id: UUID = field(default_factory=uuid4)
    version: str = INTELLIGENCE_CONTRACT_VERSION
    business_id: UUID = field(default_factory=lambda: UUID(int=0))
    tenant_id: UUID = field(default_factory=lambda: UUID(int=0))
    state_version: str = ""
    signal_ids: list[UUID] = field(default_factory=list)
    root_cause_ids: list[UUID] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    action_type: str = ""  # from CANONICAL_ACTION_TYPES
    rationale: str = ""
    potential_impact: Optional[ImpactEstimate] = None
    expected_impact: Optional[ImpactEstimate] = None
    confidence: float = 0.0
    urgency: float = 0.0
    risk: float = 0.0
    reversibility: str = "reversible"
    affected_resources: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    approval_required: bool = True
    governance_requirements: list[str] = field(default_factory=list)
    expires_at: Optional[datetime] = None
    recommendation_version: str = "1"
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: RecommendationStatus = RecommendationStatus.DETECTED


# ─────────────────────────────────────────────────────────────────────────────
# Jev Advisory — advisory only, never authoritative
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AdvisoryResult:
    """Jev advisory result — clearly distinguished from deterministic output."""
    source: AdvisorySource = AdvisorySource.DETERMINISTIC_ONLY
    confidence: float = 0.0
    reasoning: str = ""
    suggested_action: Optional[str] = None
    alternative_action: Optional[str] = None
    challenge: bool = False
    risk_flags: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    jev_consulted: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Decision Candidate — handoff to Governance/Loop
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DecisionCandidate:
    """A decision candidate ready for Governance evaluation.
    
    Intelligence produces this; Governance authorizes; Loop executes.
    Intelligence NEVER marks EXECUTED or VERIFIED.
    """
    decision_id: UUID = field(default_factory=uuid4)
    business_id: UUID = field(default_factory=lambda: UUID(int=0))
    tenant_id: UUID = field(default_factory=lambda: UUID(int=0))
    state_version: str = ""
    recommendation_id: UUID = field(default_factory=lambda: UUID(int=0))
    action_type: str = ""
    deterministic_basis: dict[str, Any] = field(default_factory=dict)
    advisory: Optional[AdvisoryResult] = None
    expected_impact: Optional[ImpactEstimate] = None
    risk: float = 0.0
    urgency: float = 0.0
    confidence: float = 0.0
    evidence_ids: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    governance_status: str = "pending"
    approval_required: bool = True
    status: DecisionCandidateStatus = DecisionCandidateStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


# ─────────────────────────────────────────────────────────────────────────────
# Alert System
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Alert:
    """An alert with deterministic deduplication fingerprint."""
    alert_id: UUID = field(default_factory=uuid4)
    business_id: UUID = field(default_factory=lambda: UUID(int=0))
    severity: AlertSeverity = AlertSeverity.INFO
    alert_type: str = ""
    title: str = ""
    description: str = ""
    signal_id: Optional[UUID] = None
    recommendation_id: Optional[UUID] = None
    decision_id: Optional[UUID] = None
    evidence_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    status: AlertStatus = AlertStatus.OPEN
    
    # Deduplication
    fingerprint: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Intelligence Run — canonical result of one evaluation
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class IntelligenceRun:
    """Canonical result of one Intelligence evaluation cycle."""
    run_id: UUID = field(default_factory=uuid4)
    business_id: UUID = field(default_factory=lambda: UUID(int=0))
    state_version: str = ""
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    status: IntelligenceRunStatus = IntelligenceRunStatus.RUNNING
    signals: list[Signal] = field(default_factory=list)
    root_causes: list[RootCause] = field(default_factory=list)
    impacts: list[ImpactEstimate] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    decision_candidates: list[DecisionCandidate] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    # Detector failures (failure isolation)
    failed_detectors: list[str] = field(default_factory=list)
    detector_errors: dict[str, str] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Copilot Answer Contract
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CopilotAnswer:
    """Owner Copilot answer — read/explanation layer over Intelligence artifacts."""
    answer: str = ""
    sources: list[str] = field(default_factory=list)  # signal_id, recommendation_id, etc.
    evidence_ids: list[str] = field(default_factory=list)
    related_signal_ids: list[UUID] = field(default_factory=list)
    related_recommendation_ids: list[UUID] = field(default_factory=list)
    confidence: float = 0.0
    freshness: FreshnessStatus = FreshnessStatus.FRESH
    limitations: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Freshness evaluation
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_freshness(
    data_timestamp: Optional[datetime],
    max_age_hours: float = 24.0,
    stale_threshold_hours: float = 4.0,
) -> FreshnessStatus:
    """Evaluate freshness of a data point.
    
    Args:
        data_timestamp: When the data was generated/observed
        max_age_hours: Beyond this = MISSING
        stale_threshold_hours: Beyond this = STALE (if not MISSING)
    """
    if data_timestamp is None:
        return FreshnessStatus.MISSING
    
    age_hours = (datetime.utcnow() - data_timestamp).total_seconds() / 3600
    
    if age_hours > max_age_hours:
        return FreshnessStatus.MISSING
    if age_hours > stale_threshold_hours:
        return FreshnessStatus.STALE
    return FreshnessStatus.FRESH


def make_signal_fingerprint(
    business_id: UUID,
    signal_type: str,
    resource: str,
    detector_version: str,
    state_version: str,
) -> str:
    """Deterministic fingerprint for signal deduplication."""
    import hashlib
    key = f"{business_id}|{signal_type}|{resource}|{detector_version}|{state_version}"
    return hashlib.sha256(key.encode()).hexdigest()[:24]


def make_alert_fingerprint(
    business_id: UUID,
    alert_type: str,
    signal_type: str,
    resource: str,
    detector_version: str,
) -> str:
    """Deterministic fingerprint for alert deduplication."""
    import hashlib
    key = f"{business_id}|{alert_type}|{signal_type}|{resource}|{detector_version}"
    return hashlib.sha256(key.encode()).hexdigest()[:24]