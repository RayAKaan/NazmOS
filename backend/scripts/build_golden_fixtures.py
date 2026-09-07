"""Deterministic generator for the NazmOS canonical golden fixtures.

The original accepted-family numbers (SALES = 91 rows over 6 distinct days, and
INVENTORY = 45 rows / 15 SKUs / 3 locations / value SAR 28,892) describe a
deterministic canonical merchant. The source CSV was never delivered to the
repo, so this script synthesizes them with EXACT acceptance values:

- 45 inventory rows = 15 SKUs x 3 locations, quantity_on_hand x unit_cost_sar
  summing to exactly SAR 28,892.00.
- The Dammam-only subset (the historical buggy projection) sums to exactly
  SAR 17,366.00 -- i.e. DIFFERENT from the whole-business 28,892.00, so any
  metric that collapses to one location is structurally caught by the harness.
- 91 sales rows spread over exactly 6 distinct days (2026-08-04..2026-08-09).

The generator is fully deterministic (no randomness, no wall-clock), so the
fixtures are stable across rebuilds.

Usage:
    cd backend
    python -m scripts.build_golden_fixtures
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

BUSINESS_ID = "BIZ-NAZMOS-001"
REGRESSION_DIR = Path(__file__).resolve().parents[1] / "tests" / "regression_data"

INVENTORY_HEADER = [
    "business_id", "sku", "product_name", "location_id", "warehouse", "city",
    "quantity_on_hand", "unit_cost_sar", "reorder_point", "active",
]
SALES_HEADER = [
    "business_id", "transaction_id", "transaction_date", "sku", "product_name",
    "branch", "transaction_type", "quantity", "unit_price_sar", "unit_cost_sar",
]

# Canonical 15 SKUs with realistic grocery names. Costs are stable 2-dp values.
SKUS = {
    "SKU-CAN-01": "Mineral Water 500ml",
    "SKU-CAN-02": "Basmati Rice 5kg",
    "SKU-CAN-03": "Flour 1kg",
    "SKU-CAN-04": "Cooking Oil 2.5L",
    "SKU-CAN-05": "Tea 100 Bags",
    "SKU-CAN-06": "Coffee 250g",
    "SKU-CAN-07": "Sugar 1kg",
    "SKU-CAN-08": "Milk Powder 900g",
    "SKU-CAN-09": "Dish Soap 750ml",
    "SKU-CAN-10": "Tuna Can 185g",
    "SKU-CAN-11": "Bread Loaf",
    "SKU-CAN-12": "Eggs 30 Pack",
    "SKU-CAN-13": "Chicken 1kg",
    "SKU-CAN-14": "Yoghurt 1kg",
    "SKU-CAN-15": "Tomato Paste 140g",
}

# unit_cost_sar per SKU (2-dp).
COST = {
    "SKU-CAN-01": Decimal("1.50"),
    "SKU-CAN-02": Decimal("38.00"),
    "SKU-CAN-03": Decimal("4.50"),
    "SKU-CAN-04": Decimal("27.00"),
    "SKU-CAN-05": Decimal("12.50"),
    "SKU-CAN-06": Decimal("24.00"),
    "SKU-CAN-07": Decimal("6.75"),
    "SKU-CAN-08": Decimal("16.00"),
    "SKU-CAN-09": Decimal("9.50"),
    "SKU-CAN-10": Decimal("28.00"),
    "SKU-CAN-11": Decimal("5.80"),
    "SKU-CAN-12": Decimal("4.20"),
    "SKU-CAN-13": Decimal("3.50"),
    "SKU-CAN-14": Decimal("21.00"),
    "SKU-CAN-15": Decimal("0.25"),
}

# Arbitrary but deterministic quantities per (location, SKU). The generator
# verifies the sums exactly and fails loudly if the golden facts ever drift.
# Location ids:
#   LOC-RYD Riyadh Main  (Riyadh)
#   LOC-JED Jeddah Branch (Jeddah)
#   LOC-DMM Dammam Branch  (Dammam)
QTY = {
    "LOC-RYD": {
        "SKU-CAN-01": 60, "SKU-CAN-02": 20, "SKU-CAN-03": 50, "SKU-CAN-04": 22,
        "SKU-CAN-05": 44, "SKU-CAN-06": 25, "SKU-CAN-07": 45, "SKU-CAN-08": 32,
        "SKU-CAN-09": 55, "SKU-CAN-10": 18, "SKU-CAN-11": 40, "SKU-CAN-12": 60,
        "SKU-CAN-13": 70, "SKU-CAN-14": 20, "SKU-CAN-15": 1115,
    },
    "LOC-JED": {
        "SKU-CAN-01": 55, "SKU-CAN-02": 16, "SKU-CAN-03": 48, "SKU-CAN-04": 16,
        "SKU-CAN-05": 42, "SKU-CAN-06": 26, "SKU-CAN-07": 46, "SKU-CAN-08": 34,
        "SKU-CAN-09": 50, "SKU-CAN-10": 13, "SKU-CAN-11": 38, "SKU-CAN-12": 58,
        "SKU-CAN-13": 68, "SKU-CAN-14": 22, "SKU-CAN-15": 368,
    },
    "LOC-DMM": {
        "SKU-CAN-01": 200, "SKU-CAN-02": 80, "SKU-CAN-03": 140, "SKU-CAN-04": 55,
        "SKU-CAN-05": 110, "SKU-CAN-06": 60, "SKU-CAN-07": 150, "SKU-CAN-08": 95,
        "SKU-CAN-09": 170, "SKU-CAN-10": 45, "SKU-CAN-11": 130, "SKU-CAN-12": 190,
        "SKU-CAN-13": 210, "SKU-CAN-14": 55, "SKU-CAN-15": 986,
    },
}

LOCATIONS = {
    "LOC-RYD": ("Riyadh Main", "Riyadh"),
    "LOC-JED": ("Jeddah Branch", "Jeddah"),
    "LOC-DMM": ("Dammam Branch", "Dammam"),
}

LOCATION_NAMES = [name for name, _ in LOCATIONS.values()]

# Canonical sales layout: 91 rows across 6 distinct days (2026-08-04..09).
SALES_START = date(2026, 8, 4)
SALES_TOTAL_ROWS = 91
SALES_SKUS = list(SKUS.keys())


def _line_value(cost: Decimal, qty: int) -> Decimal:
    return (cost * qty).quantize(Decimal("0.01"))


def build_inventory_rows() -> list[dict]:
    rows = []
    for loc_id, (warehouse, city) in LOCATIONS.items():
        loc_value = Decimal("0")
        for sku in SALES_SKUS:
            cost = COST[sku]
            qty = QTY[loc_id][sku]
            value = _line_value(cost, qty)
            loc_value += value
            rows.append({
                "business_id": BUSINESS_ID,
                "sku": sku,
                "product_name": SKUS[sku],
                "location_id": loc_id,
                "warehouse": warehouse,
                "city": city,
                "quantity_on_hand": qty,
                "unit_cost_sar": f"{cost:.2f}",
                "reorder_point": 10,
                "active": "true",
            })
        assert loc_value.quantize(Decimal("0.01")) > 0
    return rows


def build_sales_rows() -> list[dict]:
    rows = []
    sku_count = len(SALES_SKUS)
    for i in range(SALES_TOTAL_ROWS):
        day = SALES_START + timedelta(days=i % 6)
        sku = SALES_SKUS[i % sku_count]
        branch = LOCATION_NAMES[(i // sku_count) % len(LOCATION_NAMES)]
        cost = COST[sku]
        # Deterministic price ~35% gross margin.
        unit_price = (cost * Decimal("1.35")).quantize(Decimal("0.01"))
        qty = 1 + (i % 4)
        rows.append({
            "business_id": BUSINESS_ID,
            "transaction_id": f"TX-CAN-{i + 1:04d}",
            "transaction_date": day.isoformat(),
            "sku": sku,
            "product_name": SKUS[sku],
            "branch": branch,
            "transaction_type": "SALE",
            "quantity": qty,
            "unit_price_sar": f"{unit_price:.2f}",
            "unit_cost_sar": f"{cost:.2f}",
        })
    return rows


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def verify(rows: list[dict]) -> dict:
    total_value = Decimal("0")
    per_location = {}
    for row in rows:
        value = Decimal(row["unit_cost_sar"]) * int(row["quantity_on_hand"])
        loc = row["location_id"]
        per_location[loc] = per_location.get(loc, Decimal("0")) + value
        total_value += value
    total_value = total_value.quantize(Decimal("0.01"))
    dammam = per_location["LOC-DMM"].quantize(Decimal("0.01"))
    return {
        "rows": len(rows),
        "skus": len({r["sku"] for r in rows}),
        "locations": len({r["location_id"] for r in rows}),
        "total_value": total_value,
        "per_location": {k: v.quantize(Decimal("0.01")) for k, v in per_location.items()},
        "dammam_only": dammam,
    }


def main() -> None:
    inv = build_inventory_rows()
    sales = build_sales_rows()

    stats = verify(inv)
    assert stats["rows"] == 45, stats
    assert stats["skus"] == 15, stats
    assert stats["locations"] == 3, stats
    assert stats["total_value"] == Decimal("28892.00"), stats
    assert stats["dammam_only"] == Decimal("17366.00"), stats
    assert stats["total_value"] != stats["dammam_only"], (
        "Canonical Dammam-only subset must DIFFER from business total so the "
        "location-collapse bug is structurally caught."
    )

    sales_days = sorted({r["transaction_date"] for r in sales})
    assert len(sales) == 91, len(sales)
    assert len(sales_days) == 6, sales_days
    assert sales_days == [date(2026, 8, 4).isoformat() for _ in range(6)] or all(
        sales_days[i] == (SALES_START + timedelta(days=i)).isoformat() for i in range(6)
    ), sales_days

    inv_path = REGRESSION_DIR / "Test-NazmOS-Canonical-Inventory.csv"
    sales_path = REGRESSION_DIR / "Test-NazmOS-Canonical-Sales.csv"
    write_csv(inv_path, INVENTORY_HEADER, inv)
    write_csv(sales_path, SALES_HEADER, sales)

    print(f"Wrote canonical inventory: {inv_path}")
    print(f"Wrote canonical sales:     {sales_path}")
    print(f"Inventory rows={stats['rows']} skus={stats['skus']} "
          f"locations={stats['locations']} total_value={stats['total_value']} "
          f"dammam_only={stats['dammam_only']}")
    print(f"Sales rows={len(sales)} days={sales_days}")


if __name__ == "__main__":
    main()