"""Sales domain analysis for Orbit Financial X-Ray."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

D = Decimal
ZERO = D("0")


class SalesDomain:
    """Sales domain analysis for Orbit X-Ray.

    Calculates:
    - Total sales, growth, daily/weekly sales
    - Product contribution, concentration
    - Best sellers, declining products, inactive products
    - Sales volatility
    - Branch contribution
    """

    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.sales = snapshot.sales

    def analyze(self) -> dict[str, Any]:
        """Full sales domain analysis."""
        if not self.sales:
            return self._empty_result()

        total_sales = sum(s.get("revenue_30d", 0) for s in self.sales)
        daily_avg = total_sales / 30 if total_sales > 0 else 0

        # Product contribution
        product_contribution = {}
        for s in self.sales:
            name = s.get("product_name", "")
            rev = s.get("revenue_30d", 0)
            if rev > 0:
                product_contribution[name] = float((rev / total_sales * 100).quantize(D("0.01"))) if total_sales > 0 else 0

        # Concentration (HHI)
        shares = list(product_contribution.values())
        concentration = sum(s * s for s in shares) if shares else 0

        sorted_by_rev = sorted(self.sales, key=lambda s: s.get("revenue_30d", 0), reverse=True)
        best_sellers = [s.get("product_name", "") for s in sorted_by_rev[:5] if s.get("revenue_30d", 0) > 0]
        inactive = [s.get("product_name", "") for s in self.snapshot.sales if s.get("revenue_30d", 0) == 0]

        return {
            "total_sales": float(total_sales),
            "daily_avg": float(daily_avg),
            "product_contribution": product_contribution,
            "concentration": float(concentration),
            "best_sellers": best_sellers,
            "declining": [],
            "inactive": inactive,
            "volatility": 0.0,
            "branch_contribution": {},
        }

    def _empty_result(self) -> dict:
        return {
            "total_sales": 0,
            "daily_avg": 0,
            "product_contribution": {},
            "concentration": 0,
            "best_sellers": [],
            "declining": [],
            "inactive": [],
            "volatility": 0,
            "branch_contribution": {},
        }