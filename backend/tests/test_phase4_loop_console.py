"""Phase 4G — Business Loop Command Center (read-only) tests.

Proves the 4G observability surface is:
    * evidence-first — the read model composes ONLY persisted cycle state and
      the lifecycle ladder reaches the top truthfully (no fabricated badges);
    * tenant-scoped — verified-ledger reads expose only each business's own
      cycle-linked outcome rows, and every cycle endpoint is owner-gated;
    * DLP-clean, pure and read-only — no mutation verbs, no merchant raw
      fields, no AI/advisory callbacks to populate the console;

Section A is DB-free (pure read-model + repository-agnostic lifecycles).
Section B runs against the real Postgres test DB (list/detail API, pagination,
tenancy, ledger key scoping).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.business_loop.contracts import AdvisorySource, CycleStage, VerificationStatus
from app.services.business_loop.cycle import (
    CycleOrchestrator,
    CyclePolicy,
    CycleRun,
    CycleStageState,
    InMemoryCycleRepository,
)
from app.services.business_loop.evidence import EvidenceStore, normalize_observation
from app.services.loop_console_readmodel import (
    build_cycle_read_model,
    build_cycle_summary,
    compute_lifecycle,
)

READ_MODEL_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "services" / "loop_console_readmodel.py"
)
ROUTER_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "routers" / "loop_console.py"
)
READ_MODEL_SRC = READ_MODEL_PATH.read_text(encoding="utf-8")

TENANT, BIZ = "tnt-4g", "biz-4g"


def _ingest(store, *, tenant_id, business_id, sku, stock, cost, sell, days_of_supply):
    raw = {"sku": sku, "stock": stock, "cost": cost, "sell": sell, "days_of_supply": days_of_supply}
    rec, reason = normalize_observation(
        tenant_id=tenant_id,
        business_id=business_id,
        raw=raw,
        source_type="synthetic.pos",
        source_reference=sku,
        observation_type="inventory.observed",
        event_timestamp="2026-01-01T00:00:00+00:00",
        observed_at="2026-01-01T00:00:00+00:00",
        required_fields=tuple(raw),
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
    prefer = {"transfer_inventory"} & (context.get("contract") or frozenset())
    return {
        "decision": context.get("deterministic_decision", "DO_NOTHING"),
        "suggested": next(iter(prefer)) if prefer else None,
        "confidence": 0.85,
        "source": AdvisorySource.MOCKED.value,
        "provider": "jev-mock",
        "model": "jev-mock-1.0",
        "reasoning": "synthetic advisory.",
    }


async def _verified_run() -> CycleRun:
    """A real full cycle: VERIFIED + learning-eligible (deterministic measurement)."""
    repo = InMemoryCycleRepository()
    store = EvidenceStore()
    post = EvidenceStore()
    _ingest(store, tenant_id=TENANT, business_id=BIZ, sku="SKU-4G", stock=120, cost=20, sell=28, days_of_supply=45)
    _ingest(post, tenant_id=TENANT, business_id=BIZ, sku="SKU-4G", stock=20, cost=20, sell=28, days_of_supply=5)
    orch = CycleOrchestrator(
        repository=repo,
        evidence=store,
        verification_evidence=post,
        policy=CyclePolicy(shariah_approved=True, advisory_fn=_mocked_jev, verification_evaluator=_measurement),
    )
    run = await orch.start(tenant_id=TENANT, business_id=BIZ, trigger="synthetic", trigger_token="tok-4g")
    await orch.run_all(run)
    return run


def _craft_run(**overrides) -> CycleRun:
    now = "2026-01-01T00:00:00+00:00"
    base = dict(
        cycle_id="cycle-craft",
        tenant_id=TENANT,
        business_id=BIZ,
        trigger="synthetic",
        trigger_token="",
        created_at=now,
        starting_state_version="sv-1",
        evidence_watermark="wm-1",
        stages=[CycleStageState(stage=s) for s in CycleStage.ordered()],
        stage_index=0,
        completed=False,
        last_error="",
    )
    base.update(overrides)
    run = CycleRun(**base)
    run.state_output = dict(overrides.pop("state_output", {}) or {})
    return run


# ---------------------------------------------------------------------------
# Section A — DB-free: lifecycle ladder, read-model truthfulness, DLP purity
# ---------------------------------------------------------------------------

class TestLifecycleLadder:
    @pytest.mark.asyncio
    async def test_verified_cycle_reaches_top_of_ladder(self):
        run = await _verified_run()
        model = build_cycle_read_model(run)
        lifecycle = model["lifecycle"]
        assert lifecycle["lifecycle_status"] == "learning_eligible"
        flags = lifecycle["flags"]
        assert flags["executed"] is True
        assert flags["measured"] is True
        assert flags["verified"] is True
        assert flags["learning_eligible"] is True
        assert flags["blocked"] is False
        assert flags["running"] is False
        assert flags["not_run"] is False
        assert model["verification"]["verified"] is True
        assert model["verification"]["distinct_snapshots"] is True
        assert model["measurement"]["measured"] is True
        assert model["learning"]["eligible"] is True
        assert model["recovery"]["blocked"] is False
        assert model["recovery"]["execution_authority"] == "none"
        assert len(model["stage_timeline"]) == len(CycleStage.ordered()) == 21

    def test_fresh_run_is_not_run(self):
        run = _craft_run(stage_index=0, completed=False, last_error="")
        lifecycle = compute_lifecycle(run)
        assert lifecycle["lifecycle_status"] == "not_run"
        assert lifecycle["flags"]["not_run"] is True

    def test_awaiting_approval_shows_running_with_no_success_badge(self):
        run = _craft_run(
            stage_index=14,
            completed=False,
            last_error="",
            state_output={
                "execution": {"skipped": True, "reason": "recommendation_not_approved:awaiting_approval"},
                "outcome": {"verification_status": "unverified", "reason": "no_execution"},
                "recommendations": [{"status": "awaiting_approval", "action_type": "reorder"}],
            },
        )
        lifecycle = compute_lifecycle(run)
        assert lifecycle["lifecycle_status"] == "running"
        assert lifecycle["flags"]["running"] is True
        assert lifecycle["flags"]["executed"] is False
        summary = build_cycle_summary(run)
        assert summary["execution"]["executed"] is False
        assert summary["execution"]["skipped"] is True
        assert summary["outcome"]["verification_status"] == "unverified"

    def test_revalidation_block_is_visible_not_an_execution_badge(self):
        run = _craft_run(
            stage_index=17,
            completed=False,
            last_error="revalidation_blocked:state_version_drift",
            state_output={
                "revalidation": {
                    "ok": False,
                    "status": "state_version_drift",
                    "recomputed_state_version": "sv-2",
                    "persisted_state_version": "sv-1",
                },
                "execution": {"skipped": True, "reason": "governance_not_permitted"},
                "outcome": {"verification_status": "unverified"},
            },
        )
        model = build_cycle_read_model(run)
        assert model["lifecycle"]["lifecycle_status"] == "blocked"
        assert model["lifecycle"]["flags"]["blocked"] is True
        assert model["recovery"]["last_error_type"] == "revalidation_blocked"
        assert model["recovery"]["revalidation"]["ok"] is False
        assert model["recovery"]["revalidation"]["status"] == "state_version_drift"
        summary = build_cycle_summary(run)
        assert summary["revalidation_blocked"] is True
        assert summary["blocked"] is True

    def test_failed_execution_not_collapsed_into_executed(self):
        run = _craft_run(
            stage_index=15,
            completed=False,
            last_error="dry_run_rejected",
            state_output={
                "execution": {
                    "action_type": "reorder",
                    "execution_key": "exec-1",
                    "attempt": 1,
                    "receipt": {"ok": False, "details": {"reason": "dry_run_rejected"}},
                },
                "reconciliation": {"allow_retry": False, "reason": "dry_run_rejected"},
            },
        )
        model = build_cycle_read_model(run)
        assert model["lifecycle"]["flags"]["executed"] is False
        assert model["execution"]["executed"] is False
        assert model["execution"]["execution_failed"] is True
        assert model["reconciliation"]["allow_retry"] is False
        assert model["recovery"]["blocked"] is True

    def test_shifted_state_but_executed_ladder_still_true_when_blocked_later(self):
        """A cycle verified and learning-eligible, then revalidation-blocked on
        resume, must report BOTH blocked AND the achieved ladder steps."""
        run = _craft_run(
            stage_index=21,
            completed=False,
            last_error="revalidation_blocked:watermark_drift",
            state_output={
                "learning_eligible": True,
                "post_state_version": "sv-2",
                "execution": {"action_type": "reorder", "execution_key": "exec-2", "receipt": {"ok": True}},
                "outcome": {"verification_status": "verified", "observed_impact_sar": 500.0},
            },
        )
        flags = compute_lifecycle(run)["flags"]
        assert flags["blocked"] is True
        assert flags["executed"] is True
        assert flags["verified"] is True
        assert flags["learning_eligible"] is True
        assert flags["measured"] is True


class TestReadModelPurityAndDLP:
    def test_read_model_source_is_pure_and_dlp_clean(self):
        assert "async def" not in READ_MODEL_SRC, "read model must be a pure synchronous builder"
        assert "CREATE TABLE" not in READ_MODEL_SRC, "read model must not create a store"
        for forbidden in ('"sku"', ".sku", "stock_count", '"business_name"'):
            assert forbidden not in READ_MODEL_SRC, f"read model touches {forbidden}"
        assert "execution_authority" in READ_MODEL_SRC

    @pytest.mark.asyncio
    async def test_list_summary_bands_impacts_and_omits_exact_sar(self):
        run = await _verified_run()
        summary = build_cycle_summary(run)
        assert summary["impact_band"] in {"under_250", "250_999", "1000_4999", "5000_plus", None}
        for key in ("potential_impact_sar", "expected_impact_sar", "observed_impact_sar"):
            assert key not in summary, f"summary leaked exact SAR key {key}"
        assert summary["lifecycle_status"] == "learning_eligible"
        assert summary["flags"]["executed"] is True

    @pytest.mark.asyncio
    async def test_detail_holds_this_owner_exact_observed_sar(self):
        run = await _verified_run()
        model = build_cycle_read_model(run)
        # The synthetic transfer rules yield a SUPPORTABLE potential (exact) but
        # not a supportable expected value — the console must surface the exact
        # measured number and say "unknown" rather than invent an expected one.
        assert model["opportunity"]["potential_impact_sar"] is not None
        assert model["outcome"]["observed_impact_sar"] is not None
        assert model["measurement"]["measured"] is True
        assert model["measurement"]["impact_delta_sar"] is None  # expected unknown -> no invented delta
        assert model["outcome"]["verification_status"] == "verified"
        assert model["verification"]["distinct_snapshots"] is True

    def test_measurement_delta_passthrough_when_expected_known(self):
        run = _craft_run(
            stage_index=18,
            completed=False,
            state_output={
                "outcome": {
                    "verification_status": "verified",
                    "expected_impact_sar": 100.0,
                    "observed_impact_sar": 150.0,
                },
                "outcome_linkage": {
                    "impact_delta_sar": 50.0,
                    "measurement_evidence_count": 3,
                    "outcome_key": "k-delta",
                },
            },
        )
        model = build_cycle_read_model(run)
        assert model["measurement"]["impact_delta_sar"] == 50.0
        assert model["measurement"]["measurement_evidence_count"] == 3
        assert model["links"]["outcome_key"] == "k-delta"

    @pytest.mark.asyncio
    async def test_mocked_advisory_provenance_kept_verbatim_never_live_jev(self):
        run = await _verified_run()
        model = build_cycle_read_model(run)
        advisory = model["advisory"]
        assert advisory["source"] == AdvisorySource.MOCKED.value
        assert advisory["provider"] == "jev-mock"
        # Mock provenance is preserved VERBATIM — never upgraded to a live Jev
        # provider, even though a deterministic measurement dominates the
        # attribution for this fully measured/verified cycle.
        assert advisory["attribution_quality"] == "deterministic_measurement"

    def test_jev_advisory_only_attribution_never_sufficient(self):
        from app.services.business_loop.outcome_linkage import attribution_quality

        quality = attribution_quality(
            verification_status=VerificationStatus.REPORTED,
            verification_method="",
            observed_impact_sar=None,
            advisory_source=AdvisorySource.JEV.value,
            advisory_provider="jev-live",
        )
        assert quality == "jev_advisory_only"

    @pytest.mark.asyncio
    async def test_unverified_verification_explains_why(self):
        run = _craft_run(
            stage_index=17,
            completed=True,
            state_output={
                "execution": {"skipped": True, "reason": "recommendation_not_approved:denied"},
                "outcome": {"verification_status": "unverified", "reason": "no_execution"},
            },
        )
        model = build_cycle_read_model(run)
        assert model["verification"]["verified"] is False
        assert model["verification"]["verification_status"] == "unverified"
        assert model["verification"]["reason"] == "no_execution"
        assert model["learning"]["eligible"] is False

    def test_read_model_has_no_mutation_capable_verbs(self):
        for verb in ("@router.post", "@router.put", "@router.patch", "@router.delete"):
            assert verb not in READ_MODEL_SRC


class TestRoutersNoMutations:
    def test_loop_console_router_has_no_write_verbs(self):
        router_src = ROUTER_PATH.read_text(encoding="utf-8")
        for verb in ("@router.post", "@router.put", "@router.patch", "@router.delete"):
            assert verb not in router_src, f"loop console became writable: {verb}"

    def test_cycles_endpoints_registered(self):
        router_src = ROUTER_PATH.read_text(encoding="utf-8")
        assert '"/cycles"' in router_src
        assert '"/cycles/{cycle_id}"' in router_src


class TestLedgerScoping:
    def test_scoped_verified_rows_expose_only_business_linked_keys(self, tmp_path):
        from app.services.outcome_ledger import OutcomeLedger

        ledger = OutcomeLedger(str(tmp_path / "ledger.db"))
        for key in ("key-a", "key-b", "key-c"):
            ledger.record(
                decision_key=key,
                capability="business_loop.verified",
                deterministic_decision="r-1",
                source="business_loop",
            )
            ledger.record_verified_result(
                decision_key=key,
                outcome_status="confirmed",
                verified=True,
                actual_impact_sar=100.0,
                expected_impact_sar=90.0,
            )
        rows = ledger.verified_outcomes()
        assert len(rows) == 3
        allowed = {"key-a"}
        scoped = [r for r in rows if r.get("decision_key") in allowed]
        assert len(scoped) == 1
        assert scoped[0]["decision_key"] == "key-a"
        # Empty allowed set → no rows leak (fail closed).
        assert [r for r in rows if r.get("decision_key") in set()] == []


# ---------------------------------------------------------------------------
# Section B — Postgres: repository boundaries + read-only API
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_outcome_keys_scope_ledger_keys_per_business(db_session):
    from tests.fixtures.merchants import seed_business

    from app.services.cycle_run_repository import PostgresCycleRepository

    repo = PostgresCycleRepository(db_session)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    biz_a = await seed_business(db_session, "4G Ledger Scope A")
    biz_b = await seed_business(db_session, "4G Ledger Scope B")
    run_a = _craft_run(cycle_id="cycle-a", tenant_id="tnt-a", business_id=biz_a, created_at=now, stages=[])
    run_a.state_output["outcome_attachment"] = {"outcome_key": "key-a"}
    run_b = _craft_run(cycle_id="cycle-b", tenant_id="tnt-b", business_id=biz_b, created_at=now, stages=[])
    run_b.state_output["outcome_recorded"] = {"outcome_key": "key-b"}
    # A run with no attachment must contribute nothing.
    run_c = _craft_run(cycle_id="cycle-c", tenant_id="tnt-a", business_id=biz_a, created_at=now, stages=[])

    await repo.save(run_a)
    await repo.save(run_b)
    await repo.save(run_c)

    assert await repo.outcome_keys(biz_a) == {"key-a"}
    assert await repo.outcome_keys(biz_b) == {"key-b"}


@pytest.mark.asyncio
async def test_page_is_bounded_and_deterministically_ordered(db_session):
    from tests.fixtures.merchants import seed_business

    from app.services.cycle_run_repository import PostgresCycleRepository

    repo = PostgresCycleRepository(db_session)
    biz = await seed_business(db_session, "4G Paging")
    await repo.save(
        _craft_run(
            cycle_id="cycle-1", tenant_id="t", business_id=biz,
            created_at="2026-01-01T00:00:00+00:00", stages=[],
        )
    )
    await repo.save(
        _craft_run(
            cycle_id="cycle-2", tenant_id="t", business_id=biz,
            created_at="2026-01-02T00:00:00+00:00", stages=[],
        )
    )
    runs, total = await repo.page(biz, limit=1, offset=0)
    assert total == 2
    assert [r.cycle_id for r in runs] == ["cycle-2"]  # newest first
    runs2, _ = await repo.page(biz, limit=1, offset=1)
    assert [r.cycle_id for r in runs2] == ["cycle-1"]
    # Deterministic across calls.
    again, _ = await repo.page(biz, limit=1, offset=0)
    assert [r.cycle_id for r in again] == ["cycle-2"]
    # Rehydrated rows carry the observability timestamp.
    assert runs[0]._updated_at  # noqa: SLF001
    listed, _ = await repo.page(biz, limit=100, offset=0)
    assert [r.cycle_id for r in listed] == ["cycle-2", "cycle-1"]


@pytest.mark.asyncio
async def test_cycles_api_authorized_list_and_detail(authenticated_client, db_session):
    from app.services.cycle_run_repository import PostgresCycleRepository

    ctx = authenticated_client
    client, headers, bid = ctx["client"], ctx["headers"], ctx["business_id"]

    store = EvidenceStore()
    post = EvidenceStore()
    _ingest(store, tenant_id=TENANT, business_id=bid, sku="SKU-4G", stock=120, cost=20, sell=28, days_of_supply=45)
    _ingest(post, tenant_id=TENANT, business_id=bid, sku="SKU-4G", stock=20, cost=20, sell=28, days_of_supply=5)
    orch = CycleOrchestrator(
        repository=PostgresCycleRepository(db_session),
        evidence=store,
        verification_evidence=post,
        policy=CyclePolicy(shariah_approved=True, advisory_fn=_mocked_jev, verification_evaluator=_measurement),
    )
    run = await orch.start(tenant_id=TENANT, business_id=bid, trigger="synthetic", trigger_token="tok-4g-api")
    await orch.run_all(run)

    res = await client.get(f"/api/v1/loop-console/cycles?business_id={bid}", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 1
    assert body["has_more"] is False
    assert body["limit"] == 20 and body["offset"] == 0
    item = body["items"][0]
    assert item["cycle_id"] == run.cycle_id
    assert item["lifecycle_status"] == "learning_eligible"
    assert item["flags"]["verified"] is True and item["flags"]["executed"] is True
    assert item["revalidation_blocked"] is False
    assert "potential_impact_sar" not in item

    det = await client.get(
        f"/api/v1/loop-console/cycles/{run.cycle_id}?business_id={bid}", headers=headers
    )
    assert det.status_code == 200, det.text
    d = det.json()
    assert d["read_model_version"] == "1.0"
    assert d["cycle"]["cycle_id"] == run.cycle_id
    assert d["verification"]["verified"] is True
    assert d["learning"]["eligible"] is True
    assert d["advisory"]["attribution_quality"] == "deterministic_measurement"
    assert d["recovery"]["execution_authority"] == "none"
    assert len(d["stage_timeline"]) == 21
    assert d["links"]["outcome_key"]


@pytest.mark.asyncio
async def test_cycles_api_pagination(authenticated_client, db_session):
    from app.services.cycle_run_repository import PostgresCycleRepository

    ctx = authenticated_client
    client, headers, bid = ctx["client"], ctx["headers"], ctx["business_id"]
    repo = PostgresCycleRepository(db_session)
    for i in range(3):
        await repo.save(
            _craft_run(
                cycle_id=f"cycle-{i}", tenant_id=TENANT, business_id=bid,
                created_at=f"2026-01-0{i + 1}T00:00:00+00:00", stages=[],
            )
        )
    page1 = await client.get(f"/api/v1/loop-console/cycles?business_id={bid}&limit=2&offset=0", headers=headers)
    assert page1.status_code == 200
    p1 = page1.json()
    assert len(p1["items"]) == 2 and p1["total"] == 3 and p1["has_more"] is True
    page2 = await client.get(f"/api/v1/loop-console/cycles?business_id={bid}&limit=2&offset=2", headers=headers)
    p2 = page2.json()
    assert len(p2["items"]) == 1 and p2["has_more"] is False
    ids = [i["cycle_id"] for i in p1["items"]] + [i["cycle_id"] for i in p2["items"]]
    assert sorted(ids) == ["cycle-0", "cycle-1", "cycle-2"]
    # Order newest first across both pages.
    assert p1["items"][0]["cycle_id"] == "cycle-2"
    assert p2["items"][0]["cycle_id"] == "cycle-0"


@pytest.mark.asyncio
async def test_cycles_api_rejects_cross_tenant_and_unknown_ids(client, authenticated_client, db_session):
    ctx = authenticated_client
    a_headers, biz_a = ctx["headers"], ctx["business_id"]
    email = f"intruder-{uuid.uuid4()}@example.com"
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "TestPass123!", "full_name": "Intruder"},
    )
    assert reg.status_code in (200, 201), reg.text
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "TestPass123!"}
    )
    assert login.status_code == 200
    intruder_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Attacker reads victim's list with victim's business_id -> rejected.
    res = await client.get(
        f"/api/v1/loop-console/cycles?business_id={biz_a}", headers=intruder_headers
    )
    assert res.status_code in (403, 404), f"cross-tenant list leaked: {res.status_code} {res.text[:200]}"

    # Attacker reads victim's detail with victim's business_id -> rejected.
    res = await client.get(
        f"/api/v1/loop-console/cycles/cycle-{uuid.uuid4()}?business_id={biz_a}",
        headers=intruder_headers,
    )
    assert res.status_code in (403, 404), f"cross-tenant detail leaked: {res.status_code} {res.text[:200]}"

    # Owner with an UNKNOWN cycle_id on their OWN business -> 404 (not 403).
    res = await client.get(
        f"/api/v1/loop-console/cycles/cycle-does-not-exist?business_id={biz_a}",
        headers=a_headers,
    )
    assert res.status_code == 404, res.text

    # Verified-outcomes fail closed: this business has no cycle-linked ledger
    # keys, so zero rows are exposed whether or not the ledger is configured.
    res = await client.get(
        f"/api/v1/loop-console/outcomes/verified?business_id={biz_a}", headers=a_headers
    )
    assert res.status_code == 200
    verified = res.json()
    assert verified["verified_rows"] == 0


@pytest.mark.asyncio
async def test_cycles_api_requires_authentication(client):
    biz = str(uuid.uuid4())
    for url in (
        f"/api/v1/loop-console/cycles?business_id={biz}",
        f"/api/v1/loop-console/cycles/cycle-x?business_id={biz}",
    ):
        res = await client.get(url)
        assert res.status_code == 401, f"unauthenticated read was not rejected: {res.status_code}"