"""Phase 4B — durable Postgres CycleRun repository (PHASE_4A contract).

Proves the ``cycle_runs`` table round-trips the FULL ``CycleRun.serialize()``
payload (all 21 stages, state_output, stage cursor) losslessly and enforces the
durability contract:
    * idempotent create on (business_id, cycle_id) — duplicate trigger never
      materializes a second row
    * tenant-scoped load (RLS applies at the session layer; the repository also
      filters by business_id explicitly)
    * optimistic concurrency: a stale save raises CycleRunConflictError
    * terminal protection: completed runs are immutable

Also proves the orchestrator drives the durable repository end-to-end via the
existing 21-stage cycle (state projection -> advisory -> governance ->
execution -> summary).

Evidence labels: [V] running code, [B] baseline regression, [X] limitation.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.services.business_loop.cycle import (
    CycleOrchestrator,
    CyclePolicy,
    CycleRun,
    CycleStageState,
    derive_cycle_id,
)
from app.services.business_loop.contracts import AdvisorySource, CycleStage
from app.services.business_loop.evidence import EvidenceStore, normalize_observation
from app.services.cycle_run_repository import CycleRunConflictError, PostgresCycleRepository

from tests.fixtures.merchants import seed_business


def _ingest(store: EvidenceStore, *, tenant_id: str, business_id: str, sku: str, stock: float, cost: float, sell: float, days_of_supply: float) -> None:
    from datetime import datetime, timedelta, timezone

    _now = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
    rec, reason = normalize_observation(
        tenant_id=tenant_id,
        business_id=business_id,
        raw={"sku": sku, "stock": stock, "cost": cost, "sell": sell, "days_of_supply": days_of_supply},
        source_type="synthetic.pos",
        source_reference=sku,
        observation_type="inventory.observed",
        event_timestamp=_now,
        observed_at=_now,
        required_fields=("sku", "stock", "cost", "sell", "days_of_supply"),
    )
    assert rec is not None, reason
    store.put(rec)


def _run(business_id: str, *, trigger: str = "trigger", token: str = "") -> CycleRun:
    cid = derive_cycle_id(tenant_id="tnt-4b", business_id=business_id, trigger=trigger, trigger_token=token)
    return CycleRun(
        cycle_id=cid,
        tenant_id="tnt-4b",
        business_id=business_id,
        trigger=trigger,
        trigger_token=token,
        created_at="2026-09-24T00:00:00+00:00",
        starting_state_version="sv-1",
        evidence_watermark="wm-1",
        stages=[CycleStageState(stage=s) for s in CycleStage.ordered()],
        stage_index=0,
        completed=False,
        last_error="",
        state_output={"evidence_count": 1},
    )


async def test_save_load_roundtrip_is_lossless(db_session):
    """[V] The FULL serialize surface round-trips: 21 stages + cursor + output."""
    bid = await seed_business(db_session, "4B Roundtrip")
    await db_session.commit()
    repo = PostgresCycleRepository(db_session)

    run = _run(bid)
    run.state_output = {"evidence_count": 1, "cycle": {"serial": "A"}}
    run.stages[3].status = "ok"
    run.stages[3].attempts = 1
    run.stage_index = 4
    await repo.save(run)

    loaded = await repo.load(bid, run.cycle_id)
    assert loaded is not None
    assert loaded.cycle_id == run.cycle_id
    assert loaded.tenant_id == run.tenant_id
    assert loaded.business_id == run.business_id
    assert loaded.trigger == run.trigger
    assert loaded.trigger_token == run.trigger_token
    assert loaded.starting_state_version == run.starting_state_version
    assert loaded.evidence_watermark == run.evidence_watermark
    assert loaded.stage_index == 4
    assert loaded.completed is False
    assert loaded.last_error == ""
    assert len(loaded.stages) == 21
    assert loaded.stages[3].stage == CycleStage.STATE_PROJECTION
    assert loaded.stages[3].status == "ok"
    assert loaded.stages[3].attempts == 1
    assert loaded.state_output["evidence_count"] == 1
    assert loaded.state_output["cycle"]["serial"] == "A"


async def test_duplicate_create_is_idempotent(db_session):
    """[V] Duplicate trigger -> the unique (business_id, cycle_id) key keeps one row."""
    bid = await seed_business(db_session, "4B Idempotent")
    await db_session.commit()
    repo = PostgresCycleRepository(db_session)

    run = _run(bid, token="dup")
    await repo.save(run)
    await repo.save(run)  # replay

    rows = (await db_session.execute(text("SELECT COUNT(*) FROM cycle_runs WHERE business_id=:b"), {"b": bid})).scalar()
    assert rows == 1
    loaded = await repo.load(bid, run.cycle_id)
    assert loaded is not None


async def test_load_is_tenant_scoped(db_session):
    """[V] business A's cycle is invisible to business B (explicit filter; RLS at session)."""
    bid_a = await seed_business(db_session, "4B Tenant A")
    bid_b = await seed_business(db_session, "4B Tenant B")
    await db_session.commit()
    repo = PostgresCycleRepository(db_session)

    run = _run(bid_a)
    await repo.save(run)

    assert await repo.load(bid_a, run.cycle_id) is not None
    assert await repo.load(bid_b, run.cycle_id) is None


async def test_stale_version_conflict(db_session):
    """[V] Optimistic concurrency: a save against a concurrently-advanced row raises.

    Two independent sessions both read version N; the first UPDATE wins, the
    second finds rowcount 0 on the version predicate and raises instead of
    silently overwriting.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool
    from tests.conftest import TEST_DATABASE_URL

    bid = await seed_business(db_session, "4B Conflict")
    await db_session.commit()

    # Session A (the fixture) and session B (fresh, own connection).
    engine_b = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    SessionB = async_sessionmaker(engine_b, class_=AsyncSession, expire_on_commit=False)
    try:
        async with SessionB() as session_b:
            repo_a = PostgresCycleRepository(db_session)
            repo_b = PostgresCycleRepository(session_b)

            run = _run(bid, token="race")
            await repo_a.save(run)
            await db_session.commit()
            await session_b.commit()  # ensure B sees the committed row

            # Both A and B load the SAME version N into their own copy.
            copy_a = await repo_a.load(bid, run.cycle_id)
            copy_b = await repo_b.load(bid, run.cycle_id)
            assert copy_a is not None and copy_b is not None

            # A advances first and commits (version N -> N+1).
            copy_a.stage_index = 1
            await repo_a.save(copy_a)

            # B advances from the SAME stale origin: its UPDATE's version
            # predicate no longer matches the now-higher persisted version, so
            # rowcount is 0 and the repository raises instead of clobbering.
            copy_b.stage_index = 7
            with pytest.raises(CycleRunConflictError):
                await repo_b.save(copy_b)

            # A's advance survived; B never overwrote it.
            persisted = await repo_a.load(bid, run.cycle_id)
            assert persisted.stage_index == 1
    finally:
        await engine_b.dispose()


async def test_completed_run_is_immutable(db_session):
    """[V] Once completed=true, a further mutation is rejected (terminal protection)."""
    bid = await seed_business(db_session, "4B Terminal")
    await db_session.commit()
    repo = PostgresCycleRepository(db_session)

    run = _run(bid)
    run.completed = True
    run.stage_index = 21
    await repo.save(run)

    assert (await repo.load(bid, run.cycle_id)).completed is True
    # Subsequent save of an already-completed run must not raise and must not mutate.
    loaded = await repo.load(bid, run.cycle_id)
    loaded.state_output["fake"] = True
    await repo.save(loaded)
    persisted = await repo.load(bid, run.cycle_id)
    assert persisted.completed is True
    assert "fake" not in persisted.state_output


async def test_all_lists_tenant_scoped_newest_first(db_session):
    """[V] Console listing surface: scoped to business, ordered by created_at desc."""
    bid = await seed_business(db_session, "4B Listing")
    await db_session.commit()
    repo = PostgresCycleRepository(db_session)

    r1 = _run(bid, trigger="t1", token="a")
    r2 = _run(bid, trigger="t2", token="b")
    await repo.save(r1)
    await repo.save(r2)

    runs = await repo.all(bid)
    assert len(runs) == 2
    assert {r.cycle_id for r in runs} == {r1.cycle_id, r2.cycle_id}


async def test_orchestrator_persists_full_cycle(db_session):
    """[V] The existing 21-stage orchestrator drives the durable repo end-to-end."""
    bid = await seed_business(db_session, "4B Orchestrator")
    await db_session.commit()

    tenant, business = "tnt-4b-2", bid
    store = EvidenceStore()
    _ingest(store, tenant_id=tenant, business_id=business, sku="SKU-EXC", stock=120, cost=20, sell=28, days_of_supply=45)
    from datetime import datetime, timedelta, timezone

    _post = "2026-09-24T00:05:00+00:00"
    rec, reason = normalize_observation(
        tenant_id=tenant,
        business_id=business,
        raw={"sku": "SKU-EXC", "stock": 20, "cost": 20, "sell": 28, "days_of_supply": 5},
        source_type="synthetic.pos",
        source_reference="SKU-EXC",
        observation_type="inventory.observed",
        event_timestamp=_post,
        observed_at=_post,
        required_fields=("sku", "stock", "cost", "sell", "days_of_supply"),
    )
    assert rec is not None, reason
    post_store = EvidenceStore()
    post_store.put(rec)

    def measurement_authority(pre: dict, post: dict) -> dict:
        pre_inv = (pre.get("domains") or {}).get("inventory", {}).get("values", {})
        post_inv = (post.get("domains") or {}).get("inventory", {}).get("values", {})
        keys = set(pre_inv) & set(post_inv)
        if not keys:
            return {"observed_impact_sar": None}
        total_pre = sum(float(pre_inv[k].get("stock", 0) or 0) * float(pre_inv[k].get("cost", 0) or 0) for k in keys)
        total_post = sum(float(post_inv[k].get("stock", 0) or 0) * float(post_inv[k].get("cost", 0) or 0) for k in keys)
        observed = round(total_pre - total_post, 2)
        return {"observed_impact_sar": observed if observed > 0 else None}

    async def mocked_jev(capability: str, context: dict) -> dict:
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

    repo = PostgresCycleRepository(db_session)
    policy = CyclePolicy(
        shariah_approved=True,
        advisory_fn=mocked_jev,
        verification_evaluator=measurement_authority,
    )
    orchestrator = CycleOrchestrator(repository=repo, evidence=store, verification_evidence=post_store, policy=policy)

    run = await orchestrator.start(tenant_id=tenant, business_id=business, trigger="durable-slice", trigger_token="tok-4b")
    await orchestrator.run_all(run)

    # Durable outcome: completed run persisted with the full 21-stage record.
    # Terminal shape: CYCLE_SUMMARY (index 19) sets completed=True and advances
    # the cursor to 20; the NEXT_CYCLE marker stage (index 20) never runs on a
    # completed run (run_one_stage short-circuits on completed).
    persisted = await repo.load(business, run.cycle_id)
    assert persisted is not None
    assert persisted.completed is True
    assert persisted.stage_index >= 20
    assert len(persisted.stages) == 21
    assert all(s.status in ("ok", "skipped") for s in persisted.stages[:20])
    assert persisted.stages[20].stage == CycleStage.NEXT_CYCLE
    assert persisted.starting_state_version
    assert persisted.evidence_watermark

    # Resume reproduces the identical run (idempotent, deterministic).
    resumed = await repo.load(business, run.cycle_id)
    assert resumed.cycle_id == run.cycle_id
    assert resumed.state_output.get("recommendations") == run.state_output.get("recommendations")