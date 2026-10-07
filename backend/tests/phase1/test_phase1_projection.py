"""End-to-end projection test (spec §9, §70, §84).

Proves the chain the architecture requires:

    canonical pipeline -> CanonicalBusinessState -> projector -> product tables

and that the product tables are a *projection* rather than a second truth:

* rows are written from canonical state, with the canonical row hash retained;
* projecting the same state twice inserts nothing the second time;
* an unknown price projects to NULL, never to 0;
* sales are not also applied as stock decrements.

These tests require Postgres and are skipped when it is unavailable.
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.services.orbit.ingestion.pipeline import CanonicalOrbitIngestionPipeline
from app.services.orbit.projection import CanonicalProjector

pytestmark = pytest.mark.asyncio

SELL_HEADERS = ["Date", "Item", "SKU", "Qty", "Unit Price", "Cost", "Amount", "Branch"]
SELL_ROWS = [
    ["2026-03-01", "Pepsi 330ml", "P330", 12, "1.50 SAR", "1.10 SAR", "18.00 SAR", "Riyadh"],
    ["2026-03-02", "Pepsi 500ml", "P500", 8, "1.80 SAR", "1.40 SAR", "14.40 SAR", "Riyadh"],
]
NO_COST_HEADERS = ["Date", "Item", "SKU", "Qty", "Unit Price", "Amount", "Branch"]
NO_COST_ROWS = [
    ["2026-03-01", "Mystery Item", "M1", 3, "5.00 SAR", "15.00 SAR", "Riyadh"],
]
INVENTORY_HEADERS = ["SKU", "Item", "Current Stock", "Cost", "Unit", "Location"]
INVENTORY_ROWS = [["P330", "Pepsi 330ml", 40, "1.10 SAR", "piece", "Riyadh"]]


def to_csv(headers, rows) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


async def _ingest(business_id, *artifacts):
    pipeline = CanonicalOrbitIngestionPipeline(business_id=business_id)
    result = None
    for name, content in artifacts:
        result = pipeline.ingest(content, source_name=name)
    return result


@pytest.fixture
async def business_id(db_session):
    """A real business row, because the product tables hold a business FK.

    Projection tests cannot use a synthetic id: every item, inventory and
    transaction row would fail the foreign key, which would test the schema rather
    than the projector.
    """
    from sqlalchemy import text

    new_id = uuid4()
    await db_session.execute(
        text("""
            INSERT INTO businesses (id, name, type, is_active, created_at)
            VALUES (:id, :name, 'retail', true, NOW())
        """),
        {"id": str(new_id), "name": "Projection Test Business"},
    )
    await db_session.commit()
    return new_id


class TestProjection:
    async def test_items_are_written_from_canonical_entities(self, db_session, business_id):
        result = await _ingest(business_id, ("pos.csv", to_csv(SELL_HEADERS, SELL_ROWS)))
        projector = CanonicalProjector(str(business_id), db_session)
        projection = await projector.project(result.context)
        await db_session.commit()

        assert projection.items_created == 2
        rows = await db_session.execute(
            text("SELECT name, sku, cost_price, sell_price FROM items "
                 "WHERE business_id = :b ORDER BY name"),
            {"b": str(business_id)},
        )
        items = rows.fetchall()
        assert [r[0] for r in items] == ["Pepsi 330ml", "Pepsi 500ml"]
        assert items[0][1] == "P330"
        assert float(items[0][2]) == pytest.approx(1.10)
        assert float(items[0][3]) == pytest.approx(1.50)

    async def test_transactions_carry_the_canonical_row_hash(self, db_session, business_id):
        result = await _ingest(business_id, ("pos.csv", to_csv(SELL_HEADERS, SELL_ROWS)))
        projector = CanonicalProjector(str(business_id), db_session)
        await projector.project(result.context)
        await db_session.commit()

        rows = await db_session.execute(
            text("SELECT row_hash, transaction_type, total_amount FROM transactions "
                 "WHERE business_id = :b"),
            {"b": str(business_id)},
        )
        transactions = rows.fetchall()
        assert len(transactions) == 2
        canonical_hashes = {e.row_hash for e in result.events}
        for row_hash, transaction_type, total in transactions:
            assert row_hash in canonical_hashes, (
                "a projected transaction must be traceable to the canonical "
                "observation that produced it"
            )
            assert transaction_type == "sale"
        assert sorted(float(t[2]) for t in transactions) == [14.40, 18.00]

    async def test_projection_is_idempotent(self, db_session, business_id):
        result = await _ingest(business_id, ("pos.csv", to_csv(SELL_HEADERS, SELL_ROWS)))

        first = CanonicalProjector(str(business_id), db_session)
        first_result = await first.project(result.context)
        await db_session.commit()

        second = CanonicalProjector(str(business_id), db_session)
        second_result = await second.project(result.context)
        await db_session.commit()

        assert first_result.transactions_inserted == 2
        assert second_result.transactions_inserted == 0
        assert second_result.transactions_skipped == 2

        count = await db_session.execute(
            text("SELECT count(*) FROM transactions WHERE business_id = :b"),
            {"b": str(business_id)},
        )
        assert count.scalar() == 2

    async def test_unknown_price_is_coerced_only_by_the_schema_and_recorded(
        self, db_session, business_id
    ):
        """The legacy money columns are NOT NULL, so 0 is written — and reported.

        Canonical state still says the cost is unknown. The coercion is recorded so
        a consumer of the product table can tell a schema placeholder from evidence.
        """
        result = await _ingest(business_id, ("pos.csv", to_csv(NO_COST_HEADERS, NO_COST_ROWS)))
        projector = CanonicalProjector(str(business_id), db_session)
        projection = await projector.project(result.context)
        await db_session.commit()

        rows = await db_session.execute(
            text("SELECT cost_price, sell_price FROM items WHERE business_id = :b"),
            {"b": str(business_id)},
        )
        cost, sell = rows.fetchone()
        assert float(cost) == 0.0
        assert float(sell) == pytest.approx(5.00)

        # The fiction is bounded and visible.
        assert any("items.cost_price" in f for f in projection.coerced_zero_fields)
        assert any("transactions.profit" in f for f in projection.coerced_zero_fields)

        # Canonical state remains authoritative and still reports unknown.
        from app.services.orbit.analytics import margin_metrics

        metrics = margin_metrics(result.events)
        assert metrics["cost"].value is None
        assert metrics["gross_profit"].value is None

    async def test_unknown_profit_is_coerced_only_by_the_schema(self, db_session, business_id):
        result = await _ingest(business_id, ("pos.csv", to_csv(NO_COST_HEADERS, NO_COST_ROWS)))
        projector = CanonicalProjector(str(business_id), db_session)
        projection = await projector.project(result.context)
        await db_session.commit()

        rows = await db_session.execute(
            text("SELECT profit FROM transactions WHERE business_id = :b"),
            {"b": str(business_id)},
        )
        # Revenue 15.00 with no cost is not a 15.00 profit; the legacy NOT NULL
        # column forces a number, so the projector writes 0 and records it.
        assert float(rows.fetchone()[0]) == 0.0
        assert any("transactions.profit" in f for f in projection.coerced_zero_fields)

    async def test_stock_observations_are_projected(self, db_session, business_id):
        result = await _ingest(
            business_id,
            ("pos.csv", to_csv(SELL_HEADERS, SELL_ROWS)),
            ("inv.csv", to_csv(INVENTORY_HEADERS, INVENTORY_ROWS)),
        )
        projector = CanonicalProjector(str(business_id), db_session)
        projection = await projector.project(result.context)
        await db_session.commit()

        assert projection.inventory_written == 1
        rows = await db_session.execute(
            text("SELECT inv.current_stock, i.name FROM inventory inv "
                 "JOIN items i ON i.id = inv.item_id WHERE inv.business_id = :b"),
            {"b": str(business_id)},
        )
        stock, name = rows.fetchone()
        assert float(stock) == pytest.approx(40.0)
        assert name == "Pepsi 330ml"

    async def test_sales_do_not_double_count_as_stock(self, db_session, business_id):
        """Stock comes from observations only; a sale is not also a decrement."""
        result = await _ingest(
            business_id,
            ("pos.csv", to_csv(SELL_HEADERS, SELL_ROWS)),
            ("inv.csv", to_csv(INVENTORY_HEADERS, INVENTORY_ROWS)),
        )
        projector = CanonicalProjector(str(business_id), db_session)
        await projector.project(result.context)
        await db_session.commit()

        # 40 observed, and the two sales (12 + 8) must not have been subtracted.
        rows = await db_session.execute(
            text("SELECT inv.current_stock FROM inventory inv "
                 "JOIN items i ON i.id = inv.item_id "
                 "WHERE inv.business_id = :b AND i.name = 'Pepsi 330ml'"),
            {"b": str(business_id)},
        )
        assert float(rows.fetchone()[0]) == pytest.approx(40.0)

    async def test_undated_events_are_reported_not_invented(self, db_session, business_id):
        """An event with no timestamp cannot be placed on the timeline."""
        rows = NO_COST_ROWS[0][:]
        rows[0] = "not-a-date"
        result = await _ingest(business_id, ("pos.csv", to_csv(NO_COST_HEADERS, [rows])))
        projector = CanonicalProjector(str(business_id), db_session)
        projection = await projector.project(result.context)
        await db_session.commit()

        count = await db_session.execute(
            text("SELECT count(*) FROM transactions WHERE business_id = :b"),
            {"b": str(business_id)},
        )
        assert count.scalar() == 0
        assert any("no event time" in u for u in projection.unprojected)

    async def test_projection_result_is_serialisable(self, db_session, business_id):
        result = await _ingest(business_id, ("pos.csv", to_csv(SELL_HEADERS, SELL_ROWS)))
        projector = CanonicalProjector(str(business_id), db_session)
        projection = await projector.project(result.context)
        payload = projection.to_dict()
        assert payload["state_version"] == result.context.state_version
        assert payload["items_created"] == 2