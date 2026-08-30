"""WS10 — customer happy path end-to-end on the REAL PostgreSQL test database.

Proves the full merchant loop works through the production services with no
mocks and no fabricated outcomes (money-audit engine is PG-only by design:
JSONB, DATE_TRUNC, INTERVAL):

  1. Seed business + catalog + inventory + 30 days of sales.
  2. generate_money_audit -> real findings (dead stock + stockout risk) with
     canonical financial vocabulary (_sar / expected_recovery_sar).
  3. execution_engine.execute_from_request -> simulated execution that spawns a
     completed job, emits execution.completed, and never mutates item money.
  4. Analytics dead-stock SAR agrees with inventory value at risk.
"""
import uuid
from datetime import timedelta

import pytest

from app.database.models import Item
from app.utils.clock import utcnow


async def _seed(business_id, session):
    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO businesses (id, name, type, currency, constraints_json) "
            "VALUES (:id, :name, 'retail', 'SAR', CAST('{}' AS JSON))"
        ),
        {"id": str(business_id), "name": "Pilot Quick Mart"},
    )

    async def _item(name, sku, cost, sell, stock, safety=5, lead=7):
        iid = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active) "
                "VALUES (:id, :b, :n, :sku, 'piece', :cost, :sell, true)"
            ),
            {"id": str(iid), "b": str(business_id), "n": name, "sku": sku,
             "cost": cost, "sell": sell},
        )
        await session.execute(
            text(
                "INSERT INTO inventory (id, item_id, business_id, current_stock, "
                "reorder_level, safety_stock, lead_time_days) "
                "VALUES (gen_random_uuid(), :iid, :b, :stock, :ro, :safety, :lead)"
            ),
            {"iid": str(iid), "b": str(business_id), "stock": stock, "ro": safety,
             "safety": safety, "lead": lead},
        )
        return iid

    fast = await _item("Milk 1L", "MLK", 5.0, 8.0, stock=18, safety=5, lead=7)
    dead = await _item("Old Spice Pack", "SPC", 20.0, 35.0, stock=40, safety=2, lead=5)
    healthy = await _item("Bread", "BRD", 2.0, 4.0, stock=30, safety=4, lead=3)

    async def tx(item_id, qty, unit_price, unit_cost, at):
        await session.execute(
            text(
                "INSERT INTO transactions (id, business_id, item_id, quantity, unit_price, cost_price, "
                "total_amount, profit, transaction_type, transaction_at) "
                "VALUES (gen_random_uuid(), :b, :iid, :q, :up, :cp, :tot, :prof, 'sale', :t)"
            ),
            {"b": str(business_id), "iid": str(item_id), "q": qty, "up": unit_price,
             "cp": unit_cost, "tot": qty * unit_price, "prof": qty * (unit_price - unit_cost),
             "t": at},
        )

    for i in range(25):
        day = utcnow() - timedelta(days=i)
        await tx(fast, 4, 8.0, 5.0, day)
        await tx(healthy, 1, 4.0, 2.0, day)

    await session.commit()
    return {"fast": fast, "dead": dead, "healthy": healthy}


@pytest.mark.asyncio
async def test_happy_path_full_loop(db_session):
    bid = uuid.uuid4()
    ids = await _seed(bid, db_session)

    from app.services.money_audit_service import generate_money_audit

    audit = await generate_money_audit(db_session, bid)
    actions = audit["actions"]
    assert any(a["action_type"] == "reorder" for a in actions), \
        "high-velocity item must surface a reorder finding"
    discounts = [a for a in actions if a["action_type"] == "discount"]
    assert discounts, "dead (never-sold) item must surface a discount finding"
    assert any(
        a["item_id"] == str(ids["dead"]) for a in discounts
    ), "discount finding must target the dead item"

    dead_action = next(a for a in discounts if a["item_id"] == str(ids["dead"]))
    assert "recoverable_value_low_sar" in dead_action
    assert "recoverable_value_high_sar" in dead_action
    assert float(dead_action["recoverable_value_high_sar"]) > 0
    expected = dead_action.get("expected_recovery_sar")
    if expected is not None:
        assert 0 < float(expected) <= float(dead_action["recoverable_value_high_sar"])

    # --- simulated execution of the dead-stock discount ---------------------
    from app.services.execution_engine import execute_from_request

    job = await execute_from_request(
        db_session,
        business_id=bid,
        action_type="discount",
        entity_type="item",
        entity_id=ids["dead"],
        payload={
            "reason": "dead_stock",
            "simulated": True,
            "recoverable_value_low_sar": float(dead_action["recoverable_value_low_sar"]),
            "recoverable_value_high_sar": float(dead_action["recoverable_value_high_sar"]),
            "expected_recovery_sar": float(expected) if expected is not None else None,
        },
    )
    await db_session.commit()
    assert job.result["simulated"] is True
    assert job.status == "completed", f"job status {job.status}"

    # item money is untouched by a simulated execution
    item_row = await db_session.get(Item, ids["dead"])
    assert float(item_row.sell_price) == 35.0, "simulation must not reprice the item"
    assert float(item_row.cost_price) == 20.0

    # execution.completed event was emitted
    from sqlalchemy import text

    event_count = (await db_session.execute(
        text("SELECT COUNT(*) FROM events WHERE event_type = 'execution.completed' AND business_id = :b"),
        {"b": str(bid)},
    )).scalar()
    assert event_count >= 1

    # analytics dead-stock SAR must equal the capital at risk for the dead item
    from app.services.analytics_service import calculate_dead_stock_value

    total = await calculate_dead_stock_value(db_session, bid)
    assert float(total) == 40 * 20.0, "dead spice pack = 40 units x SAR 20"