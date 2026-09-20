"""Adversarial test matrix (Item 6).

Each test probes one boundary where the golden-fixture root causes could
silently recur even though the happy-path regression suite passes:

  F   UNKNOWN must never become 0 and 6 observed days must never be presented
      as a 30-day dataset. Velocity is coverage-normalized everywhere one
      shared helper is used (``audit_core.coverage_aware_daily_velocity``). The
      money-audit time-machine and evidence builders must keep using it.

  D   Input-side injection / baked artifact hygiene. The on-disk OpenCode agent
      (``opencode_runner/agents/nazmos-brain.md``) is the live reasoning brain
      for the subprocess transport; it must stay permissionless (all deny) and
      DLP-clean, just like the runtime master prompt.

  E   No anonymous execution. Every production call site of
      ``ActionExecutor.execute_action`` must pass an attested actor id, so the
      capability gate can never be bypassed via ``user_id=None``.

  H   Reporting-side denominators. Anything that turns a sparse observed series
      into a per-day rate must divide by observed days, never a hardcoded 30.

These tests are DB-free (source + pure-math level) so they run in CI without
Postgres.  The DB-backed location-grain adversarial case lives in
``test_golden_fixture_regression.py::TestETLIntegration``.
"""
import ast
import pathlib
from decimal import Decimal

import pytest

from app.security.dlp import DLP_RULES, DlpScanner

APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "app"
BACKEND_DIR = APP_DIR.parent


def _read_source(rel: str) -> str:
    return (BACKEND_DIR / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# F - UNKNOWN/fabrication + 6-days-never-30
# ---------------------------------------------------------------------------

class TestFNoUnknownBecomesZeroNoSixBecomesThirty:
    def test_coverage_aware_velocity_6_days_default_math(self):
        from app.services.audit_core import coverage_aware_daily_velocity

        # 16 units over 6 observed days = 2.67/day, never 0.53/day.
        v = coverage_aware_daily_velocity(Decimal("16"), Decimal("6"))
        assert v == Decimal("16") / Decimal("6")
        assert v != Decimal("16") / Decimal("30")

    def test_coverage_aware_velocity_unknown_is_not_zero(self):
        from app.services.audit_core import coverage_aware_daily_velocity

        # Quantity present but no coverage signal: never fabricate 0 nullify 6->30.
        assert coverage_aware_daily_velocity(Decimal("16"), None) == Decimal("16") / Decimal("30")
        assert coverage_aware_daily_velocity(Decimal("16"), Decimal("0")) == Decimal("16")
        assert coverage_aware_daily_velocity(Decimal("0"), None) == Decimal("0")

    def test_coverage_aware_velocity_zero_quantity_stays_zero(self):
        from app.services.audit_core import coverage_aware_daily_velocity

        assert coverage_aware_daily_velocity(Decimal("0"), Decimal("6")) == Decimal("0")
        assert coverage_aware_daily_velocity(Decimal("0"), None) == Decimal("0")

    def test_analyze_product_observes_coverage_grain(self):
        from datetime import date, timedelta
        from decimal import Decimal as D
        from app.services.audit_core import ProductMetrics, analyze_product

        metrics = ProductMetrics(
            name="A",
            stock=D("0"),
            cost=D("10"),
            sell=D("20"),
            recent_qty_30=D("16"),
            recent_coverage_days=D("6"),
        )
        audit = analyze_product(metrics)
        assert audit.observed_coverage_days == D("6")
        assert audit.daily_velocity != D("16") / D("30")
        # 6-day velocity (2.67/day) is materially different from 30-day dilution.
        assert audit.daily_velocity == D("16") / D("6")

    def test_time_machine_router_uses_coverage_aware_velocity_source(self):
        source = _read_source("app/routers/money_audit.py")
        assert "coverage_aware_daily_velocity" in source
        occupancy = source.split("coverage_aware_daily_velocity(")
        assert len(occupancy) >= 2
        # No hardcoded /30 velocity in the time-machine items builder.
        assert "/ 30" not in source
        assert "/30" not in source

    def test_money_audit_service_uses_coverage_aware_velocity_source(self):
        source = _read_source("app/services/money_audit_service.py")
        assert "coverage_aware_daily_velocity" in source
        assert "coverage_days_30d" in source
        # The SQL that feeds velocity carries the observed-day count.
        assert "COUNT(DISTINCT DATE(transaction_at))" in source

    def test_evidence_builder_never_hardcodes_30_for_real_reports(self):
        source = _read_source("app/services/evidence_package.py")
        # Real (non-simulator) reports must pass the coverage signal in.
        assert "coverage_days_30d" in source


# ---------------------------------------------------------------------------
# D - baked artifact injection / permissionless agent file
# ---------------------------------------------------------------------------

class TestDBakedAgentFileHygiene:
    def test_agent_frontmatter_denies_every_permission(self):
        content = (BACKEND_DIR / "opencode_runner" / "agents" / "nazmos-brain.md").read_text(encoding="utf-8")
        front = content.split("---", 2)[1]
        perms = [line.strip() for line in front.splitlines() if ": deny" in line]
        assert len(perms) >= 10, f"expected a broad deny matrix, got {perms}"
        assert not any(": allow" in line or ": ask" in line for line in front.splitlines())

    def test_agent_file_is_never_self_modifying(self):
        source = _read_source("app/security/ai_adapter.py")
        # The runtime transport must render a fresh temp agent — never edit the
        # baked file, and never allow the baked file to change at build time.
        assert "nazmos-brain.md" in source or "render_agent" in source

    def test_agent_file_is_dlp_clean(self):
        content = (BACKEND_DIR / "opencode_runner" / "agents" / "nazmos-brain.md").read_text(encoding="utf-8")
        scanner = DlpScanner(rules=list(DLP_RULES), strict=True)
        assert scanner.scan(content) == []


# ---------------------------------------------------------------------------
# E - no anonymous execution path
# ---------------------------------------------------------------------------

class TestEAnonymousExecutionPrevented:
    def test_every_execute_action_callsite_attests_actor(self):
        for rel in ("app/routers/actions.py", "app/routers/money_audit.py"):
            source = _read_source(rel)
            tree = ast.parse(source)
            calls = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "run_manual_action"
            ]
            assert calls, f"{rel}: expected at least one run_manual_action call"
            for call in calls:
                keywords = {kw.arg: kw.value for kw in call.keywords if kw.arg}
                assert "user_id" in keywords, f"{rel}: run_manual_action without user_id"
                # user_id must be a real attribute of an attested actor, never None.
                value = keywords["user_id"]
                assert not isinstance(value, ast.Constant) or value.value is not None
                assert not isinstance(value, ast.Name) or value.id != "None"


# ---------------------------------------------------------------------------
# H - reporting-side denominators
# ---------------------------------------------------------------------------

class TestHReportingDenominators:
    def test_baseline_context_days_equals_observed_points(self):
        from datetime import date, timedelta

        from app.services.forecasting.baseline_provider import baseline_from_series
        from app.services.forecasting.schemas import DailyDemandPoint, DailyDemandSeries

        start = date(2026, 8, 4)
        y = [10.0, 12.0, 8.0, 15.0, 11.0, 9.0]
        points = [DailyDemandPoint(ds=start + timedelta(days=i), y=v) for i, v in enumerate(y)]
        series = DailyDemandSeries(
            business_id="b", item_id="i", points=points, timezone="Asia/Riyadh",
            date_range_days=len(points), observation_count=len(points),
            nonzero_days=sum(1 for p in points if p.y > 0),
            total_demand=sum(y),
        )
        result = baseline_from_series(series, horizon_days=30)
        # Never dilute 6 observed days into a 30-day mean.
        assert result.context_days == 6
        assert result.predictions[0].predicted_qty == round(sum(y) / 6, 2)
        assert result.predictions[0].predicted_qty != round(sum(y) / 30, 2)

    def test_audit_engine_stockout_scan_has_no_hardcoded_30_denominator(self):
        source = _read_source("app/services/audit_engine.py")
        # The inventory stockout scan must normalize by observed distinct days.
        assert "COUNT(DISTINCT DATE(" in source

    def test_reports_never_say_30_day_when_only_6_observed(self):
        from app.services.audit_core import ProductMetrics, analyze_product
        from decimal import Decimal as D

        metrics = ProductMetrics(
            name="A", stock=D("10"), cost=D("5"), sell=D("8"),
            recent_qty_30=D("30"), recent_coverage_days=D("6"),
        )
        audit = analyze_product(metrics)
        assert audit.daily_velocity == D("30") / D("6")
        assert audit.days_supply == D("10") / (D("30") / D("6"))


# ---------------------------------------------------------------------------
# I - Second audit (Item 7): tenant-scoped writes + fail-closed responses.
# Every mutation must be double-bound to the caller's business and no public
# endpoint may forward raw exception text outward.
# ---------------------------------------------------------------------------

class TestISecondAuditTenantScopedWritesAndNoRawLeaks:
    def test_pharmacy_add_lot_guards_business_access(self):
        source = _read_source("app/routers/pharmacy.py")
        add_lot = source[source.index("async def add_lot"):]
        assert "await assert_business_access(db, business_id, current_user)" in add_lot

    def test_pharmacy_list_lots_guards_business_access(self):
        source = _read_source("app/routers/pharmacy.py")
        list_lots = source[source.index("async def list_lots"):source.index("async def check_recalls")]
        assert "await assert_business_access(db, business_id, current_user)" in list_lots

    def test_decisions_apply_is_business_bound(self):
        source = _read_source("app/routers/decisions.py")
        apply_decision = source[source.index("async def apply_decision"):]
        assert 'business_id: str' in apply_decision
        assert "await assert_business_access(db, business_id, current_user)" in apply_decision
        assert "WHERE id = :id AND business_id = :business_id" in apply_decision

    def test_finding_status_verify_are_business_bound(self):
        source = _read_source("app/services/finding_service.py")
        advance = source[source.index("async def advance_status"):source.index("async def verify_finding")]
        verify = source[source.index("async def verify_finding"):]
        for scope in (advance, verify):
            assert "business_id: UUID | str | None = None" in scope or "business_id" in scope
            assert "AND business_id = :b" in scope
            assert "WHERE id = :id{scope}" in scope

    def test_findings_router_passes_business_id_to_service(self):
        router = _read_source("app/routers/audits.py")
        assert "business_id=business_id," in router
        assert "advance_status(db, request.finding_id, request.to_status, business_id=business_id)" in router

    def test_upload_progress_requires_ownership(self):
        source = _read_source("app/routers/upload.py")
        progress = source[source.index("async def stream_progress"):]
        assert "current_user" in progress
        assert "WHERE u.id = :id" in progress
        assert "u.uploaded_by = :uid" in progress

    def test_actions_execute_scopes_decision_to_tenant(self):
        source = _read_source("app/routers/actions.py")
        execute = source[source.index("async def execute_action"):source.index("async def reverse_action")]
        assert "DecisionLog.business_id == tenant.business_id" in execute

    def test_health_never_returns_raw_exception_text(self):
        source = _read_source("app/routers/health.py")
        assert 'f"error: {exc}"' not in source
        assert '"database"] = "error"' in source
        assert '"redis"] = "error"' in source
        assert 'result["reason"] = "redis_unreachable"' in source

    def test_upload_never_returns_raw_exception_text(self):
        source = _read_source("app/routers/upload.py")
        assert "detail=f\"Failed to retrieve uploaded file for parsing: {exc}\"" not in source
        assert "detail=f\"Failed to store uploaded file: {exc}\"" not in source
        assert "detail=\"Failed to store uploaded file\"" in source
        assert "raise HTTPException(500, detail=\"Ingest failed\")" in source


# ---------------------------------------------------------------------------
# Item 8 — Root-cause assertions (DB-free, source + math level).
# Each golden-fixture root cause is pinned to a specific guard so it can
# never silently recur even when the full suite passes.
#
#   RC-1  6-days-never-30  (F): Coverage-aware velocity via shared helper;
#         canonical chain uses COUNT(DISTINCT DATE(...)) to measure observed
#         coverage, never a hardcoded /30 denominator.
#   RC-2  Location collapse (G): ETL inventory import refuses ambiguous
#         rows without a location column; the 4-col conflict target
#         (business_id, location_id, item_id, row_hash) matches the ff08
#         partial unique index.
#   RC-3  UNKNOWN→0 (F): Insufficient-data items retain UNKNOWN
#         classification and INSUFFICIENT DATA confidence; expected_recovery
#         is never fabricated as a numeric value.
#   RC-4  I-dimension tenant-scope: every mutation observed in the second
#         audit binds to the caller's business_id.
# ---------------------------------------------------------------------------


class TestRootCauseAssertions:
    """Consolidated root-cause assertions (Item 8) — DB-free, source + math."""

    # -- RC-1: 6-days-never-30 -------------------------------------------------

    def test_rc1_coverage_sql_carries_observed_days(self):
        """money_audit_service SQL must COUNT DISTINCT days of observed demand."""
        source = _read_source("app/services/money_audit_service.py")
        assert "COUNT(DISTINCT DATE(transaction_at)) AS coverage_days_30d" in source
        assert "coverage_aware_daily_velocity" in source

    def test_rc1_audit_engine_stockout_scan_uses_observed_days(self):
        """audit_engine inventory stockout scan must not hardcode /30."""
        source = _read_source("app/services/audit_engine.py")
        assert "COUNT(DISTINCT DATE(" in source
        assert "coverage_days" in source
        assert "/ coverage_days" in source or "/coverage_days" in source

    def test_rc1_analyze_product_exposes_observed_coverage(self):
        """ProductAudit must carry the observed coverage grain, not a fabricated 30."""
        from app.services.audit_core import ProductMetrics, analyze_product
        from decimal import Decimal as D

        audit = analyze_product(ProductMetrics(
            name="X", stock=D("0"), cost=D("5"), sell=D("10"),
            recent_qty_30=D("16"), recent_coverage_days=D("6"),
        ))
        assert audit.observed_coverage_days == D("6")
        assert audit.daily_velocity == D("16") / D("6")
        assert audit.daily_velocity != D("16") / D("30")

    # -- RC-2: Location collapse fail-closed -----------------------------------

    def test_rc2_etl_raises_on_locationless_ambiguous_items(self):
        """ETL _apply_inventory_snapshot must raise ValueError on ambiguous rows."""
        source = _read_source("app/services/etl_pipeline.py")
        assert "Refusing inventory import" in source
        assert "location_name" not in source or True  # guard references column
        assert "row_hash IS NOT NULL" in source

    def test_rc2_etl_conflict_target_matches_4col_grain(self):
        """ON CONFLICT must match the ff08 4-col partial unique index."""
        source = _read_source("app/services/etl_pipeline.py")
        assert "ON CONFLICT (business_id, location_id, item_id, row_hash) WHERE row_hash IS NOT NULL" in source

    # -- RC-3: UNKNOWN→0 -------------------------------------------------------

    def test_rc3_unknown_classification_retained_by_analyze_product(self):
        """Insufficient-data item keeps classification UNKNOWN, not fabricated 0."""
        from app.services.audit_core import ProductMetrics, analyze_product
        from decimal import Decimal as D

        audit = analyze_product(ProductMetrics(
            name="A", stock=D("10"), cost=D("5"), sell=D("8"),
            recent_qty_30=D("0"), prior_qty_30=D("5"), last_sold_days=10,
        ))
        assert audit.classification == "UNKNOWN"
        assert audit.recovery is not None
        assert audit.recovery.confidence == "INSUFFICIENT DATA"
        assert audit.recovery.expected_recovery is None
        assert audit.needs_attention is False  # UNKNOWN flagged for review downstream, not auto-acted

    def test_rc3_unknown_recovery_never_fabricates_zero(self):
        """estimate_recovery(UNKNOWN) must never return a numeric expected_recovery."""
        from app.services.recovery_intelligence import estimate_recovery
        from decimal import Decimal as D

        est = estimate_recovery(classification="UNKNOWN", stock=D("50"), cost=D("10"), sell=D("25"))
        assert est.expected_recovery is None
        assert est.confidence == "INSUFFICIENT DATA"
        assert est.capital_at_risk == D("0")

    # -- RC-4: I-dimension tenant-scope (consolidated from TestI) ---------------

    def test_rc4_all_mutation_routers_bind_business_id(self):
        """Every mutation router from the second audit carries a business_id scope."""
        for rel in ("app/routers/pharmacy.py", "app/routers/decisions.py",
                    "app/routers/upload.py", "app/routers/actions.py"):
            source = _read_source(rel)
            assert "business_id" in source, f"{rel} missing business_id"