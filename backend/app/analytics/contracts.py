"""Data contracts for the analytical boundary (DuckDB engine, Phase 1).

The DuckDB in-memory engine is the *execution* layer for the inventory
money-critical analytical surface. It only ever computes raw aggregates over
rows that already crossed the tenant/RLS boundary inside the caller's session.
NazmOS owns every semantic afterwards: coverage-aware velocity, valuation
basis, classification, trend, status and provenance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class ValueBasis(str, Enum):
    COST = "cost"
    SELL = "sell"


class ScopedEngineError(RuntimeError):
    """Raised when the scoped analytical engine cannot be built or closed."""


@dataclass(frozen=True)
class AnalyticalProvenance:
    """How a set of analytical results was produced.

    ``tenant_scoped`` is always True here: the loader copies rows into DuckDB
    only through the caller's session and always filters by ``business_id``
    after RLS was enforced by the middleware.
    """

    business_id: str
    engine: str = "duckdb_in_memory"
    window_days: int = 30
    observed_days: int = 0
    loaded_inventory_rows: int = 0
    loaded_sales_rows: int = 0
    anchor: datetime | None = None
    tenant_scoped: bool = True


@dataclass(frozen=True)
class ItemFact:
    """Raw per-item facts produced by the engine (no semantics applied).

    Full per-location rows are deliberately exposed alongside the aggregated
    fields so a consumer can choose the resolution it needs. Money columns are
    floats here at the engine boundary; the semantic layer re-quantizes them
    to ``Decimal`` via ``audit_core.money``.
    """

    item_id: str
    name: str
    sku: str | None = None
    category_name: str | None = None
    unit: str | None = None
    current_stock: float = 0.0
    cost_price: float = 0.0
    sell_price: float = 0.0
    reorder_level: float = 0.0
    last_restocked: datetime | None = None
    is_active: bool = True
    qty_30d: float = 0.0
    qty_7d: float = 0.0
    qty_prev7d: float = 0.0
    coverage_days_30d: int = 0
    last_sold_at: datetime | None = None

    @property
    def dead_by_scan(self) -> bool:
        """Canonical WS5 dead-stock rule: < 1 unit sold in the window w/ stock."""
        return self.current_stock > 0 and self.qty_30d < 1


@dataclass(frozen=True)
class ItemKPI:
    """NazmOS semantic-layer output derived from an ``ItemFact``.

    Velocity is coverage-aware (``audit_core.coverage_aware_daily_velocity``)
    and money is ``Decimal`` quantized to 0.01. ``status`` is NOT computed here
    because consumers intentionally use slightly different thresholds.
    """

    fact: ItemFact
    daily_avg: Decimal = Decimal("0")
    stock_value_cost: Decimal = Decimal("0")
    stock_value_sell: Decimal = Decimal("0")
    days_until_stockout: Decimal | None = None
    trend_7d: str = "stable"


@dataclass
class AnalyticalFeed:
    """One engine's worth of results plus its provenance."""

    provenance: AnalyticalProvenance
    facts: list[ItemFact] = field(default_factory=list)
    sales_series: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def by_item_id(self, item_id: str) -> ItemFact | None:
        for fact in self.facts:
            if str(fact.item_id) == str(item_id):
                return fact
        return None