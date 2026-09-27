"""Shared contracts for the continuous business improvement loop.

Single source of truth for the enums and type aliases the loop stages
(evidence -> state -> opportunity -> advisory -> recommendation ->
governance -> execution -> reconciliation -> verification -> learning)
use so each stage stays deterministic and testable without a database.

Reuse boundaries:
    * Registered actions: ``app.services.action_registry.ACTION_REGISTRY``.
    * Canonical action vocabulary: ``app.orchestration.contracts.CANONICAL_ACTION_TYPES``.
    * Execution keys: ``app.orchestration.keys.derive_execution_key``.
    * Verified outcome ledger: ``app.services.outcome_ledger``.
This module only defines the loop's *contract vocabulary*; it does not
duplicate any existing store or executor.
"""
from __future__ import annotations

from enum import Enum


class LoopSchemaVersion(str, Enum):
    """Version stamped on every loop artifact so reprojection is explicit."""

    V1 = "loop-v1"


class EvidenceValidationStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"
    DUPLICATE = "duplicate"


class EvidenceQualityFlag(str, Enum):
    """Quality/lineage flags applied to accepted evidence records."""

    FRESH = "fresh"
    STALE = "stale"
    PARTIAL = "partial"
    MISSING = "missing"
    REVISED = "revised"
    CONFLICT = "conflict"


class OpportunityType(str, Enum):
    """Deterministic opportunity categories in current NazmOS scope."""

    EXCESS_INVENTORY = "excess_inventory"
    STOCKOUT_RISK = "stockout_risk"
    MARGIN_EROSION = "margin_erosion"
    SUPPLIER_PRICE_VARIANCE = "supplier_price_variance"
    INVENTORY_ANOMALY = "inventory_anomaly"
    RECOVERY_OPPORTUNITY = "recovery_opportunity"


class ImpactKind(str, Enum):
    """Impact must NEVER be conflated: an estimate is not recovered cash."""

    POTENTIAL = "potential"
    EXPECTED = "expected"
    APPROVED = "approved"
    EXECUTED = "executed"
    VERIFIED = "verified"


class GovernanceOutcome(str, Enum):
    PERMITTED = "permitted"
    DENIED = "denied"
    REVIEW_REQUIRED = "review_required"
    APPROVAL_REQUIRED = "approval_required"
    DEFERRED = "deferred"


class RecommendationStatus(str, Enum):
    """Explicit lifecycle for a versioned recommendation.

    Derived from the conventional findings lifecycle in
    ``app/services/finding_service.py`` (detected -> ... -> verified) plus the
    loop-specific gates (advisory, policy, reconcile, verify).
    """

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


# Valid forward transitions for RecommendationStatus. Any transition not in
# this map is rejected by the lifecycle guard (no silent status dancing).
RECOMMENDATION_TRANSITIONS: dict[RecommendationStatus, set[RecommendationStatus]] = {
    RecommendationStatus.DETECTED: {RecommendationStatus.QUANTIFIED, RecommendationStatus.DENIED, RecommendationStatus.EXPIRED, RecommendationStatus.SUPERSEDED},
    RecommendationStatus.QUANTIFIED: {RecommendationStatus.ADVISORY_PENDING, RecommendationStatus.DENIED, RecommendationStatus.EXPIRED, RecommendationStatus.SUPERSEDED},
    RecommendationStatus.ADVISORY_PENDING: {RecommendationStatus.VALIDATED, RecommendationStatus.DENIED, RecommendationStatus.EXPIRED, RecommendationStatus.SUPERSEDED},
    RecommendationStatus.VALIDATED: {RecommendationStatus.POLICY_EVALUATED, RecommendationStatus.DENIED, RecommendationStatus.EXPIRED, RecommendationStatus.SUPERSEDED},
    RecommendationStatus.POLICY_EVALUATED: {RecommendationStatus.AWAITING_APPROVAL, RecommendationStatus.APPROVED, RecommendationStatus.DENIED, RecommendationStatus.EXPIRED, RecommendationStatus.SUPERSEDED},
    RecommendationStatus.AWAITING_APPROVAL: {RecommendationStatus.APPROVED, RecommendationStatus.DENIED, RecommendationStatus.EXPIRED, RecommendationStatus.SUPERSEDED},
    RecommendationStatus.APPROVED: {RecommendationStatus.EXECUTING, RecommendationStatus.DENIED, RecommendationStatus.EXPIRED, RecommendationStatus.SUPERSEDED},
    RecommendationStatus.EXECUTING: {RecommendationStatus.RECONCILING, RecommendationStatus.PARTIAL, RecommendationStatus.UNVERIFIED, RecommendationStatus.DISPUTED},
    RecommendationStatus.RECONCILING: {RecommendationStatus.VERIFYING, RecommendationStatus.DISPUTED, RecommendationStatus.UNVERIFIED},
    RecommendationStatus.VERIFYING: {RecommendationStatus.CLOSED, RecommendationStatus.PARTIAL, RecommendationStatus.DISPUTED, RecommendationStatus.UNVERIFIED},
    # Terminals
    RecommendationStatus.CLOSED: set(),
    RecommendationStatus.PARTIAL: set(),
    RecommendationStatus.DISPUTED: set(),
    RecommendationStatus.UNVERIFIED: set(),
    RecommendationStatus.DENIED: set(),
    RecommendationStatus.EXPIRED: set(),
    RecommendationStatus.SUPERSEDED: set(),
}


class VerificationStatus(str, Enum):
    """Outcome verification ladder (mirrors MASTER_PLAN sec 14.3)."""

    REPORTED = "reported"
    OBSERVED = "observed"
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    DISPUTED = "disputed"
    UNVERIFIED = "unverified"


class AdvisorySource(str, Enum):
    """Attribution must be exact: never label a fallback/provider as Jev."""

    JEV = "jev"
    OPENCODE = "opencode"
    LLM_API = "llm_api"
    DETERMINISTIC_ONLY = "deterministic_only"
    MOCKED = "mocked"


class CycleStage(str, Enum):
    """Stages of one bounded improvement cycle (MASTER_PLAN sec 16.2)."""

    EVIDENCE_DISCOVERY = "evidence_discovery"
    INGESTION = "ingestion"
    VALIDATION = "validation"
    STATE_PROJECTION = "state_projection"
    FRESHNESS_ASSESSMENT = "freshness_assessment"
    OPPORTUNITY_DETECTION = "opportunity_detection"
    IMPACT_CALCULATION = "impact_calculation"
    ACTION_CANDIDATES = "action_candidates"
    ADVISORY = "advisory"
    ADVISORY_VALIDATION = "advisory_validation"
    RECOMMENDATION = "recommendation"
    GOVERNANCE = "governance"
    APPROVAL_WAIT = "approval_wait"
    PREFLIGHT = "preflight"
    EXECUTION = "execution"
    RECONCILIATION = "reconciliation"
    VERIFICATION = "verification"
    LEARNING_ELIGIBILITY = "learning_eligibility"
    LEARNING = "learning"
    CYCLE_SUMMARY = "cycle_summary"
    NEXT_CYCLE = "next_cycle"

    @classmethod
    def ordered(cls) -> list["CycleStage"]:
        return [s for s in cls]