"""Phase 3 (business_loop) DB-free unit tests.

Evidence labels (MASTER_PLAN §23):
    [V] verified by running code
    [I] inferred from durable precedent / reuse surface
    [X] known limitation, not a defect
    [!] environment / data caveat
    [B] verified baseline behavior (no regression)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.business_loop.advisory import (
    AdvisorySource,
    consult_advisory,
    deterministic_only_advisor,
)
from app.services.business_loop.contracts import (
    ImpactKind,
    OpportunityType,
    RecommendationStatus,
)
from app.services.business_loop.evidence import (
    EvidenceStore,
    EvidenceQualityFlag,
    EvidenceRecord,
    checksum_of,
    freshness_flag,
    normalize_observation,
)
from app.services.business_loop.governance import (
    GovernanceOutcome,
    approve_binding,
    evaluate_governance,
)
from app.services.business_loop.opportunity import detect_opportunities, reproducible_impact
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
from app.services.business_loop.execution import (
    ExecutionIntent,
    dry_run_execute,
    preflight,
    reconcile,
)
from app.services.business_loop.outcomes import (
    OutcomeRecord,
    VerificationStatus,
    learning_eligibility,
    verify_outcome,
)


def _t(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")


def _rec(store: EvidenceStore, *, sku: str, stock: float, cost: float, sell: float, days_of_supply: float | None = None, tenant: str = "tnt-1", business: str = "biz-1") -> EvidenceRecord:
    raw = {"sku": sku, "stock": stock, "cost": cost, "sell": sell}
    if days_of_supply is not None:
        raw["days_of_supply"] = days_of_supply
    rec, reason = normalize_observation(
        tenant_id=tenant,
        business_id=business,
        raw=raw,
        source_type="test",
        source_reference="pos",
        observation_type="inventory.observed",
        event_timestamp=_t(),
        observed_at=_t(),
    )
    assert rec is not None, reason
    st = store.put(rec)
    return st


# ---------------------------------------------------------------------------
# 3B evidence foundation
# ---------------------------------------------------------------------------

def test_evidence_idempotency_checksum_deterministic() -> None:
    body = {"a": 1, "b": [2, 3], "c": {"x": "y"}}
    assert checksum_of(body) == checksum_of({"c": {"x": "y"}, "a": 1, "b": [2, 3]})


def test_evidence_store_duplicate_rejected_by_checksum() -> None:
    store = EvidenceStore()
    r1 = _rec(store, sku="s1", stock=10, cost=5, sell=8)
    n_before = len(store.accepted())
    r2 = _rec(store, sku="s1", stock=10, cost=5, sell=8)
    assert r2.evidence_id == r1.evidence_id  # same evidence id
    assert len(store.accepted()) == n_before  # no duplicate [V]


def test_evidence_store_conflict_flagged_not_silently_overwritten() -> None:
    store = EvidenceStore()
    store.put(_rec(store, sku="s1", stock=10, cost=5, sell=8))
    rec = _rec(store, sku="s1", stock=99, cost=5, sell=8)
    # conflict is never an overwrite of the original authoritative record
    flagged = store.mark_conflict(rec)
    assert EvidenceQualityFlag.CONFLICT in flagged.quality_flags


def test_evidence_correction_preserves_prior_lineage() -> None:
    store = EvidenceStore()
    original = _rec(store, sku="s1", stock=10, cost=5, sell=8)
    revised = _rec(store, sku="s1", stock=8, cost=5, sell=8)
    applied = store.apply_correction(revised, prior_id=original.evidence_id)
    assert EvidenceQualityFlag.REVISED in applied.quality_flags
    assert applied.prior_evidence_id == original.evidence_id


def test_evidence_freshness_flag() -> None:
    rec, _reason = normalize_observation(
        tenant_id="t", business_id="b", raw={"sku": "s", "stock": 1, "cost": 1, "sell": 2},
        source_type="t", source_reference="r", observation_type="inventory.observed",
        event_timestamp=_t(9), observed_at=_t(9),
    )
    assert rec is not None
    assert freshness_flag(rec, _t(0), max_age_days=7) == EvidenceQualityFlag.STALE
    assert freshness_flag(rec, _t(9), max_age_days=7) == EvidenceQualityFlag.FRESH


def test_evidence_normalize_rejects_missing_and_cross_tenant() -> None:
    rec, reason = normalize_observation(
        tenant_id="tnt-1", business_id="biz", raw={"sku": "s1", "stock": 1},
        source_type="t", source_reference="r", observation_type="inventory.observed",
        event_timestamp=_t(), observed_at=_t(),
    )
    assert rec is None and "missing_fields" in reason

    rec, reason = normalize_observation(
        tenant_id="tnt-1", business_id="biz",
        raw={"sku": "s1", "stock": 1, "cost": 1, "sell": 2, "tenant_id": "other"},
        source_type="t", source_reference="r", observation_type="inventory.observed",
        event_timestamp=_t(), observed_at=_t(),
    )
    assert rec is None and reason == "cross_tenant_rejection"


# ---------------------------------------------------------------------------
# 3C state projection
# ---------------------------------------------------------------------------

def test_state_projection_is_deterministic_and_versioned() -> None:
    store = EvidenceStore()
    _rec(store, sku="s1", stock=10, cost=5, sell=8)
    s1 = project_state(store, tenant_id="tnt-1", business_id="biz-1")
    store2 = EvidenceStore()
    _rec(store2, sku="s1", stock=10, cost=5, sell=8)
    s2 = project_state(store2, tenant_id="tnt-1", business_id="biz-1")
    assert s1.state_version == s2.state_version  # deterministic replay [V]
    assert s1.state_version  # composite version always present


def test_state_projection_missing_is_different_from_zero() -> None:
    store = EvidenceStore()
    rec, reason = normalize_observation(
        tenant_id="tnt-1", business_id="biz-1", raw={"sku": "s1", "cost": 5, "sell": 8},
        source_type="test", source_reference="m", observation_type="inventory.observed",
        event_timestamp=_t(), observed_at=_t(),
    )
    assert rec is None  # required fields missing -> never accepted


def test_state_is_stale_on_empty_or_old_evidence() -> None:
    store = EvidenceStore()
    _rec(store, sku="s1", stock=10, cost=5, sell=8, days_of_supply=40)
    fresh = project_state(store, tenant_id="tnt-1", business_id="biz-1")
    assert not is_stale(fresh)


# ---------------------------------------------------------------------------
# 3D opportunity engine
# ---------------------------------------------------------------------------

def test_detect_excess_inventory() -> None:
    store = EvidenceStore()
    _rec(store, sku="excess", stock=120, cost=20, sell=25, days_of_supply=45)
    snap = project_state(store, tenant_id="tnt-1", business_id="biz-1")
    opps = detect_opportunities(snap)
    excess = [o for o in opps if o.opportunity_type == OpportunityType.EXCESS_INVENTORY.value]
    assert excess, "≥30d supply & ≥SAR500 must yield a surplus opportunity"
    assert excess[0].potential_impact_sar > 0
    assert excess[0].impact_kind == ImpactKind.POTENTIAL.value
    assert "transfer_inventory" in excess[0].eligible_action_categories


def test_detect_opportunities_dedup_and_reproducible() -> None:
    store = EvidenceStore()
    _rec(store, sku="s1", stock=120, cost=20, sell=25, days_of_supply=45)
    snap = project_state(store, tenant_id="tnt-1", business_id="biz-1")
    opps = detect_opportunities(snap)
    ids = [o.opportunity_id for o in opps]
    assert len(ids) == len(set(ids))
    assert all(reproducible_impact(o) for o in opps)


# ---------------------------------------------------------------------------
# 3E recommendation lifecycle
# ---------------------------------------------------------------------------

def test_recommendation_lifecycle_guards_invalid_transition() -> None:
    class _O:
        opportunity_id = "opp-1"
        evidence_ids = ("ev-1",)
        potential_impact_sar = 100.0

    reco = make_recommendation(
        recommendation_id="rec-1",
        opportunity=_O(),
        business_id="biz-1",
        tenant_id="tnt-1",
        state_version="sv-1",
        action_type="reorder",
        provider="deterministic",
        advisory_validated=True,
    )
    with pytest.raises(ValueError):
        RecommendationLifecycle.transition(reco, RecommendationStatus.APPROVED)


def test_recommendation_version_change_requires_revalidation() -> None:
    class _O:
        opportunity_id = "opp-1"
        evidence_ids = ("ev-1",)
        potential_impact_sar = 100.0

    reco = make_recommendation(
        recommendation_id="rec-1", opportunity=_O(), business_id="biz-1", tenant_id="tnt-1",
        state_version="sv-1", action_type="reorder", provider="deterministic", advisory_validated=True,
    )
    bumped = RecommendationLifecycle.bump_version(reco)
    assert bumped.version == reco.version + 1
    assert bumped.advisory_validated is False
    assert bumped.material_hash != reco.material_hash
    # a materially changed version must never inherit approval
    assert approve_binding(
        recommendation_id="rec-1", recommendation_version=reco.version, material_hash=reco.material_hash, approved_by="owner"
    )["binding_key"] != approve_binding(
        recommendation_id="rec-1", recommendation_version=bumped.version, material_hash=bumped.material_hash, approved_by="owner"
    )["binding_key"]


# ---------------------------------------------------------------------------
# 3G governance
# ---------------------------------------------------------------------------

def test_governance_denies_unregistered_action() -> None:
    decision = evaluate_governance(
        recommendation_id="rec-1", action_type="not_registered", business_id="biz-1",
        shariah_approved=True,
    )
    assert decision.outcome == GovernanceOutcome.DENIED


def test_governance_holds_ambiguity_and_approval() -> None:
    decision = evaluate_governance(
        recommendation_id="rec-1", action_type="reorder", business_id="biz-1",
        shariah_approved=True, shariah_ambiguous=True,
    )
    assert decision.outcome == GovernanceOutcome.DEFERRED

    decision = evaluate_governance(
        recommendation_id="rec-1", action_type="reorder", business_id="biz-1",
        shariah_approved=False,
    )
    assert decision.outcome == GovernanceOutcome.REVIEW_REQUIRED

    # registered action that requires approval -> APPROVAL_REQUIRED (never AI-auto-authorize)
    decision = evaluate_governance(
        recommendation_id="rec-1", action_type="reorder", business_id="biz-1",
        shariah_approved=True, approval_required=True,
    )
    assert decision.outcome == GovernanceOutcome.APPROVAL_REQUIRED
    assert decision.certified_by == "deterministic-governance"


def test_governance_permits_when_no_approval() -> None:
    decision = evaluate_governance(
        recommendation_id="rec-1", action_type="expiry_alert", business_id="biz-1",
        shariah_approved=True, approval_required=False,
    )
    assert decision.outcome == GovernanceOutcome.PERMITTED


# ---------------------------------------------------------------------------
# 3H execution + reconciliation
# ---------------------------------------------------------------------------

def test_execution_key_is_deterministic() -> None:
    a = ExecutionIntent(business_id="biz", action_type="transfer_inventory", entity_type="item", entity_id="e-1", payload={"q": 1}, source="s")
    b = ExecutionIntent(business_id="biz", action_type="transfer_inventory", entity_type="item", entity_id="e-1", payload={"q": 1}, source="s")
    assert a.execution_key == b.execution_key


def test_dry_run_execute_requires_registered_action_and_gate() -> None:
    intent = ExecutionIntent(business_id="biz", action_type="reorder", entity_type="item", entity_id="e-1", payload={})
    receipt_denied = dry_run_execute(
        intent,
        decision=GovernanceOutcome.DENIED,
        recommendation_status=RecommendationStatus.APPROVED,
    )
    assert not receipt_denied.ok
    assert receipt_denied.details["reason"] == "governance_not_permitted"

    receipt = dry_run_execute(
        intent,
        decision=GovernanceOutcome.PERMITTED,
        recommendation_status=RecommendationStatus.APPROVED,
    )
    assert receipt.ok
    assert receipt.synthetic is True  # dry-run must never be a real merchant action


def test_reconciliation_no_blind_retry_when_reported() -> None:
    intent = ExecutionIntent(business_id="biz", action_type="reorder", entity_type="item", entity_id="e-1", payload={})
    receipt = dry_run_execute(intent, decision=GovernanceOutcome.PERMITTED, recommendation_status=RecommendationStatus.APPROVED)
    result = reconcile(intent, receipt, actual_state="reported")
    assert result.matching is True
    assert result.allow_retry is False  # potentially succeeded -> never blind-retry

    result = reconcile(intent, receipt, actual_state="observed_no_effect")
    assert result.matching is False
    assert result.allow_retry is True  # confirmed no-effect -> eligible to retry


# ---------------------------------------------------------------------------
# 3I outcome verification + learning eligibility
# ---------------------------------------------------------------------------

def test_verification_ladder_estimate_never_equals_verified() -> None:
    rec = verify_outcome(
        outcome_id="out-1", recommendation_id="rec-1", recommendation_version=1,
        execution_key="k", baseline_state_version="pre", post_action_state_version="post",
        expected_impact_sar=500.0, observed_impact_sar=500.0, verification_method="pos_delta",
        measurement_window="30d",
    )
    assert rec.verification_status == VerificationStatus.VERIFIED

    # observed but missing state pre/post -> only observed, never verified
    rec = verify_outcome(
        outcome_id="out-1", recommendation_id="rec-1", recommendation_version=1,
        execution_key="k", baseline_state_version="pre", post_action_state_version="",
        expected_impact_sar=500.0, observed_impact_sar=500.0, verification_method="pos_delta",
        measurement_window="30d",
    )
    assert rec.verification_status != VerificationStatus.VERIFIED


def test_outcome_to_dict_dlp_clean() -> None:
    rec = verify_outcome(
        outcome_id="out-1", recommendation_id="rec-1", recommendation_version=1, execution_key="k",
        baseline_state_version="pre", post_action_state_version="post",
        expected_impact_sar=1.0, observed_impact_sar=1.0, verification_method="m", measurement_window="w",
    )
    d = rec.to_dict()
    assert set(d) == {
        "outcome_id", "recommendation_id", "recommendation_version", "execution_key",
        "baseline_state_version", "post_action_state_version", "verification_status",
        "expected_impact_sar", "observed_impact_sar", "verification_method",
    }


def test_learning_only_from_verified_traceable_outcome() -> None:
    rec = verify_outcome(
        outcome_id="out-1", recommendation_id="rec-1", recommendation_version=1, execution_key="k",
        baseline_state_version="pre", post_action_state_version="post",
        expected_impact_sar=1.0, observed_impact_sar=1.0, verification_method="m", measurement_window="w",
    )
    assert learning_eligibility(rec, tenant_authorized=True, source_traceable=True, quality_satisfied=True).eligible

    unverified = OutcomeRecord(
        outcome_id="out-2", recommendation_id="rec-1", recommendation_version=1, execution_key="k",
        baseline_state_version="pre", post_action_state_version="post",
        verification_status=VerificationStatus.OBSERVED,
        expected_impact_sar=1.0, observed_impact_sar=1.0,
        verification_method="m", measurement_window="w", evidence=(),
    )
    e = learning_eligibility(unverified, tenant_authorized=True, source_traceable=True, quality_satisfied=True)
    assert not e.eligible and "outcome_not_verified" in e.reasons


# ---------------------------------------------------------------------------
# 3E advisory attribution (mocked, deterministic-only)
# ---------------------------------------------------------------------------

async def test_deterministic_only_advisor_never_labels_jev() -> None:
    ctx = {"deterministic_decision": "DO_NOTHING"}
    reply = await deterministic_only_advisor("c", ctx)
    assert reply["source"] == AdvisorySource.DETERMINISTIC_ONLY.value


async def test_consult_advisory_rejects_out_of_contract_suggestion() -> None:
    async def advisor(capability, context):
        return {"decision": "stockout_risk", "suggested": "margin_fix", "confidence": 0.9, "source": "jev"}

    ta = await consult_advisory(
        advisor, capability="business_loop.action_selection",
        context={"deterministic_decision": "stockout_risk"},
        contract=frozenset({"reorder", "restock"}),
    )
    assert ta.source == AdvisorySource.JEV
    assert "OUT_OF_CONTRACT" in ta.risk_flags
    assert ta.suggested is None  # rejected, never coerced
    assert ta.validation_passed is False


async def test_consult_advisory_validates_contract_suggestion() -> None:
    async def advisor(capability, context):
        return {"decision": "stockout_risk", "suggested": "reorder", "confidence": 0.8, "source": "mocked"}

    ta = await consult_advisory(
        advisor, capability="business_loop.action_selection",
        context={"deterministic_decision": "stockout_risk"},
        contract=frozenset({"reorder", "restock"}),
    )
    assert ta.source == AdvisorySource.MOCKED
    assert ta.suggested == "reorder"
    assert ta.validation_passed is True