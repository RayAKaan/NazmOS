"""Canonical Intelligence layer — Orbit → Intelligence → Governance → Loop.

The Intelligence layer is the *understanding* layer. It consumes canonical
Orbit state and produces evidence-backed, deterministic artifacts:

    BusinessContext → Signals → RootCauses → ImpactEstimates
                    → Recommendations → AdvisoryResult → DecisionCandidates
                    → Alerts → OwnerCopilot

Intelligence never executes business mutations and never authorizes actions.
Governance decides permission; Loop executes, reconciles, verifies and learns.
"""
from app.services.intelligence.contracts import (
    INTELLIGENCE_CONTRACT_VERSION,
    AdvisoryResult,
    AdvisorySource,
    Alert,
    AlertSeverity,
    AlertStatus,
    BusinessContext,
    CopilotAnswer,
    DecisionCandidate,
    DecisionCandidateStatus,
    FreshnessStatus,
    ImpactEstimate,
    ImpactKind,
    IntelligenceRun,
    IntelligenceRunStatus,
    Recommendation,
    RecommendationStatus,
    RootCause,
    RootCauseSupportLevel,
    Signal,
    SignalSeverity,
    SignalStatus,
    evaluate_freshness,
    make_alert_fingerprint,
    make_signal_fingerprint,
)
from app.services.intelligence.context import (
    OrbitStateUnavailable,
    baseline_window,
    build_business_context,
)
from app.services.intelligence.monitoring import (
    MONITOR_VERSION,
    run_intelligence,
    run_is_idempotent,
    signals_by_fingerprint,
)
from app.services.intelligence.copilot import answer_from_run, classify_intent
from app.services.intelligence.decisions import (
    DECISION_CONTRACT_VERSION,
    build_decision_candidate,
    generate_decision_candidates,
    handoff_to_governance,
)
from app.services.intelligence.advisory import (
    ADVISORY_CONTRACT_VERSION,
    advisory_for_recommendation,
    deterministic_only,
)

__all__ = [
    "ADVISORY_CONTRACT_VERSION",
    "DECISION_CONTRACT_VERSION",
    "INTELLIGENCE_CONTRACT_VERSION",
    "MONITOR_VERSION",
    "AdvisoryResult",
    "AdvisorySource",
    "Alert",
    "AlertSeverity",
    "AlertStatus",
    "BusinessContext",
    "CopilotAnswer",
    "DecisionCandidate",
    "DecisionCandidateStatus",
    "FreshnessStatus",
    "ImpactEstimate",
    "ImpactKind",
    "IntelligenceRun",
    "IntelligenceRunStatus",
    "OrbitStateUnavailable",
    "Recommendation",
    "RecommendationStatus",
    "RootCause",
    "RootCauseSupportLevel",
    "Signal",
    "SignalSeverity",
    "SignalStatus",
    "advisory_for_recommendation",
    "answer_from_run",
    "baseline_window",
    "build_business_context",
    "build_decision_candidate",
    "classify_intent",
    "deterministic_only",
    "evaluate_freshness",
    "generate_decision_candidates",
    "handoff_to_governance",
    "make_alert_fingerprint",
    "make_signal_fingerprint",
    "run_intelligence",
    "run_is_idempotent",
    "signals_by_fingerprint",
]
