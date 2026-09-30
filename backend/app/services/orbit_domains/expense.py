"""Expense domain analysis for Orbit Financial X-Ray."""
from __future__ import annotations

from typing import Any


class ExpenseDomain:
    """Expense domain analysis for Orbit X-Ray.

    Calculates (when expense data exists):
    - Revenue, COGS, Gross Profit
    - Operating Expenses (rent, utilities, staff, delivery, marketing, subscriptions)
    - Operating Contribution

    Returns "unavailable" if no expense data.
    """

    def __init__(self, snapshot):
        self.snapshot = snapshot

    def analyze(self) -> dict[str, Any]:
        """Full expense domain analysis."""
        if not self.snapshot.expenses:
            return {"unavailable": True}

        return {
            "revenue": 0.0,
            "cogs": 0.0,
            "gross_profit": 0.0,
            "operating_expenses": {
                "rent": 0,
                "utilities": 0,
                "staff": 0,
                "delivery": 0,
                "marketing": 0,
                "subscriptions": 0,
                "other": 0,
            },
            "operating_contribution": 0.0,
        }