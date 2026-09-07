"""Analytical boundary (DuckDB engine, Phase 1).

DuckDB is the analytical *execution* engine for the inventory money-critical
surface. The engine never talks to the database directly and never owns
business policy: it computes raw aggregates over tenant-scoped rows streamed
through the caller's session, and every semantic (velocity, valuation basis,
status, dead-stock) is implemented in the NazmOS layer on top of the results.
"""
from app.analytics.contracts import (  # noqa: F401
    AnalyticalFeed,
    AnalyticalProvenance,
    ItemFact,
    ItemKPI,
    ScopedEngineError,
    ValueBasis,
)
from app.analytics.repository import (  # noqa: F401
    inventory_feed,
    item_sales_series,
)