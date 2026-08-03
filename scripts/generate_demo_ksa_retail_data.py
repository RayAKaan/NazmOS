#!/usr/bin/env python3
"""Generate realistic Saudi retail demo data for NazmOS.

This is synthetic data styled after a multi-branch KSA supermarket chain.
It is designed to surface real recovery signals (stockouts, shrinkage,
expiring inventory, price/margin issues) without using any real merchant data.
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
random.seed(42)

# --- Configuration ---
# Generate a recent 30-day window so the Money Audit's velocity calculations
# (anchored to the most recent transaction date) see active sales instead of
# treating the upload as stale history.
END_DATE = date.today()
START_DATE = END_DATE - timedelta(days=30)
BRANCHES = [
    {"name": "Riyadh - Tahlia", "city": "Riyadh"},
    {"name": "Riyadh - Yasmin", "city": "Riyadh"},
    {"name": "Jeddah - Tahlia", "city": "Jeddah"},
    {"name": "Jeddah - Rawdah", "city": "Jeddah"},
    {"name": "Dammam - King Fahd", "city": "Dammam"},
    {"name": "Khobar - Corniche", "city": "Khobar"},
    {"name": "Makkah - Ibrahim Khalil", "city": "Makkah"},
    {"name": "Madinah - Quba", "city": "Madinah"},
]

CATEGORIES = [
    "Dates & Nuts",
    "Dairy & Eggs",
    "Beverages",
    "Snacks & Confectionery",
    "Bakery",
    "Household",
    "Personal Care",
    "Rice & Grains",
    "Oils & Ghee",
    "Frozen Foods",
]

PRODUCTS = [
    # Dates & Nuts
    {"name": "Sukari Dates 1kg", "sku": "DAT-SUK-01", "category": "Dates & Nuts", "cost": 22.0, "price": 38.0, "barcode": "628000100001", "brand": "Qassim Farms", "pack": "1kg", "storage": "ambient", "shelf_life_days": 365},
    {"name": "Ajwa Dates 500g", "sku": "DAT-AJW-02", "category": "Dates & Nuts", "cost": 35.0, "price": 62.0, "barcode": "628000100002", "brand": "Madinah Premium", "pack": "500g", "storage": "ambient", "shelf_life_days": 270},
    {"name": "Mixed Nuts 400g", "sku": "NUT-MIX-03", "category": "Dates & Nuts", "cost": 28.0, "price": 48.0, "barcode": "628000100003", "brand": "AlFaisal", "pack": "400g", "storage": "ambient", "shelf_life_days": 240},
    # Dairy & Eggs
    {"name": "Fresh Milk 1L", "sku": "DAI-MLK-04", "category": "Dairy & Eggs", "cost": 5.5, "price": 8.75, "barcode": "628000200004", "brand": "Nadec", "pack": "1L", "storage": "chilled", "shelf_life_days": 14},
    {"name": "Laban 180ml", "sku": "DAI-LAB-05", "category": "Dairy & Eggs", "cost": 1.5, "price": 2.75, "barcode": "628000200005", "brand": "Nadec", "pack": "180ml", "storage": "chilled", "shelf_life_days": 21},
    {"name": "Eggs Large 30pcs", "sku": "DAI-EGG-06", "category": "Dairy & Eggs", "cost": 18.0, "price": 26.5, "barcode": "628000200006", "brand": "Balady", "pack": "30pcs", "storage": "chilled", "shelf_life_days": 28},
    {"name": "Cheese Slices 200g", "sku": "DAI-CHS-07", "category": "Dairy & Eggs", "cost": 12.0, "price": 19.0, "barcode": "628000200007", "brand": "Puck", "pack": "200g", "storage": "chilled", "shelf_life_days": 90},
    # Beverages
    {"name": "Arabic Coffee 250g", "sku": "BEV-COF-08", "category": "Beverages", "cost": 16.0, "price": 27.0, "barcode": "628000300008", "brand": "Nazmak Coffee", "pack": "250g", "storage": "ambient", "shelf_life_days": 540},
    {"name": "Bottled Water 330ml x12", "sku": "BEV-WTR-09", "category": "Beverages", "cost": 7.0, "price": 11.5, "barcode": "628000300009", "brand": "Nova", "pack": "12x330ml", "storage": "ambient", "shelf_life_days": 730},
    {"name": "Soft Drink Can 330ml", "sku": "BEV-SOD-10", "category": "Beverages", "cost": 1.85, "price": 3.25, "barcode": "628000300010", "brand": "Pepsi", "pack": "330ml", "storage": "ambient", "shelf_life_days": 365},
    {"name": "Orange Juice 1L", "sku": "BEV-JUC-11", "category": "Beverages", "cost": 8.0, "price": 13.5, "barcode": "628000300011", "brand": "Tropicana", "pack": "1L", "storage": "chilled", "shelf_life_days": 45},
    {"name": "Green Tea 100 bags", "sku": "BEV-TEA-12", "category": "Beverages", "cost": 14.0, "price": 22.0, "barcode": "628000300012", "brand": "Lipton", "pack": "100 bags", "storage": "ambient", "shelf_life_days": 730},
    # Snacks & Confectionery
    {"name": "Chocolate Bar 100g", "sku": "SNK-CHO-13", "category": "Snacks & Confectionery", "cost": 5.0, "price": 8.5, "barcode": "628000400013", "brand": "Galaxy", "pack": "100g", "storage": "ambient", "shelf_life_days": 365},
    {"name": "Potato Chips 150g", "sku": "SNK-CHP-14", "category": "Snacks & Confectionery", "cost": 4.0, "price": 6.75, "barcode": "628000400014", "brand": "Lay's", "pack": "150g", "storage": "ambient", "shelf_life_days": 270},
    {"name": "Biscuits 300g", "sku": "SNK-BIS-15", "category": "Snacks & Confectionery", "cost": 6.0, "price": 9.5, "barcode": "628000400015", "brand": "Digestive", "pack": "300g", "storage": "ambient", "shelf_life_days": 365},
    # Bakery
    {"name": "Sliced Bread 600g", "sku": "BAK-BRD-16", "category": "Bakery", "cost": 3.5, "price": 5.75, "barcode": "628000500016", "brand": "Yaumi", "pack": "600g", "storage": "ambient", "shelf_life_days": 7},
    {"name": "Croissant 4pcs", "sku": "BAK-CRO-17", "category": "Bakery", "cost": 8.0, "price": 13.0, "barcode": "628000500017", "brand": "La Poire", "pack": "4pcs", "storage": "ambient", "shelf_life_days": 5},
    # Household
    {"name": "Dishwashing Liquid 1L", "sku": "HOU-DSH-18", "category": "Household", "cost": 9.0, "price": 14.5, "barcode": "628000600018", "brand": "Fairy", "pack": "1L", "storage": "ambient", "shelf_life_days": 1095},
    {"name": "Laundry Powder 2.5kg", "sku": "HOU-LND-19", "category": "Household", "cost": 28.0, "price": 44.0, "barcode": "628000600019", "brand": "Tide", "pack": "2.5kg", "storage": "ambient", "shelf_life_days": 1095},
    {"name": "Trash Bags 30pcs", "sku": "HOU-TRB-20", "category": "Household", "cost": 10.0, "price": 16.0, "barcode": "628000600020", "brand": "Glad", "pack": "30pcs", "storage": "ambient", "shelf_life_days": 1460},
    # Personal Care
    {"name": "Shampoo 400ml", "sku": "PER-SHM-21", "category": "Personal Care", "cost": 18.0, "price": 29.0, "barcode": "628000700021", "brand": "Head & Shoulders", "pack": "400ml", "storage": "ambient", "shelf_life_days": 1095},
    {"name": "Toothpaste 100ml", "sku": "PER-PST-22", "category": "Personal Care", "cost": 7.0, "price": 11.5, "barcode": "628000700022", "brand": "Colgate", "pack": "100ml", "storage": "ambient", "shelf_life_days": 1095},
    {"name": "Soap Bar 4pcs", "sku": "PER-SOP-23", "category": "Personal Care", "cost": 9.0, "price": 14.0, "barcode": "628000700023", "brand": "Lux", "pack": "4pcs", "storage": "ambient", "shelf_life_days": 1095},
    # Rice & Grains
    {"name": "Basmati Rice 5kg", "sku": "RIC-BAS-24", "category": "Rice & Grains", "cost": 32.0, "price": 49.0, "barcode": "628000800024", "brand": "India Gate", "pack": "5kg", "storage": "ambient", "shelf_life_days": 730},
    {"name": "Oats 1kg", "sku": "RIC-OAT-25", "category": "Rice & Grains", "cost": 12.0, "price": 19.5, "barcode": "628000800025", "brand": "Quaker", "pack": "1kg", "storage": "ambient", "shelf_life_days": 540},
    # Oils & Ghee
    {"name": "Cooking Oil 1.8L", "sku": "OIL-COK-26", "category": "Oils & Ghee", "cost": 16.0, "price": 25.0, "barcode": "628000900026", "brand": "Afia", "pack": "1.8L", "storage": "ambient", "shelf_life_days": 540},
    {"name": "Butter Ghee 800g", "sku": "OIL-GHE-27", "category": "Oils & Ghee", "cost": 34.0, "price": 52.0, "barcode": "628000900027", "brand": "Almarai", "pack": "800g", "storage": "ambient", "shelf_life_days": 365},
    # Frozen Foods
    {"name": "Frozen Chicken 900g", "sku": "FRZ-CHI-28", "category": "Frozen Foods", "cost": 19.0, "price": 29.0, "barcode": "628001000028", "brand": "Almarai", "pack": "900g", "storage": "frozen", "shelf_life_days": 365},
    {"name": "Frozen Fries 1kg", "sku": "FRZ-FRI-29", "category": "Frozen Foods", "cost": 11.0, "price": 17.5, "barcode": "628001000029", "brand": "McCain", "pack": "1kg", "storage": "frozen", "shelf_life_days": 540},
    {"name": "Ice Cream 1L", "sku": "FRZ-ICE-30", "category": "Frozen Foods", "cost": 14.0, "price": 22.0, "barcode": "628001000030", "brand": "Ben & Jerry's", "pack": "1L", "storage": "frozen", "shelf_life_days": 365},
]

PAYMENT_METHODS = ["mada", "cash", "visa", "mastercard", "apple_pay"]


def generate_sales(rows: int = 150) -> list[dict]:
    sales = []
    current = START_DATE
    delta = (END_DATE - START_DATE).days
    while len(sales) < rows:
        # Generate 5-12 transactions per day
        daily_transactions = random.randint(5, 12)
        for _ in range(daily_transactions):
            branch = random.choice(BRANCHES)
            product = random.choice(PRODUCTS)
            qty = random.choices(
                [1, 2, 3, 4, 5, 6, 8, 10, 12],
                weights=[40, 25, 15, 8, 5, 3, 2, 1, 1]
            )[0]
            # Add occasional realistic pricing errors that trigger margin leakage.
            # Most transactions use the normal shelf price; a small fraction are
            # discounted too aggressively (below target margin or even below cost).
            price_roll = random.random()
            if price_roll < 0.05:
                # Severe pricing error: sold below cost
                unit_price = round(max(0.1, product["cost"] * 0.85), 2)
            elif price_roll < 0.12:
                # Thin margin: below the 22% target
                unit_price = round(product["cost"] * 1.10, 2)
            else:
                unit_price = product["price"]
            total = round(qty * unit_price, 2)
            cost = round(qty * product["cost"], 2)
            payment = random.choice(PAYMENT_METHODS)
            tx_id = f"TX-{current.isoformat()}-{len(sales)+1:04d}"
            sales.append({
                "Date": current.isoformat(),
                "Transaction ID": tx_id,
                "Branch": branch["name"],
                "City": branch["city"],
                "Product": product["name"],
                "SKU": product["sku"],
                "Category": product["category"],
                "Qty": qty,
                "Unit Price SAR": unit_price,
                "Total SAR": total,
                "Cost SAR": cost,
                "Payment Method": payment,
            })
            if len(sales) >= rows:
                break
        current += timedelta(days=1)
        if current > END_DATE:
            current = START_DATE
    return sales


def generate_inventory() -> list[dict]:
    inv = []
    today = END_DATE
    # Deliberately underprice a couple of products so margin leakage is
    # detectable by construction (shelf price below the 22% target margin).
    underpriced_skus = set(random.sample([p["sku"] for p in PRODUCTS], k=2))

    for product in PRODUCTS:
        # Base stock between 0 and 200, weighted toward mid levels
        base_stock = random.choices(
            range(0, 201, 10),
            weights=[5 if 20 <= x <= 100 else 2 for x in range(0, 201, 10)]
        )[0]
        # Intentional stockouts for high-velocity items to create recovery signals
        if product["sku"] in ("DAT-SUK-01", "BEV-WTR-09", "RIC-BAS-24") and random.random() < 0.3:
            base_stock = 0
        # Intentional overstock for perishables to create expiry risk
        if product["storage"] in ("chilled", "frozen", "bakery") and random.random() < 0.25:
            base_stock = random.randint(80, 150)

        # Use a below-target shelf price for the underpriced SKUs so the audit
        # surfaces margin leakage; all other products keep their healthy margin.
        if product["sku"] in underpriced_skus:
            shelf_price = round(product["cost"] * 1.12, 2)
        else:
            shelf_price = product["price"]

        max_days = max(7, product["shelf_life_days"])
        expiry = today + timedelta(days=random.randint(7, max_days))
        # Force some near-expiry items
        if product["storage"] in ("chilled", "bakery") and random.random() < 0.2:
            expiry = today + timedelta(days=random.randint(3, min(14, max_days)))

        inv.append({
            "Product": product["name"],
            "SKU": product["sku"],
            "Category": product["category"],
            "Brand": product["brand"],
            "Pack Size": product["pack"],
            "Current Stock": base_stock,
            "Cost Price SAR": product["cost"],
            "Shelf Price SAR": shelf_price,
            "Barcode": product["barcode"],
            "Storage Type": product["storage"],
            "Expiry Date": expiry.isoformat(),
            "Batch Number": f"{product['sku'][:3]}-B{random.randint(1, 5):02d}",
            "Reorder Level": random.randint(10, 30),
            "Supplier": random.choice(["Nazmak Distribution", "Tamimi Supply", "Almarai Direct", "Panda Logistics"]),
        })
    return inv


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    sales = generate_sales(rows=150)
    inventory = generate_inventory()

    sales_path = ROOT / "sample_data" / "demo_ksa_retail_sales_q3_2026.csv"
    inv_path = ROOT / "sample_data" / "demo_ksa_retail_inventory_aug_2026.csv"

    write_csv(sales_path, sales)
    write_csv(inv_path, inventory)

    print(f"Wrote {len(sales)} sales rows to {sales_path}")
    print(f"Wrote {len(inventory)} inventory rows to {inv_path}")

    # Print a few recovery signals baked into the data
    stockouts = [p for p in inventory if p["Current Stock"] == 0]
    near_expiry = [p for p in inventory if p["Storage Type"] in ("chilled", "bakery")]
    print(f"Intentional stockouts: {len(stockouts)}")
    print(f"Perishables with near/expiry risk: {len(near_expiry)}")


if __name__ == "__main__":
    main()
