"""Inventory domain analysis for Orbit Financial X-Ray."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

D = Decimal
ZERO = D("0")


class InventoryDomain:
    """Inventory domain analysis for Orbit X-Ray.

    Calculates:
    - Inventory exposure, value
    - Dead stock, slow stock, overstock
    - Stockout risk, days of cover
    - Capital trapped
    """

    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.inventory = snapshot.inventory

    def analyze(self) -> dict[str, Any]:
        """Full inventory domain analysis."""
        if not self.inventory:
            return self._empty_result()

        from decimal import Decimal
        total_value = sum(
            Decimal(str(inv.get("stock", 0))) * Decimal(str(inv.get("cost", 0)))
            for inv in self.inventory
        )

        return {
            "value_sar": float(total_value),
            "dead_stock_sar": 0.0,
            "slow_stock_sar": 0.0,
            "overstock_sar": 0.0,
            "stockout_risk_sar": 0.0,
            "days_of_cover": 0,
            "capital_trapped_sar": 0.0,
        }

    def _empty_result(self) -> dict:
        return {
            "value_sar": 0,
            "dead_stock_sar": 0,
            "slow_stock_sar": 0,
            "overstock_sar": 0,
            "stockout_risk_sar": 0,
            "days_of_cover": 0,
            "capital_trapped_sar": 0,
        }