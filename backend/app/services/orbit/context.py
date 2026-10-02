"""Canonical business context (spec §41).

``BusinessContext`` is the single object a later phase receives. This module is
the one producer of it.

The rule that shapes the whole module: **no placeholder empty structures.** Where
real data exists it is populated; where it does not, the field is accompanied by a
limitation that says so. An empty ``financial_state`` and an empty ``financial_state
because we have no financial evidence`` are different claims, and only the first is
made by returning ``{}``.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from app.services.orbit.contracts import (
    BusinessContext,
    BusinessEvent,
    BusinessProfile,
    CanonicalBusinessState,
    Conflict,
    DataQualityReport,
    DomainCapabilityFlag,
    DomainFreshness,
    Entity,
    EvidenceRegistry,
    FreshnessState,
    _utcnow,
)


def build_business_context(
    state: CanonicalBusinessState,
    profile: Optional[BusinessProfile] = None,
    quality: Optional[DataQualityReport] = None,
    registry: Optional[EvidenceRegistry] = None,
) -> BusinessContext:
    """Produce the canonical context for a business's current state."""
    limitations: list[str] = list(state.limitations)
    if profile is not None:
        limitations.extend(profile.limitations)

    # Domains with no evidence are named explicitly. Omitting them would let a
    # consumer assume "no data" meant "nothing to worry about".
    for flag in state.capabilities:
        if not flag.data_available:
            limitations.append(
                f"no data is available for {flag.domain.value}; anything the "
                f"business does there is unknown, not absent"
            )

    missing_domains = [
        f.domain for f in state.freshness if f.freshness is FreshnessState.MISSING
    ]
    if missing_domains:
        limitations.append(
            "no events observed for domains: " + ", ".join(sorted(missing_domains))
        )

    unresolved = [c for c in state.conflicts if not _is_resolved(c)]
    if unresolved:
        limitations.append(
            f"{len(unresolved)} unresolved conflict(s) are present; the affected "
            "values cannot be treated as settled"
        )

    return BusinessContext(
        business_id=state.business_id,
        tenant_id=getattr(state, "tenant_id", None),
        state_version=state.state_version,
        previous_state_version=state.previous_state_version,
        snapshot_timestamp=_utcnow(),
        business_profile=profile,
        freshness=state.freshness,
        data_quality=quality,
        entities=state.entities,
        events=state.events,
        relationships=state.relationships,
        conflicts=state.conflicts,
        financial_state=state.financial_state,
        inventory_state=state.inventory_state,
        procurement_state=state.procurement_state,
        workforce_state=state.workforce_state,
        marketing_state=state.marketing_state,
        customer_state=state.customer_state,
        external_context={},
        capabilities=state.capabilities,
        active_constraints={},
        active_goals={},
        # Phase 1 emits no recommendations and no outcomes. Those belong to the
        # Intelligence and Loop phases; leaving them empty here is correct, not a
        # placeholder.
        open_recommendations=(),
        previous_outcomes=(),
        evidence_ids=state.evidence_ids,
        source_artifacts=state.artifact_ids,
        ingestion_run_ids=state.ingestion_run_ids,
        historical_coverage=state.historical_coverage,
        evidence_coverage=state.evidence_coverage,
        limitations=tuple(dict.fromkeys(limitations)),
    )


def _is_resolved(conflict: Conflict) -> bool:
    from app.services.orbit.contracts import ConflictResolution

    return conflict.status is not ConflictResolution.UNRESOLVED


def context_capability_summary(context: BusinessContext) -> dict[str, dict[str, Any]]:
    """Per-domain capability, for API and UI consumers."""
    return {
        flag.domain.value: {
            "observed_capability": flag.observed_capability,
            "data_available": flag.data_available,
            "evidence_count": flag.evidence_count,
            "confidence": flag.confidence,
        }
        for flag in context.capabilities
    }


def context_freshness_summary(context: BusinessContext) -> dict[str, dict[str, Any]]:
    return {
        f.domain: {
            "freshness": f.freshness.value,
            "last_observed_at": f.last_observed_at.isoformat() if f.last_observed_at else None,
            "source_age_hours": f.source_age_hours,
            "reason": f.reason,
        }
        for f in context.freshness
    }


def assert_context_is_populated(context: BusinessContext) -> list[str]:
    """Return the problems that would make this context misleading.

    Used by tests and by the API layer to refuse serving a context that claims
    more than its evidence supports.
    """
    problems: list[str] = []
    if not context.state_version:
        problems.append("context has no state_version, so it cannot be traced to content")
    if not context.entities and not context.events and not context.limitations:
        problems.append(
            "context is empty and declares no limitations; an empty context must "
            "always state why it is empty"
        )
    if context.data_quality is not None and context.data_quality.overall_score is None:
        problems.append(
            "quality report has no overall score; ensure the report lists its "
            "unevaluated dimensions"
        )
    return problems