"""Canonical reorder urgency band (Batch 3: procurement.reorder_urgency).

Deterministic source: the reorder proposal path's float urgency ladder
(procurement_agent: ``urgency 0.7 if days < 5 else 0.4``), re-anchored on the
canonical coverage-aware days-of-supply so the band is stable.

The reported window is DAYS OF SUPPLY (projected cover), NOT days-since-last-sale:
  * canonical WS5 dead-by-scan = ``< 1 unit sold in the 30-day feed window``
    (``app.analytics.contracts.ItemFact.dead_by_scan``), which excludes DEAD
    items from REORDER (``ab_decision_framework`` skips DEAD).
  * money-audit DEAD dormancy threshold is ``>= 60`` days
    (``app.services.recovery_intelligence``).
  * the unused ``DEAD_STOCK_DAYS = 45`` constants (audit_core,
    money_audit_service) are dead code and are NOT consulted here.

The band mirrors the deterministic ladder exactly; Jev may only score the same
two rungs (HIGH/LOW) in shadow mode.
"""
from __future__ import annotations

from decimal import Decimal

from app.orchestration.contracts import REORDER_URGENCY_BANDS

_HIGH_URGENCY_MAX_DAYS = Decimal("5")


def reorder_urgency_band(days_of_supply: int | float | Decimal | None) -> str:
    """Deterministic urgency band over canonical days-of-supply.

    HIGH when projected cover < 5 days (mirrors the 0.7 urgency rung),
    else LOW (mirrors 0.4). ``None`` (no projection) => LOW; urgency is never
    fabricated without a cover projection.
    """
    if days_of_supply is None:
        return "LOW"
    return "HIGH" if Decimal(str(days_of_supply)) < _HIGH_URGENCY_MAX_DAYS else "LOW"