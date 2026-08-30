#!/usr/bin/env python3
"""NAZMOS CORE REALITY TEST V1 — controlled dataset generator + runner.

Generates a deterministic, recently-anchored (ends today) sales + inventory
dataset for ~18 SKUs designed to surface the product scenarios, uploads it
through the real customer workflow, and runs the Money Audit.
"""
from __future__ import annotations

import csv
import os
import random
import json
import time
from datetime import date, timedelta
from pathlib import Path

random.seed(20260829)
END = date.today()
DAYS = 105  # history window (3.5 months so monthly-concentration seasonal works)
START = END - timedelta(days=DAYS)

BRANCH = "Riyadh - Tahlia"
CITY = "Riyadh"

# (sku, name, category, cost, price, stock, reorder_level, supplier, per_day_recent, per_day_prior, recent_only)
# recent = last 30 days, prior = the 30 days before that. daily units.
SKUS = [
    # 1. FAST mover — high velocity, in stock -> REORDER
    {"sku":"RIC-BAS-24","name":"Basmati Rice 5kg","cat":"Rice & Grains","cost":32.0,"price":49.0,"stock":8,"reorder":15,"supplier":"India Gate Supply","recent":1.6,"prior":1.5,"start_recent":40},
    # 2. DEAD stock — no sales for 90+ days, has stock -> discount/recovery
    {"sku":"HOU-TRB-20","name":"Trash Bags 30pcs","cat":"Household","cost":10.0,"price":16.0,"stock":150,"reorder":5,"supplier":"Glad Dist","recent":0.0,"prior":0.0,"start_recent":0,"dead":True},
    # 3. SLOW MOVING — near zero velocity, thin stock
    {"sku":"PER-PST-22","name":"Toothpaste 100ml","cat":"Personal Care","cost":7.0,"price":11.5,"stock":2,"reorder":6,"supplier":"Colgate KSA","recent":0.4,"prior":0.8,"start_recent":80},
    # 4. SEASONAL — strong monthly concentration (Ramadan dates), high stock
    {"sku":"DAT-SUK-01","name":"Sukari Dates 1kg","cat":"Dates & Nuts","cost":22.0,"price":38.0,"stock":200,"reorder":20,"supplier":"Qassim Farms","recent":1.0,"prior":3.0,"start_recent":95,"seasonal":True},
    # 5. OVERSTOCK — healthy steady demand but huge stock (>45 days supply)
    {"sku":"BEV-WTR-09","name":"Bottled Water 12x330ml","cat":"Beverages","cost":7.0,"price":11.5,"stock":900,"reorder":60,"supplier":"Nova Bottlers","recent":6.0,"prior":6.0,"start_recent":45},
    # 6. STOCKOUT risk — fast demand, near-zero stock (<5 days supply)
    {"sku":"DAI-MLK-04","name":"Fresh Milk 1L","cat":"Dairy & Eggs","cost":5.5,"price":8.75,"stock":6,"reorder":40,"supplier":"Nadec Dairy","recent":8.0,"prior":8.0,"start_recent":30,"stockout":True},
    # 7. inbound-PO-lookalike (low stock + confirmed inbound via PO later) — skip CSV, note
    # 8. Supplier reliability — low reliability supplier with thin margin
    {"sku":"OIL-GHE-27","name":"Butter Ghee 800g","cat":"Oils & Ghee","cost":34.0,"price":52.0,"stock":30,"reorder":12,"supplier":"Unreliable Grocers Co","recent":1.2,"prior":1.0,"start_recent":60},
    # 9. Promotional — recent spike from a low base (demand sharp recent-only rise)
    {"sku":"SNK-CHO-13","name":"Chocolate Bar 100g","cat":"Snacks","cost":5.0,"price":8.5,"stock":120,"reorder":50,"supplier":"Galaxy ME","recent":5.0,"prior":1.0,"start_recent":35,"promo":True},
    # 10. Strategic product — preserve (via constraints), slower but valuable
    {"sku":"DAT-AJW-02","name":"Ajwa Dates 500g","cat":"Dates & Nuts","cost":35.0,"price":62.0,"stock":80,"reorder":10,"supplier":"Madinah Premium","recent":0.3,"prior":0.5,"start_recent":90,"strategic":True},
    # 11. Constrained purchase — fast DEMAND but MOQ/cash-constrained (supplier MOQ, low cash budget)
    {"sku":"RIC-OAT-25","name":"Oats 1kg","cat":"Rice & Grains","cost":12.0,"price":19.5,"stock":3,"reorder":25,"supplier":"Quaker KSA","recent":4.0,"prior":4.0,"start_recent":30,"constrained":True},
    # 12. Branch transfer — high stock in A, demand in B. (multi-branch in transactions)
    {"sku":"HOU-LND-19","name":"Laundry Powder 2.5kg","cat":"Household","cost":28.0,"price":44.0,"stock":160,"reorder":6,"supplier":"Tide GCC","recent":0.5,"prior":0.5,"start_recent":90,"transfer":True},
    # 13. Ambiguous / context-heavy — declining velocity, moderate stock
    {"sku":"BEV-COF-08","name":"Arabic Coffee 250g","cat":"Beverages","cost":16.0,"price":27.0,"stock":45,"reorder":20,"supplier":"Nazmak Coffee","recent":0.5,"prior":1.2,"start_recent":70,"declining":True},
    # 14. DO_NOTHING — healthy steady stock, comfortable supply
    {"sku":"BEV-TEA-12","name":"Green Tea 100 bags","cat":"Beverages","cost":14.0,"price":22.0,"stock":40,"reorder":15,"supplier":"Lipton KSA","recent":1.0,"prior":1.0,"start_recent":55},
    # 15. healthy low stock price/cost healthy
    {"sku":"PER-SHM-21","name":"Shampoo 400ml","cat":"Personal Care","cost":18.0,"price":29.0,"stock":20,"reorder":15,"supplier":"H&S KSA","recent":1.1,"prior":1.1,"start_recent":50},
    # 16. chilled short shelf-life fast
    {"sku":"DAI-EGG-06","name":"Eggs Large 30pcs","cat":"Dairy & Eggs","cost":18.0,"price":26.5,"stock":25,"reorder":30,"supplier":"Balady Farm","recent":3.0,"prior":3.0,"start_recent":25},
    # 17. frozen medium
    {"sku":"FRZ-CHI-28","name":"Frozen Chicken 900g","cat":"Frozen Foods","cost":19.0,"price":29.0,"stock":40,"reorder":25,"supplier":"Almarai Frozen","recent":2.0,"prior":2.0,"start_recent":35},
    # 18. slow thin healthy
    {"sku":"SNK-BIS-15","name":"Biscuits 300g","cat":"Snacks","cost":6.0,"price":9.5,"stock":18,"reorder":12,"supplier":"Digestive KSA","recent":0.8,"prior":0.8,"start_recent":45},
]


def daily_qty(sku: dict, days_ago: int) -> float:
    """Return expected units sold on the day <days_ago> before END for a SKU."""
    if sku.get("dead"):
        return 0.0
    # Within recent window (last 30 days) use recent rate
    if days_ago < 30:
        rate = sku["recent"]
        # promo: recent-only spike with randomness
        if sku.get("promo") and days_ago < 14:
            rate = sku["recent"] * (1.0 + 0.6 * random.random())
        return rate
    # prior window (30-60 days ago)
    if days_ago < 60:
        rate = sku["prior"]
        # seasonal: build the concentration over the whole window; keep steady
        if sku.get("seasonal") and days_ago < 30:
            rate = sku["recent"]
        return rate
    # older window (60-105) — prior-ish, some for weekly concentration
    rate = sku["prior"]
    if sku.get("seasonal"):
        rate = sku["prior"]
    if sku.get("declining"):
        rate = sku["prior"] * 0.5
    return rate


def build_sales(path: Path):
    rows = []
    tx_id = 0
    for days_ago in range(DAYS, -1, -1):
        d = END - timedelta(days=days_ago)
        if d.weekday() >= 5:  # weekend (KSA weekend Fri/Sat: 4,5)
            weekend = 1.3
        else:
            weekend = 1.0
        for sku in SKUS:
            q = daily_qty(sku, days_ago) * weekend
            if q <= 0:
                continue
            n = int(round(q))
            if n <= 0:
                continue
            tx_id += 1
            unit = sku["cost"] * (1.28)  # ~22% margin
            rows.append({
                "Date": d.isoformat(),
                "Transaction ID": f"TX-RT-{tx_id:06d}",
                "Branch": BRANCH,
                "City": CITY,
                "Product": sku["name"],
                "SKU": sku["sku"],
                "Category": sku["cat"],
                "Qty": n,
                "Unit Price SAR": f"{unit:.2f}",
                "Total SAR": f"{round(unit * n, 2):.2f}",
                "Cost SAR": f"{sku['cost'] * n:.2f}",
                "Payment Method": "mada",
            })
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def build_inventory(path: Path):
    rows = []
    for sku in SKUS:
        rows.append({
            "Product": sku["name"],
            "SKU": sku["sku"],
            "Category": sku["cat"],
            "Brand": "Test",
            "Pack Size": "1",
            "Current Stock": sku["stock"],
            "Cost Price SAR": f"{sku['cost']:.2f}",
            "Shelf Price SAR": f"{sku['price']:.2f}",
            "Barcode": f"6{sku['sku'].replace('-','')}",
            "Storage Type": "ambient",
            "Expiry Date": (END + timedelta(days=180)).isoformat(),
            "Batch Number": f"B-{sku['sku'][:3]}",
            "Reorder Level": sku["reorder"],
            "Supplier": sku["supplier"],
        })
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    import sys
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("reality_fixture")
    outdir.mkdir(parents=True, exist_ok=True)
    sales = build_sales(outdir / "reality_sales.csv")
    inv = build_inventory(outdir / "reality_inventory.csv")
    print(f"wrote sales({sales}) inventory({inv}) to {outdir}")
    print("sku list:", [s['sku'] for s in SKUS])
