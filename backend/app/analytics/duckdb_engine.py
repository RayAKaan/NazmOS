"""Scoped in-memory DuckDB analytical engine (Phase 1).

Lifecycle and safety contract
-----------------------------
- One engine per analytical computation; the connection is created inside the
  ``async with`` block and **always** closed on exit (fail-closed). No shared
  or cached connections exist, so a request can never observe another
  tenant's data.
- The engine never talks to the database directly. The caller's RLS-scoped
  SQLAlchemy session streams the canonical analytical dataset (active + all
  inventory rows it owns, plus the sales rows it owns) into DuckDB, already
  filtered by ``business_id``. DuckDB therefore only ever sees
  pre-authorized rows (``tenant_scoped`` is part of the provenance).
- DuckDB computes **raw aggregates only**: sums over the loaded window,
  distinct observed sale days, latest sale timestamp. Velocity, valuation
  basis, classification and recommendations are NazmOS-owned and live in
  ``app.analytics.metrics``; nothing here encodes business policy.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping

import duckdb
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.contracts import AnalyticalProvenance, ScopedEngineError
from app.utils.clock import utcnow

DEFAULT_WINDOW_DAYS = 30

# Canonical analytical dataset, tenant-scoped at load time. ``is_active`` is
# retained so each consumer decides exactly as it did before (health scores
# previously included inactive items while listings excluded them).
# CAST(business_id AS TEXT) keeps the engine database-agnostic: Postgres
# refuses ``uuid = character varying`` without an explicit cast.
_INVENTORY_LOAD_SQL = """
SELECT
    i.id                 AS item_id,
    i.name               AS name,
    i.sku                AS sku,
    c.name               AS category_name,
    i.unit               AS unit,
    inv.current_stock    AS current_stock,
    i.cost_price         AS cost_price,
    i.sell_price         AS sell_price,
    inv.reorder_level    AS reorder_level,
    inv.last_restocked   AS last_restocked,
    COALESCE(i.is_active, FALSE) AS is_active
FROM inventory inv
JOIN items i ON i.id = inv.item_id
LEFT JOIN categories c ON c.id = i.category_id
WHERE CAST(inv.business_id AS TEXT) = :bid
"""

_SALES_LOAD_SQL = """
SELECT item_id, location_id, transaction_at, quantity AS qty
FROM transactions
WHERE CAST(business_id AS TEXT) = :bid
"""
_SALES_WINDOW_SQL = _SALES_LOAD_SQL + " AND transaction_at >= :since"

_FACTS_JOIN_SQL = """
SELECT
    i.item_id            AS item_id,
    i.name               AS name,
    i.sku                AS sku,
    i.category_name      AS category_name,
    i.unit               AS unit,
    i.current_stock      AS current_stock,
    i.cost_price         AS cost_price,
    i.sell_price         AS sell_price,
    i.reorder_level      AS reorder_level,
    i.last_restocked     AS last_restocked,
    COALESCE(i.is_active, FALSE) AS is_active,
    COALESCE(f.qty_30d, 0)         AS qty_30d,
    COALESCE(f.qty_7d, 0)          AS qty_7d,
    COALESCE(f.qty_prev7d, 0)      AS qty_prev7d,
    COALESCE(f.coverage_days_30d, 0) AS coverage_days_30d,
    f.last_sold_at       AS last_sold_at
FROM inventory_facts i
LEFT JOIN item_facts f ON f.item_id = i.item_id
"""


def _clean(value: Any) -> Any:
    """Normalize engine-returned scalar (NaN / Timestamp) to Python types."""
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, float) and value != value:  # NaN
        return None
    return value


def _clean_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _clean(row[key]) for key in row}


class ScopedAnalyticalEngine:
    """Async context manager that streams tenant rows into an in-memory DuckDB."""

    def __init__(
        self,
        db: AsyncSession,
        business_id: Any,
        *,
        window_days: int | None = DEFAULT_WINDOW_DAYS,
        anchor: datetime | None = None,
    ):
        self._db = db
        self.business_id = str(business_id)
        self.window_days = window_days
        self.anchor = anchor or utcnow()
        self._con: duckdb.DuckDBPyConnection | None = None
        self.provenance: AnalyticalProvenance | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def __aenter__(self) -> "ScopedAnalyticalEngine":
        self._con = duckdb.connect()  # in-memory; nothing is persisted
        try:
            await self._load()
            await asyncio.to_thread(self._build_facts)
        except Exception as exc:  # fail-closed: never leave a live handle
            self._close()
            raise ScopedEngineError("DuckDB analytical engine failed to build") from exc
        return self

    async def __aexit__(self, *exc_info: Any) -> bool:
        self._close()
        return False

    def _close(self) -> None:
        if self._con is not None:
            try:
                self._con.close()
            finally:
                self._con = None

    # ------------------------------------------------------------------ #
    # Load (canonical analytical data, tenant-scoped, via caller's session)
    # ------------------------------------------------------------------ #
    async def _load(self) -> None:
        inventory_rows = (
            await self._db.execute(
                text(_INVENTORY_LOAD_SQL).bindparams(bid=self.business_id)
            )
        ).mappings().all()

        if self.window_days is None:
            sales_sql = text(_SALES_LOAD_SQL)
            sales_params: dict[str, Any] = {"bid": self.business_id}
        else:
            sales_sql = text(_SALES_WINDOW_SQL)
            sales_params = {
                "bid": self.business_id,
                "since": self.anchor - timedelta(days=self.window_days),
            }
        sales_rows = (await self._db.execute(sales_sql, sales_params)).mappings().all()

        self._load_frames([dict(r) for r in inventory_rows], [dict(r) for r in sales_rows])

    def _load_frames(
        self, inventory_rows: list[dict[str, Any]], sales_rows: list[dict[str, Any]]
    ) -> None:
        assert self._con is not None
        inv_df = pd.DataFrame(inventory_rows, columns=[
            "item_id", "name", "sku", "category_name", "unit", "current_stock",
            "cost_price", "sell_price", "reorder_level", "last_restocked", "is_active",
        ])
        sales_df = pd.DataFrame(sales_rows, columns=[
            "item_id", "location_id", "transaction_at", "qty",
        ])
        # The engine may receive timestamps as driver strings (SQLite text()).
        # Normalize to pandas datetimes / text ids so DuckDB sees TIMESTAMP and
        # both frames join on the same VARCHAR key.
        inv_df["item_id"] = inv_df["item_id"].astype(str)
        sales_df["item_id"] = sales_df["item_id"].astype(str)
        inv_df["last_restocked"] = pd.to_datetime(inv_df["last_restocked"], errors="coerce")
        sales_df["transaction_at"] = pd.to_datetime(sales_df["transaction_at"], errors="coerce")
        self._con.register("inv_raw", inv_df)
        self._con.register("sales_raw", sales_df)

    # ------------------------------------------------------------------ #
    # Raw aggregation (DuckDB executes; no business semantics)
    # ------------------------------------------------------------------ #
    def _build_facts(self) -> None:
        assert self._con is not None
        self._con.execute(
            "CREATE OR REPLACE TABLE inventory_facts AS SELECT * FROM inv_raw"
        )
        self._con.execute(
            "CREATE OR REPLACE TABLE sales_facts AS SELECT "
            "item_id, transaction_at AS tx_at, "
            "CAST(transaction_at AS DATE) AS sold_on, "
            "COALESCE(qty, 0) AS qty "
            "FROM sales_raw"
        )
        seven = self.anchor - timedelta(days=7)
        fourteen = self.anchor - timedelta(days=14)
        self._con.execute(
            """
            CREATE OR REPLACE TABLE item_facts AS
            SELECT
                item_id,
                COALESCE(SUM(qty), 0)                AS qty_30d,
                COALESCE(SUM(CASE WHEN tx_at >= CAST(? AS TIMESTAMP) THEN qty ELSE 0 END), 0) AS qty_7d,
                COALESCE(SUM(CASE WHEN tx_at >= CAST(? AS TIMESTAMP) AND tx_at < CAST(? AS TIMESTAMP)
                                  THEN qty ELSE 0 END), 0) AS qty_prev7d,
                COUNT(DISTINCT sold_on)              AS coverage_days_30d,
                MAX(tx_at)                           AS last_sold_at
            FROM sales_facts
            GROUP BY item_id
            """,
            [seven, fourteen, seven],
        )
        observed = self._con.execute(
            "SELECT COUNT(DISTINCT sold_on) FROM sales_facts"
        ).fetchone()[0]
        self.provenance = AnalyticalProvenance(
            business_id=self.business_id,
            window_days=self.window_days if self.window_days is not None else 0,
            observed_days=int(observed or 0),
            loaded_inventory_rows=int(self._con.execute(
                "SELECT COUNT(*) FROM inventory_facts").fetchone()[0]
            ),
            loaded_sales_rows=int(self._con.execute(
                "SELECT COUNT(*) FROM sales_facts").fetchone()[0]
            ),
            anchor=self.anchor,
            tenant_scoped=True,
        )

    # ------------------------------------------------------------------ #
    # Results
    # ------------------------------------------------------------------ #
    def inventory_facts_rows(self) -> list[dict[str, Any]]:
        """Joined per-item raw facts (inventory x window aggregates)."""
        assert self._con is not None
        rows = self._con.execute(_FACTS_JOIN_SQL).fetchall()
        result = []
        for row in rows:
            mapping = self._con.description
            result.append(_clean_row(dict(zip([c[0] for c in mapping], row))))
        return result

    def item_sales_series(self, item_id: Any) -> list[dict[str, Any]]:
        """Daily sales totals for one item (date, qty) from the engine window."""
        assert self._con is not None
        rows = self._con.execute(
            """
            SELECT CAST(sold_on AS VARCHAR) AS date, CAST(SUM(qty) AS DOUBLE) AS qty
            FROM sales_facts
            WHERE item_id = ?
            GROUP BY sold_on
            ORDER BY sold_on
            """,
            [str(item_id)],
        ).fetchall()
        return [{"date": r[0], "qty": r[1]} for r in rows]

    def raw_query(self, sql: str, params: Iterable[Any] | None = None) -> list[dict[str, Any]]:
        """Exposed for analytical consumers that need a richer DuckDB query.

        Callers must keep queries free of business policy; semantics belong to
        the NazmOS layer. The connection is snapshot-only (read queries).
        """
        assert self._con is not None
        rows = self._con.execute(sql, list(params) if params else None).fetchall()
        mapping = self._con.description
        return [_clean_row(dict(zip([c[0] for c in mapping], row))) for row in rows]

    def close(self) -> None:
        self._close()