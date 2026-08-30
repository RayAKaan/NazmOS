"""Generate the second adversarial NazmOS Reality Test corpus.

The hidden ground truth is written separately from merchant inputs.  No NazmOS
code imports this module during an actual audit run.
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

SEED = 20260824
END = date(2026, 8, 24)
START = END - timedelta(days=119)
OUT = Path(__file__).resolve().parent / "fixtures" / "reality_v2"

BUSINESSES = {
    "baqala": [
        ("B001", "Milk 1L", "Dairy", 6, 4.2, 12, "fast"),
        ("B002", "Water 1.5L", "Beverage", 2, .75, 25, "fast"),
        ("B003", "Imported Biscuit", "Snacks", 16, 10.5, 2, "dead"),
        ("B004", "Seasonal Ice Cream", "Frozen", 28, 18, 5, "seasonal"),
        ("B005", "Phone Cable", "Accessories", 22, 12, 2, "slow"),
    ],
    "supermarket": [
        ("S001", "Rice 5kg", "Grocery", 32, 24, 18, "fast"),
        ("S002", "Chicken 1kg", "Fresh", 19, 15.5, 25, "fast"),
        ("S003", "Organic Cereal", "Grocery", 34, 25, 2, "dead"),
        ("S004", "BBQ Charcoal", "Seasonal", 22, 13.5, 4, "seasonal"),
        ("S005", "Olive Oil", "Grocery", 38, 30, 2, "slow"),
    ],
    "cafe": [
        ("C001", "Americano", "Coffee", 12, 3.2, 30, "fast"),
        ("C002", "Latte", "Coffee", 18, 5.5, 25, "fast"),
        ("C003", "Imported Syrup", "Ingredient", 55, 34, 1, "dead"),
        ("C004", "Berry Tart", "Dessert", 28, 15, 1, "seasonal"),
        ("C005", "Matcha Latte", "Coffee", 22, 7, 7, "slow"),
    ],
    "restaurant": [
        ("R001", "Chicken Plate", "Main", 32, 14, 18, "fast"),
        ("R002", "Mixed Grill", "Main", 68, 31, 10, "fast"),
        ("R003", "Imported Dessert", "Dessert", 32, 18, 1, "dead"),
        ("R004", "Iftar Box", "Seasonal", 85, 48, 3, "seasonal"),
        ("R005", "Premium Steak", "Main", 115, 68, 2, "slow"),
    ],
    "general_retail": [
        ("G001", "USB-C Charger", "Electronics", 49, 27, 10, "fast"),
        ("G002", "Phone Case", "Accessories", 35, 15, 6, "fast"),
        ("G003", "Old Android Cable", "Electronics", 18, 10, 1, "dead"),
        ("G004", "School Backpack", "Seasonal", 85, 48, 4, "seasonal"),
        ("G005", "Desk Lamp", "Home", 65, 36, 3, "slow"),
    ],
}


def poissonish(rng: random.Random, lam: float) -> int:
    n = max(1, int(lam * 2))
    return sum(rng.random() < min(lam / n, 1) for _ in range(n))


def generate() -> None:
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    hidden = []
    for business, products in BUSINESSES.items():
        sales = []
        inventory = []
        for sku, name, category, price, cost, reorder, pattern in products:
            stock = reorder * ({"fast": 2, "slow": 7, "dead": 12, "seasonal": 8}[pattern])
            for offset in range(120):
                d = START + timedelta(days=offset)
                weekend = 1.25 if d.weekday() in (4, 5) else 1.0
                seasonal = 4.0 if pattern == "seasonal" and d >= END - timedelta(days=20) else (0.15 if pattern == "seasonal" else 1.0)
                scale = {"baqala": 3, "supermarket": 6, "cafe": 5, "restaurant": 4, "general_retail": 2}[business]
                rate = {"fast": 1, "slow": .35, "dead": .02, "seasonal": .08}[pattern] * scale * weekend * seasonal
                qty = poissonish(rng, rate) if not (pattern == "dead" and offset > 45) else 0
                if qty:
                    sales.append({
                        "business": business, "date": d.isoformat(), "sku": sku, "item_name": name,
                        "category": category, "quantity": qty, "unit_price": price,
                        "total_amount": round(qty * price, 2), "cost_price": cost,
                        "transaction_type": "sale",
                    })
                    stock -= qty
                if stock <= reorder and pattern == "fast":
                    stock += reorder * 4
                elif pattern == "dead" and d in (START + timedelta(days=12), START + timedelta(days=35)):
                    stock += reorder * 5
            # Deliberate risk/false-positive cases.
            if pattern == "fast":
                stock = max(1, int(reorder * .6))
            if pattern == "seasonal":
                stock = reorder * 7
            inventory.append({
                "business": business, "snapshot_date": END.isoformat(), "sku": sku,
                "item_name": name, "category": category, "current_stock": max(0, int(stock)),
                "cost_price": cost, "sell_price": price, "supplier": f"{business}-supplier",
                "reorder_level": reorder, "inventory_age_days": 90 if pattern == "dead" else 15,
            })
            hidden.append({"business": business, "sku": sku, "ground_truth": pattern})

        # Add malformed/incomplete records only to merchant input files.
        sales_df = pd.DataFrame([r for r in sales if r["business"] == business])
        inventory_df = pd.DataFrame([r for r in inventory if r["business"] == business])
        sales_df.to_csv(OUT / f"{business}_sales.csv", index=False)
        inventory_df.to_csv(OUT / f"{business}_inventory.csv", index=False)

    pd.DataFrame(hidden).to_csv(OUT / "hidden_ground_truth.csv", index=False)
    (OUT / "README.md").write_text(
        "Merchant input files are the five *_sales.csv and *_inventory.csv files. "
        "hidden_ground_truth.csv must never be uploaded to NazmOS. Seed=20260824; 120 days.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    generate()
