"""Phase 4F — canonical execution→outcome linkage + verified capture (DB-free).

Proves the smallest canonical association between an executed cycle and its
outcome record, and its persistence through the EXISTING OutcomeLedger V1:

   * executed action -> OutcomeRecord -> measurement -> verification ->
     OutcomeLedger V1 -> deterministic learning-eligibility gate

Conservative by design: an estimate is never a measurement, a measurement is
never a verification, a reused identical state snapshot is NEVER verified, and
a Jev advisory alone can neither verify nor authorize learning. Replays of the
same execution coalesce onto one ledger row; tenant scope is enforced.

Evidence labels: [V] running code, [B] baseline regression, [X] limitation.
"""
from __future__ import annotations

import json

import pytest

from app.services.business_loop.contracts import AdvisorySource, VerificationStatus
from app.services.business_loop.cycle import CycleOrchestrator, CyclePolicy, CycleRun, InMemoryCycleRepository
from app.services.business_loop.evidence import EvidenceStore, normalize_observation
from app.services.business_loop.outcome_linkage import (
    OutcomeAttachment,
    OutcomeLinkage,
    attach_cycle_outcome,
    attach_outcome,
    attribution_quality,
    attribution_sufficient,
    build_linkage,
    derive_outcome_key,
    outcome_from_run,
)
from app.services.business_loop.outcomes import OutcomeRecord, learning_eligibility, unverified_outcome, verify_outcome
from app.services.outcome_ledger import OutcomeLedger


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _verified_outcome(**overrides) -> OutcomeRecord:
    base = dict(
        outcome_id="out-4f-1",
        recommendation_id="rec-4f-1",
        recommendation_version=2,
        execution_key="exec-4f-1",
        baseline_state_version="pre-4f",
        post_action_state_version="post-4f",
        expected_impact_sar=500.0,
        observed_impact_sar=900.0,
        verification_method="synthetic_measurement",
        measurement_window="1d",
    )
    base.update(overrides)
    return verify_outcome(**base)


def _run(
    *,
    outcome: OutcomeRecord | None = None,
    state_output: dict | None = None,
    cycle_id: str = "cycle-4f-1",
    tenant_id: str = "tnt-4f",
    business_id: str = "biz-4f-1",
    starting_state_version: str = "pre-4f",
    watermark: str = "2024-01-01T00:00:00Z",
    created_at: str = "2024-01-01T00:00:00Z",
) -> CycleRun:
    run = CycleRun(
        cycle_id=cycle_id,
        tenant_id=tenant_id,
        business_id=business_id,
        trigger="synthetic",
        trigger_token="tok-4f",
        created_at=created_at,
        starting_state_version=starting_state_version,
        evidence_watermark=watermark,
        stages=[],
    )
    if state_output:
        run.state_output.update(state_output)
    if outcome is not None:
        run.state_output["outcome"] = outcome.to_dict()
        run.state_output["post_state_version"] = outcome.post_action_state_version
    return run


def _run_with_execution(
    *,
    outcome: OutcomeRecord,
    execution_ok: bool = True,
    skipped: bool = False,
    advisory: dict | None = None,
    opportunity_id: str = "opp-4f-1",
    action_type: str = "transfer_inventory",
    **run_kwargs,
) -> CycleRun:
    run = _run(outcome=outcome, **run_kwargs)
    if skipped:
        run.state_output["execution"] = {"skipped": True, "reason": "governance_not_permitted"}
    else:
        run.state_output["execution"] = {
            "action_type": action_type,
            "recommendation_id": outcome.recommendation_id,
            "execution_key": outcome.execution_key,
            "receipt": {
                "receipt_id": "rcpt-4f-1",
                "ok": execution_ok,
                "synthetic": True,
                "details": {"note": "SYNTHETIC - not a real merchant action"},
            },
        }
    run.state_output["recommendations"] = [
        {
            "recommendation_id": outcome.recommendation_id,
            "version": outcome.recommendation_version,
            "opportunity_id": opportunity_id,
            "action_type": action_type,
            "status": "approved",
            "expected_impact_sar": outcome.expected_impact_sar,
        }
    ]
    run.state_output["opportunities"] = [
        {"opportunity_id": opportunity_id, "opportunity_type": "excess_inventory"}
    ]
    if advisory is not None:
        run.state_output["advisory"] = advisory
    else:
        run.state_output["advisory"] = {
            "source": "none",
            "provider": "deterministic",
            "model": "n/a",
            "validation_passed": True,
        }
    return run


# ---------------------------------------------------------------------------
# A. linkage construction: executed action -> OutcomeRecord
# ---------------------------------------------------------------------------


def test_executed_action_produces_canonical_linkage() -> None:
    outcome = _verified_outcome()
    run = _run_with_execution(outcome=outcome)
    linkage = build_linkage(run)
    assert isinstance(linkage, OutcomeLinkage)
    assert linkage.outcome_id == "out-4f-1"
    assert linkage.recommendation_id == "rec-4f-1"
    assert linkage.execution_key == "exec-4f-1"
    assert linkage.action_type == "transfer_inventory"
    assert linkage.opportunity_id == "opp-4f-1"
    assert linkage.verification_status == VerificationStatus.VERIFIED.value
    d = linkage.to_dict()
    json.dumps(d)  # JSON-safe [V]


def test_unknown_execution_has_no_verifiable_outcome() -> None:
    run = _run()
    run.state_output["execution"] = {"skipped": True, "reason": "governance_not_permitted"}
    outcome = outcome_from_run(run)
    assert outcome.verification_status == VerificationStatus.UNVERIFIED
    assert not outcome.is_verified
    assert not outcome.recommendation_id and not outcome.execution_key
    assert attach_cycle_outcome(run) is None  # no realized execution to record


def test_linkage_preserves_canonical_ids() -> None:
    outcome = _verified_outcome()
    run = _run_with_execution(outcome=outcome, cycle_id="cycle-X", tenant_id="tnt-Y", business_id="biz-Z")
    linkage = build_linkage(run)
    assert linkage.cycle_id == "cycle-X"
    assert linkage.tenant_id == "tnt-Y"
    assert linkage.business_id == "biz-Z"
    # Stable identity: same inputs -> same key (restart/replay safe).
    assert linkage.outcome_key == derive_outcome_key(
        tenant_id="tnt-Y",
        execution_key=outcome.execution_key,
        recommendation_id=outcome.recommendation_id,
        recommendation_version=outcome.recommendation_version,
    )


# ---------------------------------------------------------------------------
# B. measurement ladder: estimate != measured != verified
# ---------------------------------------------------------------------------


def test_estimate_and_measurement_are_distinct_facts() -> None:
    outcome = _verified_outcome(expected_impact_sar=500.0, observed_impact_sar=900.0)
    linkage = build_linkage(_run_with_execution(outcome=outcome))
    assert linkage.expected_impact_sar == 500.0
    assert linkage.observed_impact_sar == 900.0
    assert linkage.impact_delta_sar == 400.0  # observed - expected, computed not invented
    assert linkage.expected_impact_sar != linkage.observed_impact_sar


def test_measured_is_not_verified_without_criteria() -> None:
    # measured (900.0) but missing baseline snapshot -> PARTIALLY_VERIFIED, never VERIFIED
    rec = _verified_outcome(baseline_state_version="", post_action_state_version="post-4f")
    assert rec.verification_status == VerificationStatus.PARTIALLY_VERIFIED
    assert not rec.is_verified


def test_estimate_never_equals_measured_never_equals_verified() -> None:
    # estimate only (no measured value) -> REPORTED
    rec = _verified_outcome(observed_impact_sar=None)
    assert rec.verification_status == VerificationStatus.REPORTED
    assert rec.observed_impact_sar is None
    # measured but no method -> OBSERVED (invalid measurement, never VERIFIED)
    rec2 = _verified_outcome(verification_method="")
    assert rec2.verification_status == VerificationStatus.OBSERVED
    assert not rec2.is_verified
    # measured + method + distinct versions -> VERIFIED
    rec3 = _verified_outcome()
    assert rec3.verification_status == VerificationStatus.VERIFIED


def test_same_state_version_is_never_verified() -> None:
    rec = _verified_outcome(baseline_state_version="SAME", post_action_state_version="SAME")
    assert rec.verification_status != VerificationStatus.VERIFIED
    assert rec.verification_status == VerificationStatus.PARTIALLY_VERIFIED
    # eligibility must reject the reused snapshot even if status were VERIFIED
    synthetic = OutcomeRecord(
        outcome_id="o",
        recommendation_id="rec-1",
        recommendation_version=1,
        execution_key="k",
        baseline_state_version="SAME",
        post_action_state_version="SAME",
        verification_status=VerificationStatus.VERIFIED,
        expected_impact_sar=1.0,
        observed_impact_sar=1.0,
        verification_method="m",
        measurement_window="w",
        evidence=(),
    )
    e = learning_eligibility(synthetic, tenant_authorized=True, source_traceable=True, quality_satisfied=True)
    assert not e.eligible
    assert "state_versions_not_distinct" in e.reasons


def test_distinct_state_versions_verify() -> None:
    rec = _verified_outcome(baseline_state_version="pre-A", post_action_state_version="post-A")
    assert rec.verification_status == VerificationStatus.VERIFIED


# ---------------------------------------------------------------------------
# C. measurement evidence watermark
# ---------------------------------------------------------------------------


def test_watermark_and_evidence_flow_into_linkage() -> None:
    outcome = _verified_outcome()
    run = _run_with_execution(outcome=outcome, watermark="2024-02-02T02:02:02Z")
    linkage = build_linkage(run)
    assert linkage.evidence_watermark == "2024-02-02T02:02:02Z"
    assert linkage.measurement_evidence_count == 0  # loop outcome carries no evidence tuple


# ---------------------------------------------------------------------------
# D. deterministic attribution: Jev can neither verify nor authorize learning
# ---------------------------------------------------------------------------


def test_attribution_quality_is_deterministic() -> None:
    assert (
        attribution_quality(
            verification_status=VerificationStatus.VERIFIED,
            verification_method="synthetic_measurement",
            observed_impact_sar=900.0,
            advisory_source=AdvisorySource.JEV.value,
            advisory_provider="system-one",
        )
        == "deterministic_measurement"
    )  # measurement dominates advisory; Jev cannot downgrade it
    assert (
        attribution_quality(
            verification_status=VerificationStatus.OBSERVED,
            verification_method="",
            observed_impact_sar=None,
            advisory_source=AdvisorySource.JEV.value,
            advisory_provider="system-one",
        )
        == "jev_advisory_only"
    )
    assert (
        attribution_quality(
            verification_status=VerificationStatus.OBSERVED,
            verification_method="",
            observed_impact_sar=None,
            advisory_source="",
            advisory_provider="",
        )
        == "none"
    )


def test_jev_advisory_only_is_never_sufficient() -> None:
    q = attribution_quality(
        verification_status=VerificationStatus.OBSERVED,
        verification_method="",
        observed_impact_sar=None,
        advisory_source=AdvisorySource.JEV.value,
        advisory_provider="system-one",
    )
    assert q == "jev_advisory_only"
    assert attribution_sufficient(q) is False
    # deterministic measurement and provider/fallback attribution are candidate-sufficient
    assert attribution_sufficient("deterministic_measurement") is True
    assert attribution_sufficient("provider_advisory") is True


def test_jev_advisor_cannot_verify_or_gate_learning() -> None:
    # Jev advisory is not even an input to verification (verify_outcome is pure).
    rec = _verified_outcome()
    # even a "jev-sourced" advisory record attached to the run neither verifies nor downgrades
    run = _run_with_execution(
        outcome=rec,
        advisory={"source": AdvisorySource.JEV.value, "provider": "system-one", "model": "jev-1.13.0", "validation_passed": True, "risk_flags": []},
    )
    linkage = build_linkage(run)
    assert linkage.attribution_source == AdvisorySource.JEV.value
    assert linkage.attribution_quality == "deterministic_measurement"  # measured path wins
    eligibility = learning_eligibility(
        rec,
        tenant_authorized=True,
        source_traceable=True,
        quality_satisfied=True,
        attribution_sufficient=attribution_sufficient(linkage.attribution_quality),
    )
    assert eligibility.eligible


# ---------------------------------------------------------------------------
# E. attachment through OutcomeLedger V1 (idempotent, readback-confirmed)
# ---------------------------------------------------------------------------


def test_verified_outcome_attach_readback_confirmed(tmp_path) -> None:
    ledger = OutcomeLedger(str(tmp_path / "ledger.sqlite"))
    outcome = _verified_outcome()
    run = _run_with_execution(outcome=outcome)
    attach = attach_cycle_outcome(run, ledger=ledger)
    assert isinstance(attach, OutcomeAttachment)
    assert attach.recorded is True
    assert attach.row_present is True
    assert attach.row_verified is True
    assert attach.outcome_status == "confirmed"
    assert attach.reason == ""
    assert attach.ledger == "outcome_ledger_v1"
    row = ledger.row(attach.outcome_key)
    assert row is not None
    assert row["verified"] is True
    assert row["capability"] == "business_loop.verified"
    assert row["capsule_hash"] == outcome.execution_key
    assert row["schema_version"] == "v1"


def test_duplicate_attach_coalesces_one_row(tmp_path) -> None:
    ledger = OutcomeLedger(str(tmp_path / "ledger.sqlite"))
    outcome = _verified_outcome()
    run = _run_with_execution(outcome=outcome)
    first = attach_cycle_outcome(run, ledger=ledger)
    second = attach_outcome(outcome, run=run, ledger=ledger)
    assert first.recorded is True and second.recorded is True
    assert first.outcome_key == second.outcome_key
    assert ledger.summary()["total_captured"] == 1  # idempotent ON CONFLICT upgrade
    assert ledger.summary()["verified"] == 1


def test_concurrent_duplicate_attach_still_one_row(tmp_path) -> None:
    ledger = OutcomeLedger(str(tmp_path / "ledger.sqlite"))
    outcome = _verified_outcome()
    # Two independent capture attempts for the same key (the V1 write path is
    # serialized by SQLite); the second must upgrade, never duplicate.
    a1 = attach_outcome(outcome, run=_run_with_execution(outcome=outcome), ledger=ledger)
    a2 = attach_outcome(outcome, run=_run_with_execution(outcome=outcome), ledger=ledger)
    assert a1.outcome_key == a2.outcome_key
    assert ledger.summary()["total_captured"] == 1


def test_unresolved_execution_is_not_attached(tmp_path) -> None:
    ledger = OutcomeLedger(str(tmp_path / "ledger.sqlite"))
    outcome = _verified_outcome()
    run = _run_with_execution(outcome=outcome, execution_ok=False)
    assert attach_cycle_outcome(run, ledger=ledger) is None


def test_attach_never_fires_before_the_outcome_record(tmp_path) -> None:
    ledger = OutcomeLedger(str(tmp_path / "ledger.sqlite"))
    outcome = _verified_outcome()
    run = _run_with_execution(outcome=outcome)
    # A run advanced past EXECUTION but before VERIFICATION has no outcome yet:
    # advancing must NOT fabricate a placeholder capture on an empty key.
    run.state_output["outcome"] = {}
    assert attach_cycle_outcome(run, ledger=ledger) is None
    assert ledger.summary()["total_captured"] == 0


def test_pending_measurement_is_reported_and_flagged(tmp_path) -> None:
    ledger = OutcomeLedger(str(tmp_path / "ledger.sqlite"))
    outcome = _verified_outcome(observed_impact_sar=None)
    assert outcome.verification_status == VerificationStatus.REPORTED
    run = _run_with_execution(outcome=outcome)
    attach = attach_cycle_outcome(run, ledger=ledger)
    assert attach is not None
    assert attach.recorded is True
    assert attach.row_present is True
    assert attach.row_verified is False
    assert attach.outcome_status == "unknown"
    assert ledger.verified_outcomes() == []  # pending rows never leak to learning


def test_invalid_measurement_is_never_verified() -> None:
    outcome = _verified_outcome(verification_method="")
    assert outcome.verification_status == VerificationStatus.OBSERVED
    assert not outcome.is_verified
    e = learning_eligibility(
        outcome, tenant_authorized=True, source_traceable=True, quality_satisfied=True, attribution_sufficient=True
    )
    assert not e.eligible and "outcome_not_verified" in e.reasons


def test_asset_settlement_unknown_outcome_never_reaches_verified_reads(tmp_path) -> None:
    ledger = OutcomeLedger(str(tmp_path / "ledger.sqlite"))
    outcome = unverified_outcome(outcome_id="out-unk", recommendation_id="rec-unk", recommendation_version=1, execution_key="exec-unk")
    logger = attach_outcome(outcome, run=_run(outcome=outcome), ledger=ledger)
    assert logger.recorded is True
    assert logger.outcome_status == "rejected"
    assert logger.row_verified is False
    assert ledger.verified_outcomes() == []


# ---------------------------------------------------------------------------
# F. learning eligibility gate
# ---------------------------------------------------------------------------


def test_learning_eligibility_accepted() -> None:
    rec = _verified_outcome()
    assert rec.verification_status == VerificationStatus.VERIFIED
    eligibility = learning_eligibility(
        rec, tenant_authorized=True, source_traceable=True, quality_satisfied=True, attribution_sufficient=True
    )
    assert eligibility.eligible is True
    assert eligibility.reasons == ()


def test_learning_eligibility_rejects_attribution_insufficient() -> None:
    rec = _verified_outcome()
    eligibility = learning_eligibility(
        rec, tenant_authorized=True, source_traceable=True, quality_satisfied=True, attribution_sufficient=False
    )
    assert not eligibility.eligible
    assert "attribution_insufficient" in eligibility.reasons


def test_learning_eligibility_rejects_unverified_even_when_else_ok() -> None:
    rec = _verified_outcome(observed_impact_sar=None)  # REPORTED
    eligibility = learning_eligibility(
        rec, tenant_authorized=True, source_traceable=True, quality_satisfied=True, attribution_sufficient=True
    )
    assert not eligibility.eligible
    assert "outcome_not_verified" in eligibility.reasons


def test_learning_eligibility_rejects_untraceable_source() -> None:
    rec = _verified_outcome(recommendation_id="", execution_key="")
    eligibility = learning_eligibility(
        rec, tenant_authorized=True, source_traceable=True, quality_satisfied=True, attribution_sufficient=True
    )
    assert not eligibility.eligible
    assert "source_not_traceable" in eligibility.reasons


# ---------------------------------------------------------------------------
# G. attribution + tenant isolation
# ---------------------------------------------------------------------------


def test_provider_and_fallback_attribution_captured_verbatim(tmp_path) -> None:
    ledger = OutcomeLedger(str(tmp_path / "ledger.sqlite"))
    outcome = _verified_outcome()
    run = _run_with_execution(
        outcome=outcome,
        advisory={"source": "fallback", "provider": "provider-beta", "model": "beta-1.0", "validation_passed": True, "risk_flags": []},
    )
    attach = attach_cycle_outcome(run, ledger=ledger)
    row = ledger.row(attach.outcome_key)
    assert row["provider"] == "provider-beta"
    assert row["model"] == "beta-1.0"
    assert row["source"] == "fallback"


def test_tenant_isolation_keys_never_collide() -> None:
    k_a = derive_outcome_key(tenant_id="tnt-a", execution_key="exec-1", recommendation_id="rec-1", recommendation_version=1)
    k_b = derive_outcome_key(tenant_id="tnt-b", execution_key="exec-1", recommendation_id="rec-1", recommendation_version=1)
    assert k_a != k_b
    # same tenant + same execution -> stable identity (dedup, not randomized)
    k_a2 = derive_outcome_key(tenant_id="tnt-a", execution_key="exec-1", recommendation_id="rec-1", recommendation_version=1)
    assert k_a == k_a2


def test_tenant_unscoped_attach_is_refused() -> None:
    outcome = _verified_outcome()
    attach = attach_outcome(outcome, run=None)  # no tenant binding -> refuse
    assert attach.recorded is False
    assert attach.reason == "tenant_unscoped"


def test_attach_cycle_outcome_marker_gate(tmp_path) -> None:
    ledger = OutcomeLedger(str(tmp_path / "ledger.sqlite"))
    outcome = _verified_outcome()
    run = _run_with_execution(outcome=outcome)
    first = attach_cycle_outcome(run, ledger=ledger)
    assert first.recorded is True
    # the activity persists the marker with the run before any replay
    run.state_output["outcome_recorded"] = first.to_dict()
    second = attach_cycle_outcome(run, ledger=ledger)
    assert second is None
    assert ledger.summary()["total_captured"] == 1


# ---------------------------------------------------------------------------
# H. restart-safe, JSON-safe linkage + orchestrator end-to-end
# ---------------------------------------------------------------------------


def test_linkage_is_json_safe_and_restart_stable() -> None:
    outcome = _verified_outcome()
    run1 = _run_with_execution(outcome=outcome, cycle_id="cycle-R", tenant_id="tnt-R", business_id="biz-R")
    d1 = build_linkage(run1).to_dict()
    # Rebuild the "restarted" run purely from the persisted state_output copy.
    run2 = _run(
        outcome=outcome,
        state_output=dict(run1.state_output),
        cycle_id="cycle-R",
        tenant_id="tnt-R",
        business_id="biz-R",
        starting_state_version=run1.starting_state_version,
        watermark=run1.evidence_watermark,
    )
    d2 = build_linkage(run2).to_dict()
    assert d1 == d2
    assert d1["outcome_key"] == d2["outcome_key"]
    json.dumps(d1)


def _ingest(store: EvidenceStore, *, tenant_id: str, business_id: str, sku: str, stock: float, cost: float, sell: float, days_of_supply: float) -> None:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    raw = {"sku": sku, "stock": stock, "cost": cost, "sell": sell, "days_of_supply": days_of_supply}
    rec, reason = normalize_observation(
        tenant_id=tenant_id,
        business_id=business_id,
        raw=raw,
        source_type="synthetic.pos",
        source_reference=sku,
        observation_type="inventory.observed",
        event_timestamp=(now - timedelta(minutes=1)).isoformat(timespec="seconds"),
        observed_at=(now - timedelta(minutes=1)).isoformat(timespec="seconds"),
        required_fields=("sku", "stock", "cost", "sell", "days_of_supply"),
    )
    assert rec is not None, reason
    store.put(rec)


def _measurement(pre: dict, post: dict) -> dict:
    pre_inv = (pre.get("domains") or {}).get("inventory", {}).get("values", {})
    post_inv = (post.get("domains") or {}).get("inventory", {}).get("values", {})
    keys = set(pre_inv) & set(post_inv)
    if not keys:
        return {"observed_impact_sar": None}
    total_pre = sum(float(pre_inv[k].get("stock", 0) or 0) * float(pre_inv[k].get("cost", 0) or 0) for k in keys)
    total_post = sum(float(post_inv[k].get("stock", 0) or 0) * float(post_inv[k].get("cost", 0) or 0) for k in keys)
    observed = round(total_pre - total_post, 2)
    return {"observed_impact_sar": observed if observed > 0 else None}


async def _mocked_jev(capability: str, context: dict) -> dict:
    contract = context.get("contract") or frozenset()
    prefer = {"transfer_inventory"} & contract
    return {
        "decision": context.get("deterministic_decision", "DO_NOTHING"),
        "suggested": next(iter(prefer)) if prefer else None,
        "confidence": 0.85,
        "source": AdvisorySource.MOCKED.value,
        "provider": "jev-mock",
        "model": "jev-mock-1.0",
        "reasoning": "synthetic advisory.",
    }


@pytest.mark.asyncio
async def test_orchestrator_produces_canonical_linkage_end_to_end() -> None:
    tenant_id, business_id = "tnt-4f-e2e", "biz-4f-e2e"
    store = EvidenceStore()
    _ingest(store, tenant_id=tenant_id, business_id=business_id, sku="SKU-4F", stock=120, cost=20, sell=28, days_of_supply=45)
    post_store = EvidenceStore()
    _ingest(post_store, tenant_id=tenant_id, business_id=business_id, sku="SKU-4F", stock=20, cost=20, sell=28, days_of_supply=5)

    orch = CycleOrchestrator(
        repository=InMemoryCycleRepository(),
        evidence=store,
        verification_evidence=post_store,
        policy=CyclePolicy(shariah_approved=True, advisory_fn=_mocked_jev, verification_evaluator=_measurement),
    )
    run = await orch.start(tenant_id=tenant_id, business_id=business_id, trigger="synthetic", trigger_token="tok-4f-e2e")
    await orch.run_all(run)

    out = run.state_output
    assert out["outcome"]["verification_status"] == VerificationStatus.VERIFIED.value
    assert out["learning_eligible"] is True
    linkage = out["outcome_linkage"]
    assert linkage is not None
    assert linkage["cycle_id"] == run.cycle_id
    assert linkage["tenant_id"] == tenant_id
    assert linkage["business_id"] == business_id
    assert linkage["opportunity_id"]
    assert linkage["execution_key"]
    assert linkage["attribution_quality"] == "deterministic_measurement"
    assert linkage["verification_status"] == VerificationStatus.VERIFIED.value