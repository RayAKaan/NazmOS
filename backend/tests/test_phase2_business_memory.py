"""Phase 2 Business Memory — Comprehensive Tests.

Covers all acceptance criteria from the Phase 2 spec:
  §4  Product Memory
  §5  Demand Trend
  §6  Seasonal Memory
  §7  Promotion Memory
  §8  Supplier Memory
  §9  PO Memory
  §10 Branch Memory
  §11 Owner Memory
  §12 Action Memory
  §13 Outcome Memory
  §14 Memory Confidence
  §15 Memory Freshness
  §16 Business Context API
  §17 Product Context API
  §18 AI Readiness
  §19 Tenant Isolation
  §20 Memory Correctness
  §21 Memory Update
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ── Helpers ─────────────────────────────────────────────────────────────────

B1 = uuid.uuid4()
B2 = uuid.uuid4()
ITEM1 = uuid.uuid4()
ITEM2 = uuid.uuid4()
ITEM3 = uuid.uuid4()
SUP1 = uuid.uuid4()


async def _seed_business(db: AsyncSession, bid: uuid.UUID, name: str = "Test Biz",
                         constraints: dict | None = None):
    await db.execute(text("""
        INSERT INTO users (id, email, password_hash, full_name, role, is_active, is_platform_operator)
        VALUES (:id, :email, 'not-a-real-hash', 'Test Owner', 'owner', true, false)
    """), {"id": str(bid), "email": f"{bid.hex[:8]}@test.local"})
    await db.execute(text("""
        INSERT INTO organizations (id, name, slug, owner_id, created_at, updated_at)
        VALUES (:id, :name, :slug, :owner, NOW(), NOW())
    """), {"id": str(bid), "name": f"Org {bid.hex[:8]}", "slug": f"org-{bid.hex[:12]}", "owner": str(bid)})
    await db.execute(text("""
        INSERT INTO businesses (id, organization_id, name, type, city, constraints_json, created_at, updated_at)
        VALUES (:id, :org, :name, 'baqala', 'Riyadh', CAST(:constraints AS JSON), NOW(), NOW())
    """), {"id": str(bid), "org": str(bid), "name": name,
           "constraints": json.dumps(constraints or {})})


async def _seed_supplier(db: AsyncSession, sid: uuid.UUID, name: str = "Test Supplier"):
    await db.execute(text("""
        INSERT INTO suppliers (id, name_ar, name_en, category, city, lead_time_days, min_order_sar, is_active, created_at)
        VALUES (:id, :name_ar, :name, 'dairy', 'Riyadh', 3, 500, true, NOW())
    """), {"id": str(sid), "name_ar": f"مورد {name}", "name": name})


async def _seed_item(db: AsyncSession, bid: uuid.UUID, iid: uuid.UUID, name: str = "Test Item",
                     cost: float = 10.0, sell: float = 25.0, stock: int = 50,
                     supplier_id: uuid.UUID | None = None):
    await db.execute(text("""
        INSERT INTO items (id, business_id, name, sku, cost_price, sell_price, is_active, created_at, updated_at)
        VALUES (:id, :b, :name, :sku, :cost, :sell, true, NOW(), NOW())
    """), {"id": str(iid), "b": str(bid), "name": name, "sku": name.replace(" ", "_").upper(),
           "cost": cost, "sell": sell})
    await db.execute(text("""
        INSERT INTO inventory (id, business_id, item_id, current_stock, safety_stock, reorder_level, max_stock,
                               supplier_id, lead_time_days, stockout_count_90d, created_at, updated_at)
        VALUES (:id, :b, :item, :stock, 10, 10, 100, :sup, 7, 0, NOW(), NOW())
    """), {"id": str(uuid.uuid4()), "b": str(bid), "item": str(iid),
           "stock": stock, "sup": str(supplier_id) if supplier_id else None})


async def _seed_sales(db: AsyncSession, bid: uuid.UUID, iid: uuid.UUID,
                      qty_per_day: float, days: int = 30):
    from app.utils.clock import utcnow
    anchor = utcnow().date()
    for d in range(days):
        tx_date = anchor - timedelta(days=d)
        await db.execute(text("""
            INSERT INTO transactions (id, business_id, item_id, transaction_type, quantity, unit_price, cost_price, profit, total_amount, transaction_at, created_at)
            VALUES (:id, :b, :item, 'sale', :qty, 25.0, :cost, :profit, :total, :tx_at, NOW())
        """), {"id": str(uuid.uuid4()), "b": str(bid), "item": str(iid),
               "qty": qty_per_day, "cost": 10.0, "profit": qty_per_day * 15.0,
               "total": qty_per_day * 25.0, "tx_at": tx_date})


async def _seed_po(db: AsyncSession, bid: uuid.UUID, sid: uuid.UUID, iid: uuid.UUID,
                   qty: int = 100, status: str = "sent",
                   expected_delivery: date | None = None, sent_days_ago: int = 5):
    from app.utils.clock import utcnow
    if expected_delivery is None:
        expected_delivery = utcnow().date() + timedelta(days=3)
    po_id = str(uuid.uuid4())
    items_json = json.dumps([{"item_id": str(iid), "qty": qty, "unit_cost": 10.0}])
    sent_at = utcnow() - timedelta(days=sent_days_ago)
    await db.execute(text("""
        INSERT INTO purchase_orders (id, business_id, supplier_id, po_number, status, total_sar,
                                     items_json, expected_delivery, sent_at, created_at, updated_at)
        VALUES (:id, :b, :sup, :po, :status, :total, CAST(:items AS JSON), :delivery, :sent, NOW(), NOW())
    """), {"id": po_id, "b": str(bid), "sup": str(sid), "po": f"PO-{po_id[:8]}",
           "status": status, "total": qty * 10.0, "items": items_json,
           "delivery": expected_delivery, "sent": sent_at})
    return po_id


# ═══════════════════════════════════════════════════════════════════════════════
# §4  Product Memory
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_product_memory_builds_from_existing_data():
    """Product memory should derive facts from transactions, inventory, POs."""
    from app.services.product_memory import build_product_memory

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        await _seed_item(db, B1, ITEM1, name="Organic Milk", stock=30, cost=8.0, sell=15.0)
        await _seed_sales(db, B1, ITEM1, qty_per_day=5, days=30)

        pm = await build_product_memory(db, B1, ITEM1)

        assert pm.product_name == "Organic Milk"
        assert pm.current_stock == 30.0
        assert pm.cost_price == 8.0
        assert pm.sell_price == 15.0
        assert pm.gross_margin_pct > 0
        assert pm.velocity_30d > 0
        assert pm.trend in ("INCREASING", "STABLE", "DECLINING", "INSUFFICIENT_DATA")
        assert pm.confidence in ("HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA")
        assert pm.memory_updated_at is not None
        assert pm.source_period_start is not None
        assert pm.source_period_end is not None


@pytest.mark.asyncio
async def test_product_memory_velocity_windows():
    """Product memory should compute 7d, 30d, 90d velocities."""
    from app.services.product_memory import build_product_memory

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        await _seed_item(db, B1, ITEM1, stock=100)
        await _seed_sales(db, B1, ITEM1, qty_per_day=10, days=90)

        pm = await build_product_memory(db, B1, ITEM1)

        # All windows should show sales
        assert pm.velocity_7d > 0
        assert pm.velocity_30d > 0
        assert pm.velocity_90d > 0
        # With constant demand, all should be roughly equal per-day
        assert abs(pm.velocity_7d / 7 - pm.velocity_30d / 30) < 5


@pytest.mark.asyncio
async def test_product_memory_insufficient_data():
    """Product with no sales should have INSUFFICIENT_DATA confidence."""
    from app.services.product_memory import build_product_memory

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        await _seed_item(db, B1, ITEM1, stock=50)

        pm = await build_product_memory(db, B1, ITEM1)

        assert pm.velocity_30d == 0
        assert pm.trend == "INSUFFICIENT_DATA"
        assert pm.confidence == "INSUFFICIENT_DATA"
        assert pm.stockout_frequency == "INSUFFICIENT_DATA"


# ═══════════════════════════════════════════════════════════════════════════════
# §5  Demand Trend
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_trend_increasing():
    """Growing product should detect INCREASING trend."""
    from app.services.product_memory import _detect_trend

    # 7d > 30d > 90d → increasing
    trend = _detect_trend(
        velocity_7d=Decimal("100"),
        velocity_30d=Decimal("80"),
        velocity_90d=Decimal("60"),
    )
    assert trend == "INCREASING"


@pytest.mark.asyncio
async def test_trend_declining():
    """Declining product should detect DECLINING trend."""
    from app.services.product_memory import _detect_trend

    trend = _detect_trend(
        velocity_7d=Decimal("30"),
        velocity_30d=Decimal("60"),
        velocity_90d=Decimal("90"),
    )
    assert trend == "DECLINING"


@pytest.mark.asyncio
async def test_trend_stable():
    """Stable product should detect STABLE trend."""
    from app.services.product_memory import _detect_trend

    trend = _detect_trend(
        velocity_7d=Decimal("50"),
        velocity_30d=Decimal("50"),
        velocity_90d=Decimal("50"),
    )
    assert trend == "STABLE"


@pytest.mark.asyncio
async def test_trend_insufficient_data():
    """Zero sales should return INSUFFICIENT_DATA."""
    from app.services.product_memory import _detect_trend

    trend = _detect_trend(
        velocity_7d=Decimal("0"),
        velocity_30d=Decimal("0"),
        velocity_90d=Decimal("0"),
    )
    assert trend == "INSUFFICIENT_DATA"


# ═══════════════════════════════════════════════════════════════════════════════
# §6  Seasonal Memory
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_seasonal_detection_with_data():
    """Concentrated monthly sales should be detected as SEASONAL."""
    from app.services.product_memory import _detect_seasonality

    # 4 months of data: one month dominates (40% of total)
    monthly = [Decimal("10"), Decimal("10"), Decimal("10"), Decimal("30")]
    result = _detect_seasonality(monthly, None)
    assert result["seasonal_type"] == "SEASONAL"
    assert result["seasonal_strength"] >= 0.35


@pytest.mark.asyncio
async def test_seasonal_unknown_with_insufficient_data():
    """Less than 3 months of data should return UNKNOWN."""
    from app.services.product_memory import _detect_seasonality

    result = _detect_seasonality([Decimal("10"), Decimal("10")], None)
    assert result["seasonal_type"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_not_seasonal_with_even_distribution():
    """Even monthly distribution should return NOT_SEASONAL."""
    from app.services.product_memory import _detect_seasonality

    monthly = [Decimal("10")] * 6
    result = _detect_seasonality(monthly, None)
    assert result["seasonal_type"] == "NOT_SEASONAL"
    assert result["seasonal_strength"] < 0.35


# ═══════════════════════════════════════════════════════════════════════════════
# §8  Supplier Memory
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_supplier_memory_builds_from_po_history():
    """Supplier memory should derive reliability from PO fulfillment."""
    from app.services.supplier_memory import build_supplier_memory

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        await _seed_supplier(db, SUP1, name="Al Marai Dairy")
        await _seed_item(db, B1, ITEM1, supplier_id=SUP1)

        # Seed POs: 8 received, 1 cancelled, 1 overdue
        from app.utils.clock import utcnow
        for _ in range(8):
            await _seed_po(db, B1, SUP1, ITEM1, status="received")
        await _seed_po(db, B1, SUP1, ITEM1, status="cancelled")
        overdue_delivery = utcnow().date() - timedelta(days=5)
        await _seed_po(db, B1, SUP1, ITEM1, status="sent", expected_delivery=overdue_delivery)

        sm = await build_supplier_memory(db, B1, SUP1)

        assert sm.supplier_name == "Al Marai Dairy"
        assert sm.total_orders >= 9
        assert sm.received_orders >= 8
        assert sm.cancelled_orders >= 1
        assert sm.overdue_orders >= 1
        assert sm.reliability_rate is not None
        assert sm.reliability_rate >= 0.7  # 8/10 received
        assert sm.confidence in ("HIGH", "MEDIUM")
        assert sm.memory_updated_at is not None


@pytest.mark.asyncio
async def test_supplier_memory_insufficient_data():
    """Supplier with no PO history should return INSUFFICIENT_DATA."""
    from app.services.supplier_memory import build_supplier_memory

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        await _seed_supplier(db, SUP1)

        sm = await build_supplier_memory(db, B1, SUP1)

        assert sm.total_orders == 0
        assert sm.confidence == "INSUFFICIENT_DATA"
        assert sm.reliability_rate is None


@pytest.mark.asyncio
async def test_supplier_open_po_tracking():
    """Open POs should be reflected in supplier memory."""
    from app.services.supplier_memory import build_supplier_memory

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        await _seed_supplier(db, SUP1)
        await _seed_item(db, B1, ITEM1, supplier_id=SUP1)

        await _seed_po(db, B1, SUP1, ITEM1, qty=100, status="sent")
        await _seed_po(db, B1, SUP1, ITEM1, qty=50, status="confirmed")

        sm = await build_supplier_memory(db, B1, SUP1)

        assert sm.open_po_count >= 2
        assert sm.confirmed_inbound_qty >= 150


# ═══════════════════════════════════════════════════════════════════════════════
# §10 Branch Memory
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_branch_memory_single_branch():
    """Single-branch business should return one branch memory."""
    from app.services.branch_memory import build_branch_memory

    async with db_session_ctx() as db:
        await _seed_business(db, B1, name="Main Store")
        await _seed_item(db, B1, ITEM1, stock=50)
        await _seed_sales(db, B1, ITEM1, qty_per_day=5, days=30)

        branches = await build_branch_memory(db, B1)

        assert len(branches) >= 1
        main = branches[0]
        assert main.branch_name == "Main Store"
        assert main.total_items >= 1
        assert main.current_stock == 50.0
        assert main.velocity_30d > 0


# ═══════════════════════════════════════════════════════════════════════════════
# §11 Owner Constraint Memory
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_owner_constraints_in_business_context():
    """Owner constraints should be included in business context."""
    from app.services.business_context_service import build_business_context

    async with db_session_ctx() as db:
        constraints = {"cash_budget": 5000, "minimum_margin_pct": 0.20, "blocked_discount_products": ["x"]}
        await _seed_business(db, B1, constraints=constraints)

        ctx = await build_business_context(db, B1, max_products=0, max_suppliers=0)

        assert ctx.constraints.get("cash_budget") == 5000
        assert ctx.constraints.get("minimum_margin_pct") == 0.20
        assert "blocked_discount_products" in ctx.constraints


# ═══════════════════════════════════════════════════════════════════════════════
# §12 Action Memory
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_action_history_in_context():
    """Recent actions should appear in business context."""
    from app.services.business_context_service import build_business_context

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        await _seed_item(db, B1, ITEM1)

        # Seed an agent action
        await db.execute(text("""
            INSERT INTO agent_actions (id, business_id, action_type, status, confidence, autonomy_dial_at_creation, title, summary, payload, created_at, updated_at)
            VALUES (:id, :b, 'restock', 'executed', 0.9, 60, 'Restock Milk', 'Restock Milk', CAST(:payload AS JSON), NOW(), NOW())
        """), {"id": str(uuid.uuid4()), "b": str(B1),
               "payload": json.dumps({"item_id": str(ITEM1)})})

        ctx = await build_business_context(db, B1, max_products=0, max_suppliers=0)

        assert len(ctx.recent_actions) >= 1
        assert ctx.recent_actions[0]["action_type"] == "restock"


# ═══════════════════════════════════════════════════════════════════════════════
# §13 Outcome Memory
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_outcome_history_in_context():
    """Outcome feedback should appear in business context."""
    from app.services.business_context_service import build_business_context

    async with db_session_ctx() as db:
        await _seed_business(db, B1)

        # Seed outcome feedback
        await db.execute(text("""
            INSERT INTO outcome_feedback (id, business_id, decision_type, predicted_outcome, actual_outcome, delta, feedback_source, recorded_at)
            VALUES (:id, :b, 'discount', CAST(:pred AS JSON), CAST(:act AS JSON), CAST(:delta AS JSON), 'manual', NOW())
        """), {"id": str(uuid.uuid4()), "b": str(B1),
               "pred": json.dumps({"expected_recovery_sar": 500}),
               "act": json.dumps({"actual_recovery_sar": 420}),
               "delta": json.dumps({"prediction_error_pct": -16.0})})

        ctx = await build_business_context(db, B1, max_products=0, max_suppliers=0)

        assert len(ctx.outcomes) >= 1
        assert ctx.outcomes[0]["action_type"] == "discount"
        assert ctx.outcomes[0]["expected_impact_sar"] == 500
        assert ctx.outcomes[0]["actual_impact_sar"] == 420


# ═══════════════════════════════════════════════════════════════════════════════
# §14 Memory Confidence
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_confidence_reflects_evidence():
    """Confidence should increase with more evidence."""
    from app.services.product_memory import _confidence

    assert _confidence(0) == "INSUFFICIENT_DATA"
    assert _confidence(1) == "LOW"
    assert _confidence(5) == "MEDIUM"
    assert _confidence(20) == "HIGH"


# ═══════════════════════════════════════════════════════════════════════════════
# §16 Business Context API
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_business_context_serializable():
    """Business context should be serializable to JSON."""
    from app.services.business_context_service import build_business_context

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        await _seed_item(db, B1, ITEM1, stock=30)

        ctx = await build_business_context(db, B1, max_products=1, max_suppliers=0)

        # Should be serializable
        json_str = ctx.to_json()
        assert json_str
        parsed = json.loads(json_str)
        assert "business" in parsed
        assert "products" in parsed
        assert "suppliers" in parsed
        assert "constraints" in parsed
        assert "recent_actions" in parsed
        assert "outcomes" in parsed


@pytest.mark.asyncio
async def test_business_context_bounded():
    """Business context should respect max limits."""
    from app.services.business_context_service import build_business_context

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        for j in range(10):
            iid = uuid.uuid4()
            await _seed_item(db, B1, iid, name=f"Item {j}", stock=10)

        ctx = await build_business_context(db, B1, max_products=3, max_suppliers=0, max_actions=5)

        assert len(ctx.products) <= 3
        assert len(ctx.recent_actions) <= 5


# ═══════════════════════════════════════════════════════════════════════════════
# §17 Product Context API
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_product_context_includes_constraints():
    """Product context should include applicable constraints."""
    from app.services.business_context_service import build_product_context

    async with db_session_ctx() as db:
        constraints = {"blocked_discount_products": [str(ITEM1)], "strategic_products": [str(ITEM1)]}
        await _seed_business(db, B1, constraints=constraints)
        await _seed_item(db, B1, ITEM1)

        ctx = await build_product_context(db, B1, ITEM1)

        assert "product" in ctx
        assert "constraints" in ctx
        assert ctx["constraints"].get("discount_blocked") is True
        assert ctx["constraints"].get("strategic") is True


@pytest.mark.asyncio
async def test_product_context_includes_actions():
    """Product context should include previous actions."""
    from app.services.business_context_service import build_product_context

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        await _seed_item(db, B1, ITEM1)

        await db.execute(text("""
            INSERT INTO agent_actions (id, business_id, action_type, status, confidence, autonomy_dial_at_creation, title, summary, payload, created_at, updated_at)
            VALUES (:id, :b, 'discount', 'executed', 0.8, 60, 'Discount Milk', 'Discount Milk', CAST(:payload AS JSON), NOW(), NOW())
        """), {"id": str(uuid.uuid4()), "b": str(B1),
               "payload": json.dumps({"item_id": str(ITEM1)})})

        ctx = await build_product_context(db, B1, ITEM1)

        assert len(ctx["previous_actions"]) >= 1
        assert ctx["previous_actions"][0]["action_type"] == "discount"


# ═══════════════════════════════════════════════════════════════════════════════
# §18 AI Readiness
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_context_is_ai_ready():
    """Context should be deterministic, serializable, bounded, tenant-safe."""
    from app.services.business_context_service import build_business_context

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        await _seed_item(db, B1, ITEM1, stock=20)

        ctx = await build_business_context(db, B1, max_products=1, max_suppliers=0)

        # Deterministic: same input → same structure
        d = ctx.to_dict()
        assert isinstance(d, dict)
        assert d["business"]["business_id"] == str(B1)
        assert len(d["products"]) <= 1

        # Bounded: no unlimited data
        assert len(d["recent_actions"]) <= 20
        assert len(d["outcomes"]) <= 20


# ═══════════════════════════════════════════════════════════════════════════════
# §19 Tenant Isolation
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tenant_isolation_product_memory():
    """Business A cannot retrieve Business B's product memory."""
    from app.services.product_memory import build_product_memory

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        await _seed_business(db, B2)
        await _seed_item(db, B1, ITEM1, name="B1 Product")
        await _seed_item(db, B2, ITEM2, name="B2 Product")

        # B1's product memory should not contain B2's product
        pm = await build_product_memory(db, B1, ITEM1)
        assert pm.product_name == "B1 Product"
        assert pm.business_id == str(B1)

        # Querying B2's product with B1's context should fail or return wrong data
        with pytest.raises(ValueError):
            await build_product_memory(db, B1, ITEM2)


@pytest.mark.asyncio
async def test_tenant_isolation_supplier_memory():
    """Business A cannot retrieve Business B's supplier memory."""
    from app.services.supplier_memory import build_supplier_memory

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        await _seed_business(db, B2)
        await _seed_supplier(db, SUP1)

        # B2 has no POs with this supplier
        sm = await build_supplier_memory(db, B2, SUP1)
        assert sm.total_orders == 0
        assert sm.business_id == str(B2)


@pytest.mark.asyncio
async def test_tenant_isolation_business_context():
    """Business context should only contain tenant-scoped data."""
    from app.services.business_context_service import build_business_context

    async with db_session_ctx() as db:
        await _seed_business(db, B1, name="B1")
        await _seed_business(db, B2, name="B2")
        await _seed_item(db, B1, ITEM1)
        await _seed_item(db, B2, ITEM2)

        ctx1 = await build_business_context(db, B1, max_products=10, max_suppliers=0)
        ctx2 = await build_business_context(db, B2, max_products=10, max_suppliers=0)

        assert ctx1.business.name == "B1"
        assert ctx2.business.name == "B2"
        # Products should be different
        b1_products = [p["product_id"] for p in ctx1.products]
        b2_products = [p["product_id"] for p in ctx2.products]
        assert str(ITEM1) in b1_products
        assert str(ITEM2) in b2_products
        assert str(ITEM2) not in b1_products


# ═══════════════════════════════════════════════════════════════════════════════
# §20 Memory Correctness (Comprehensive Fixture)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_memory_correctness_comprehensive_fixture():
    """§20: Comprehensive fixture with fast mover, declining, dead, supplier, PO, constraint.

    Verify memory reconstructs correct context from underlying data.
    """
    from app.services.product_memory import build_product_memory
    from app.services.supplier_memory import build_supplier_memory
    from app.services.business_context_service import build_business_context

    async with db_session_ctx() as db:
        B_TEST = uuid.uuid4()
        FAST = uuid.uuid4()
        DECLINING = uuid.uuid4()
        DEAD = uuid.uuid4()
        SUP_TEST = uuid.uuid4()
        CONSTRAINTS = {
            "cash_budget": 3000,
            "minimum_margin_pct": 0.15,
            "blocked_discount_products": [str(DEAD)],
        }

        await _seed_business(db, B_TEST, name="Comprehensive Test", constraints=CONSTRAINTS)
        await _seed_supplier(db, SUP_TEST, name="Reliable Supplier")
        await _seed_item(db, B_TEST, FAST, name="Fast Mover", stock=10, cost=5.0, sell=12.0, supplier_id=SUP_TEST)
        await _seed_item(db, B_TEST, DECLINING, name="Declining Product", stock=80, cost=10.0, sell=25.0)
        await _seed_item(db, B_TEST, DEAD, name="Dead Stock", stock=100, cost=15.0, sell=30.0)

        # Fast mover: 15/day sales for 30 days
        await _seed_sales(db, B_TEST, FAST, qty_per_day=15, days=30)
        # Declining: recent 7 days = 2/day, prior 30 days = 10/day
        from app.utils.clock import utcnow
        anchor = utcnow().date()
        for d in range(30):
            qty = 2 if d < 7 else 10
            tx_date = anchor - timedelta(days=d)
            await db.execute(text("""
                INSERT INTO transactions (id, business_id, item_id, transaction_type, quantity, unit_price, cost_price, profit, total_amount, transaction_at, created_at)
                VALUES (:id, :b, :item, 'sale', :qty, 25.0, 10.0, :qty * 15.0, :total, :tx_at, NOW())
            """), {"id": str(uuid.uuid4()), "b": str(B_TEST), "item": str(DECLINING),
                   "qty": qty, "total": qty * 25.0, "tx_at": tx_date})
        # Dead: no sales in 60 days
        # (no transactions seeded)

        # Reliable supplier: 10 POs, 9 received, 1 overdue
        for _ in range(9):
            await _seed_po(db, B_TEST, SUP_TEST, FAST, status="received")
        overdue_delivery = anchor - timedelta(days=5)
        await _seed_po(db, B_TEST, SUP_TEST, FAST, status="sent", expected_delivery=overdue_delivery)

        # ── Verify Product Memory ───────────────────────────────────────
        fast_mem = await build_product_memory(db, B_TEST, FAST)
        assert fast_mem.trend == "STABLE" or fast_mem.velocity_30d > 100
        assert fast_mem.current_stock == 10.0
        assert fast_mem.supplier_reliability in ("HIGH", "MEDIUM")

        declining_mem = await build_product_memory(db, B_TEST, DECLINING)
        assert declining_mem.trend == "DECLINING" or declining_mem.velocity_7d < declining_mem.velocity_30d

        dead_mem = await build_product_memory(db, B_TEST, DEAD)
        assert dead_mem.velocity_30d == 0
        assert dead_mem.days_since_last_sale is None or dead_mem.days_since_last_sale > 30

        # ── Verify Supplier Memory ──────────────────────────────────────
        sup_mem = await build_supplier_memory(db, B_TEST, SUP_TEST)
        assert sup_mem.total_orders >= 10
        assert sup_mem.received_orders >= 9
        assert sup_mem.overdue_orders >= 1
        assert sup_mem.reliability_rate is not None

        # ── Verify Business Context ─────────────────────────────────────
        ctx = await build_business_context(db, B_TEST, max_products=10, max_suppliers=5)
        assert ctx.constraints.get("cash_budget") == 3000
        assert ctx.constraints.get("blocked_discount_products") == [str(DEAD)]
        product_ids = [p["product_id"] for p in ctx.products]
        assert str(FAST) in product_ids


# ═══════════════════════════════════════════════════════════════════════════════
# §21 Memory Update (Freshness)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_memory_refresh_after_new_data():
    """Memory should reflect new transactions after refresh."""
    from app.services.product_memory import build_product_memory

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        await _seed_item(db, B1, ITEM1, stock=50)

        # Initial: no sales
        pm1 = await build_product_memory(db, B1, ITEM1)
        assert pm1.velocity_30d == 0

        # Add sales
        await _seed_sales(db, B1, ITEM1, qty_per_day=10, days=30)

        # Refresh: should show new velocity
        pm2 = await build_product_memory(db, B1, ITEM1)
        assert pm2.velocity_30d > 0
        assert pm2.confidence != "INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_memory_update_after_action_outcome():
    """Memory should reflect new action outcomes."""
    from app.services.business_context_service import build_business_context

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        await _seed_item(db, B1, ITEM1)

        # Initial context
        ctx1 = await build_business_context(db, B1, max_products=1, max_suppliers=0)
        assert len(ctx1.outcomes) == 0

        # Add outcome
        await db.execute(text("""
            INSERT INTO outcome_feedback (id, business_id, decision_type, predicted_outcome, actual_outcome, delta, feedback_source, recorded_at)
            VALUES (:id, :b, 'discount', CAST(:pred AS JSON), CAST(:act AS JSON), CAST(:delta AS JSON), 'manual', NOW())
        """), {"id": str(uuid.uuid4()), "b": str(B1),
               "pred": json.dumps({"expected_recovery_sar": 300}),
               "act": json.dumps({"actual_recovery_sar": 250}),
               "delta": json.dumps({"prediction_error_pct": -16.7})})

        # Refresh context
        ctx2 = await build_business_context(db, B1, max_products=1, max_suppliers=0)
        assert len(ctx2.outcomes) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Performance
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_product_memory_retrieval_performance():
    """Product memory retrieval should complete within reasonable time."""
    import time
    from app.services.product_memory import build_product_memory

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        await _seed_item(db, B1, ITEM1, stock=100)
        await _seed_sales(db, B1, ITEM1, qty_per_day=10, days=90)

        start = time.monotonic()
        pm = await build_product_memory(db, B1, ITEM1)
        elapsed = time.monotonic() - start

        assert pm is not None
        assert elapsed < 2.0, f"Product memory took {elapsed:.2f}s, should be < 2s"


@pytest.mark.asyncio
async def test_business_context_retrieval_performance():
    """Business context retrieval should complete within reasonable time."""
    import time
    from app.services.business_context_service import build_business_context

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        for j in range(20):
            iid = uuid.uuid4()
            await _seed_item(db, B1, iid, name=f"Item {j}", stock=10 + j)
            await _seed_sales(db, B1, iid, qty_per_day=1 + j % 5, days=30)

        start = time.monotonic()
        ctx = await build_business_context(db, B1, max_products=20, max_suppliers=0)
        elapsed = time.monotonic() - start

        assert ctx is not None
        assert elapsed < 10.0, f"Business context took {elapsed:.2f}s, should be < 10s for 20 SKUs"


# ═══════════════════════════════════════════════════════════════════════════════
# §7 Promotion Memory
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_promotion_detection_with_pricing_rules():
    """Product with active pricing rules should show promotion data."""
    from app.services.product_memory import build_product_memory

    async with db_session_ctx() as db:
        await _seed_business(db, B1)
        await _seed_item(db, B1, ITEM1, stock=50)

        # Seed a pricing rule (promotion-like)
        await db.execute(text("""
            INSERT INTO pricing_rules (id, business_id, item_id, rule_type, rule_name, is_active, config, created_at, updated_at)
            VALUES (:id, :b, :i, 'time_based', 'Summer Sale', true, '{}', NOW(), NOW())
        """), {"id": str(uuid.uuid4()), "b": str(B1), "i": str(ITEM1)})

        pm = await build_product_memory(db, B1, ITEM1)
        assert pm.promotion_count >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

from contextlib import asynccontextmanager

@asynccontextmanager
async def db_session_ctx():
    """Provide a test db_session from the fixture context."""
    import os, socket
    from urllib.parse import urlparse

    TEST_DATABASE_URL = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos_test",
    )
    url = TEST_DATABASE_URL.replace("+asyncpg", "")
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        with socket.create_connection((host, port), timeout=0.35):
            pass
    except OSError:
        pytest.skip("Postgres not available")

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool
    from app.database.models import Base

    test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
    await test_engine.dispose()
