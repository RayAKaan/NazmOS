"""Café vertical configuration for Orbit Financial X-Ray."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CafeConfig:
    """Café vertical configuration for Orbit X-Ray.

    Defines café-specific metrics, vocabulary, and schema extensions.
    """
    # Core metrics
    metrics: list[str] = field(default_factory=lambda: [
        "sales",
        "inventory",
        "ingredient_cost",
        "menu_margin",
        "waste",
    ])

    # Product categories
    categories: list[str] = field(default_factory=lambda: [
        "coffee",
        "cold_drinks",
        "frappes",
        "desserts",
        "food",
        "other",
    ])

    # Recipe-ready schema (future-proof)
    recipe_fields: list[str] = field(default_factory=lambda: [
        "recipe_id",
        "menu_item",
        "ingredients",
        "ingredient_cost",
        "prep_time_minutes",
        "serving_size",
        "allergen_info",
    ])

    # Branch support
    branch_fields: list[str] = field(default_factory=lambda: [
        "branch_id",
        "location_id",
        "source_file",
    ])

    # Waste tracking
    waste_categories: list[str] = field(default_factory=lambda: [
        "spoilage",
        "preparation_waste",
        "overproduction",
        "expired",
        "spillage",
    ])

    def get_metric_config(self, metric: str) -> dict:
        """Get configuration for a specific metric."""
        configs = {
            "sales": {
                "sub_categories": ["coffee", "cold_drinks", "frappes", "desserts", "food", "other"],
                "time_grain": "daily",
            },
            "inventory": {
                "track_waste": True,
                "track_ingredients": True,
            },
            "ingredient_cost": {
                "track_per_recipe": True,
                "track_per_ingredient": True,
            },
            "menu_margin": {
                "target_margin_pct": 0.70,  # 70% typical for cafes
            },
            "waste": {
                "categories": self.waste_categories,
                "track_cost": True,
            },
        }
        return configs.get(metric, {})


# Default café configuration
CAFE_CONFIG = CafeConfig()