"""POS pull-sync dedup regression tests.

The legacy pull-sync dedup tested ``transaction_at >= record.date``: any sale
whose date was NOT later than the earliest already-fetched transaction of the
day was silently dropped -- e.g. a merchant back-entering an order dated
yesterday while today's orders were already synced lost the row forever, and a
distinct same-day sale that landed earlier in the day was never imported.

The fix dedups on exact business facts (item, day, quantity, total) instead, so
re-syncs of identical rows stay suppressed but genuinely new rows -- including
backdated ones -- are ingested.
"""
import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from app.database.models import Item, POSConnection, Transaction

pytestmark = pytest.mark.asyncio


def _record(item_id, day, quantity, total):
    return {
        "item_id": item_id,
        "date": f"2026-08-{day:02d}T10:00:00",
        "quantity": quantity,
        "unit_price": 5.0,
        "cost_price": 3.0,
        "total": total,
        "profit": total - quantity * 3.0,
        "item_name": "Cola 330ml",
        "sku": "COLA",
    }


class _FakeAdapter:
    def __init__(self, credentials, source):
        self.credentials = credentials
        self.source = source

    async def fetch_sales(self, date_from=None, date_to=None):
        return list(self.source)

    async def fetch_inventory(self):
        return []


class _FakeAdapterFactory:
    def __init__(self, source):
        self._source = source

    def __call__(self, adapter_type):
        src = self._source

        class _BoundAdapter(_FakeAdapter):
            def __init__(self, credentials):
                _FakeAdapter.__init__(self, credentials, src)
        return _BoundAdapter


async def test_pull_sync_dedupes_exact_rows_but_keeps_backdated_and_distinct_sales(
    authenticated_client: dict, db_session, monkeypatch
):
    ctx = authenticated_client
    business_id = ctx["business_id"]

    item = Item(
        business_id=business_id,
        name="Cola 330ml",
        sku="COLA",
        cost_price=3.0,
        sell_price=5.0,
    )
    db_session.add(item)
    await db_session.flush()

    connection = POSConnection(
        business_id=business_id,
        adapter_type="fake_pos",
        connection_name="Fake POS",
        credentials_encrypted=b"test-creds",
        is_active=True,
        sync_sales=True,
        sync_inventory=False,
    )
    db_session.add(connection)
    await db_session.commit()
    connection_id = str(connection.id)

    source = [
        _record(item.id, 1, 2, 10.0),
        _record(item.id, 2, 1, 5.0),
    ]

    monkeypatch.setattr(
        "app.tasks.pos_sync_tasks.POSCredentialManager",
        lambda: type(
            "FakeVault",
            (),
            {"decrypt_credentials": lambda self, encrypted_bytes: {"credentials": {}, "adapter_type": "fake_pos"}},
        )(),
    )
    monkeypatch.setattr(
        "app.tasks.pos_sync_tasks.get_adapter",
        _FakeAdapterFactory(source),
    )

    from app.tasks.pos_sync_tasks import run_sync_pos_connection

    async def _sync():
        return await asyncio.to_thread(run_sync_pos_connection, connection_id, str(business_id))

    async def _transaction_count():
        result = await db_session.execute(
            select(func.count(Transaction.id)).where(Transaction.business_id == business_id)
        )
        return result.scalar_one()

    # --- first sync: two brand-new rows import -------------------------------
    first = await _sync()
    assert first["success"] is True, first
    assert first["records_processed"] == 2
    assert await _transaction_count() == 2

    # --- identical re-sync: both are exact duplicates -> nothing imported ----
    second = await _sync()
    assert second["success"] is True, second
    assert second["records_processed"] == 0
    assert await _transaction_count() == 2

    # --- add a backdated order (day 0) + a distinct same-day sale + a copy ---
    # The backdated order predates every existing transaction; the legacy
    # `transaction_at >=` heuristic would have silently dropped it because an
    # existing row was dated >= day 0.
    source.append(_record(item.id, 0, 5, 25.0))       # backdated, must import
    source.append(_record(item.id, 2, 3, 15.0))       # distinct same-day, must import
    source.append(_record(item.id, 2, 1, 5.0))        # exact copy of day-2 row, skip
    third = await _sync()
    assert third["success"] is True, third
    assert third["records_processed"] == 2
    assert await _transaction_count() == 4

    fetched = await db_session.execute(
        select(Transaction.quantity, Transaction.total_amount)
        .where(Transaction.business_id == business_id)
        .order_by(Transaction.quantity)
    )
    facts = {(float(q), float(t)) for q, t in fetched.all()}
    assert (1.0, 5.0) in facts   # original day-2 row (still exactly one)
    assert (2.0, 10.0) in facts  # day-1 row
    assert (5.0, 25.0) in facts  # backdated day-0 row present (the fix)
    assert (3.0, 15.0) in facts  # distinct same-day row present

    # No duplicates: exactly one (qty=1, total=5) despite the re-sync + copy.
    dup = await db_session.execute(
        select(func.count(Transaction.id)).where(
            Transaction.business_id == business_id,
            Transaction.quantity == 1,
            Transaction.total_amount == 5.0,
        )
    )
    assert dup.scalar_one() == 1