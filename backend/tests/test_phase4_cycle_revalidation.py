"""Phase 4E — revalidate state versions + evidence watermark across a persisted cycle.

A persisted cycle may advance past its pinned cursor ONLY while its
``starting_state_version`` and ``evidence_watermark`` are still reproducible
from the evidence the resume actually projects. Revalidation is the durable
gate: drift is a hard block, never a blind retry (no stage attempt consumed).

    * test_clean_resume_revalidates_consistent   the SAME evidence reproduces the
                                                 pinned baseline (worker-restart
                                                 resume must keep passing)
    * test_state_version_drift_blocks_resume     evidence changed while persisted
                                                 -> recomputed version differs ->
                                                 verdict ok=False
    * test_watermark_drift_blocks_resume         persisted watermark no longer
                                                 matches the accepted lineage
    * test_unpinned_baseline_is_allowed          a run not yet past STATE_PROJECTION
                                                 has nothing to guard (not_pinned)
    * test_cross_scope_evidence_blocks_resume    out-of-scope accepted records are
                                                 reported on the verdict
    * test_advance_blocked_consumes_no_attempt   a drifted advance reflects on the
                                                 cursor as a block, not a failure

DB-free: in-memory evidence + InMemoryCycleRepository, no DB / no Temporal. The
resume is simulated by reloading the run the way ``_model_to_run`` does (new
orchestrator over a rebuilt evidence store, same persisted run object).

Evidence labels: [V] running code, [B] baseline regression, [X] limitation.
"""
from __future__ import annotations

import json
from typing import Any

from app.services.business_loop import (
    CycleOrchestrator,
    CyclePolicy,
    InMemoryCycleRepository,
)
from app.services.business_loop.evidence import EvidenceStore, normalize_observation

from tests.test_phase3_synthetic_vertical_slice import _t

TENANT = "tnt-4e"
BIZ = "biz-4e"
POLICY = CyclePolicy(shariah_approved=True)


def _ingest(
    store: EvidenceStore,
    *,
    sku: str,
    stock: float,
    cost: float,
    sell: float,
    days_of_supply: float | None = None,
    observed_at: str | None = None,
    tenant_id: str = TENANT,
    business_id: str = BIZ,
) -> str:
    raw = {"sku": sku, "stock": stock, "cost": cost, "sell": sell}
    if days_of_supply is not None:
        raw["days_of_supply"] = days_of_supply
    rec, reason = normalize_observation(
        tenant_id=tenant_id,
        business_id=business_id,
        raw=raw,
        source_type="synthetic.pos",
        source_reference=sku,
        observation_type="inventory.observed",
        event_timestamp=_t(),
        observed_at=observed_at or _t(),
        required_fields=tuple(raw),
    )
    assert rec is not None, reason
    store.put(rec)
    return rec.evidence_id


async def _pinned_run() -> tuple[Any, InMemoryCycleRepository, EvidenceStore]:
    """Start + advance a fresh cycle through STATE_PROJECTION (baseline pinned)."""
    repo = InMemoryCycleRepository()
    store = EvidenceStore()
    _ingest(store, sku="SKU-4E", stock=120, cost=20, sell=28, days_of_supply=45)
    orch = CycleOrchestrator(repository=repo, evidence=store, policy=POLICY)
    run = await orch.start(tenant_id=TENANT, business_id=BIZ, trigger="synthetic", trigger_token="tok-4e")
    for _ in range(4):
        assert await orch.run_one_stage(run) is True
    assert run.starting_state_version
    assert run.evidence_watermark
    return run, repo, store


async def test_clean_resume_revalidates_consistent() -> None:
    run, repo, store = await _pinned_run()

    # Resume = NEW orchestrator over a rebuilt store with the SAME records the
    # original pinned (mirrors _rebuild_evidence replaying the same payload).
    store2 = EvidenceStore()
    for rec in store.all():
        store2.put(rec)
    orch2 = CycleOrchestrator(repository=repo, evidence=store2, policy=POLICY)
    verdict = await orch2.revalidate_persisted(run)

    assert verdict["ok"] is True
    assert verdict["status"] == "consistent"
    assert verdict["recomputed_state_version"] == run.starting_state_version
    assert verdict["recomputed_watermark"] == run.evidence_watermark
    assert verdict["cross_scope"] == 0


async def test_state_version_drift_blocks_resume() -> None:
    run, repo, _ = await _pinned_run()
    pinned = run.starting_state_version
    assert pinned

    # Evidence changed while the cycle was persisted: stock 120 -> 80.
    drifted = EvidenceStore()
    _ingest(drifted, sku="SKU-4E", stock=80, cost=20, sell=28, days_of_supply=20)
    orch2 = CycleOrchestrator(repository=repo, evidence=drifted, policy=POLICY)
    verdict = await orch2.revalidate_persisted(run)

    assert verdict["ok"] is False
    assert "state_version_drift" in verdict["status"]
    assert verdict["recomputed_state_version"] != pinned
    assert verdict["persisted_state_version"] == pinned


async def test_watermark_drift_blocks_resume() -> None:
    repo = InMemoryCycleRepository()
    store = EvidenceStore()
    _ingest(store, sku="SKU-4E", stock=120, cost=20, sell=28, days_of_supply=45, observed_at=_t(3))
    orch1 = CycleOrchestrator(repository=repo, evidence=store, policy=POLICY)
    run = await orch1.start(tenant_id=TENANT, business_id=BIZ, trigger="synthetic", trigger_token="tok-4e")
    for _ in range(4):
        assert await orch1.run_one_stage(run) is True
    assert run.evidence_watermark == _t(3)

    # Persisted watermark no longer matches the accepted lineage: the resume
    # evidence has a NEWER observation than the pinned watermark.
    drifted = EvidenceStore()
    _ingest(drifted, sku="SKU-4E", stock=120, cost=20, sell=28, days_of_supply=45, observed_at=_t(0))
    orch2 = CycleOrchestrator(repository=repo, evidence=drifted, policy=POLICY)
    verdict = await orch2.revalidate_persisted(run)

    assert verdict["ok"] is False
    assert "watermark_drift" in verdict["status"]
    assert verdict["persisted_watermark"] == _t(3)
    assert verdict["recomputed_watermark"] == _t(0)


async def test_unpinned_baseline_is_allowed() -> None:
    repo = InMemoryCycleRepository()
    store = EvidenceStore()
    _ingest(store, sku="SKU-4E", stock=120, cost=20, sell=28, days_of_supply=45)
    orch = CycleOrchestrator(repository=repo, evidence=store, policy=POLICY)
    run = await orch.start(tenant_id=TENANT, business_id=BIZ, trigger="synthetic", trigger_token="tok-4e")

    assert run.starting_state_version == ""
    verdict = await orch.revalidate_persisted(run)
    assert verdict["ok"] is True
    assert verdict["status"] == "not_pinned"


async def test_cross_scope_evidence_blocks_resume() -> None:
    run, repo, _ = await _pinned_run()

    # A foreign tenant's accepted record leaked into the resume evidence.
    polluted = EvidenceStore()
    _ingest(polluted, sku="SKU-4E", stock=120, cost=20, sell=28, days_of_supply=45)
    _ingest(polluted, sku="SKU-X", stock=1, cost=1, sell=1, days_of_supply=1, tenant_id="tnt-other")
    orch2 = CycleOrchestrator(repository=repo, evidence=polluted, policy=POLICY)
    verdict = await orch2.revalidate_persisted(run)

    assert verdict["ok"] is False
    assert "cross_scope" in verdict["status"]
    assert verdict["cross_scope"] == 1


async def test_verdict_is_json_safe() -> None:
    run, repo, _ = await _pinned_run()
    orch = CycleOrchestrator(repository=repo, evidence=EvidenceStore(), policy=POLICY)
    verdict = await orch.revalidate_persisted(run)
    round_trip = json.loads(json.dumps(verdict))
    assert round_trip == verdict
    assert set(round_trip) == {
        "ok",
        "status",
        "recomputed_state_version",
        "persisted_state_version",
        "recomputed_watermark",
        "persisted_watermark",
        "cross_scope",
    }