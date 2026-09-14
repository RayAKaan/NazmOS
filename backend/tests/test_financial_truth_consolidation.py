"""Cross-surface financial-truth consolidation sentinels (Change 3).

Every live surface that quotes money must compute it from ONE canonical source.
These tests pin those contracts so a future re-implementation cannot quietly
introduce a second definition:

- Dead stock: the agent tool ``get_dead_stock_summary`` returns per-item values
  that equal ``stock_value(..., ValueBasis.COST)`` over the scoped DuckDB feed
  (``inventory_feed`` + ``dead_by_scan``) — no bespoke raw-SQL valuation.
- Stock value: item detail quotes ``stock_value(..., ValueBasis.SELL)`` — the
  sell-basis canonical.  A raw ``current_stock * sell_price`` in any surface is
  a regression even if it happens to equal it today.
- Margin: ``audit_core.gross_margin_pct`` is the single formula; both the money
  audit and the product auditor use it.
- Health: exactly two explicitly-named metrics (``findings_health`` /
  ``inventory_health``); payloads carry a ``metric`` key; the dashboard view
  delegates to ``analytics_service.calculate_health_score`` (no duplicate).
- Constraints: the AI layers (``ai_response_validator`` owner constraints and
  ``ai_challenge`` v11 guard) route through the canonical constraint engine
  (item_id AND sku vocabulary), preserving the stable error strings.
- Approval: money-audit approve/reject/complete and orchestration
  agent-approve/reject share the same capability gate (``can_approve_actions``).
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base, Business, Finding, Inventory, Item, Transaction


@pytest_asyncio.fixture
async def sqlite_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield SessionLocal
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# 1. Dead stock — agent tool == canonical feed + stock_value(COST)
# ---------------------------------------------------------------------------


async def _seed_dead_stock(db: AsyncSession) -> uuid.UUID:
    business = Business(id=uuid.uuid4(), name="Dead Stock Sent", type="baqala")
    db.add(business)
    await db.flush()
    items = [
        Item(id=uuid.uuid4(), business_id=business.id, name="ItemA", cost_price=2.0, sell_price=3.0),
        Item(id=uuid.uuid4(), business_id=business.id, name="ItemB", cost_price=5.0, sell_price=7.0),
        Item(id=uuid.uuid4(), business_id=business.id, name="ItemC", cost_price=1.0, sell_price=1.5),
    ]
    db.add_all(items)
    await db.flush()
    for item in items:
        db.add(Inventory(id=uuid.uuid4(), business_id=business.id, item_id=item.id, current_stock=20))
    await db.flush()
    now = datetime.now(timezone.utc)
    db.add_all([
        Transaction(
            id=uuid.uuid4(), business_id=business.id, item_id=items[0].id,
            quantity=2, unit_price=3.0, cost_price=2.0, total_amount=6.0,
            profit=2.0, transaction_at=now - timedelta(days=62),
        ),
        Transaction(
            id=uuid.uuid4(), business_id=business.id, item_id=items[1].id,
            quantity=3, unit_price=7.0, cost_price=5.0, total_amount=21.0,
            profit=6.0, transaction_at=now - timedelta(days=50),
        ),
    ])
    await db.commit()
    return business.id


@pytest.mark.asyncio
async def test_agent_dead_stock_matches_canonical_feed_cost_basis(sqlite_db):
    from app.analytics import ValueBasis
    from app.analytics.metrics import stock_value as canonical_stock_value
    from app.analytics.repository import inventory_feed
    from app.services.agent_tools import execute_agent_tool

    SessionLocal = sqlite_db
    async with SessionLocal() as db:
        business_id = await _seed_dead_stock(db)
        result = await execute_agent_tool(
            "get_dead_stock_summary", {"days_no_sale": 30}, business_id, db
        )

        feed = await inventory_feed(db, business_id, window_days=30)

    assert result["days_no_sale"] == 30
    rows = {r["item_id"]: r for r in result["dead_stock_items"]}

    # Every row must correspond to a fact flagged dead by the canonical scan…
    dead_facts = {f.item_id: f for f in feed.facts if f.dead_by_scan}
    assert set(rows) == set(dead_facts) == {str(f.item_id) for f in feed.facts}
    assert len(rows) == 3

    # …and every quoted value must be the canonical COST-basis stock value.
    for item_id, row in rows.items():
        fact = dead_facts[item_id]
        assert row["stuck_sar"] == float(
            canonical_stock_value(fact.current_stock, fact.cost_price, ValueBasis.COST)
        )
        assert row["item_id"] == str(fact.item_id)
        assert row["name"]

    assert result["total_stuck_sar"] == pytest.approx(20 * 2.0 + 20 * 5.0 + 20 * 1.0)


# ---------------------------------------------------------------------------
# 2. Stock value — item detail quotes canonical SELL basis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_item_detail_stock_value_is_canonical_sell_basis(sqlite_db):
    from app.analytics import ValueBasis
    from app.analytics.metrics import stock_value as canonical_stock_value
    from app.services.analytics_service import get_item_detail

    SessionLocal = sqlite_db
    async with SessionLocal() as db:
        business = Business(id=uuid.uuid4(), name="Item Sent", type="baqala")
        item = Item(id=uuid.uuid4(), business_id=business.id, name="Milk 1L",
                    cost_price=4.5, sell_price=6.0, sku="SKU-SENTINEL")
        inv = Inventory(id=uuid.uuid4(), business_id=business.id, item_id=item.id,
                        current_stock=50, reorder_level=10, max_stock=100)
        db.add_all([business, item, inv])
        await db.commit()

        detail = await get_item_detail(db, business.id, item.id)

    assert detail is not None
    canonical = canonical_stock_value(inv.current_stock, item.sell_price, ValueBasis.SELL)
    assert detail.item.stock_value == float(canonical) == pytest.approx(50 * 6.0)
    assert detail.item.sell_price == 6.0
    # Cost basis must NOT leak into item-detail valuation.
    assert detail.item.stock_value != pytest.approx(50 * 4.5)


# ---------------------------------------------------------------------------
# 3. Margin — one formula in audit_core drives money audit AND product audit
# ---------------------------------------------------------------------------


def test_margin_single_formula_and_no_duplicate_in_money_audit():
    from app.services.audit_core import ProductMetrics, analyze_product, gross_margin_pct

    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "app" / "services" / "money_audit_service.py"
    source = src.read_text(encoding="utf-8")

    # The money audit imports the canonical helper instead of re-deriving it.
    assert "from app.services.audit_core import gross_margin_pct" in source
    assert "margin = gross_margin_pct(sell, cost)" in source
    # No inline duplicate formula.
    assert source.count("(sell - cost) / sell") == 0

    assert gross_margin_pct(Decimal("10"), Decimal("6")) == Decimal("0.4")
    assert gross_margin_pct(Decimal("10"), Decimal("9")) == Decimal("0.1")
    assert gross_margin_pct(Decimal("-4"), Decimal("2")) == Decimal("0")
    assert gross_margin_pct(Decimal("0"), Decimal("2")) == Decimal("0")

    # analyze_product must classify from the same formula.
    audit = analyze_product(ProductMetrics(
        name="x", stock=Decimal("10"), cost=Decimal("6"),
        sell=Decimal("10"), recent_qty_30=Decimal("5"),
    ))
    assert audit.margin_leakage == Decimal("0")
    assert audit.has_margin_leakage is False

    # Same product at a thin margin (< 22%) triggers leakage via the formula.
    thin = analyze_product(ProductMetrics(
        name="y", stock=Decimal("10"), cost=Decimal("9.5"),
        sell=Decimal("10"), recent_qty_30=Decimal("5"),
    ))
    assert thin.has_margin_leakage is True
    assert thin.margin_leakage > 0


# ---------------------------------------------------------------------------
# 4. Health — explicitly-named metrics; dashboard health delegates
# ---------------------------------------------------------------------------


def test_findings_health_weights_are_canonical():
    from app.services.health_metrics import (
        EXCLUDED_FINDING_STATUSES,
        FINDINGS_SEVERITY_WEIGHTS,
    )

    assert FINDINGS_SEVERITY_WEIGHTS == {
        "critical": 12, "high": 6, "medium": 2, "low": 0, "info": 0,
    }
    assert EXCLUDED_FINDING_STATUSES == ("rejected", "failed", "verified")
    # Weekly and audit-report both render the severity-penalty score; there is
    # no weight with which low/info drag health.
    assert FINDINGS_SEVERITY_WEIGHTS["low"] == 0
    assert FINDINGS_SEVERITY_WEIGHTS["info"] == 0


@pytest.mark.asyncio
async def test_findings_health_labeled_and_traceable(sqlite_db):
    from app.services.health_metrics import (
        DOMAIN_DIMENSION,
        DIMENSIONS,
        findings_health_breakdown,
        findings_health_score,
    )

    SessionLocal = sqlite_db
    async with SessionLocal() as db:
        business = Business(id=uuid.uuid4(), name="Health Sent", type="baqala")
        db.add(business)
        await db.flush()
        db.add_all([
            Finding(id=uuid.uuid4(), business_id=business.id, domain="inventory",
                    category="dead_stock", severity="critical", title="Dead stock",
                    status="detected", estimated_financial_impact_sar=1000),
            Finding(id=uuid.uuid4(), business_id=business.id, domain="money_audit",
                    category="margin_leakage", severity="high", title="Margin leak",
                    status="detected", estimated_financial_impact_sar=400),
            Finding(id=uuid.uuid4(), business_id=business.id, domain="compliance",
                    category="record_keeping", severity="low", title="Low",
                    status="detected", estimated_financial_impact_sar=10),
            # A "verified" finding must NOT penalize.
            Finding(id=uuid.uuid4(), business_id=business.id, domain="inventory",
                    category="dead_stock", severity="critical", title="Fixed",
                    status="verified", estimated_financial_impact_sar=500),
        ])
        await db.commit()

        score = await findings_health_score(db, business.id)
        breakdown = await findings_health_breakdown(db, business.id)

    assert score["metric"] == "findings_health"
    assert "basis" in score
    # 100 - 12(critical) - 6(high) - 0(low) = 82; the "verified" critical is excluded.
    assert score["overall_health"] == 82
    assert score["formula"] == {
        "critical": 1, "high": 1, "medium": 0, "low": 1, "info": 0, "penalty": 18,
    }

    assert breakdown["metric"] == "findings_health"
    assert breakdown["overall_health"] == 82
    dims = {d["dimension"]: d for d in breakdown["dimensions"]}
    assert set(d for d in dims).issubset(DIMENSIONS)
    assert DOMAIN_DIMENSION["money_audit"] == "margins"
    assert dims["margins"]["findings"] == 1


@pytest.mark.asyncio
async def test_inventory_health_delegates_to_analytics_and_is_distinct(sqlite_db):
    from app.analytics import ValueBasis
    from app.analytics.metrics import stock_value as canonical_stock_value
    from app.services.analytics_service import calculate_health_score
    from app.services.health_metrics import inventory_health_score

    SessionLocal = sqlite_db
    async with SessionLocal() as db:
        business = Business(id=uuid.uuid4(), name="Inv Health Sent", type="baqala")
        item = Item(id=uuid.uuid4(), business_id=business.id, name="A",
                    cost_price=1.0, sell_price=2.0)
        db.add_all([business, item])
        await db.flush()
        db.add(Inventory(id=uuid.uuid4(), business_id=business.id,
                         item_id=item.id, current_stock=100))
        await db.commit()

        delegated = await inventory_health_score(db, business.id)
        dashboard = await calculate_health_score(db, business.id)

    # The dashboard composite is delegated, never re-implemented, and is integer.
    assert delegated == dashboard
    assert isinstance(delegated, int)
    # Sanity: a stock-full, no-sale business scores poorly (inventory metric),
    # NOT 100 — proving these two metrics are genuinely different signals.
    assert delegated < 100


# ---------------------------------------------------------------------------
# 5. Constraints — AI layers route through the canonical engine (sku vocab)
# ---------------------------------------------------------------------------


class _FakeItem:
    def __init__(self, sku):
        self.sku = sku
        self.id = sku
        self.supplier_moq = 500

    def to_dict(self):
        return {"sku": self.sku}


class _FakeAI:
    def __init__(self, decision, discount_pct=None):
        self.decision = decision
        self.confidence = 0.9
        self.reasoning = "evidence-based decision"
        self.evidence_ids = []
        self.risk_flags = []
        self.recommended_action = {"discount_pct": discount_pct} if discount_pct else {}


def _constraints(*, blocked_products=None, blocked_skus=None, strategic_products=None,
                 strategic_skus=None, max_discount_pct=None, cash_budget=None):
    return {
        "blocked_discount_products": list(blocked_products or []),
        "blocked_discount_skus": list(blocked_skus or []),
        "strategic_products": list(strategic_products or []),
        "strategic_skus": list(strategic_skus or []),
        "max_discount_pct": max_discount_pct,
        "cash_budget": cash_budget,
    }


def test_owner_constraints_delegate_to_canonical_engine_sku_vocab():
    from app.services.ai_response_validator import validate_ai_response

    item = _FakeItem("SKU-BLOCKED")
    ai = _FakeAI("DISCOUNT", discount_pct=5)

    def _validate(constraints):
        # Object contract: item/business thread through the object-path params.
        return validate_ai_response(
            ai, known_evidence_ids=item, deterministic_decision=None,
            allowed_constraints=constraints,
        )

    # Legacy surface: SKUs historically stored in blocked_discount_products.
    legacy = _validate(_constraints(blocked_products=["SKU-BLOCKED"]))
    assert legacy.constraint_rejected is True
    assert legacy.is_valid is False
    assert "DISCOUNT_BLOCKED_BY_CONSTRAINT" in legacy.errors

    # Canonical surface: SKU vocabulary in blocked_discount_skus.
    canonical = _validate(_constraints(blocked_skus=["SKU-BLOCKED"]))
    assert canonical.constraint_rejected is True
    assert "DISCOUNT_BLOCKED_BY_CONSTRAINT" in canonical.errors


def test_owner_constraints_strategic_max_and_moq_map_to_stable_strings():
    from app.services.ai_response_validator import validate_ai_response

    def _validate(ai, sku, constraints):
        return validate_ai_response(
            ai, known_evidence_ids=_FakeItem(sku), deterministic_decision=None,
            allowed_constraints=constraints,
        )

    strategic = _validate(_FakeAI("DISCOUNT"), "SKU-STRAT",
                          _constraints(strategic_skus=["SKU-STRAT"]))
    assert strategic.constraint_rejected is True
    assert "DISCOUNT_BLOCKED_STRATEGIC_PRODUCT" in strategic.errors

    over_max = _validate(_FakeAI("DISCOUNT", discount_pct=50), "SKU-X",
                         _constraints(max_discount_pct=30))
    assert over_max.constraint_rejected is True
    assert "DISCOUNT_EXCEEDS_MAX_PCT" in over_max.errors

    moq = _validate(_FakeAI("REORDER"), "SKU-Y",
                    _constraints(cash_budget=100))
    assert moq.constraint_rejected is True
    assert "REORDER_MOQ_EXCEEDS_BUDGET" in moq.errors


def test_canonical_engine_sku_checks_agree_with_validator():
    from app.services.constraint_service import (
        CODE_DISCOUNT_BLOCKED,
        CODE_DISCOUNT_STRATEGIC,
        filter_action_with_code,
    )

    feasible, code, _ = filter_action_with_code(
        "discount", {"sku": "SKU-BLOCKED"},
        {"blocked_discount_skus": ["SKU-BLOCKED"]},
    )
    assert (feasible, code) == (False, CODE_DISCOUNT_BLOCKED)

    feasible, code, _ = filter_action_with_code(
        "discount", {"sku": "SKU-STRAT"},
        {"strategic_skus": ["SKU-STRAT"]},
    )
    assert (feasible, code) == (False, CODE_DISCOUNT_STRATEGIC)


# ---------------------------------------------------------------------------
# 6. Approval — money audit and orchestration share one capability gate
# ---------------------------------------------------------------------------


def test_money_audit_and_agent_approve_share_capability_gate():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app" / "routers"
    money_src = (root / "money_audit.py").read_text(encoding="utf-8")
    agent_src = (root / "agent.py").read_text(encoding="utf-8")

    # Money-audit lifecycle entry points each require the approval capability.
    for endpoint in ("approve_action", "reject_action", "complete_action"):
        assert endpoint in money_src
    assert money_src.count('"can_approve_actions"') >= 3

    # Orchestration agent-approve/reject use the identical gate.
    assert 'require_capability("can_approve_actions", "business_id")' in agent_src
    assert "run_agent_approval" in agent_src
    assert "run_agent_rejection" in agent_src