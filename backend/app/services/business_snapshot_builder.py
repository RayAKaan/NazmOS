"""Legacy BusinessSnapshot compatibility adapter.

BusinessSnapshotBuilder used to parse DataFrames itself and therefore formed a
second truth path. It now delegates all interpretation to the canonical Orbit
ingestion pipeline and only projects canonical events into the legacy snapshot
shape required by older callers.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pandas as pd

from app.services.orbit.ingestion.pipeline import CanonicalOrbitIngestionPipeline
from app.services.orbit.contracts import BusinessEventType, EntityKind
from app.services.orbit_contracts import BusinessSnapshot


class BusinessSnapshotBuilder:
    """Compatibility wrapper; Orbit owns all parsing and normalization."""

    def __init__(self, business_id: str | None = None, business_type: str = "retail"):
        self.business_id = business_id
        self.business_type = business_type
        self._pipeline = CanonicalOrbitIngestionPipeline(
            business_id=UUID(str(business_id)) if business_id else None
        )
        self._results = []

    def add_file(self, df: pd.DataFrame, manifest: dict[str, Any], resolution: Any = None) -> None:
        result = self._pipeline.ingest(
            df.to_csv(index=False).encode("utf-8"),
            source_name=str(manifest.get("source_name") or manifest.get("filename") or "legacy-data.csv"),
            mime_type="text/csv",
        )
        self._results.append((result, manifest))

    def build(self) -> BusinessSnapshot:
        product_names = {
            e.entity_id: e.canonical_name or e.normalized_name or e.entity_id
            for result, _manifest in self._results
            for e in result.entities
            if e.kind is EntityKind.PRODUCT
        }

        ledger: dict[str, dict[str, Any]] = {}
        manifests: list[dict[str, Any]] = []

        for result, manifest in self._results:
            manifests.append(dict(manifest))
            for event in result.events:
                product_id = event.entity_refs.get(EntityKind.PRODUCT.value)
                if not product_id:
                    continue
                name = product_names.get(product_id, product_id)
                entry = ledger.setdefault(
                    name,
                    {
                        "stock": None,
                        "cost": None,
                        "sell": None,
                        "qty_30d": Decimal("0"),
                        "prior_qty_30": Decimal("0"),
                        "revenue_30d": Decimal("0"),
                        "last_sold_at": None,
                        "sources": [],
                    },
                )
                if event.cost.value is not None:
                    entry["cost"] = event.cost.value
                if event.unit_price.value is not None:
                    entry["sell"] = event.unit_price.value
                if event.event_type is BusinessEventType.STOCK_OBSERVATION and event.quantity.value is not None:
                    entry["stock"] = event.quantity.value
                elif event.event_type is BusinessEventType.SALE:
                    qty = event.quantity.value or Decimal("0")
                    amount = event.amount.value or Decimal("0")
                    entry["qty_30d"] += qty
                    entry["revenue_30d"] += amount
                    if event.event_time is not None and (
                        entry["last_sold_at"] is None or event.event_time > entry["last_sold_at"]
                    ):
                        entry["last_sold_at"] = event.event_time
                elif event.event_type in (BusinessEventType.RETURN, BusinessEventType.REFUND):
                    qty = event.quantity.value or Decimal("0")
                    amount = event.amount.value or Decimal("0")
                    entry["qty_30d"] -= qty
                    entry["revenue_30d"] -= amount

        products = []
        sales = []
        inventory = []
        for name, entry in ledger.items():
            evidence = next(
                (
                    eid
                    for result, _ in self._results
                    for eid in result.evidence_ids
                ),
                "",
            )
            products.append({
                "name": name,
                "stock": entry["stock"] if entry["stock"] is not None else Decimal("0"),
                "cost": entry["cost"] if entry["cost"] is not None else Decimal("0"),
                "sell": entry["sell"] if entry["sell"] is not None else Decimal("0"),
                "evidence_id": evidence,
                "sources": entry["sources"],
            })
            if entry["qty_30d"] or entry["revenue_30d"]:
                last_sold_days = (
                    (datetime.now(entry["last_sold_at"].tzinfo) - entry["last_sold_at"]).days
                    if entry["last_sold_at"]
                    else None
                )
                sales.append({
                    "product_name": name,
                    "qty_30d": entry["qty_30d"],
                    "prior_qty_30": entry["prior_qty_30"],
                    "revenue_30d": entry["revenue_30d"],
                    "sell": entry["sell"] or Decimal("0"),
                    "cost": entry["cost"] or Decimal("0"),
                    "last_sold_days": last_sold_days,
                })
            if entry["stock"] is not None or entry["cost"] is not None or entry["sell"] is not None:
                inventory.append({
                    "product_name": name,
                    "stock": entry["stock"] or Decimal("0"),
                    "cost": entry["cost"] or Decimal("0"),
                    "sell": entry["sell"] or Decimal("0"),
                    "age_days": None,
                })

        snapshot = BusinessSnapshot(
            business_id=self.business_id,
            business_type=self.business_type,
            period_start=None,
            period_end=datetime.utcnow(),
            products=products,
            sales=sales,
            inventory=inventory,
            purchases=[],
            suppliers=[],
            expenses=[],
            data_quality={
                "total_products": len(products),
                "products_with_sales": sum(1 for x in sales if x.get("qty_30d", 0) > 0),
                "products_with_inventory": sum(1 for x in inventory if x.get("stock", 0) > 0),
                "products_with_cost": sum(1 for x in products if x.get("cost", 0) > 0),
                "total_records": sum(
                    result.records_accepted for result, _ in self._results
                ),
            },
            evidence_ids={p["name"]: p["evidence_id"] for p in products},
            ingestion_manifests=manifests,
        )
        return snapshot

    def to_product_metrics_list(self, snapshot: BusinessSnapshot) -> list[dict[str, Any]]:
        return snapshot.to_product_metrics_list()

    def run_audit(self, snapshot: BusinessSnapshot) -> list:
        from app.services.audit_core import ProductMetrics, analyze_product
        return [analyze_product(ProductMetrics(**m)) for m in snapshot.to_product_metrics_list()]


def build_business_snapshot(
    dataframes: list,
    manifests: list[dict[str, Any]],
    resolutions: list,
    business_id: str | None = None,
    business_type: str = "retail",
) -> BusinessSnapshot:
    builder = BusinessSnapshotBuilder(business_id=business_id, business_type=business_type)
    for index, df in enumerate(dataframes):
        manifest = manifests[index] if index < len(manifests) else {}
        resolution = resolutions[index] if index < len(resolutions) else None
        builder.add_file(df, manifest, resolution)
    return builder.build()


def build_snapshot_from_manifests(
    dataframes: list,
    manifests: list[dict[str, Any]],
    resolutions: list,
    business_id: str | None = None,
) -> BusinessSnapshot:
    return build_business_snapshot(dataframes, manifests, resolutions, business_id=business_id)
