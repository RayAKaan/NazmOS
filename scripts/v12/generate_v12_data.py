"""V12 AI-OFF Reality Test - Phase 6 data generator.

Produces a clean, deterministic, 100+ SKU dataset for a fresh supermarket such
that EVERY GT SKU lands on its intended classification + deterministic decision
(as authored in results/v12/ground_truth.json) once the data is ingested.

KEY FACT: money_audit_service.compute_money_audit anchors on
`period_end = MAX(transaction_at)`. So we fix T0 = 2026-06-15 as the newest
transaction date. Then with anchor A = T0:
  - qty_30d   = SUM(qty) for date in [A-30, A]
  - qty_prior = SUM(qty) for date in [A-60, A-30)
  - monthly   = per-calendar-month SUM(qty) for date in [A-90, A]
  - daily     = qty_30d / 30
  - days_since_last_sale = (A - last_sale_date).days  (None if no sale)

The script ports the EXACT classify_inventory + deterministic_decision_for_item
logic (copied from the V12 codebase) to self-verify every GT SKU before upload.

Run (host):  python scripts/v12/generate_v12_data.py
Outputs:      sample_data/v12/sales_history.csv
              sample_data/v12/inventory_snapshot.csv
              sample_data/v12/master_expected.csv   (per-SKU expected class+decision)
              sample_data/v12/generator_selfcheck.txt
"""
import csv
import json
import os
from datetime import date, timedelta
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GT_PATH = os.path.join(ROOT, "results", "v12", "ground_truth.json")
OUT_DIR = os.path.join(ROOT, "sample_data", "v12")
os.makedirs(OUT_DIR, exist_ok=True)

T0 = date(2026, 6, 15)


def days_ago(n):
    return T0 - timedelta(days=n)


# ---------------- ported oracle (exact copy of V12 code) ----------------
def classify_inventory(*, stock, recent_qty_30, prior_qty_30, days_since_last_sale,
                       inventory_age_days=None, seasonal_index=None, product_age_days=None,
                       monthly_concentrations=None):
    from decimal import Decimal as D
    if product_age_days is not None and product_age_days < 30:
        return "NEW"
    daily = recent_qty_30 / D("30") if recent_qty_30 > 0 else D("0")
    if recent_qty_30 > 0 and monthly_concentrations and len(monthly_concentrations) >= 2:
        total = sum(max(m, D("0")) for m in monthly_concentrations)
        if total > 0:
            peak = max(monthly_concentrations)
            concentration = peak / total
            if concentration >= D("0.60"):
                return "SEASONAL"
    if seasonal_index is not None and seasonal_index >= D("1.5") and recent_qty_30 < prior_qty_30:
        return "SEASONAL"
    if recent_qty_30 <= 0:
        is_dormant = (days_since_last_sale is None) or (
            days_since_last_sale is not None and days_since_last_sale >= 60)
        if is_dormant and prior_qty_30 <= 0:
            return "DEAD"
        return "UNKNOWN"
    if stock <= 0 and daily > 0 and daily < D("3"):
        return "SLOW MOVING"
    if stock <= 0:
        return "HEALTHY"
    if daily >= D("1"):
        return "FAST"
    return "HEALTHY"


def deterministic_decision_for_item(item):
    cls = item["classification"]
    if item["current_stock"] == 0 and item["daily_velocity"] > 0:
        if item["confirmed_inbound_qty"] > 0:
            return "DO_NOTHING"
        return "REORDER"
    if item["confirmed_inbound_qty"] > 0 and item["current_stock"] == 0:
        if item["days_since_last_sale"] and item["days_since_last_sale"] > 120:
            return "REORDER"
    if cls == "DEAD":
        return "DISCOUNT" if item["current_stock"] > 0 else "DO_NOTHING"
    if cls == "SEASONAL":
        if item["current_stock"] > 0 and item["daily_velocity"] == 0:
            if item.get("monthly_concentration_peak") and item["monthly_concentration_peak"] > 0.5:
                return "DO_NOTHING"
        if item.get("overstock_days") and item["overstock_days"] > 90:
            return "DO_NOTHING"
        if item.get("monthly_concentration_peak") and item["monthly_concentration_peak"] > 0.7:
            return "DO_NOTHING"
        return "REORDER"
    if cls == "SLOW MOVING":
        return "DISCOUNT" if item["current_stock"] > 0 else "REORDER"
    if cls == "FAST":
        if item.get("stockout_days"):
            return "REORDER"
        if item.get("overstock_days") and item["overstock_days"] > 90:
            return "TRANSFER"
        return "DO_NOTHING"
    if cls == "UNKNOWN":
        if item["current_stock"] == 0 and item["daily_velocity"] > 0:
            return "REORDER"
        if item["current_stock"] == 0 and item["daily_velocity"] == 0:
            return "DO_NOTHING"
        if item["current_stock"] > 0 and item["days_since_last_sale"] and item["days_since_last_sale"] > 45:
            return "DISCOUNT"
        if item["current_stock"] > 0 and item["recent_velocity_per_day"] > 0:
            return "DO_NOTHING"
        return "MANUAL_REVIEW"
    if cls == "NEW":
        return "DO_NOTHING"
    if item.get("overstock_days") and item["overstock_days"] > 120:
        return "RECOVERY_MATCH"
    if item.get("stockout_days"):
        return "REORDER"
    return "DO_NOTHING"


# ---------------- row emission ----------------
def sale_rows(base_date, qty, *, unit_price, cost_price, name, sku, spread=1):
    qty = int(qty)
    spread = max(1, min(int(spread), qty))
    if qty <= 0 or spread <= 0:
        return []
    days = [base_date - timedelta(days=i) for i in range(spread)]
    days.reverse()
    base_amount = qty // spread
    remainder = qty % spread
    rows = []
    for i, d in enumerate(days):
        amt = base_amount + (1 if i < remainder else 0)
        if amt > 0:
            rows.append({
                "transaction_at": d.isoformat(), "item_name": name, "item_sku": sku,
                "quantity": amt, "unit_price": f"{unit_price:.2f}",
                "cost_price": f"{cost_price:.2f}", "total_amount": f"{amt * unit_price:.2f}",
                "transaction_type": "sale",
            })
    return rows


def place_in_month(month_start, qty, unit_price, cost_price, name, sku):
    import calendar
    last_day = calendar.monthrange(month_start.year, month_start.month)[1]
    end = min(T0, date(month_start.year, month_start.month, last_day))
    if end < month_start:
        return []
    spread = max(1, min(15, qty))
    return sale_rows(end, qty, unit_price=unit_price, cost_price=cost_price,
                     name=name, sku=sku, spread=spread)


def recent_month_buckets(window_days):
    buckets = []
    d = days_ago(window_days)
    cur = date(d.year, d.month, 1)
    while cur <= T0:
        buckets.append(cur)
        y, m = (cur.year + 1, 1) if cur.month == 12 else (cur.year, cur.month + 1)
        cur = date(y, m, 1)
    return buckets


# ---------------- per-SKU data construction targeting expected classification ----
def build_sku(c):
    """Numeric-driven: place each GT case's qty_prior_30d / qty_30d / monthly
    concentrations / current_stock exactly in the correct date windows relative
    to anchor A=T0, so the resulting classification follows the GT-designed class."""
    sku = c["sku"]
    name = f"GT {sku}"
    i = c["inputs"]
    exp_cls = c["expected_classification"]
    cost = float(i["cost_price"]); sell = float(i["sell_price"])
    stock = int(i["current_stock"])
    ciq = int(i.get("confirmed_inbound_qty", 0))
    qty30 = int(i.get("qty_30d", 0))
    qtyprior = int(i.get("qty_prior_30d", 0))
    dsls = i.get("days_since_last_sale")
    monthly = i.get("monthly_concentrations") or []
    rows = []

    if exp_cls == "SEASONAL":
        # Realize monthly concentrations across the trailing 90-day month buckets,
        # and ALSO place qty30 within the last 30 days (recent_qty_30>0 is required
        # for the seasonal branch to trigger).
        buckets = recent_month_buckets(90)
        for idx, b in enumerate(buckets):
            tar = monthly[idx] if idx < len(monthly) else 0
            if tar and tar > 0:
                rows += place_in_month(b, int(tar), sell, cost, name, sku)
        if qty30 > 0 and not any((T0 - date.fromisoformat(r["transaction_at"])).days <= 30 for r in rows):
            rows += sale_rows(days_ago(min(dsls if dsls is not None else 2, 5)), qty30,
                              unit_price=sell, cost_price=cost, name=name, sku=sku, spread=min(15, qty30))
    elif exp_cls in ("DEAD", "UNKNOWN"):
        # Still need qty_prior in (A-60,A-30] if designed, and NO sales in last 30d.
        if qtyprior > 0:
            rows += sale_rows(days_ago(40), qtyprior, unit_price=sell, cost_price=cost, name=name, sku=sku, spread=min(15, qtyprior))
        elif monthly and any(m and m > 0 for m in monthly):
            # place the oldest-month spike >60 days ago (outside prior window)
            buckets = recent_month_buckets(90)
            first = next((b for b, m in zip(buckets, monthly) if m and m > 0), None)
            if first is not None:
                rows += place_in_month(first, int(max(m for m in monthly if m and m > 0)), sell, cost, name, sku)
    elif exp_cls == "SLOW MOVING":
        # stock<=0, daily>0 and <3  => qty30 modest, place in last 30d
        if qty30 > 0:
            rows += sale_rows(days_ago(min(dsls if dsls is not None else 1, 5)), qty30,
                              unit_price=sell, cost_price=cost, name=name, sku=sku, spread=min(10, qty30))
        if qtyprior > 0:
            rows += sale_rows(days_ago(40), qtyprior, unit_price=sell, cost_price=cost, name=name, sku=sku, spread=min(10, qtyprior))
    elif exp_cls == "FAST":
        if qty30 > 0:
            rows += sale_rows(days_ago(min(dsls if dsls is not None else 1, 5)), qty30,
                              unit_price=sell, cost_price=cost, name=name, sku=sku, spread=min(20, qty30))
        if qtyprior > 0:
            rows += sale_rows(days_ago(40), qtyprior, unit_price=sell, cost_price=cost, name=name, sku=sku, spread=min(20, qtyprior))
    else:  # HEALTHY
        if qty30 > 0:
            rows += sale_rows(days_ago(min(dsls if dsls is not None else 2, 5)), qty30,
                              unit_price=sell, cost_price=cost, name=name, sku=sku, spread=min(20, qty30))
        if qtyprior > 0:
            rows += sale_rows(days_ago(40), qtyprior, unit_price=sell, cost_price=cost, name=name, sku=sku, spread=min(20, qtyprior))

    item = {
        "sku": sku, "name": name, "stock": stock, "cost": cost, "sell": sell, "ciq": ciq,
        "reorder": max(0, int(i.get("qty_30d", 0) * 1.5 // 30)), "maxstock": max(10, int(stock) * 5),
    }
    return rows, item


# ---------------- compute resulting classification from rows ----------------
def compute_from_rows(rows, item):
    qty30 = 0; prior = 0; months = defaultdict(int)
    last_sale = None
    for r in rows:
        d = date.fromisoformat(r["transaction_at"]); q = int(r["quantity"])
        if (T0 - d).days <= 30:
            qty30 += q
            if last_sale is None or d > last_sale:
                last_sale = d
        if 30 < (T0 - d).days <= 60:
            prior += q
        if (T0 - d).days <= 90:
            months[(d.year, d.month)] += q
    dsls = (T0 - last_sale).days if last_sale else None
    monthly_conc = [months.get((T0.year, T0.month), 0)]
    # build buckets in last 90 days ordered by recency
    buckets = recent_month_buckets(90)
    monthly_conc = [months.get((b.year, b.month), 0) for b in buckets]
    cls = classify_inventory(
        stock=item["stock"], recent_qty_30=qty30, prior_qty_30=prior,
        days_since_last_sale=dsls, monthly_concentrations=monthly_conc)
    daily = qty30 / 30.0
    # stockout_days / overstock_days for decision
    stockout_days = None
    overstock_days = None
    if daily > 0:
        cov = item["stock"] / daily if item["stock"] > 0 else 0
        if item["stock"] == 0:
            stockout_days = 0
        elif cov <= 1:
            stockout_days = 1
        if cov > 30:
            overstock_days = int(cov)
    peak = max(monthly_conc) if monthly_conc else 0
    tot = sum(monthly_conc)
    peak_ratio = (peak / tot) if tot else 0
    dec = deterministic_decision_for_item({
        "classification": cls, "current_stock": item["stock"],
        "daily_velocity": daily, "confirmed_inbound_qty": item["ciq"],
        "days_since_last_sale": dsls, "monthly_concentration_peak": peak_ratio,
        "overstock_days": overstock_days, "stockout_days": stockout_days,
        "recent_velocity_per_day": daily,
    })
    return cls, dec, qty30, prior, dsls, monthly_conc


# ---------------- filler (non-GT) ----------------
import random
from decimal import Decimal as _D


def generate_filler(n):
    rng = random.Random(20260615)
    name_pool = ["Rice 5kg", "Cooking Oil 3L", "Sugar 2kg", "Flour 5kg", "Pasta 500g",
                 "Mayo 750ml", "Ketchup 1kg", "Olive Oil 1L", "Tea 400g", "Coffee 250g",
                 "Milk 1L", "Yogurt 500g", "Cheddar 1kg", "Butter 500g", "Eggs 30pk",
                 "Chicken 1kg", "Beef 1kg", "Fish 800g", "Cucumber 1kg", "Tomato 1kg",
                 "Potato 5kg", "Onion 5kg", "Banana 1kg", "Apple 1kg", "Orange 1kg",
                 "Cola 1.5L", "Water 6pk", "Juice 1L", "Chips 24pk", "Biscuits 400g",
                 "Chocolate 100g", "Candy 500g", "Detergent 3kg", "Soap 6pk", "Shampoo 400ml",
                 "Toothpaste 3pk", "Tissue 6pk", "Wipes 80pk", "Diapers M40", "Formula 900g",
                 "Salt 1kg", "Spices 100g", "Honey 500g", "Jam 400g", "Cereal 500g",
                 "Oats 1kg", "Nuts 300g", "Dried Fruit 400g", "Canned Beans 400g", "Tuna 180g",
                 "Instant Noodles 5pk", "Frozen Veg 1kg", "Ice Cream 2L", "Pizza Frozen",
                 "Spring Onion", "Lettuce", "Zucchini", "Eggplant", "Mango 1kg",
                 "Grapes 500g", "Dates 1kg", "Pomegranate", "Baby Carrots",
                 "Cashews 200g", "Almonds 200g", "Pistachio 250g", "Hazelnut 250g",
                 "Sesame Paste", "Vinegar 1L", "Soy Sauce 500ml", "Stock Cubes 12pk",
                 "Garlic 1kg", "Ginger 500g", "Turmeric 200g", "Paprika 100g", "Lemons 1kg",
                 "Limes 500g", "Mint", "Parsley", "Basil"]
    fillers = []
    for idx in range(n):
        sku = f"V12-FIL-{idx:03d}"
        name = name_pool[idx % len(name_pool)]
        cost = round(rng.uniform(2.0, 45.0), 2)
        sell = round(cost * rng.uniform(1.15, 1.6), 2)
        pattern = rng.choice(["fast", "dead", "slow", "seasonal", "healthy", "stockout", "overstock"])
        rows = []
        stock = int(rng.choice([5, 15, 40, 80, 150, 600]))
        master_tag = "FAST"
        if pattern == "fast":
            rows += sale_rows(days_ago(1), rng.randint(70, 240), unit_price=sell, cost_price=cost, name=name, sku=sku, spread=20)
            rows += sale_rows(days_ago(40), rng.randint(70, 240), unit_price=sell, cost_price=cost, name=name, sku=sku, spread=20)
            master_tag = "FAST"
        elif pattern == "dead":
            rows += sale_rows(days_ago(90), rng.randint(3, 10), unit_price=sell, cost_price=cost, name=name, sku=sku, spread=3)
            rows += sale_rows(days_ago(150), rng.randint(3, 8), unit_price=sell, cost_price=cost, name=name, sku=sku, spread=3)
            stock = rng.randint(80, 600)
            master_tag = "DEAD"
        elif pattern == "slow":
            rows += sale_rows(days_ago(5), rng.randint(5, 25), unit_price=sell, cost_price=cost, name=name, sku=sku, spread=6)
            rows += sale_rows(days_ago(40), rng.randint(5, 25), unit_price=sell, cost_price=cost, name=name, sku=sku, spread=6)
            master_tag = "SLOW"
        elif pattern == "healthy":
            rows += sale_rows(days_ago(3), rng.randint(25, 60), unit_price=sell, cost_price=cost, name=name, sku=sku, spread=10)
            rows += sale_rows(days_ago(40), rng.randint(25, 60), unit_price=sell, cost_price=cost, name=name, sku=sku, spread=10)
            master_tag = "FAST"
        elif pattern == "stockout":
            rows += sale_rows(days_ago(1), rng.randint(70, 150), unit_price=sell, cost_price=cost, name=name, sku=sku, spread=15)
            rows += sale_rows(days_ago(40), rng.randint(70, 150), unit_price=sell, cost_price=cost, name=name, sku=sku, spread=15)
            stock = 0
            master_tag = "STOCKOUT"
        elif pattern == "overstock":
            rows += sale_rows(days_ago(3), rng.randint(25, 45), unit_price=sell, cost_price=cost, name=name, sku=sku, spread=10)
            rows += sale_rows(days_ago(40), rng.randint(25, 45), unit_price=sell, cost_price=cost, name=name, sku=sku, spread=10)
            stock = 2000
            master_tag = "OVERSTOCK"
        else:  # seasonal
            months = recent_month_buckets(90)
            rows += place_in_month(months[0], rng.randint(100, 200), sell, cost, name, sku)
            rows += place_in_month(months[1] if len(months) > 1 else months[0], rng.randint(8, 20), sell, cost, name, sku)
            rows += sale_rows(days_ago(3), 6, unit_price=sell, cost_price=cost, name=name, sku=sku, spread=3)
            master_tag = "SEASONAL"
        item = {"sku": sku, "name": name, "stock": stock, "cost": cost, "sell": sell,
                "ciq": 0, "reorder": int(rng.choice([5, 10, 20])), "maxstock": max(10, stock) * 4}
        cls, dec, *_ = compute_from_rows(rows, item)
        fillers.append({
            "sku": sku, "name": name, "cost": cost, "sell": sell, "stock": stock,
            "rows": rows, "cls": cls, "dec": dec, "master_tag": master_tag,
            "reorder": item["reorder"], "maxstock": item["maxstock"],
            "supplier": rng.choice(["Global Foods Traders", "Al Baraka Supply", "Riyadh Distributors"]),
        })
    return fillers


CATEGORY = {
    "DEAD": "Home & Durable", "FAST": "Groceries", "SLOW": "Beverages",
    "SEASONAL": "Seasonal", "STOCKOUT": "Groceries", "PO": "Groceries",
    "OVERSTOCK": "Bulk", "GROWTH": "Fresh", "MARGIN": "Impulse",
    "OWNER_CONSTRAINT": "Strategic",
}


def main():
    gt = json.load(open(GT_PATH, encoding="utf-8"))
    gt_cases = gt["cases"]

    sales_rows = []
    master_rows = []
    selfcheck = []
    failures = 0

    for c in gt_cases:
        rows, item = build_sku(c)
        cls, dec, q30, prior, dsls, months = compute_from_rows(rows, item)
        ok = (cls == c["expected_classification"]) and (dec == c["expected_decision"])
        if not ok:
            failures += 1
        selfcheck.append({"sku": c["sku"], "got_cls": cls, "exp_cls": c["expected_classification"],
                          "got_dec": dec, "exp_dec": c["expected_decision"], "ok": ok,
                          "q30": q30, "prior": prior, "dsls": dsls, "months": months})
        sales_rows.extend(rows)
        master_rows.append({"sku": c["sku"], "expected_classification": cls,
                            "expected_decision": dec, "category": c["category"],
                            "expected_primary_action": c["expected_primary_action"],
                            "financial_expectation": c["financial_expectation"]})

    # filler
    fillers = generate_filler(80)
    filler_master = []
    for f in fillers:
        sales_rows.extend(f["rows"])
        tag = f["master_tag"]
        filler_master.append({"sku": f["sku"], "expected_classification": f["cls"],
                              "expected_decision": f["dec"], "category": tag,
                              "expected_primary_action": "none", "financial_expectation": "NONE"})
        master_rows.append({"sku": f["sku"], "expected_classification": f["cls"],
                            "expected_decision": f["dec"], "category": tag,
                            "expected_primary_action": "none", "financial_expectation": "NONE"})

    # inventory snapshot
    inv_rows = []
    for c in gt_cases:
        rows, item = build_sku(c)
        inv_rows.append({"item_sku": c["sku"], "item_name": f"GT {c['sku']}",
                         "category_name": CATEGORY.get(c["category"], "General"),
                         "cost_price": f"{item['cost']:.2f}", "sell_price": f"{item['sell']:.2f}",
                         "current_stock": item["stock"], "reorder_level": item["reorder"],
                         "max_stock": item["maxstock"], "supplier": "Global Foods Traders"})
    for f in fillers:
        inv_rows.append({"item_sku": f["sku"], "item_name": f["name"],
                         "category_name": CATEGORY.get(f["master_tag"], "General"),
                         "cost_price": f"{f['cost']:.2f}", "sell_price": f"{f['sell']:.2f}",
                         "current_stock": f["stock"], "reorder_level": f["reorder"],
                         "max_stock": f["maxstock"], "supplier": f["supplier"]})

    # write CSVs
    with open(os.path.join(OUT_DIR, "sales_history.csv"), "w", newline="", encoding="utf-8") as fh:
        cols = ["transaction_at", "item_name", "item_sku", "quantity", "unit_price",
                "cost_price", "total_amount", "transaction_type"]
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        # sort by date then sku for a realistic chronological file
        sales_rows.sort(key=lambda r: (r["transaction_at"], r["item_sku"]))
        w.writerows(sales_rows)

    with open(os.path.join(OUT_DIR, "inventory_snapshot.csv"), "w", newline="", encoding="utf-8") as fh:
        cols = ["item_sku", "item_name", "category_name", "cost_price", "sell_price",
                "current_stock", "reorder_level", "max_stock", "supplier"]
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(inv_rows)

    with open(os.path.join(OUT_DIR, "master_expected.csv"), "w", newline="", encoding="utf-8") as fh:
        cols = ["sku", "expected_classification", "expected_decision", "category",
                "expected_primary_action", "financial_expectation"]
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        # ensure each sku appears once (last write wins if dup keys)
        seen = set()
        for r in master_rows:
            if r["sku"] in seen:
                continue
            seen.add(r["sku"]); w.writerow(r)

    # selfcheck file
    with open(os.path.join(OUT_DIR, "generator_selfcheck.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"GT self-check failures: {failures}/{len(gt_cases)}\n")
        for s in selfcheck:
            fh.write(f"{s['sku']}: got={s['got_cls']}/{s['got_dec']} exp={s['exp_cls']}/{s['exp_dec']} "
                     f"ok={s['ok']} q30={s['q30']} prior={s['prior']} dsls={s['dsls']} months={s['months']}\n")

    print(f"sales rows: {len(sales_rows)}")
    print(f"SKUs: {len(inv_rows)} (GT {len(gt_cases)} + filler {len(fillers)})")
    print(f"GT self-check failures: {failures}/{len(gt_cases)}")
    for s in selfcheck:
        if not s["ok"]:
            print("  MISMATCH", s["sku"], s["got_cls"], s["exp_cls"], s["got_dec"], s["exp_dec"])
    print(f"outputs -> {OUT_DIR}")


if __name__ == "__main__":
    main()
