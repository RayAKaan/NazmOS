import asyncio
import hashlib
import json
import uuid as _uuid
from typing import AsyncGenerator
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as aioredis
from pathlib import Path

from app.database.connection import async_session_scope
from app.config import get_settings
from app.services.data_normalizer import normalize_dataframe
from app.services.shariah_compliance import audit_inventory_halal_status

settings = get_settings()


class ETLPipeline:
    VALIDATION = "validation"
    TRANSFORM = "transform"
    LOAD = "load"

    def __init__(self, upload_id: str | None = None, business_id: str | None = None, df: pd.DataFrame | None = None, column_mapping: dict | None = None):
        # Backward-compatible no-arg mode is used by legacy tests/tools.
        # Production ingestion passes all four arguments.
        self.upload_id = upload_id
        self.business_id = business_id
        self.df = normalize_dataframe(df, column_mapping or {}) if df is not None and business_id is not None else df
        self.redis = None
        self.progress_channel = f"etl_progress:{upload_id or 'legacy'}"
        self._stats = {
            "imported": 0,
            "skipped": 0,
            "failed": 0,
            "items_created": 0,
            "items_updated": 0,
            "inventory_updated": 0,
            "date_range": (None, None),
        }


    def get_stages(self) -> list[str]:
        return [self.VALIDATION, self.TRANSFORM, self.LOAD]

    def process(self, df: pd.DataFrame, business_id: str) -> dict:
        """Synchronous legacy API for smoke tests.

        Real imports use the async Celery pipeline. This method validates that
        the DataFrame is processable and returns import-style counters.
        """
        from app.services.data_normalizer import DataNormalizer
        mapping = {
            "product_name": "product_name",
            "item_name": "product_name",
            "sku": "sku",
            "item_sku": "sku",
            "category": "category",
            "category_name": "category",
            "quantity": "quantity",
            "unit_price": "unit_price",
            "price": "unit_price",
            "supplier": "supplier",
        }
        available = {c: mapping[c] for c in df.columns if c in mapping}
        normalized = DataNormalizer().normalize(df, available)
        return {
            "business_id": business_id,
            "rows_processed": int(len(df)),
            "rows_imported": int(len(normalized)),
            "rows_failed": int(max(0, len(df) - len(normalized))),
        }

    async def run(self) -> dict:
        try:
            self.redis = aioredis.from_url(settings.REDIS_URL)
        except:
            self.redis = None

        async with async_session_scope() as session:
            try:
                await self._push_progress("Starting Money Audit import...", 0)

                has_inventory_snapshot = "current_stock" in self.df.columns
                has_sales_history = "transaction_at" in self.df.columns

                item_map = await self._upsert_items(session)
                await self._push_progress(f"Synced {len(item_map)} products", 25)

                await self._ensure_inventory(session, item_map)
                await self._push_progress("Inventory records ready", 35)

                if has_inventory_snapshot:
                    inventory_stats = await self._apply_inventory_snapshot(session, item_map)
                    self._stats.update(inventory_stats)
                    await self._push_progress(
                        f"Updated stock for {inventory_stats['inventory_updated']} products", 55
                    )

                transaction_stats = {"imported": 0, "failed": 0, "date_range": (None, None)}
                if has_sales_history:
                    transaction_stats = await self._bulk_insert_transactions(session, item_map)
                    self._stats.update(transaction_stats)
                    await self._push_progress(
                        f"Imported {transaction_stats['imported']} sales rows", 80
                    )
                else:
                    self._stats["imported"] = self._stats.get("inventory_updated", 0)

                if transaction_stats.get("date_range") and transaction_stats["date_range"][0]:
                    await self._rebuild_summaries(session, transaction_stats["date_range"])
                    await self._push_progress("Rebuilt sales summaries", 90)

                await self._invalidate_forecasts(session, item_map)
                await self._push_progress("Money Audit import complete", 100)

                await session.commit()
                return self._stats

            except Exception as e:
                await session.rollback()
                await self._push_progress(f"Import failed: {str(e)}", -1)
                raise

    async def _push_progress(self, message: str, percent: int):
        if self.redis:
            try:
                await self.redis.publish(
                    self.progress_channel,
                    json.dumps({"message": message, "percent": percent})
                )
            except Exception:
                self.redis = None

        # Always write progress to the DB so polling endpoints can read it.
        if self.upload_id:
            try:
                from app.database.connection import AsyncSessionLocal
                async with AsyncSessionLocal() as session:
                    await session.execute(
                        text("""
                            UPDATE uploaded_files
                            SET row_count_imported = COALESCE(row_count_imported, 0),
                                status = CASE
                                    WHEN :percent = 100 THEN 'completed'
                                    WHEN :percent = -1 THEN 'failed'
                                    ELSE 'processing'
                                END
                            WHERE id = :upload_id
                        """),
                        {"upload_id": self.upload_id, "percent": percent}
                    )
                    await session.commit()
            except Exception:
                pass

    @staticmethod
    def _clean_text(value) -> str | None:
        if pd.isna(value):
            return None
        text_value = str(value).strip()
        if not text_value or text_value.lower() in {"nan", "none", "null"}:
            return None
        return text_value

    @staticmethod
    def _as_float(value, default: float = 0.0) -> float:
        if pd.isna(value):
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    async def _get_or_create_category(self, session: AsyncSession, category_name: str | None) -> str | None:
        category_name = self._clean_text(category_name)
        if not category_name:
            return None

        result = await session.execute(
            text("""
                INSERT INTO categories (id, business_id, name, description, sort_order, is_active, created_at)
                VALUES (:id, :business_id, :name, NULL, 0, true, NOW())
                ON CONFLICT (business_id, name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
            """),
            {"id": str(_uuid.uuid4()), "business_id": self.business_id, "name": category_name},
        )
        row = result.fetchone()
        return str(row[0]) if row else None

    async def _upsert_items(self, session: AsyncSession) -> dict:
        work = self.df.copy()
        optional_columns = [
            "category_name", "item_sku", "barcode", "brand", "pack_size", "storage_type",
            "cost_price", "unit_price", "sell_price",
        ]
        for col in optional_columns:
            if col not in work.columns:
                work[col] = None

        work = work[work["item_name"].notna()].copy()
        work["_item_key"] = work["item_name"].astype(str).str.strip().str.lower()
        unique_items = work.sort_index().groupby("_item_key", as_index=False).first()

        for _, row in unique_items.iterrows():
            item_name = self._clean_text(row.get("item_name"))
            if not item_name:
                continue

            category_id = await self._get_or_create_category(session, row.get("category_name"))
            item_sku = self._clean_text(row.get("item_sku"))
            barcode = self._clean_text(row.get("barcode"))
            brand = self._clean_text(row.get("brand"))
            pack_size = self._clean_text(row.get("pack_size"))
            storage_type = self._clean_text(row.get("storage_type"))
            cost_price = self._as_float(row.get("cost_price"), 0.0)
            sell_price = self._as_float(row.get("sell_price"), 0.0) or self._as_float(row.get("unit_price"), 0.0)

            guardrail_audit = audit_inventory_halal_status([{
                "name": item_name,
                "description": str(row.get("category_name", "")) if pd.notna(row.get("category_name")) else "",
                "sku": item_sku or barcode or "",
            }])
            guardrail_flags = guardrail_audit.get("flagged_violations", [])
            guardrail_status = "flagged_haram" if guardrail_flags else "halal_guard_passed"

            params = {
                "business_id": self.business_id,
                "name": item_name,
                "sku": item_sku,
                "category_id": category_id,
                "cost_price": cost_price,
                "sell_price": sell_price,
                "barcode": barcode,
                "brand": brand,
                "pack_size": pack_size,
                "storage_type": storage_type,
                "shariah_status": guardrail_status,
                "shariah_flags": json.dumps(guardrail_flags),
            }
            existing = await session.execute(
                text("""
                    SELECT id FROM items
                    WHERE business_id = :business_id AND LOWER(name) = LOWER(:name)
                    LIMIT 1
                """),
                params,
            )
            existing_row = existing.fetchone()
            if existing_row:
                await session.execute(
                    text("""
                        UPDATE items
                        SET sku = COALESCE(NULLIF(:sku, ''), sku),
                            category_id = COALESCE(:category_id, category_id),
                            cost_price = CASE WHEN :cost_price > 0 THEN :cost_price ELSE cost_price END,
                            sell_price = CASE WHEN :sell_price > 0 THEN :sell_price ELSE sell_price END,
                            barcode = COALESCE(NULLIF(:barcode, ''), barcode),
                            brand = COALESCE(NULLIF(:brand, ''), brand),
                            pack_size = COALESCE(NULLIF(:pack_size, ''), pack_size),
                            storage_type = COALESCE(NULLIF(:storage_type, ''), storage_type),
                            shariah_status = :shariah_status,
                            shariah_flags = CAST(:shariah_flags AS JSON),
                            shariah_checked_at = NOW(),
                            updated_at = NOW()
                        WHERE id = :id AND business_id = :business_id
                    """),
                    {**params, "id": str(existing_row[0])},
                )
                self._stats["items_updated"] += 1
            else:
                item_id = str(_uuid.uuid4())
                await session.execute(
                    text("""
                        INSERT INTO items
                            (id, business_id, name, sku, category_id, unit, cost_price, sell_price,
                             barcode, brand, pack_size, storage_type,
                             shariah_status, shariah_flags, shariah_checked_at, is_active, created_at)
                        VALUES
                            (:id, :business_id, :name, :sku, :category_id, 'piece', :cost_price, :sell_price,
                             :barcode, :brand, :pack_size, :storage_type,
                             :shariah_status, CAST(:shariah_flags AS JSON), NOW(), true, NOW())
                    """),
                    {**params, "id": item_id},
                )
                self._stats["items_created"] += 1

        result = await session.execute(
            text("SELECT id, LOWER(name) FROM items WHERE business_id = :bid"),
            {"bid": self.business_id}
        )
        return {str(row[1]): str(row[0]) for row in result}

    async def _ensure_inventory(self, session: AsyncSession, item_map: dict):
        for item_name_lower in item_map.keys():
            await session.execute(
                text("""
                    INSERT INTO inventory (id, business_id, item_id, current_stock, reorder_level, max_stock, created_at)
                    SELECT :id, :business_id, :item_id, 0, 10, 100, NOW()
                    WHERE NOT EXISTS (
                        SELECT 1 FROM inventory
                        WHERE business_id = :business_id AND item_id = :item_id
                    )
                """),
                {"id": str(_uuid.uuid4()), "business_id": self.business_id, "item_id": item_map[item_name_lower]}
            )

    async def _apply_inventory_snapshot(self, session: AsyncSession, item_map: dict) -> dict:
        updated = 0
        failed = 0

        if "current_stock" not in self.df.columns:
            return {"inventory_updated": 0, "failed": 0}

        for _, row in self.df.iterrows():
            item_name = self._clean_text(row.get("item_name"))
            if not item_name:
                failed += 1
                continue
            item_id = item_map.get(item_name.strip().lower())
            if not item_id:
                failed += 1
                continue

            current_stock = max(0.0, self._as_float(row.get("current_stock"), 0.0))
            reorder_level = self._as_float(row.get("reorder_level"), None) if "reorder_level" in self.df.columns else None
            max_stock = self._as_float(row.get("max_stock"), None) if "max_stock" in self.df.columns else None
            if max_stock is None or max_stock <= 0:
                max_stock = max(current_stock, 100.0)

            await session.execute(
                text("""
                    INSERT INTO inventory
                        (id, business_id, item_id, current_stock, reorder_level, max_stock, last_restocked, updated_at, created_at)
                    VALUES
                        (:id, :business_id, :item_id, :current_stock, COALESCE(:reorder_level, 10), :max_stock, NOW(), NOW(), NOW())
                    ON CONFLICT (business_id, item_id) DO UPDATE SET
                        current_stock = EXCLUDED.current_stock,
                        reorder_level = COALESCE(:reorder_level, inventory.reorder_level),
                        max_stock = COALESCE(:max_stock, inventory.max_stock),
                        last_restocked = CASE
                            WHEN EXCLUDED.current_stock > inventory.current_stock THEN NOW()
                            ELSE inventory.last_restocked
                        END,
                        updated_at = NOW()
                """),
                {
                    "id": str(_uuid.uuid4()),
                    "business_id": self.business_id,
                    "item_id": item_id,
                    "current_stock": current_stock,
                    "reorder_level": reorder_level,
                    "max_stock": max_stock,
                },
            )
            updated += 1

        await session.commit()
        return {"inventory_updated": updated, "failed": failed}

    async def _bulk_insert_transactions(self, session: AsyncSession, item_map: dict) -> dict:
        rows = []
        skipped = 0
        failed = 0
        dates = []

        for _, row in self.df.iterrows():
            item_name = str(row["item_name"]).strip().lower()
            item_id = item_map.get(item_name)
            if not item_id:
                failed += 1
                continue

            transaction_at = row["transaction_at"]
            if isinstance(transaction_at, pd.Timestamp):
                transaction_at = transaction_at.to_pydatetime()

            quantity = float(row.get("quantity", 1))
            unit_price = float(row.get("unit_price", row.get("total_amount", 0)))
            cost_price = float(row.get("cost_price", 0))
            total_amount = float(row.get("total_amount", quantity * unit_price))

            # Dedup hash over the row's identifying business facts. Deterministic
            # across re-uploads (no per-upload salt) so a re-import of the same
            # file never double-counts sales. The partial unique index
            # (business_id, row_hash) WHERE row_hash IS NOT NULL makes the
            # ON CONFLICT DO NOTHING below idempotent.
            row_hash = hashlib.sha256(
                json.dumps({
                    "business_id": self.business_id,
                    "item_id": item_id,
                    "transaction_at": str(transaction_at),
                    "quantity": quantity,
                    "total_amount": total_amount,
                }, sort_keys=True).encode()
            ).hexdigest()

            rows.append({
                "business_id": self.business_id,
                "item_id": item_id,
                "quantity": quantity,
                "unit_price": unit_price,
                "cost_price": cost_price,
                "total_amount": total_amount,
                "profit": total_amount - (quantity * cost_price),
                "transaction_at": transaction_at if transaction_at else None,
                "transaction_type": "sale",
                "row_hash": row_hash,
            })
            if row.get("transaction_at"):
                dates.append(row["transaction_at"])

        imported = 0
        for idx, row_data in enumerate(rows, start=1):
            if not row_data["transaction_at"]:
                continue
            try:
                result = await session.execute(
                    text("""
                        INSERT INTO transactions
                            (id, business_id, item_id, quantity, unit_price, cost_price,
                             total_amount, profit, transaction_at, transaction_type, row_hash, created_at)
                        VALUES (:id, :business_id, :item_id, :quantity, :unit_price, :cost_price,
                                :total_amount, :profit, :transaction_at, :transaction_type, :row_hash, NOW())
                        ON CONFLICT (business_id, row_hash) WHERE row_hash IS NOT NULL
                        DO NOTHING
                    """),
                    {**row_data, "id": str(_uuid.uuid4())}
                )
                # rowcount is 0 when the unique dedup index suppressed the row.
                if result.rowcount and result.rowcount > 0:
                    imported += 1
                else:
                    skipped += 1
                # Chunked commit every 1,000 rows to prevent table lock exhaustion
                if idx % 1000 == 0:
                    await session.commit()
            except Exception as exc:
                failed += 1
                import logging
                logging.getLogger("etl_pipeline").warning("Transaction insert failed: %s", exc)

        await session.commit()

        return {
            "imported": imported,
            "skipped": skipped,
            "failed": failed,
            "items_created": len(item_map),
            "date_range": (min(dates) if dates else None, max(dates) if dates else None),
        }

    async def _rebuild_summaries(self, session: AsyncSession, date_range: tuple):
        if not date_range or not date_range[0]:
            return

        start_date, end_date = date_range
        if isinstance(start_date, pd.Timestamp):
            start_date = start_date.to_pydatetime()
        if isinstance(end_date, pd.Timestamp):
            end_date = end_date.to_pydatetime()
        # Normalize to date for DATE(...) comparisons.
        start_date = start_date.date() if hasattr(start_date, "date") else start_date
        end_date = end_date.date() if hasattr(end_date, "date") else end_date

        await session.execute(
            text("""
                WITH daily_totals AS (
                    SELECT
                        business_id,
                        DATE(transaction_at) AS d,
                        COALESCE(SUM(total_amount), 0) AS total_sales,
                        COALESCE(SUM(profit), 0) AS total_profit,
                        COUNT(*) AS total_transactions
                    FROM transactions
                    WHERE business_id = :business_id
                      AND DATE(transaction_at) >= :start_date
                      AND DATE(transaction_at) <= :end_date
                    GROUP BY business_id, DATE(transaction_at)
                ),
                item_totals AS (
                    SELECT
                        business_id,
                        DATE(transaction_at) AS d,
                        item_id,
                        SUM(quantity) AS qty,
                        ROW_NUMBER() OVER (
                            PARTITION BY DATE(transaction_at)
                            ORDER BY SUM(quantity) DESC
                        ) AS rn
                    FROM transactions
                    WHERE business_id = :business_id
                      AND DATE(transaction_at) >= :start_date
                      AND DATE(transaction_at) <= :end_date
                    GROUP BY business_id, DATE(transaction_at), item_id
                )
                INSERT INTO daily_summaries
                    (id, business_id, date, total_sales, total_profit, total_transactions, top_item_id, top_item_qty, created_at)
                SELECT
                    gen_random_uuid(),
                    dt.business_id,
                    dt.d,
                    dt.total_sales,
                    dt.total_profit,
                    dt.total_transactions,
                    it.item_id,
                    it.qty,
                    NOW()
                FROM daily_totals dt
                LEFT JOIN item_totals it
                    ON dt.d = it.d AND it.rn = 1
                ON CONFLICT (business_id, date) DO UPDATE SET
                    total_sales = EXCLUDED.total_sales,
                    total_profit = EXCLUDED.total_profit,
                    total_transactions = EXCLUDED.total_transactions,
                    top_item_id = EXCLUDED.top_item_id,
                    top_item_qty = EXCLUDED.top_item_qty
            """),
            {"business_id": self.business_id, "start_date": start_date, "end_date": end_date}
        )

    async def _invalidate_forecasts(self, session: AsyncSession, item_map: dict):
        item_ids = list(item_map.values())
        if item_ids:
            await session.execute(
                text("DELETE FROM forecast_cache WHERE business_id = :business_id AND item_id = ANY(:item_ids)"),
                {"business_id": self.business_id, "item_ids": item_ids}
            )
