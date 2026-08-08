"""Guest Money Audit — public, auth-free "front door" value demonstration.

Accepts a small CSV/JSON payload of sales or inventory rows and returns a
simplified Money Audit estimate. The goal is to show trapped cash in under
60 seconds without requiring account creation.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import uuid4

import pandas as pd

TARGET_MARGIN_PCT = Decimal("0.22")
DEAD_STOCK_DAYS = 45
OVERSTOCK_DAYS = Decimal("45")
STOCKOUT_DAYS = Decimal("5")
MAX_GUEST_ACTIONS = 8


def _money(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lower-case and de-duplicate column names for robust mapping."""
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def _find_column(candidates: list[str], df: pd.DataFrame) -> str | None:
    cols = {c.lower().replace(" ", "_"): c for c in df.columns}
    for candidate in candidates:
        key = candidate.lower().replace(" ", "_")
        if key in cols:
            return cols[key]
    return None


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(",", ""), errors="coerce").fillna(0)


def _detect_file_kind(df: pd.DataFrame) -> str:
    cols = {c.lower().replace(" ", "_") for c in df.columns}
    inventory_signals = {"current_stock", "stock", "quantity_on_hand", "cost_price", "purchase_price"}
    sales_signals = {"sale_date", "transaction_date", "sold_quantity", "total_amount", "revenue"}
    date_signals = {"date", "sale_date", "transaction_date", "order_date", "created_at"}

    inv_score = len(cols & inventory_signals)
    sales_score = len(cols & sales_signals)
    has_date = bool(cols & date_signals)

    # A date column strongly indicates sales history; explicit stock signals
    # indicate inventory snapshot.
    if inv_score > 0 and sales_score == 0:
        return "inventory_snapshot"
    if has_date and ("quantity" in cols or "qty" in cols or "units" in cols):
        return "sales_history"
    if sales_score > inv_score:
        return "sales_history"
    return "inventory_snapshot"


def _parse_date(value: Any) -> datetime | None:
    if pd.isna(value):
        return None
    try:
        return pd.to_datetime(value)
    except Exception:
        return None


async def run_guest_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Run a simplified Money Audit over raw uploaded rows.

    The heuristic works best when the merchant uploads sales rows with product
    name, date, quantity, and price, plus inventory rows with current stock and
    cost. A single-file upload is also handled using simple column detection.
    """
    if not rows:
        return _empty_audit("No data received. Upload a CSV with sales or inventory rows.")

    df = _normalize_columns(pd.DataFrame(rows))
    if len(df) == 0:
        return _empty_audit("No rows found in the uploaded file.")

    file_kind = _detect_file_kind(df)

    # Build a unified item ledger keyed by normalized product name.
    ledger: dict[str, dict[str, Any]] = {}

    name_col = _find_column(["product_name", "item_name", "name", "product", "title"], df)
    qty_col = _find_column(["quantity", "qty", "sold_quantity", "units", "amount"], df)
    price_col = _find_column(["unit_price", "price", "sale_price", "sell_price", "total_amount", "revenue"], df)
    cost_col = _find_column(["cost_price", "cost", "purchase_price", "buy_price"], df)
    stock_col = _find_column(["current_stock", "stock", "stock_quantity", "quantity_on_hand"], df)
    date_col = _find_column(["date", "sale_date", "transaction_date", "order_date", "created_at"], df)

    missing = []
    if not name_col:
        missing.append("Product name column not found. Expected one of: product_name, item_name, name.")
    if not qty_col and file_kind == "sales_history":
        missing.append("Quantity column not found for sales history.")
    if not stock_col and file_kind == "inventory_snapshot":
        missing.append("Current stock column not found for inventory snapshot.")
    if missing:
        return _empty_audit(" ".join(missing))

    if file_kind == "sales_history":
        for _, row in df.iterrows():
            name = str(row.get(name_col) or "").strip()
            if not name:
                continue
            qty = _coerce_numeric(pd.Series([row.get(qty_col, 0)])).iloc[0]
            price = _coerce_numeric(pd.Series([row.get(price_col, 0)])).iloc[0]
            cost = _coerce_numeric(pd.Series([row.get(cost_col, 0)])).iloc[0]
            tx_date = _parse_date(row.get(date_col)) if date_col else None

            entry = ledger.setdefault(name, {
                "name": name,
                "stock": Decimal("0"),
                "cost": cost if cost > 0 else Decimal("0"),
                "sell": price if price > 0 else Decimal("0"),
                "qty_30d": Decimal("0"),
                "revenue_30d": Decimal("0"),
                "last_sold_at": None,
                "records": 0,
            })
            entry["qty_30d"] += _money(qty)
            entry["revenue_30d"] += _money(qty * price)
            entry["records"] += 1
            if cost > 0 and entry["cost"] == 0:
                entry["cost"] = _money(cost)
            if price > 0 and entry["sell"] == 0:
                entry["sell"] = _money(price)
            if tx_date and (entry["last_sold_at"] is None or tx_date > entry["last_sold_at"]):
                entry["last_sold_at"] = tx_date
    else:
        for _, row in df.iterrows():
            name = str(row.get(name_col) or "").strip()
            if not name:
                continue
            stock = _coerce_numeric(pd.Series([row.get(stock_col, 0)])).iloc[0]
            cost = _coerce_numeric(pd.Series([row.get(cost_col, 0)])).iloc[0]
            sell = _coerce_numeric(pd.Series([row.get(price_col, 0)])).iloc[0]
            ledger[name] = {
                "name": name,
                "stock": _money(stock),
                "cost": _money(cost),
                "sell": _money(sell),
                "qty_30d": Decimal("0"),
                "revenue_30d": Decimal("0"),
                "last_sold_at": None,
                "records": 1,
            }

    if not ledger:
        return _empty_audit("Could not recognize any products in the uploaded file.")

    dead_stock_value = Decimal("0")
    stockout_value = Decimal("0")
    margin_leakage = Decimal("0")
    overstock_value = Decimal("0")
    actions: list[dict[str, Any]] = []

    today = datetime.utcnow()

    for entry in ledger.values():
        stock = _money(entry["stock"])
        cost = _money(entry["cost"])
        sell = _money(entry["sell"])
        qty_30d = _money(entry["qty_30d"])
        daily_velocity = qty_30d / Decimal("30") if qty_30d > 0 else Decimal("0")
        last_sold = entry["last_sold_at"]
        last_sold_days = (today - last_sold).days if last_sold else None
        stock_value = stock * cost
        item_name = entry["name"]

        if stock > 0 and cost > 0 and (qty_30d <= 0 or (last_sold_days is not None and last_sold_days >= DEAD_STOCK_DAYS)):
            dead_stock_value += stock_value
            expected = (stock_value * Decimal("0.35")).quantize(Decimal("0.01"))
            days_label = f"{last_sold_days} days" if last_sold_days is not None else "30+ days"
            actions.append({
                "action_type": "discount",
                "priority": 1 if stock_value >= Decimal("5000") else 2,
                "title": f"Recover cash from slow-moving {item_name}",
                "description": f"{stock} units in stock with no meaningful sales for {days_label}. Start with a controlled 15–25% discount or bundle before writing it off.",
                "expected_recovery_sar": float(expected),
                "quantity": float(stock),
                "recommended_discount_pct": 20,
            })

        if stock > 0 and cost > 0 and daily_velocity > 0:
            days_supply = stock / daily_velocity if daily_velocity > 0 else Decimal("999")
            if days_supply > OVERSTOCK_DAYS:
                surplus_qty = max(Decimal("0"), stock - (daily_velocity * Decimal("30")))
                surplus_value = surplus_qty * cost
                overstock_value += surplus_value
                if surplus_value >= Decimal("500"):
                    actions.append({
                        "action_type": "recovery_match",
                        "priority": 3,
                        "title": f"Review {item_name} for Recovery Match",
                        "description": f"Estimated {surplus_qty.quantize(Decimal('0.01'))} surplus units. If expiry and category are safe, offer to nearby opted-in retailers after founder review.",
                        "expected_recovery_sar": float((surplus_value * Decimal("0.30")).quantize(Decimal("0.01"))),
                        "quantity": float(surplus_qty.quantize(Decimal("0.01"))),
                        "recommended_discount_pct": 15,
                    })

        if daily_velocity > 0 and sell > 0:
            days_left = stock / daily_velocity if stock > 0 else Decimal("0")
            if days_left < STOCKOUT_DAYS:
                protected_sales = (daily_velocity * Decimal("7") * sell).quantize(Decimal("0.01"))
                stockout_value += protected_sales
                reorder_qty = max(Decimal("1"), (daily_velocity * Decimal("14")) - stock).quantize(Decimal("1"))
                actions.append({
                    "action_type": "reorder",
                    "priority": 1 if days_left < Decimal("2") else 2,
                    "title": f"Prevent stockout on {item_name}",
                    "description": f"Only {days_left.quantize(Decimal('0.1'))} days of supply left. Reorder about {reorder_qty} units before the next weekend rush.",
                    "expected_recovery_sar": float(protected_sales),
                    "quantity": float(reorder_qty),
                })

        if qty_30d > 0 and cost > 0 and sell > 0:
            margin_pct = (sell - cost) / sell if sell > 0 else Decimal("0")
            if margin_pct < TARGET_MARGIN_PCT:
                target_price = (cost / (Decimal("1") - TARGET_MARGIN_PCT)).quantize(Decimal("0.01"))
                leak_per_unit = max(Decimal("0"), target_price - sell)
                leakage = (leak_per_unit * qty_30d).quantize(Decimal("0.01"))
                if leakage > 0:
                    margin_leakage += leakage
                    actions.append({
                        "action_type": "margin_fix",
                        "priority": 2,
                        "title": f"Fix margin leakage on {item_name}",
                        "description": f"Current gross margin is {(margin_pct * 100).quantize(Decimal('0.1'))}%. Review shelf price or supplier cost. Suggested target price: SAR {target_price}.",
                        "expected_recovery_sar": float(leakage),
                        "quantity": float(qty_30d),
                    })

    actions = sorted(actions, key=lambda a: (a["priority"], -a["expected_recovery_sar"]))[:MAX_GUEST_ACTIONS]
    money_at_risk = (dead_stock_value + stockout_value + margin_leakage).quantize(Decimal("0.01"))

    # Confidence is higher when we see both sales and stock/cost signals.
    has_sales = any(e["qty_30d"] > 0 for e in ledger.values())
    has_cost = any(e["cost"] > 0 for e in ledger.values())
    has_stock = any(e["stock"] > 0 for e in ledger.values())
    confidence = Decimal("30")
    if has_sales:
        confidence += Decimal("30")
    if has_cost:
        confidence += Decimal("20")
    if has_stock:
        confidence += Decimal("20")

    summary = {
        "money_at_risk_sar": float(money_at_risk),
        "dead_stock_value_sar": float(dead_stock_value),
        "stockout_risk_value_sar": float(stockout_value),
        "margin_leakage_sar": float(margin_leakage),
        "overstock_value_sar": float(overstock_value),
        "action_count": len(actions),
        "row_count": len(df),
        "file_kind": file_kind,
        "confidence_score": float(confidence.quantize(Decimal("0.01"))),
        "detected_columns": {
            "name": name_col,
            "quantity": qty_col,
            "price": price_col,
            "cost": cost_col,
            "stock": stock_col,
            "date": date_col,
        },
        "generated_at": datetime.utcnow().isoformat(),
        "guest_session_id": str(uuid4()),
    }

    return {
        "summary": summary,
        "actions": actions,
        "missing_data": [],
    }


def _empty_audit(message: str) -> dict[str, Any]:
    return {
        "summary": {
            "money_at_risk_sar": 0.0,
            "dead_stock_value_sar": 0.0,
            "stockout_risk_value_sar": 0.0,
            "margin_leakage_sar": 0.0,
            "overstock_value_sar": 0.0,
            "action_count": 0,
            "row_count": 0,
            "file_kind": "unknown",
            "confidence_score": 0.0,
            "generated_at": datetime.utcnow().isoformat(),
            "guest_session_id": str(uuid4()),
        },
        "actions": [
            {
                "action_type": "review",
                "priority": 1,
                "title": "Upload a clearer file",
                "description": message,
                "expected_recovery_sar": 0.0,
            }
        ],
        "missing_data": [{"code": "parse_issue", "message": message}],
    }
