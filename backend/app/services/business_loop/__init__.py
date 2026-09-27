"""Continuous business improvement loop (Phase 3) — package facade.

High-level pipeline (MASTER_PLAN §17.1), staged and DB-free:
    evidence -> state -> opportunity -> advisory -> recommendation ->
    governance -> execution (dry-run) -> reconciliation -> verification ->
    verified-only learning -> next cycle

The facade wires the reusable, deterministic loop modules. Real AI transport is
injected lazily via ``ai_gateway``/``canonical_advisor`` (shadow-only); nothing
here re-implements AI, Postgres persistence, or Temporal scheduling.
"""
from __future__ import annotations

from app.services.business_loop.advisory import (
    AdvisoryFn,
    TypedAdvisory,
    canonical_advisor,
    consult_advisory,
    deterministic_only_advisor,
)
from app.services.business_loop.contracts import (
    AdvisorySource,
    CycleStage,
    EvidenceQualityFlag,
    EvidenceValidationStatus,
    GovernanceOutcome,
    ImpactKind,
    LoopSchemaVersion,
    OpportunityType,
    RecommendationStatus,
    RECOMMENDATION_TRANSITIONS,
    VerificationStatus,
)
from app.services.business_loop.cycle import (
    CycleOrchestrator,
    CyclePolicy,
    CycleRun,
    CycleRepository,
    CycleStageState,
    InMemoryCycleRepository,
    derive_cycle_id,
)
from app.services.business_loop.evidence import (
    EvidenceRecord,
    EvidenceStore,
    checksum_of,
    freshness_flag,
    normalize_observation,
)
from app.services.business_loop.execution import (
    ExecutionIntent,
    Reconciliation,
    SyntheticReceipt,
    dry_run_execute,
    preflight,
    reconcile,
)
from app.services.business_loop.governance import (
    GovernanceDecision,
    approve_binding,
    evaluate_governance,
)
from app.services.business_loop.opportunity import (
    Opportunity,
    detect_opportunities,
    reproducible_impact,
)
from app.services.business_loop.outcomes import (
    LearningEligibility,
    OutcomeRecord,
    VerifiedOutcomeLedger,
    learning_eligibility,
    latest_verified_impact,
    verify_outcome,
)
from app.services.business_loop.recommendation import (
    Recommendation,
    RecommendationLifecycle,
    make_recommendation,
)
from app.services.business_loop.state import (
    BusinessStateSnapshot,
    DomainState,
    has_missing_required_fields,
    is_stale,
    project_state,
)

__all__ = [
    "AdvisoryFn",
    "AdvisorySource",
    "BusinessStateSnapshot",
    "CycleOrchestrator",
    "CyclePolicy",
    "CycleRepository",
    "CycleRun",
    "CycleStage",
    "CycleStageState",
    "DomainState",
    "EvidenceQualityFlag",
    "EvidenceRecord",
    "EvidenceStore",
    "EvidenceValidationStatus",
    "ExecutionIntent",
    "GovernanceDecision",
    "GovernanceOutcome",
    "ImpactKind",
    "InMemoryCycleRepository",
    "LearningEligibility",
    "LoopSchemaVersion",
    "Opportunity",
    "OpportunityType",
    "OutcomeRecord",
    "Recommendation",
    "RecommendationLifecycle",
    "RecommendationStatus",
    "RECOMMENDATION_TRANSITIONS",
    "Reconciliation",
    "SyntheticReceipt",
    "TypedAdvisory",
    "VerificationStatus",
    "VerifiedOutcomeLedger",
    "approve_binding",
    "canonical_advisor",
    "checksum_of",
    "consult_advisory",
    "derive_cycle_id",
    "detect_opportunities",
    "deterministic_only_advisor",
    "dry_run_execute",
    "evaluate_governance",
    "freshness_flag",
    "has_missing_required_fields",
    "is_stale",
    "learning_eligibility",
    "latest_verified_impact",
    "make_recommendation",
    "normalize_observation",
    "preflight",
    "project_inventory_domain",
    "project_state",
    "reconcile",
    "reproducible_impact",
    "verify_outcome",
]