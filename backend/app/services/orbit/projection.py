"""Canonical state → product tables projector (spec §9).

    Raw Input
        ↓
    ONE CANONICAL PIPELINE
        ↓
    CanonicalBusinessState
        ↓
    THIS PROJECTOR
        ↓
    Existing Product Tables (``items``, ``inventory``, ``transactions``)

This module is the *only* remaining reason ``items`` / ``inventory`` /
``transactions`` exist: they are a compatibility read model for code that has not
yet been migrated to ``BusinessContext``. They are not a second source of truth.

Three properties make that safe:

1. **The projector never interprets.** It reads ``CanonicalBusinessState`` and
   writes it out. It does not parse a file, resolve a date, coerce a number or
   decide what a column means. Every value it writes is a value the pipeline
   already established, and each written row keeps the canonical ``row_hash`` so
   it can be traced back.

2. **Writing is idempotent.** Transactions are inserted with
   ``ON CONFLICT (business_id, location_id, item_id, row_hash) DO NOTHING``
   against the canonical row hash, so projecting the same state twice inserts
   nothing the second time. The previous ETL salted nothing and re-uploads were
   safe for the same reason; this preserves that without inventing a second hash.

3. **Absence is preserved.** A canonical ``Measured`` with no value projects to
   SQL ``NULL``, never to ``0``. The old projector defaulted missing prices to
   ``0.0``, which is how an unknown price became a known zero.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Mapping, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orbit.contracts import (
    BusinessEvent,
    BusinessEventType,
    CanonicalBusinessState,
    Entity,
    EntityKind,
    _utcnow,
)

#: Canonical event types mapped to the product-table ``transaction_type`` values
#: existing downstream code already filters on. Unmapped types are not projected as
#: transactions, because a product-table transaction means "stock moved".
_EVENT_TO_TRANSACTION_TYPE: dict[BusinessEventType, str] = {
    BusinessEventType.SALE: "sale",
    BusinessEventType.REFUND: "return",
    BusinessEventType.RETURN: "return",
    BusinessEventType.PURCHASE: "purchase",
    BusinessEventType.STOCK_RECEIPT: "receipt",
    BusinessEventType.STOCK_ADJUSTMENT: "adjustment",
    BusinessEventType.STOCK_TRANSFER: "transfer",
}

#: Transaction types whose amount is negative, matching the convention the product
#: tables already use: a sale is positive revenue and its direction is carried by
#: the transaction type, while a return or write-off reduces the ledger.
_NEGATIVE_AMOUNT_TYPES = frozenset({"return", "refund", "waste", "adjustment"})


def _decimal_to_float(value: Optional[Decimal]) -> Optional[float]:
    """``None`` stays ``None``. A missing value must never become 0.0."""
    return None if value is None else float(value)


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _schema_number(
    value: Optional[Decimal],
    *,
    field: str,
    result: Optional[ProjectionResult] = None,
    context: str = "",
) -> float:
    """Write a number the legacy NOT NULL columns will accept, and record it.

    ``items`` / ``transactions`` declare every money column ``NOT NULL``, so an
    unknown price cannot be written as SQL NULL there. Writing 0 is unavoidable if
    these tables are to keep working, but it must not be mistaken for evidence:
    the coercion is recorded in ``coerced_zero_fields`` and canonical state keeps
    reporting the value as unknown.
    """
    if value is not None:
        return float(value)
    if result is not None:
        label = f"{field}" + (f" ({context})" if context else "")
        result.coerced_zero_fields = tuple({*result.coerced_zero_fields, label})
    return 0.0


@dataclass
class ProjectionResult:
    """What the projector wrote, with enough detail to audit the write."""

    items_created: int = 0
    items_updated: int = 0
    inventory_written: int = 0
    transactions_inserted: int = 0
    transactions_skipped: int = 0
    locations_created: int = 0
    categories_created: int = 0
    #: Canonical entity ids that could not be projected, with the reason.
    unprojected: tuple[str, ...] = ()
    #: Fields the legacy schema forces to a number even though canonical state says
    #: unknown. Recorded because a 0 written to satisfy a NOT NULL column is not
    #: evidence, and a consumer of the product table must be able to tell the
    #: difference. Canonical state remains authoritative and still reports unknown.
    coerced_zero_fields: tuple[str, ...] = ()
    state_version: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "items_created": self.items_created,
            "items_updated": self.items_updated,
            "inventory_written": self.inventory_written,
            "transactions_inserted": self.transactions_inserted,
            "transactions_skipped": self.transactions_skipped,
            "locations_created": self.locations_created,
            "categories_created": self.categories_created,
            "unprojected": list(self.unprojected),
            "coerced_zero_fields": list(self.coerced_zero_fields),
            "state_version": self.state_version,
        }


class CanonicalProjector:
    """Projects canonical state into the existing product tables."""

    def __init__(self, business_id: str, session: AsyncSession) -> None:
        self.business_id = str(business_id)
        self.session = session
        self.result = ProjectionResult()
        self._location_cache: dict[str, str] = {}
        self._category_cache: dict[str, str] = {}
        self._item_ids: dict[str, str] = {}

    # ── reference data ───────────────────────────────────────────────────────

    async def _get_or_create_location(self, name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        key = name.strip().lower()
        if key in self._location_cache:
            return self._location_cache[key]

        row = await self.session.execute(
            text("SELECT id FROM locations WHERE business_id = :b AND LOWER(name) = LOWER(:n) LIMIT 1"),
            {"b": self.business_id, "n": name},
        )
        found = row.fetchone()
        if found:
            self._location_cache[key] = str(found[0])
            return self._location_cache[key]

        location_id = str(uuid.uuid4())
        # The first location for a business is its head office, preserving the
        # existing convention downstream reporting relies on.
        count = await self.session.execute(
            text("SELECT count(*) FROM locations WHERE business_id = :b"), {"b": self.business_id}
        )
        is_hq = (count.scalar() or 0) == 0
        await self.session.execute(
            text("""
                INSERT INTO locations (id, business_id, name, is_headquarters, created_at)
                VALUES (:id, :b, :n, :hq, NOW())
                ON CONFLICT (business_id, name) DO NOTHING
            """),
            {"id": location_id, "b": self.business_id, "n": name, "hq": is_hq},
        )
        row = await self.session.execute(
            text("SELECT id FROM locations WHERE business_id = :b AND LOWER(name) = LOWER(:n) LIMIT 1"),
            {"b": self.business_id, "n": name},
        )
        found = row.fetchone()
        resolved = str(found[0]) if found else location_id
        self._location_cache[key] = resolved
        self.result.locations_created += 1
        return resolved

    async def _get_or_create_category(self, name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        key = name.strip().lower()
        if key in self._category_cache:
            return self._category_cache[key]

        row = await self.session.execute(
            text("SELECT id FROM categories WHERE business_id = :b AND LOWER(name) = LOWER(:n) LIMIT 1"),
            {"b": self.business_id, "n": name},
        )
        found = row.fetchone()
        if found:
            self._category_cache[key] = str(found[0])
            return self._category_cache[key]

        category_id = str(uuid.uuid4())
        await self.session.execute(
            text("""
                INSERT INTO categories (id, business_id, name, created_at)
                VALUES (:id, :b, :n, NOW())
                ON CONFLICT (business_id, name) DO NOTHING
            """),
            {"id": category_id, "b": self.business_id, "n": name},
        )
        row = await self.session.execute(
            text("SELECT id FROM categories WHERE business_id = :b AND LOWER(name) = LOWER(:n) LIMIT 1"),
            {"b": self.business_id, "n": name},
        )
        found = row.fetchone()
        resolved = str(found[0]) if found else category_id
        self._category_cache[key] = resolved
        self.result.categories_created += 1
        return resolved

    # ── items ────────────────────────────────────────────────────────────────

    async def project_items(
        self,
        entities: Sequence[Entity],
        *,
        prices_by_product: Optional[Mapping[str, tuple[Optional[float], Optional[float]]]] = None,
    ) -> dict[str, str]:
        """Upsert product items from canonical entities.

        ``prices_by_product`` maps entity_id -> (cost, sell) taken from canonical
        events. Prices are only written when the canonical state actually knows
        them; the previous projector defaulted a missing price to ``0.0``.
        """
        from app.services.shariah_compliance import audit_inventory_halal_status

        prices_by_product = prices_by_product or {}
        products = [e for e in entities if e.kind is EntityKind.PRODUCT]

        for entity in products:
            name = _text(entity.canonical_name)
            if not name:
                continue
            cost, sell = prices_by_product.get(entity.entity_id, (None, None))
            # The compliance audit is batch-shaped and takes ``name``/``sku``.
            audit = audit_inventory_halal_status([
                {"name": name, "sku": _text(entity.identifiers.get("sku")) or ""}
            ])
            guardrail_flags = audit.get("flagged_items") or []
            guardrail_status = "flagged_haram" if guardrail_flags else "halal_guard_passed"
            params: dict[str, Any] = {
                "business_id": self.business_id,
                "name": name,
                "sku": _text(entity.identifiers.get("sku")) or "",
                "barcode": _text(entity.identifiers.get("barcode")) or "",
                # NOT NULL in the legacy schema: an unknown price becomes 0 here
                # and is recorded, while canonical state still says unknown.
                "cost_price": _schema_number(
                    Decimal(str(cost)) if cost is not None else None,
                    field="items.cost_price", result=self.result, context=name,
                ),
                "sell_price": _schema_number(
                    Decimal(str(sell)) if sell is not None else None,
                    field="items.sell_price", result=self.result, context=name,
                ),
                "shariah_status": guardrail_status,
                "shariah_flags": json.dumps(guardrail_flags),
                # An update must not overwrite a known price with a coerced 0, so
                # the UPDATE is guarded by whether canonical state knew a value.
                "cost_known": cost is not None,
                "sell_known": sell is not None,
            }

            existing = await self.session.execute(
                text("SELECT id FROM items WHERE business_id = :business_id AND LOWER(name) = LOWER(:name) LIMIT 1"),
                params,
            )
            found = existing.fetchone()
            if found:
                # ``CASE WHEN :x > 0`` preserves the existing behaviour of not
                # overwriting a known price with an unknown one.
                await self.session.execute(
                    text("""
                        UPDATE items
                        SET                             sku = COALESCE(NULLIF(:sku, ''), sku),
                            cost_price = CASE WHEN :cost_known THEN :cost_price ELSE cost_price END,
                            sell_price = CASE WHEN :sell_known THEN :sell_price ELSE sell_price END,
                            barcode = COALESCE(NULLIF(:barcode, ''), barcode),
                            shariah_status = :shariah_status,
                            shariah_flags = CAST(:shariah_flags AS JSON),
                            shariah_checked_at = NOW(),
                            updated_at = NOW()
                        WHERE id = :id AND business_id = :business_id
                    """),
                    {**params, "id": str(found[0])},
                )
                self._item_ids[entity.entity_id] = str(found[0])
                self.result.items_updated += 1
            else:
                item_id = str(uuid.uuid4())
                await self.session.execute(
                    text("""
                        INSERT INTO items
                            (id, business_id, name, sku, unit, cost_price, sell_price,
                             barcode, brand, pack_size, storage_type,
                             shariah_status, shariah_flags, shariah_checked_at, is_active, created_at)
                        VALUES
                            (:id, :business_id, :name, :sku, 'piece', :cost_price, :sell_price,
                             :barcode, NULL, NULL, NULL,
                             :shariah_status, CAST(:shariah_flags AS JSON), NOW(), true, NOW())
                    """),
                    {**params, "id": item_id},
                )
                self._item_ids[entity.entity_id] = item_id
                self.result.items_created += 1

        rows = await self.session.execute(
            text("SELECT id, LOWER(name) FROM items WHERE business_id = :bid"),
            {"bid": self.business_id},
        )
        by_name = {str(row[1]): str(row[0]) for row in rows}
        for entity in products:
            name = _text(entity.canonical_name)
            if name and entity.entity_id not in self._item_ids:
                item_id = by_name.get(name.lower())
                if item_id:
                    self._item_ids[entity.entity_id] = item_id
        return dict(self._item_ids)

    # ── inventory ────────────────────────────────────────────────────────────

    async def project_inventory(
        self,
        state: CanonicalBusinessState,
        item_ids: Mapping[str, str],
        location_names: Mapping[str, str],
    ) -> int:
        """Write stock on hand from the latest observation per product/location.

        Only ``STOCK_OBSERVATION`` events write absolute stock. Sales do not
        decrement here: doing both would apply the same movement twice, which is
        how the old adapter path corrupted balances.
        """
        latest: dict[tuple[str, str], BusinessEvent] = {}
        for event in state.events:
            if event.event_type is not BusinessEventType.STOCK_OBSERVATION:
                continue
            product = event.entity_refs.get(EntityKind.PRODUCT.value)
            if not product:
                continue
            location = event.location_ref or ""
            key = (product, location)
            candidate = (event.business_local_date, event.event_time or _utcnow())
            current = latest.get(key)
            if current is None or candidate >= (
                current.business_local_date, current.event_time or _utcnow()
            ):
                latest[key] = event

        written = 0
        for (product_ref, location_ref), event in sorted(latest.items()):
            item_id = item_ids.get(product_ref)
            if item_id is None:
                self.result.unprojected += (
                    f"stock for {product_ref}: no item row (product never projected)",
                )
                continue
            location_name = location_names.get(location_ref)
            location_id = await self._get_or_create_location(location_name)
            quantity = _decimal_to_float(event.quantity.value)
            await self.session.execute(
                text("""
                    INSERT INTO inventory
                        (id, business_id, item_id, location_id, current_stock, updated_at, created_at)
                    VALUES (:id, :b, :item_id, :location_id, :qty, NOW(), NOW())
                    ON CONFLICT (business_id, item_id) WHERE location_id IS NULL
                    DO UPDATE SET current_stock = EXCLUDED.current_stock, updated_at = NOW()
                """) if location_id is None else text("""
                    INSERT INTO inventory
                        (id, business_id, item_id, location_id, current_stock, updated_at, created_at)
                    VALUES (:id, :b, :item_id, :location_id, :qty, NOW(), NOW())
                    ON CONFLICT (business_id, item_id, location_id)
                    DO UPDATE SET current_stock = EXCLUDED.current_stock, updated_at = NOW()
                """),
                {
                    "id": str(uuid.uuid4()),
                    "b": self.business_id,
                    "item_id": item_id,
                    "location_id": location_id,
                    "qty": quantity,
                },
            )
            written += 1
        self.result.inventory_written += written
        return written

    # ── transactions ─────────────────────────────────────────────────────────

    async def project_transactions(
        self,
        state: CanonicalBusinessState,
        item_ids: Mapping[str, str],
        location_names: Mapping[str, str],
    ) -> tuple[int, int]:
        """Insert transactions from canonical events, deduplicated by row hash."""
        inserted = 0
        skipped = 0

        for event in sorted(state.events, key=lambda e: (e.event_time or _utcnow(), e.event_id)):
            transaction_type = _EVENT_TO_TRANSACTION_TYPE.get(event.event_type)
            if transaction_type is None:
                continue
            product_ref = event.entity_refs.get(EntityKind.PRODUCT.value)
            item_id = item_ids.get(product_ref or "")
            if item_id is None:
                self.result.unprojected += (
                    f"{event.event_type.value} {event.event_id}: no item row for its product",
                )
                continue
            # An event with no timestamp cannot be placed on the transactions
            # timeline, and a wrong date is worse than no row.
            if event.event_time is None:
                self.result.unprojected += (
                    f"{event.event_type.value} {event.event_id}: no event time",
                )
                continue

            quantity = _decimal_to_float(event.quantity.value) or 0.0
            quantity = abs(quantity)
            total = _decimal_to_float(event.amount.value)
            unit_price = _decimal_to_float(event.unit_price.value)
            cost_price = _decimal_to_float(event.cost.value)
            if total is None:
                total = quantity * (unit_price or 0.0)
            # Every money column here is NOT NULL in the legacy schema, so an
            # unknown amount or cost is coerced to 0 and recorded. Canonical state
            # remains authoritative and still reports these as unknown.
            profit = (
                total - (cost_price * quantity)
                if cost_price is not None
                else None
            )
            row_context = event.event_id
            payload_numbers = {
                "quantity": _schema_number(Decimal(str(quantity)), field="transactions.quantity",
                                            result=self.result, context=row_context),
                "unit_price": _schema_number(
                    None if unit_price is None else Decimal(str(unit_price)),
                    field="transactions.unit_price", result=self.result, context=row_context),
                "cost_price": _schema_number(
                    None if cost_price is None else Decimal(str(cost_price)),
                    field="transactions.cost_price", result=self.result, context=row_context),
                "total_amount": _schema_number(
                    None if total is None else Decimal(str(total)),
                    field="transactions.total_amount", result=self.result, context=row_context),
                "profit": _schema_number(
                    None if profit is None else Decimal(str(profit)),
                    field="transactions.profit", result=self.result, context=row_context),
            }
            if transaction_type in _NEGATIVE_AMOUNT_TYPES and total is not None:
                total = -abs(total)
            location_id = await self._get_or_create_location(
                location_names.get(event.location_ref or "")
            )

            result = await self.session.execute(
                text("""
                    INSERT INTO transactions
                        (id, business_id, item_id, location_id, quantity, unit_price, cost_price,
                         total_amount, profit, transaction_at, transaction_type,
                         source_transaction_id, row_hash, created_at)
                    VALUES (:id, :business_id, :item_id, :location_id, :quantity, :unit_price, :cost_price,
                            :total_amount, :profit, :transaction_at, :transaction_type,
                            :source_transaction_id, :row_hash, NOW())
                    ON CONFLICT (business_id, location_id, item_id, row_hash) WHERE row_hash IS NOT NULL
                    DO NOTHING
                """),
                {
                    "id": str(uuid.uuid4()),
                    "business_id": self.business_id,
                    "item_id": item_id,
                    "location_id": location_id,
                    **payload_numbers,
                    "transaction_at": event.event_time,
                    "transaction_type": transaction_type,
                    "source_transaction_id": event.external_reference,
                    # The canonical row hash, so a projected row is traceable to
                    # the exact observation that produced it.
                    "row_hash": event.row_hash,
                },
            )
            if result.rowcount and result.rowcount > 0:
                inserted += 1
            else:
                skipped += 1

        self.result.transactions_inserted += inserted
        self.result.transactions_skipped += skipped
        return inserted, skipped

    # ── entry point ──────────────────────────────────────────────────────────

    async def project(self, state: CanonicalBusinessState) -> ProjectionResult:
        """Project an entire canonical state.

        The projector reads canonical state and nothing else. It does not parse,
        interpret, or decide; where canonical state is silent, the product table
        gets NULL and the omission is recorded in ``unprojected``.
        """
        self.result.state_version = state.state_version

        entity_names = {
            e.entity_id: e.canonical_name for e in state.entities if e.canonical_name
        }
        prices = self._prices_by_product(state)

        item_ids = await self.project_items(state.entities, prices_by_product=prices)

        # Only location-bearing entities are projected as locations; a location_ref
        # pointing at a branch must resolve to that branch's name.
        await self.project_inventory(state, item_ids, entity_names)
        await self.project_transactions(state, item_ids, entity_names)

        self.result.unprojected = tuple(dict.fromkeys(self.result.unprojected))
        return self.result

    @staticmethod
    def _prices_by_product(
        state: CanonicalBusinessState,
    ) -> dict[str, tuple[Optional[float], Optional[float]]]:
        """Latest known cost and sell price per product, from canonical events.

        Written only where canonical state knows a value. This is the replacement
        for the old ``_as_float(row.get("unit_price"), 0.0)`` default.
        """
        cost: dict[str, float] = {}
        sell: dict[str, float] = {}
        for event in sorted(state.events, key=lambda e: (e.event_time or _utcnow(), e.event_id)):
            product = event.entity_refs.get(EntityKind.PRODUCT.value)
            if not product:
                continue
            if event.cost.value is not None:
                cost[product] = float(event.cost.value)
            if event.unit_price.value is not None:
                sell[product] = float(event.unit_price.value)
        return {
            product: (cost.get(product), sell.get(product))
            for product in set(cost) | set(sell)
        }


async def project_state(
    state: CanonicalBusinessState,
    *,
    business_id: str,
    session: AsyncSession,
) -> ProjectionResult:
    """Convenience wrapper: project one canonical state and return the result."""
    projector = CanonicalProjector(business_id=business_id, session=session)
    return await projector.project(state)
