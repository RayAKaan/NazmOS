"""Tests for ETL transaction dedup (Phase 2.2).

The pipeline computes a deterministic row_hash per sale row and relies on the
partial unique index ``(business_id, row_hash) WHERE row_hash IS NOT NULL`` so
re-importing the same file is idempotent (ON CONFLICT DO NOTHING).  These tests
run against SQLite with the partial index created explicitly to mirror the
PostgreSQL DDL.
"""
import uuid
from datetime import datetime, timezone

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database.models import Base
from app.services.etl_pipeline import ETLPipeline

BUSINESS_ID = str(uuid.uuid4())
ITEM_ID = str(uuid.uuid4())


def _register_now(engine) -> None:
    """Make NOW() available so Postgres-style SQL runs unmodified on SQLite."""
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection, connection_record):
        dbapi_connection.create_function("NOW", 0, lambda: datetime.now(timezone.utc).isoformat())


@pytest.fixture
async def sqlite_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _register_now(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # SQLAlchemy applies postgresql_where only on Postgres; mirror the
        # production partial unique index on SQLite so ON CONFLICT semantics
        # match.  A NULL row_hash stays exempt from uniqueness.
        await conn.execute(
            text("DROP INDEX uq_transactions_row_hash")
        )
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX uq_transactions_row_hash "
                "ON transactions (business_id, row_hash) "
                "WHERE row_hash IS NOT NULL"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO items (id, business_id, name, unit, cost_price, "
                "sell_price, is_active, created_at) "
                "VALUES (:id, :bid, 'Cola', 'piece', 2.0, 3.0, true, :now)"
            ),
            {"id": ITEM_ID, "bid": BUSINESS_ID, "now": datetime.now(timezone.utc)},
        )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


def _df(quantity: float = 2.0) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "item_name": "Cola",
            "transaction_at": datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
            "quantity": quantity,
            "unit_price": 3.0,
            "cost_price": 2.0,
            "total_amount": 6.0,
        }
    ])


def _pipeline(df: pd.DataFrame) -> ETLPipeline:
    pipeline = ETLPipeline()
    pipeline.upload_id = str(uuid.uuid4())
    pipeline.business_id = BUSINESS_ID
    pipeline.df = df
    pipeline.redis = None
    return pipeline


async def test_reimport_is_idempotent(sqlite_session):
    df = _df()
    item_map = {"cola": ITEM_ID}

    first = await _pipeline(df)._bulk_insert_transactions(sqlite_session, item_map)
    assert first["imported"] == 1
    assert first["skipped"] == 0

    second = await _pipeline(df)._bulk_insert_transactions(sqlite_session, item_map)
    assert second["imported"] == 0
    assert second["skipped"] == 1

    count = await sqlite_session.execute(
        text("SELECT COUNT(*) FROM transactions WHERE business_id = :bid"),
        {"bid": BUSINESS_ID},
    )
    assert count.scalar_one() == 1


async def test_changed_quantity_is_new_row(sqlite_session):
    item_map = {"cola": ITEM_ID}

    first = await _pipeline(_df(quantity=2.0))._bulk_insert_transactions(sqlite_session, item_map)
    changed = await _pipeline(_df(quantity=4.0))._bulk_insert_transactions(sqlite_session, item_map)

    assert first["imported"] == 1
    assert changed["imported"] == 1
    assert changed["skipped"] == 0

    count = await sqlite_session.execute(
        text("SELECT COUNT(*) FROM transactions WHERE business_id = :bid"),
        {"bid": BUSINESS_ID},
    )
    assert count.scalar_one() == 2


async def test_row_hash_matches_decision_spec(sqlite_session):
    """Hash covers business_id, item_id, transaction_at, quantity, total_amount."""
    import hashlib
    import json

    df = _df()
    transaction_at = df.iloc[0]["transaction_at"]
    quantity = float(df.iloc[0]["quantity"])
    total_amount = float(df.iloc[0]["total_amount"])

    expected = hashlib.sha256(
        json.dumps({
            "business_id": BUSINESS_ID,
            "item_id": ITEM_ID,
            "transaction_at": str(transaction_at),
            "quantity": quantity,
            "total_amount": total_amount,
        }, sort_keys=True).encode()
    ).hexdigest()

    await _pipeline(df)._bulk_insert_transactions(sqlite_session, {"cola": ITEM_ID})

    row = await sqlite_session.execute(
        text("SELECT row_hash FROM transactions WHERE business_id = :bid"),
        {"bid": BUSINESS_ID},
    )
    assert row.scalar_one() == expected


async def test_null_row_hash_allowed_multiple(sqlite_session):
    """Rows without a hash (legacy/webhook path) are not blocked by the index."""
    from sqlalchemy import text as sa_text

    for i in range(2):
        await sqlite_session.execute(
            sa_text(
                "INSERT INTO transactions "
                "(id, business_id, item_id, quantity, unit_price, cost_price, "
                "total_amount, profit, transaction_type, transaction_at, row_hash) "
                "VALUES (:id, :bid, :iid, 1, 1, 1, 1, 0, 'sale', :now, NULL)"
            ),
            {
                "id": str(uuid.uuid4()),
                "bid": BUSINESS_ID,
                "iid": ITEM_ID,
                "now": datetime.now(timezone.utc),
            },
        )
        await sqlite_session.commit()
