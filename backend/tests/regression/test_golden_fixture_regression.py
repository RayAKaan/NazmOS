"""Golden CSV regression harness (Item 5).

Root-cause regression suite for the canonical financial chain:

    canonical (45 rows)  ->  45 positions  ->  3 locations  ->  SAR 28,892
    sales (91 rows)      ->  6 distinct days -> velocity over 6 observed days

and the same chain against the merchant-provided real fixtures:

    inventory (100 rows) -> 100 positions -> 5 locations -> SAR 72,363.60
    sales (500 rows)     -> 50 distinct days

The historical bug this guards against: a report pipeline that collapsed the
(SKU x location) grain to a single location and projected a "total" inventory
value that was only a Dammam-only subset (SAR 17,366) while claiming to be the
business-wide value (SAR 28,892).  The golden fixtures are built so those two
numbers differ, so any regression to location-collapse is structurally caught.

Two layers:
  * ``TestFileContracts`` + ``TestSchemaMapping``      - DB-free.
  * ``TestETLIntegration``                             - needs a migrated Postgres
    test DB (skipped automatically otherwise), mirrors the Celery/RLS session
    pattern used by ``app.tasks.ingestion_tasks.run_process_upload``.
"""
import os
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from app.database.connection import sync_rls_tenant_context
from app.database import connection as connection_mod

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_test",
)

REGRESSION_DIR = Path(__file__).resolve().parents[1] / "regression_data"

REAL_SALES = REGRESSION_DIR / "Test-NazmOS-Sales.csv"
REAL_INV = REGRESSION_DIR / "Test-NazmOS-Inventory.csv"
CANON_SALES = REGRESSION_DIR / "Test-NazmOS-Canonical-Sales.csv"
CANON_INV = REGRESSION_DIR / "Test-NazmOS-Canonical-Inventory.csv"

# The exact column mapping a merchant/upload-confirm screen would produce for
# these fixtures.  This is the production path: `column_mapping` is confirmed
# before any ETL runs, and SchemaDetector is only the pre-fill.
SALES_COLUMN_MAPPING = {
    "transaction_date": "transaction_at",
    "transaction_id": "source_transaction_id",
    "sku": "item_sku",
    "product_name": "item_name",
    "branch": "location_name",
    "transaction_type": "transaction_type",
    "quantity": "quantity",
    "unit_price_sar": "unit_price",
    "unit_cost_sar": "cost_price",
}
INV_COLUMN_MAPPING = {
    "sku": "item_sku",
    "product_name": "item_name",
    "warehouse": "location_name",
    "quantity_on_hand": "current_stock",
    "reorder_point": "reorder_level",
    "unit_cost_sar": "cost_price",
}

# Acceptance facts extracted from the fixture files themselves.
REAL_SALES_FACTS = {"rows": 500, "days": 50, "skus": 18, "locations": 5}
REAL_INV_FACTS = {"rows": 100, "skus": 20, "locations": 5, "value": Decimal("72363.60")}
REAL_INV_PER_LOCATION = {
    "Riyadh Main": Decimal("15326.10"),
    "Jeddah Branch": Decimal("11993.50"),
    "Dammam Branch": Decimal("22591.15"),
    "Madinah Branch": Decimal("8098.20"),
    "Khobar Branch": Decimal("14354.65"),
}
CANON_SALES_FACTS = {"rows": 91, "days": 6}
CANON_INV_FACTS = {"rows": 45, "skus": 15, "locations": 3,
                   "value": Decimal("28892.00"), "dammam_only": Decimal("17366.00")}

SALES_TEMPLATE_COLUMNS = [
    "business_id", "transaction_id", "transaction_date", "sku", "product_name",
    "branch", "transaction_type", "quantity", "unit_price_sar", "unit_cost_sar",
]
INV_TEMPLATE_COLUMNS = [
    "business_id", "sku", "product_name", "location_id", "warehouse", "city",
    "quantity_on_hand", "unit_cost_sar", "reorder_point", "active",
]


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _value2d(value) -> Decimal:
    return Decimal(str(round(float(value), 2))).quantize(Decimal("0.01"))


@pytest.fixture(scope="module")
def migrated_db():
    """Ensure the test DB is migrated to head (mirrors the Celery RLS suite)."""
    if connection_mod._is_sqlite:
        pytest.skip("Golden ETL integration requires PostgreSQL")
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    env = os.environ.copy()
    env["DATABASE_URL"] = TEST_DATABASE_URL
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Alembic upgrade failed:\n{result.stdout}\n{result.stderr}")
    yield


class TestFileContracts:
    """DB-free assertions over the golden CSV files as-delivered."""

    def test_real_sales_file_contract(self):
        df = _read(REAL_SALES)
        assert list(df.columns) == SALES_TEMPLATE_COLUMNS
        assert len(df) == REAL_SALES_FACTS["rows"]
        assert df["transaction_date"].nunique() == REAL_SALES_FACTS["days"]
        assert df["sku"].nunique() == REAL_SALES_FACTS["skus"]
        assert df["branch"].nunique() == REAL_SALES_FACTS["locations"]
        assert set(df["transaction_type"].unique()) <= {"SALE", "RETURN"}

    def test_real_inventory_file_contract(self):
        df = _read(REAL_INV)
        assert list(df.columns) == INV_TEMPLATE_COLUMNS
        assert len(df) == REAL_INV_FACTS["rows"]
        assert df["sku"].nunique() == REAL_INV_FACTS["skus"]
        assert df["location_id"].nunique() == REAL_INV_FACTS["locations"]
        value = Decimal(str(round(float(
            (df["quantity_on_hand"].fillna(0) * df["unit_cost_sar"].fillna(0)).sum()
        ), 2)))
        assert value == REAL_INV_FACTS["value"]

    def test_real_inventory_location_grain_never_collapses(self):
        """Real inventory must retain the (sku x location) grain (100 positions)."""
        df = _read(REAL_INV)
        grain = df.groupby(["sku", "location_id"]).ngroups
        assert grain == REAL_INV_FACTS["rows"], f"SKU x location grain collapsed: {grain}"

    def test_canonical_inventory_acceptance_numbers(self):
        df = _read(CANON_INV)
        assert len(df) == CANON_INV_FACTS["rows"]
        assert df["sku"].nunique() == CANON_INV_FACTS["skus"]
        assert df["location_id"].nunique() == CANON_INV_FACTS["locations"]
        # 45 rows MUST map to exactly 45 positions (no SKU-modal collapse).
        assert df.groupby(["sku", "location_id"]).ngroups == CANON_INV_FACTS["rows"]
        # Whole-business value from the raw file.
        total = Decimal(str(round(float(
            (df["quantity_on_hand"] * df["unit_cost_sar"]).sum()
        ), 2)))
        assert total == CANON_INV_FACTS["value"], f"canonical total drifted: {total}"
        # Dammam-only subset must DIFFER -- this is the bug-structure contract.
        dammam = Decimal(str(round(float(
            (df.loc[df["location_id"] == "LOC-DMM", "quantity_on_hand"]
             * df.loc[df["location_id"] == "LOC-DMM", "unit_cost_sar"]).sum()
        ), 2)))
        assert dammam == CANON_INV_FACTS["dammam_only"], f"dammam-only drifted: {dammam}"
        assert total != dammam

    def test_canonical_sales_shape(self):
        df = _read(CANON_SALES)
        assert list(df.columns) == SALES_TEMPLATE_COLUMNS
        assert len(df) == CANON_SALES_FACTS["rows"]
        days = sorted(df["transaction_date"].unique())
        assert len(days) == CANON_SALES_FACTS["days"]
        assert days == [f"2026-08-{4 + i:02d}" for i in range(6)]

    def test_distinct_days_never_multiplicated(self):
        """6 observed days must remain 6 -- regression for '6-as-30' bugs."""
        df = _read(CANON_SALES)
        assert df["transaction_date"].nunique() == 6


class TestSchemaMapping:
    """Confirmed-mapping path (production) must map clean for the fixtures."""

    def test_explicit_mappings_cover_every_etl_column(self):
        for mapping, template in (
            (SALES_COLUMN_MAPPING, {"transaction_at", "item_name", "item_sku",
                                    "location_name", "quantity", "unit_price",
                                    "cost_price", "transaction_type", "source_transaction_id"}),
            (INV_COLUMN_MAPPING, {"item_name", "item_sku", "location_name",
                                  "current_stock", "reorder_level", "cost_price"}),
        ):
            assert template <= set(mapping.values())

    def test_normalize_strict_path_accepts_all_fixtures(self):
        from app.services.data_normalizer import normalize_dataframe
        for path, mapping in (
            (REAL_SALES, SALES_COLUMN_MAPPING),
            (REAL_INV, INV_COLUMN_MAPPING),
            (CANON_SALES, SALES_COLUMN_MAPPING),
            (CANON_INV, INV_COLUMN_MAPPING),
        ):
            df = _read(path)
            norm = normalize_dataframe(df, mapping, strict=True)
            report = norm.attrs["data_quality_report"]
            assert len(norm) == len(df), (
                f"{path.name}: normalization dropped rows {report}"
            )

    def test_baseline_series_from_6_observed_days_never_uses_30(self):
        """Velocity must be computed over the 6 OBSERVED days (Item 8 root cause)."""
        from datetime import date, timedelta
        from app.services.forecasting.baseline_provider import baseline_from_series
        from app.services.forecasting.schemas import DailyDemandPoint, DailyDemandSeries

        start = date(2026, 8, 4)
        y = [10.0, 12.0, 8.0, 15.0, 11.0, 9.0]
        points = [DailyDemandPoint(ds=start + timedelta(days=i), y=v) for i, v in enumerate(y)]
        series = DailyDemandSeries(
            business_id=str(uuid.uuid4()), item_id=str(uuid.uuid4()),
            points=points, timezone="Asia/Riyadh",
            date_range_days=len(points), observation_count=len(points),
            nonzero_days=sum(1 for p in points if p.y > 0),
            total_demand=round(sum(v for _, v in [(i, p.y) for i, p in enumerate(points)]), 4),
        )
        result = baseline_from_series(series, horizon_days=30)
        assert result.context_days == 6
        assert len(result.predictions) == 30
        # Base level must be mean of the 6 observed days, NOT total/30.
        mean6 = sum(y) / 6
        assert round(result.predictions[0].predicted_qty, 2) == round(mean6, 2)
        assert result.predictions[0].predicted_qty != round(sum(y) / 30, 2)


@pytest.mark.skipif(connection_mod._is_sqlite, reason="Needs PostgreSQL RLS")
class TestETLIntegration:
    """End-to-end ETL through the real pipeline into a migrated Postgres test DB."""

    @pytest.fixture(autouse=True)
    def _unique_business(self, migrated_db):
        with sync_rls_tenant_context(None):
            from sqlalchemy.orm import Session
            session = Session(connection_mod._get_sync_engine())
            try:
                from sqlalchemy import text
                self.business_id = str(uuid.uuid4())
                session.execute(
                    text(
                        "INSERT INTO businesses (id, name, type, currency, is_active) "
                        "VALUES (:id, :name, 'retail', 'SAR', true)"
                    ),
                    {"id": self.business_id, "name": "NazmOS Regression Biz"},
                )
                session.commit()
            finally:
                session.close()
        yield

    def _run_etl(self, df: pd.DataFrame, column_mapping: dict):
        import asyncio
        from contextlib import asynccontextmanager
        import pandas as pd
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

        from app.services.etl_pipeline import ETLPipeline

        _engine = create_async_engine(TEST_DATABASE_URL)
        _sf = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

        @asynccontextmanager
        async def _scope():
            async with _sf() as session:
                await connection_mod._set_rls_context(session)
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise
                finally:
                    await session.close()

        async def _run():
            pipeline = ETLPipeline(None, self.business_id, df, column_mapping)
            return await pipeline.run(session_factory=_scope)

        try:
            result = asyncio.run(_run())
        finally:
            asyncio.run(_engine.dispose())
        return result

    def _query(self, sql: str, params: dict | None = None):
        from sqlalchemy.orm import Session
        session = Session(connection_mod._get_sync_engine())
        try:
            from sqlalchemy import text
            return session.execute(text(sql), params or {}).fetchall()
        finally:
            session.close()

    def _run_inventory_etl(self, path: Path):
        df = _read(path)
        return self._run_etl(df, INV_COLUMN_MAPPING)

    def _run_sales_etl(self, path: Path):
        df = _read(path)
        return self._run_etl(df, SALES_COLUMN_MAPPING)

    def test_canonical_inventory_45_3_28892(self):
        stats = self._run_inventory_etl(CANON_INV)
        rows = self._query(
            """
            SELECT l.name AS loc, SUM(i.current_stock * it.cost_price)::numeric AS val
            FROM inventory i
            JOIN items it ON it.id = i.item_id AND it.business_id = i.business_id
            LEFT JOIN locations l ON l.id = i.location_id
            WHERE i.business_id = :bid
            GROUP BY l.name
            """,
            {"bid": self.business_id},
        )
        total = Decimal(str(round(sum(float(r[1]) for r in rows), 2)))
        per_loc = {r[0]: Decimal(str(round(float(r[1]), 2))) for r in rows}
        assert total == CANON_INV_FACTS["value"], f"canonical ETL value: {total}"
        assert len(rows) == CANON_INV_FACTS["locations"]
        assert "Dammam Branch" in per_loc
        assert per_loc["Dammam Branch"] == CANON_INV_FACTS["dammam_only"]

    def test_real_inventory_100_5_72363(self):
        self._run_inventory_etl(REAL_INV)
        rows = self._query(
            """
            SELECT COUNT(*), COUNT(DISTINCT i.location_id)
            FROM inventory i
            WHERE i.business_id = :bid
            """,
            {"bid": self.business_id},
        )
        assert rows[0][0] == REAL_INV_FACTS["rows"]
        assert rows[0][1] == REAL_INV_FACTS["locations"]

    def test_canonical_sales_91_rows_6_days(self):
        self._run_sales_etl(CANON_SALES)
        rows = self._query(
            """
            SELECT COUNT(*), COUNT(DISTINCT DATE(transaction_at))
            FROM transactions WHERE business_id = :bid
            """,
            {"bid": self.business_id},
        )
        # 91 rows ingested; 6 distinct days preserved.
        assert rows[0][0] == CANON_SALES_FACTS["rows"], rows
        assert rows[0][1] == CANON_SALES_FACTS["days"], rows

    def test_real_sales_500_rows_50_days(self):
        self._run_sales_etl(REAL_SALES)
        rows = self._query(
            """
            SELECT COUNT(*), COUNT(DISTINCT DATE(transaction_at)),
                   COUNT(DISTINCT location_id)
            FROM transactions WHERE business_id = :bid
            """,
            {"bid": self.business_id},
        )
        assert rows[0][0] == REAL_SALES_FACTS["rows"], rows
        assert rows[0][1] == REAL_SALES_FACTS["days"], rows
        assert rows[0][2] == REAL_SALES_FACTS["locations"], rows

    def test_location_collapse_is_impossible_in_db(self):
        """DB view of canonical value must be 28,892, not the 17,366 subset."""
        stats = self._run_inventory_etl(CANON_INV)
        rows = self._query(
            """
            SELECT COALESCE(SUM(i.current_stock * it.cost_price), 0)::numeric
            FROM inventory i
            JOIN items it ON it.id = i.item_id AND it.business_id = i.business_id
            WHERE i.business_id = :bid
            """,
            {"bid": self.business_id},
        )
        total = Decimal(str(round(float(rows[0][0]), 2)))
        assert total == CANON_INV_FACTS["value"]
        assert total != CANON_INV_FACTS["dammam_only"]

    def test_missing_location_ingest_fails_closed_on_grain_collapse(self):
        """G-dimension: an inventory file with NO location column whose rows
        duplicate an item must be REFUSED -- not silently collapsed to a single
        site.  Last-write-wins under a NULL-location index is precisely the bug
        that turned business-wide SAR 28,892 into a Dammam-only SAR 17,366."""
        df = _read(CANON_INV).drop(columns=["location_id", "warehouse", "city"])
        mapping = {k: v for k, v in INV_COLUMN_MAPPING.items() if v != "location_name"}
        with pytest.raises(ValueError, match="grain would collapse"):
            self._run_etl(df, mapping)
        # No inventory rows may exist for a refused ambiguous import.
        rows = self._query(
            "SELECT COUNT(*) FROM inventory WHERE business_id = :bid",
            {"bid": self.business_id},
        )
        assert rows[0][0] == 0
        loc_rows = self._query(
            "SELECT COUNT(*) FROM locations WHERE business_id = :bid",
            {"bid": self.business_id},
        )
        assert loc_rows[0][0] == 0