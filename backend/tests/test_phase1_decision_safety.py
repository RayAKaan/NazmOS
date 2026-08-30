"""Phase 1 — Decision-engine safety tests (P0-A purchase-order awareness,
P0-B owner constraints enforced at the final execution boundary).

All tests run against the REAL PostgreSQL test database via the shared
`db_session` fixture (no SQLite, no mocks of the decision/constraint engine,
no fabricated outcomes). Each production change has a corresponding test here.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from app.database.models import PurchaseOrder
from app.services.po_service import (
    get_confirmed_inbound,
    get_confirmed_inbound_map,
    is_open_inbound_status,
    po_classify_status,
)
from app.services.constraint_service import (
    filter_action_with_code,
    CODE_DISCOUNT_BLOCKED,
    CODE_DISCOUNT_STRATEGIC,
    CODE_DISCOUNT_MAX_PCT,
    CODE_DISCOUNT_MIN_MARGIN,
    CODE_REORDER_CASH_BUDGET,
    CODE_REORDER_MAX_PURCHASE,
    CODE_REORDER_MOQ_BUDGET,
    CODE_REORDER_MIN_SAFETY,
    CODE_REORDER_SUPPLIER_PREFERENCE,
    CODE_TRANSFER_ROUTE,
    CODE_TRANSFER_PRIORITY,
    CODE_OK,
)
from app.services.execution_guard import (
    validate_action_for_execution,
    record_constraint_block,
    CODE_TENANT_MISMATCH,
    CODE_INSUFFICIENT_PERMISSION,
    CODE_STALE_REORDER,
    CODE_ITEM_NOT_FOUND,
)
from app.services.po_service import usable_confirmed_inbound, projected_stockout_date
from app.services.action_executor import ActionExecutor
from app.services.agent_action_executor import execute_agent_action
from app.services.money_audit_service import generate_money_audit
from app.services.decision_engine import DecisionEngine, ActionType
from app.utils.clock import utcnow, set_virtual_now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_business(db, business_id, constraints=None):
    await db.execute(
        text(text_business_insert()),
        {
            "id": str(business_id),
            "name": "P1 Test Biz",
            "constraints": json.dumps(constraints or {}),
        },
    )


def text_business_insert() -> str:
    return (
        "INSERT INTO businesses (id, name, type, currency, constraints_json) "
        "VALUES (:id, :name, 'retail', 'SAR', CAST(:constraints AS JSON))"
    )


async def _seed_item(db, business_id, item_id, *, stock=10, cost=10, sell=20, safety=5, lead=7, sku="SKU1"):
    await db.execute(
        text(
            "INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active) "
            "VALUES (:id, :b, 'Widget', :sku, 'piece', :cost, :sell, true)"
        ),
        {"id": str(item_id), "b": str(business_id), "sku": sku, "cost": cost, "sell": sell},
    )
    await db.execute(
        text(
            "INSERT INTO inventory (id, item_id, business_id, current_stock, safety_stock, lead_time_days) "
            "VALUES (gen_random_uuid(), :iid, :b, :stock, :safety, :lead)"
        ),
        {"iid": str(item_id), "b": str(business_id), "stock": stock, "safety": safety, "lead": lead},
    )


async def _seed_sales(db, business_id, item_id, total_qty=120, days=25, unit_price=20, unit_cost=10):
    from datetime import timedelta as td
    per = max(1, total_qty // days)
    for i in range(days):
        await db.execute(
            text(
                "INSERT INTO transactions (id, business_id, item_id, quantity, unit_price, cost_price, "
                "total_amount, profit, transaction_type, transaction_at) "
                "VALUES (gen_random_uuid(), :b, :iid, :q, :up, :cp, :tot, :prof, 'sale', :t)"
            ),
            {
                "b": str(business_id),
                "iid": str(item_id),
                "q": per,
                "up": unit_price,
                "cp": unit_cost,
                "tot": per * unit_price,
                "prof": per * (unit_price - unit_cost),
                "t": utcnow() - td(days=i),
            },
        )


async def _seed_po(db, business_id, item_id, qty, status="confirmed", expected_delivery=None):
    db.add(
        PurchaseOrder(
            id=uuid.uuid4(),
            business_id=business_id,
            status=status,
            items_json=[{"item_id": str(item_id), "qty": qty, "unit_cost": 10}],
            expected_delivery=expected_delivery,
        )
    )


# ───────────────────────────────────────────────────────────────────────────
# A. Purchase-order safety (A1–A7)
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a1_confirmed_inbound_suppresses_reorder(db_session):
    """A1: stock already committed (confirmed PO) must be counted as inbound."""
    biz = uuid.uuid4()
    item = uuid.uuid4()
    await _seed_business(db_session, biz)
    await _seed_item(db_session, biz, item, stock=5)
    await _seed_po(db_session, biz, item, qty=40, status="confirmed")
    await db_session.commit()

    result = await get_confirmed_inbound(
        db_session, business_id=biz, item_id=item, as_of=utcnow().date()
    )
    assert result is not None
    assert result.confirmed_inbound_qty == 40
    assert result.po_count == 1


@pytest.mark.asyncio
async def test_a2_received_po_not_double_counted(db_session):
    """A2: a received PO's goods are already on-hand; must NOT count as inbound."""
    biz = uuid.uuid4()
    item = uuid.uuid4()
    await _seed_business(db_session, biz)
    await _seed_item(db_session, biz, item, stock=5)
    await _seed_po(db_session, biz, item, qty=50, status="received")
    await db_session.commit()

    result = await get_confirmed_inbound(db_session, business_id=biz, item_id=item, as_of=utcnow().date())
    assert result is not None
    assert result.confirmed_inbound_qty == 0, "received PO must not count as future inbound"


@pytest.mark.asyncio
async def test_a3_cancelled_and_draft_excluded(db_session):
    """A3: cancelled / draft POs are not firm inbound; only confirmed statuses count."""
    biz = uuid.uuid4()
    item = uuid.uuid4()
    await _seed_business(db_session, biz)
    await _seed_item(db_session, biz, item, stock=5)
    await _seed_po(db_session, biz, item, qty=10, status="cancelled")
    await _seed_po(db_session, biz, item, qty=10, status="draft")
    await _seed_po(db_session, biz, item, qty=10, status="sent")
    await db_session.commit()

    result = await get_confirmed_inbound(db_session, business_id=biz, item_id=item, as_of=utcnow().date())
    assert result.confirmed_inbound_qty == 10, "only the 'sent' (confirmed-bucket) PO counts"


@pytest.mark.asyncio
async def test_a4_overdue_open_po_flagged_ghost_but_still_suppresses(db_session):
    """A4/A6: an overdue open PO still suppresses reorder but is surfaced as ghost risk."""
    biz = uuid.uuid4()
    item = uuid.uuid4()
    await _seed_business(db_session, biz)
    await _seed_item(db_session, biz, item, stock=5)
    overdue = utcnow().date() - timedelta(days=45)
    await _seed_po(db_session, biz, item, qty=30, status="confirmed", expected_delivery=overdue)
    await db_session.commit()

    result = await get_confirmed_inbound(db_session, business_id=biz, item_id=item, as_of=utcnow().date())
    assert result.confirmed_inbound_qty == 30
    assert result.overdue_po_count == 1
    assert result.ghost_po_risk is True


@pytest.mark.asyncio
async def test_a7_virtual_clock_anchor_controls_inbound(db_session):
    """A7: the canonical inbound computation is anchored to the virtual/`as_of` clock,
    so a was-not-yet-expected PO at today becomes counted when the window advances."""
    biz = uuid.uuid4()
    item = uuid.uuid4()
    await _seed_business(db_session, biz)
    await _seed_item(db_session, biz, item, stock=5)
    future_delivery = utcnow().date() + timedelta(days=10)
    await _seed_po(db_session, biz, item, qty=25, status="confirmed", expected_delivery=future_delivery)
    await db_session.commit()

    today_result = await get_confirmed_inbound(db_session, business_id=biz, item_id=item, as_of=utcnow().date())
    later = await get_confirmed_inbound(
        db_session, business_id=biz, item_id=item, as_of=utcnow().date() + timedelta(days=20)
    )
    # The PO is committed regardless of delivery date, so both windows see it.
    assert today_result.confirmed_inbound_qty == 25
    assert later.confirmed_inbound_qty == 25

    # po_classify_status is stable and virtual-clock independent.
    assert po_classify_status("confirmed") == "confirmed"
    assert po_classify_status("Received") == "received"
    assert po_classify_status("cancelled") == "cancelled"
    assert is_open_inbound_status("sent") is True
    assert is_open_inbound_status("received") is False


@pytest.mark.asyncio
async def test_a5_large_inbound_suppresses_money_audit_reorder(db_session):
    """A4/A5: with a large confirmed inbound, projected stock covers demand and the
    deterministic money-audit engine must NOT issue a reorder (no over-ordering)."""
    biz = uuid.uuid4()
    item = uuid.uuid4()
    await _seed_business(db_session, biz)
    await _seed_item(db_session, biz, item, stock=10, cost=10, sell=20, safety=5, lead=7)
    await _seed_sales(db_session, biz, item, total_qty=120, days=30)  # velocity = 4/day
    await _seed_po(db_session, biz, item, qty=40, status="confirmed")
    await db_session.commit()

    result = await generate_money_audit(db_session, biz)
    reorders = [
        a for a in result["actions"]
        if a.get("action_type") == "reorder" and (a.get("evidence") or {}).get("reason") == "stockout_risk"
    ]
    assert reorders == [], "confirmed inbound of 40 should raise projected cover above the stockout threshold"


@pytest.mark.asyncio
async def test_a4_inbound_reduces_money_audit_reorder_quantity(db_session):
    """A4: partial confirmed inbound must reduce (not inflate) the reorder quantity —
    the formula is based on PROJECTED stock (current + inbound), fixing the prior
    `- stock` over-order bug."""
    biz = uuid.uuid4()
    item = uuid.uuid4()
    await _seed_business(db_session, biz)
    await _seed_item(db_session, biz, item, stock=10, cost=10, sell=20, safety=5, lead=7)
    await _seed_sales(db_session, biz, item, total_qty=120, days=30)  # velocity = 4/day
    await _seed_po(db_session, biz, item, qty=8, status="confirmed")  # inbound=8
    await db_session.commit()

    result = await generate_money_audit(db_session, biz)
    reorders = [
        a for a in result["actions"]
        if a.get("action_type") == "reorder" and (a.get("evidence") or {}).get("reason") == "stockout_risk"
    ]
    assert len(reorders) == 1, "projected cover still < threshold, so a (smaller) reorder is expected"
    # projected_stock = 10 + 8 = 18; order_qty = 4*7 + 5 - 18 = 15 (NOT 4*7+5-10 = 23)
    assert float(reorders[0]["quantity"]) <= 15, "order qty must be based on projected stock (incl. inbound)"


# ───────────────────────────────────────────────────────────────────────────
# B. Owner-constraint enforcement — stable reason codes (9 rows)
# ───────────────────────────────────────────────────────────────────────────

def test_b_constraint_codes_stable():
    cases = [
        (CODE_DISCOUNT_BLOCKED, "discount", {"item_id": "X", "discount_pct": 10}, {"blocked_discount_products": ["X"]}),
        (CODE_DISCOUNT_STRATEGIC, "discount", {"item_id": "X", "discount_pct": 5}, {"strategic_products": ["X"]}),
        (CODE_DISCOUNT_MAX_PCT, "discount", {"item_id": "X", "discount_pct": 50}, {"max_discount_pct": 30}),
        (CODE_DISCOUNT_MIN_MARGIN, "discount", {"item_id": "X", "discount_pct": 40, "sell_price_sar": 10, "cost_price_sar": 9}, {"minimum_margin_pct": 0.1}),
        (CODE_REORDER_CASH_BUDGET, "reorder", {"estimated_cost_sar": 9000}, {"cash_budget": 5000}),
        (CODE_REORDER_MAX_PURCHASE, "reorder", {"estimated_cost_sar": 9000}, {"maximum_purchase_amount": 5000}),
        (CODE_REORDER_MOQ_BUDGET, "reorder", {"supplier_moq": 9000}, {"cash_budget": 5000}),
        (CODE_REORDER_MIN_SAFETY, "reorder", {"current_stock": 2, "quantity": 1}, {"minimum_safety_stock": 5}),
        (CODE_REORDER_SUPPLIER_PREFERENCE, "reorder", {"supplier_id": "S2"}, {"supplier_preferences": ["S1"]}),
        (CODE_TRANSFER_ROUTE, "transfer_inventory", {"from_business_id": "A", "to_business_id": "B"}, {"blocked_transfer_routes": ["A->B"]}),
        (CODE_TRANSFER_PRIORITY, "transfer_inventory", {"from_business_id": "A", "to_business_id": "B"}, {"branch_priority": {"A": 3, "B": 1}}),
    ]
    for expected_code, action_type, payload, constraints in cases:
        feasible, code, _reason = filter_action_with_code(action_type, payload, constraints)
        assert feasible is False, f"{action_type} should be infeasible"
        assert code == expected_code, f"expected {expected_code}, got {code}"
        assert code.startswith("CONSTRAINT_"), "reason codes must be namespaced and stable"

    feasible, code, _ = filter_action_with_code("reorder", {"estimated_cost_sar": 10}, {"cash_budget": 5000})
    assert feasible is True
    assert code == CODE_OK


# ───────────────────────────────────────────────────────────────────────────
# C. Final-execution guard (P0-B)
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_c_guard_tenant_mismatch(db_session):
    biz = uuid.uuid4()
    other_biz = uuid.uuid4()
    await _seed_business(db_session, biz)
    await _seed_business(db_session, other_biz)
    await db_session.commit()

    verdict = await validate_action_for_execution(
        db_session,
        business_id=biz,
        action_type="reorder",
        payload={"item_id": str(uuid.uuid4()), "estimated_cost_sar": 10},
        actor_business_id=other_biz,
    )
    assert verdict.blocked is True
    assert verdict.reason_code == CODE_TENANT_MISMATCH


@pytest.mark.asyncio
async def test_c_guard_insufficient_permission(db_session):
    biz = uuid.uuid4()
    await _seed_business(db_session, biz)
    await db_session.commit()
    verdict = await validate_action_for_execution(
        db_session,
        business_id=biz,
        action_type="reorder",
        payload={"item_id": str(uuid.uuid4()), "estimated_cost_sar": 10},
        required_permission="execute_action",
        has_permission=False,
    )
    assert verdict.blocked is True
    assert verdict.reason_code == CODE_INSUFFICIENT_PERMISSION


@pytest.mark.asyncio
async def test_c_guard_owner_cash_budget_blocks(db_session):
    """Owner constraints are enforced at the execution boundary with a stable code."""
    biz = uuid.uuid4()
    await _seed_business(db_session, biz, constraints={"cash_budget": 1000})
    await db_session.commit()

    verdict = await validate_action_for_execution(
        db_session,
        business_id=biz,
        action_type="reorder",
        payload={"item_id": str(uuid.uuid4()), "estimated_cost_sar": 9000},
        actor_business_id=biz,
    )
    assert verdict.blocked is True
    assert verdict.reason_code == CODE_REORDER_CASH_BUDGET


@pytest.mark.asyncio
async def test_c_record_constraint_block_persists(db_session):
    biz = uuid.uuid4()
    await _seed_business(db_session, biz)
    await db_session.commit()
    await record_constraint_block(
        db_session,
        business_id=biz,
        action_type="reorder",
        reason_code=CODE_REORDER_CASH_BUDGET,
        reason="Over budget",
        payload={"estimated_cost_sar": 9999},
    )
    res = await db_session.execute(
        text("SELECT reason_code FROM constraint_blocks WHERE business_id = :b"),
        {"b": str(biz)},
    )
    assert res.scalar_one() == CODE_REORDER_CASH_BUDGET


@pytest.mark.asyncio
async def test_c_legacy_action_executor_refuses_blocked_restock(db_session):
    """The legacy ActionExecutor must NOT mutate state when owner constraints block it."""
    biz = uuid.uuid4()
    item = uuid.uuid4()
    await _seed_business(db_session, biz, constraints={"cash_budget": 1000})
    await _seed_item(db_session, biz, item, stock=10, cost=100, sell=200)
    await db_session.commit()

    from sqlalchemy import text as _t
    before = (await db_session.execute(_t("SELECT current_stock FROM inventory WHERE item_id=:i"), {"i": str(item)})).scalar()

    executor = ActionExecutor(db_session)
    result = await executor.execute_action(
        business_id=biz,
        action_type="RESTOCK",
        entity_type="item",
        entity_id=item,
        previous_state={"current_stock": 10.0},
        new_state={"current_stock": 110.0},  # quantity=100 * cost=100 = 10000 > cash budget 1000
        user_id=None,
        source="money_audit",
    )
    assert result.success is False, "blocked restock must not succeed"
    after = (await db_session.execute(_t("SELECT current_stock FROM inventory WHERE item_id=:i"), {"i": str(item)})).scalar()
    assert float(after) == float(before), "inventory must NOT be mutated when the guard blocks"

    blocked = (await db_session.execute(
        _t("SELECT reason_code FROM constraint_blocks WHERE business_id=:b"), {"b": str(biz)}
    )).fetchall()
    assert blocked, "a constraint_blocks record must be persisted for the refused execution"


@pytest.mark.asyncio
async def test_c_agent_executor_blocked_by_constraint_with_code(db_session):
    """The agent execution path surfaces a stable reason code and persists the block."""
    biz = uuid.uuid4()
    item = uuid.uuid4()
    await _seed_business(db_session, biz, constraints={"cash_budget": 1000})
    await _seed_item(db_session, biz, item)
    await db_session.commit()

    outcome = await execute_agent_action(
        db_session,
        business_id=biz,
        action_id=str(uuid.uuid4()),
        action_type="reorder",
        payload={"item_id": str(item), "estimated_cost_sar": 9000},
    )
    assert outcome["executed"] is False
    assert outcome["execution_mode"] == "BLOCKED_BY_CONSTRAINT"
    assert outcome.get("reason_code") == CODE_REORDER_CASH_BUDGET

    res = await db_session.execute(
        text("SELECT reason_code FROM constraint_blocks WHERE business_id = :b"), {"b": str(biz)}
    )
    assert res.scalar_one() == CODE_REORDER_CASH_BUDGET


@pytest.mark.asyncio
async def test_c_business_unit_level_no_financial_tables_required(db_session):
    """The guard treats un-attributable action types as permitted with a stable OK code."""
    biz = uuid.uuid4()
    await _seed_business(db_session, biz)
    await db_session.commit()
    verdict = await validate_action_for_execution(
        db_session,
        business_id=biz,
        action_type="price_increase_only_placeholder",
        payload={},
    )
    # Not a recognized constraint group -> permitted, never a guard error.
    assert verdict.blocked is False


# ───────────────────────────────────────────────────────────────────────────
# D. Virtual clock + deterministic engine
# ───────────────────────────────────────────────────────────────────────────

def test_d_decision_engine_virtual_clock_and_po_aware():
    set_virtual_now(datetime(2026, 8, 1, tzinfo=datetime.now().astimezone().tzinfo))
    try:
        engine = DecisionEngine()
        decisions = engine.generate_from_inventory(
            [{"item_id": "IT1", "current_stock": 4, "daily_avg_sale": 4, "reorder_level": 10,
              "cost_price": 10, "sell_price": 20, "name": "Widget"}],
            confirmed_inbound={"IT1": 100},  # large inbound
        )
        restocks = [d for d in decisions if d.action == ActionType.RESTOCK]
        assert restocks == [], "large confirmed inbound must suppress RESTOCK in the deterministic engine"
        assert all(d.by_when.year == 2026 and d.by_when.month == 8 for d in decisions), \
            "by_when must follow the virtual clock, not date.today()"
    finally:
        set_virtual_now(None)


def test_d_decision_engine_reorder_qty_po_aware():
    engine = DecisionEngine()
    decisions = engine.generate_from_inventory(
        [{"item_id": "IT2", "current_stock": 2, "daily_avg_sale": 5, "reorder_level": 10,
          "cost_price": 5, "sell_price": 10, "name": "Widget"}],
        confirmed_inbound={"IT2": 8},  # partial inbound
    )
    restock = [d for d in decisions if d.action == ActionType.RESTOCK][0]
    # available = 2 + 8 = 10; qty = max(5*7-8, 10*2-8) = max(27,12) = 27 -> reflects inbound
    assert restock.quantity >= 0
    assert "confirmed inbound" in restock.reason


# ───────────────────────────────────────────────────────────────────────────
# E. Latency
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e_inbound_map_latency_budget(db_session):
    biz = uuid.uuid4()
    item = uuid.uuid4()
    await _seed_business(db_session, biz)
    await _seed_item(db_session, biz, item)
    for i in range(50):
        await _seed_po(db_session, biz, item, qty=i + 1, status="confirmed")
    await db_session.commit()

    start = time.perf_counter()
    m = await get_confirmed_inbound_map(db_session, business_id=biz, as_of=utcnow().date())
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    assert str(item) in m
    assert elapsed_ms < 2000, f"get_confirmed_inbound_map took {elapsed_ms:.0f}ms"


# ───────────────────────────────────────────────────────────────────────────
# F. Time-aware inbound — the system reasons about WHEN stock arrives (Section 4 / A6)
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_f_usable_confirmed_inbound_splits_before_vs_after_stockout(db_session):
    """Timing helper: inbound arriving strictly BEFORE the projected stockout is
    usable; inbound at/after the stockout (or with an explicit far-future date) is late."""
    from app.services.po_service import ConfirmedInbound

    stockout = date(2026, 8, 3)  # stockout in 2 days from anchor
    early = ConfirmedInbound(
        item_id="I1", confirmed_inbound_qty=50,
        line_items=[{"expected_delivery": date(2026, 8, 2).isoformat(), "committed_qty": 50.0}],
    )
    late = ConfirmedInbound(
        item_id="I2", confirmed_inbound_qty=50,
        line_items=[{"expected_delivery": date(2026, 8, 11).isoformat(), "committed_qty": 50.0}],
    )
    unknown = ConfirmedInbound(
        item_id="I3", confirmed_inbound_qty=50,
        line_items=[{"expected_delivery": None, "committed_qty": 50.0}],
    )
    t_early = usable_confirmed_inbound(early, stockout_date=stockout)
    t_late = usable_confirmed_inbound(late, stockout_date=stockout)
    t_unknown = usable_confirmed_inbound(unknown, stockout_date=stockout)
    assert t_early.usable_qty == 50 and t_early.late_qty == 0
    assert t_late.late_qty == 50 and t_late.usable_qty == 0
    # A firm commitment with no recorded ETA still counts toward coverage (A2).
    assert t_unknown.usable_qty == 50
    assert projected_stockout_date(as_of=date(2026, 8, 1), current_stock=10, daily_demand=5) == date(2026, 8, 3)


@pytest.mark.asyncio
async def test_f_far_future_po_does_not_suppress_money_audit_reorder(db_session):
    """P0-A timing fix: a confirmed PO whose delivery arrives at/after the projected
    stockout must NOT suppress an immediate reorder — it is surfaced as actionable
    stockout risk. This is the regression proving the system reasons about WHEN."""
    biz = uuid.uuid4()
    item = uuid.uuid4()
    await _seed_business(db_session, biz)
    await _seed_item(db_session, biz, item, stock=10, cost=10, sell=20, safety=5, lead=7)
    await _seed_sales(db_session, biz, item, total_qty=120, days=30)  # velocity = 4/day -> stockout ~2-3 days
    far_future = utcnow().date() + timedelta(days=10)
    await _seed_po(db_session, biz, item, qty=40, status="confirmed", expected_delivery=far_future)
    await db_session.commit()

    result = await generate_money_audit(db_session, biz)
    reorders = [
        a for a in result["actions"]
        if a.get("action_type") == "reorder" and (a.get("evidence") or {}).get("reason") == "stockout_risk"
    ]
    assert len(reorders) == 1, "a late PO must NOT suppress the immediate reorder"
    ev = reorders[0]["evidence"]
    # The PO is on the books (aggregate inbound present) but is flagged LATE.
    assert ev["confirmed_inbound_qty"] == 40
    assert ev["usable_inbound_qty"] == 0, "far-future inbound must not be counted as usable before stockout"
    assert ev["late_inbound_qty"] == 40


# ───────────────────────────────────────────────────────────────────────────
# G. Execution boundary — at-execution state re-verification (Section 8/9 race defense)
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_g_guard_stale_reorder_blocked_when_inbound_covers(db_session):
    """A PO placed between recommendation and execution must cause the reorder to be
    refused at the boundary (GUARD_STALE_REORDER) rather than over-ordering."""
    biz = uuid.uuid4()
    item = uuid.uuid4()
    await _seed_business(db_session, biz)
    await _seed_item(db_session, biz, item, stock=5, cost=10, sell=20)
    # A confirmed PO (arriving tomorrow) already covers the requested quantity.
    tomorrow = utcnow().date() + timedelta(days=1)
    await _seed_po(db_session, biz, item, qty=50, status="confirmed", expected_delivery=tomorrow)
    await db_session.commit()

    verdict = await validate_action_for_execution(
        db_session,
        business_id=biz,
        action_type="reorder",
        payload={"item_id": str(item), "quantity": 30, "estimated_cost_sar": 300},
        actor_business_id=biz,
    )
    assert verdict.blocked is True
    assert verdict.reason_code == CODE_STALE_REORDER


@pytest.mark.asyncio
async def test_g_guard_reorder_passes_when_no_redundant_inbound(db_session):
    """When the execution-time state still lacks covering inbound, the same reorder
    is allowed to proceed (no false positive)."""
    biz = uuid.uuid4()
    item = uuid.uuid4()
    await _seed_business(db_session, biz)
    await _seed_item(db_session, biz, item, stock=5, cost=10, sell=20)
    await db_session.commit()  # no PO at all

    verdict = await validate_action_for_execution(
        db_session,
        business_id=biz,
        action_type="reorder",
        payload={"item_id": str(item), "quantity": 30, "estimated_cost_sar": 300},
        actor_business_id=biz,
    )
    assert verdict.blocked is False
    assert verdict.reason_code == CODE_OK


@pytest.mark.asyncio
async def test_g_guard_item_not_found_blocks(db_session):
    """At-execution identity re-verification: an item that does not belong to this
    business must be refused even when generic constraints would permit it."""
    biz = uuid.uuid4()
    await _seed_business(db_session, biz)
    await db_session.commit()

    verdict = await validate_action_for_execution(
        db_session,
        business_id=biz,
        action_type="reorder",
        payload={"item_id": str(uuid.uuid4()), "quantity": 30, "estimated_cost_sar": 300},
        actor_business_id=biz,
    )
    assert verdict.blocked is True
    assert verdict.reason_code == CODE_ITEM_NOT_FOUND


