"""Phase 3 synthetic vertical slice end-to-end (MASTER_PLAN §19/§14).

Runs the COMPLETE improvement pipeline on synthetic data with:
    * in-memory evidence + in-memory cycle repository (no DB, no Temporal)
    * a MOCKED Jev advisor, explicitly labelled ``source=mocked``
    * SIMULATED owner approval, explicitly labelled SYNTHETIC
    * dry-run (synthetic) execution, never a real merchant action
    * outcome verification via an injected measurement authority that is only
      the measurement, never a number the loop invents

This test proves the smallest complete slice works and the authority
boundaries hold: an estimate is never an observed impact, AI never authorizes,
recommendations bind to their exact material, duplicate triggers cannot create
duplicate cycles.

Evidence labels: [V] running code, [B] baseline regression, [X] limitation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.business_loop import (
    AdvisorySource,
    CycleOrchestrator,
    CyclePolicy,
    GovernanceOutcome,
    ImpactKind,
    InMemoryCycleRepository,
    OpportunityType,
    RecommendationStatus,
)
from app.services.business_loop.contracts import VerificationStatus
from app.services.business_loop.evidence import EvidenceStore, normalize_observation


def _t(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")


def _ingest(store: EvidenceStore, *, tenant_id: str, business_id: str, sku: str, stock: float, cost: float, sell: float, days_of_supply: float | None = None, source: str = "pos") -> str:
    raw = {"sku": sku, "stock": stock, "cost": cost, "sell": sell}
    if days_of_supply is not None:
        raw["days_of_supply"] = days_of_supply
    rec, reason = normalize_observation(
        tenant_id=tenant_id,
        business_id=business_id,
        raw=raw,
        source_type="synthetic.pos",
        source_reference=source,
        observation_type="inventory.observed",
        event_timestamp=_t(),
        observed_at=_t(),
        required_fields=("sku", "stock", "cost", "sell", "days_of_supply")
        if days_of_supply is not None
        else ("sku", "stock", "cost", "sell"),
    )
    assert rec is not None, reason
    store.put(rec)
    return rec.evidence_id


async def _mocked_jev(capability: str, context: dict) -> dict:
    """Mocked Jev: deterministic candidate selection inside the contract only."""
    contract = context.get("contract") or frozenset()
    prefer = {"transfer_inventory"} & contract
    return {
        "decision": context.get("deterministic_decision", "DO_NOTHING"),
        "suggested": next(iter(prefer)) if prefer else None,
        "confidence": 0.85,
        "source": AdvisorySource.MOCKED.value,
        "provider": "jev-mock",
        "model": "jev-mock-1.0",
        "reasoning": "synthetic advisory: prefer autonomous transfer within contract.",
    }


def _measurement_authority(pre: dict, post: dict) -> dict:
    """The measurement is external reality, not something the loop claims.

    Here the synthetic authority reports a recovered cash impact because the
    post-action state shows the surplus was materially reduced. In production
    this comes from the POS/accounting measurement pipeline, never from Jev.
    """
    pre_inv = (pre.get("domains") or {}).get("inventory", {}).get("values", {})
    post_inv = (post.get("domains") or {}).get("inventory", {}).get("values", {})
    keys = set(pre_inv) & set(post_inv)
    if not keys:
        return {"observed_impact_sar": None}
    total_pre = sum(float(pre_inv[k].get("stock", 0) or 0) * float(pre_inv[k].get("cost", 0) or 0) for k in keys)
    total_post = sum(float(post_inv[k].get("stock", 0) or 0) * float(post_inv[k].get("cost", 0) or 0) for k in keys)
    observed = round(total_pre - total_post, 2)
    observed = observed if observed > 0 else None
    return {"observed_impact_sar": observed}


class TestSyntheticVerticalSlice:
    async def test_complete_slice(self) -> None:
        tenant_id, business_id = "tnt-vertical", "biz-vertical-01"
        store = EvidenceStore()
        _ingest(store, tenant_id=tenant_id, business_id=business_id, sku="SKU-EXC", stock=120, cost=20, sell=28, days_of_supply=45)
        # verification evidence = the post-action world (measurement reality)
        post_store = EvidenceStore()
        _ingest(post_store, tenant_id=tenant_id, business_id=business_id, sku="SKU-EXC", stock=20, cost=20, sell=28, days_of_supply=5)

        repo = InMemoryCycleRepository()
        policy = CyclePolicy(
            shariah_approved=True,
            advisory_fn=_mocked_jev,
            verification_evaluator=_measurement_authority,
        )
        orchestrator = CycleOrchestrator(repository=repo, evidence=store, verification_evidence=post_store, policy=policy)

        run = await orchestrator.start(tenant_id=tenant_id, business_id=business_id, trigger="synthetic-slice", trigger_token="tok-1")
        await orchestrator.run_all(run)

        out = run.state_output
        # --- evidence foundation: deterministic, dedup, no cross-scope pollution
        assert out["evidence_count"] >= 1
        # --- state projection: versioned
        assert run.starting_state_version
        # --- opportunity detection yields only the expected opportunity types
        types = {o["opportunity_type"] for o in out["opportunities"]}
        assert OpportunityType.EXCESS_INVENTORY.value in types
        assert not ({OpportunityType.STOCKOUT_RISK.value, OpportunityType.MARGIN_EROSION.value} & types)
        # --- advisory attribution is EXACT (mocked != jev) + validated
        advisory = out["advisory"]
        assert advisory["source"] == AdvisorySource.MOCKED.value
        assert advisory["provider"] == "jev-mock"
        assert advisory["validation_passed"] is True
        # --- recommendation binds to candidate contract; validated suggestion narrows
        reco = out["recommendations"][0]
        assert reco["advisory_validated"] is True
        assert reco["action_type"] == "transfer_inventory"
        assert reco["material_hash"]
        assert reco["status"] == RecommendationStatus.APPROVED.value
        # --- governance resolved to approval-required then simulated owner approval
        assert out["governance"]["outcome"] == GovernanceOutcome.APPROVAL_REQUIRED.value
        assert out["approval"]["mode"] == "simulated_owner_approval"
        assert "SYNTHETIC" in out["approval"]["note"]
        # --- execution is a synthetic dry-run, never a real merchant action
        receipt = out["execution"]["receipt"]
        assert receipt["ok"] is True
        assert receipt["synthetic"] is True
        assert "SYNTHETIC - not a real merchant action" in receipt["details"]["note"]
        # --- reconciliation: reported-recorded, never blind-retry
        assert out["reconciliation"]["allow_retry"] is False
        assert out["reconciliation"]["reason"] == "reported_recorded_await_verification"
        # --- verification: observed impact came from the measurement authority, not the loop
        outcome = out["outcome"]
        assert outcome["verification_status"] == VerificationStatus.VERIFIED.value
        assert outcome["observed_impact_sar"] is not None
        assert outcome["observed_impact_sar"] == 2000.0  # pre 2400 - post 400 (measured)
        # --- verified-only learning
        assert out["learning_eligible"] is True
        assert out["summary"]["verified"] is True

    async def test_duplicate_trigger_suppressed(self) -> None:
        store = EvidenceStore()
        _ingest(store, tenant_id="tnt-2", business_id="biz-2", sku="SKU-1", stock=100, cost=10, sell=15, days_of_supply=60)
        repo = InMemoryCycleRepository()
        orchestrator = CycleOrchestrator(repository=repo, evidence=store, policy=CyclePolicy(shariah_approved=True, advisory_fn=_mocked_jev))
        first = await orchestrator.start(tenant_id="tnt-2", business_id="biz-2", trigger="trigger", trigger_token="same")
        await orchestrator.run_all(first)
        again = await orchestrator.start(tenant_id="tnt-2", business_id="biz-2", trigger="trigger", trigger_token="same")
        assert again.cycle_id == first.cycle_id  # idempotent by design [V]

    async def test_no_opportunity_is_a_successful_noop(self) -> None:
        store = EvidenceStore()
        # sub-threshold fresh evidence: value < SAR500, ample supply, healthy margin
        _ingest(store, tenant_id="tnt-3", business_id="biz-3", sku="SKU-OK", stock=10, cost=2, sell=5, days_of_supply=60)
        repo = InMemoryCycleRepository()
        orchestrator = CycleOrchestrator(repository=repo, evidence=store, policy=CyclePolicy(shariah_approved=True))
        run = await orchestrator.start(tenant_id="tnt-3", business_id="biz-3", trigger_token="noop")
        await orchestrator.run_all(run)
        assert run.completed is True
        assert run.state_output["opportunity_count"] == 0
        assert run.state_output["recommendations"] == []
        assert run.state_output["learning_eligible"] is False

    async def test_out_of_contract_advisory_is_dropped_not_coerced(self) -> None:
        store = EvidenceStore()
        _ingest(store, tenant_id="tnt-4", business_id="biz-4", sku="SKU-1", stock=100, cost=10, sell=15, days_of_supply=60)

        async def rogue_advisor(capability, context):
            return {"decision": "excess_inventory", "suggested": "expiry_alert", "confidence": 0.9, "source": "mocked"}

        repo = InMemoryCycleRepository()
        orchestrator = CycleOrchestrator(
            repository=repo,
            evidence=store,
            policy=CyclePolicy(shariah_approved=True, advisory_fn=rogue_advisor),
        )
        run = await orchestrator.start(tenant_id="tnt-4", business_id="biz-4", trigger_token="rogue")
        await orchestrator.run_all(run)
        # Out-of-contract suggestion is recorded and dropped, never coerced.
        assert run.state_output["advisory"]["validation_passed"] is False
        assert run.state_output["advisory"]["suggested"] is None
        # The recommendation continues ONLY on the deterministic candidate path
        # and is NOT treated as advisory-validated.
        assert run.state_output["recommendations"][0]["action_type"] == "recovery_match"
        assert run.state_output["recommendations"][0]["advisory_validated"] is False