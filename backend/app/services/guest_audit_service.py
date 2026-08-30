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

from app.services.recovery_intelligence import classify_inventory, estimate_recovery, stockout_financials

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

    inventory_value = Decimal("0")
    capital_at_risk = Decimal("0")
    revenue_at_risk = Decimal("0")
    gross_profit_at_risk = Decimal("0")
    recoverable_low = Decimal("0")
    recoverable_high = Decimal("0")
    dead_stock_value = Decimal("0")
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
        inventory_value += stock_value
        classification = classify_inventory(stock=stock, recent_qty_30=qty_30d, prior_qty_30=Decimal("0"), days_since_last_sale=last_sold_days, inventory_age_days=None)

        recovery = estimate_recovery(classification=classification, stock=stock, cost=cost, sell=sell)
        if classification in {"DEAD", "SLOW MOVING"}:
            capital_at_risk += stock_value
            if classification == "DEAD":
                dead_stock_value += stock_value
            recoverable_low += recovery.recoverable_low
            recoverable_high += recovery.recoverable_high
            actions.append({
                "action_type": "discount", "priority": 2,
                "title": f"Review {entry['name']} inventory",
                "description": f"{stock} units are classified {classification.lower()}; recovery is not estimated without observed outcomes.",
                "expected_recovery_sar": None,
                "recoverable_value_low_sar": float(recovery.recoverable_low),
                "recoverable_value_high_sar": float(recovery.recoverable_high),
                "recovery_confidence": recovery.confidence, "quantity": float(stock),
            })

        if daily_velocity > 0 and stock / daily_velocity > OVERSTOCK_DAYS and classification != "SEASONAL":
            surplus_qty = max(Decimal("0"), stock - daily_velocity * Decimal("30"))
            surplus_value = surplus_qty * cost
            if surplus_value >= Decimal("500"):
                capital_at_risk += surplus_value
                overstock_value += surplus_value
                recoverable_high += min(surplus_value, surplus_qty * sell)
                actions.append({
                    "action_type": "recovery_match", "priority": 3,
                    "title": f"Review {entry['name']} for excess inventory",
                    "description": f"{surplus_qty.quantize(Decimal('0.01'))} units exceed 30-day demand cover.",
                    "expected_recovery_sar": None, "recoverable_value_low_sar": 0.0,
                    "recoverable_value_high_sar": float(min(surplus_value, surplus_qty * sell)),
                    "recovery_confidence": "LOW", "quantity": float(surplus_qty),
                })

        if daily_velocity > 0 and sell > 0 and stock / daily_velocity < STOCKOUT_DAYS:
            stockout = stockout_financials(stock=stock, daily_velocity=daily_velocity, sell=sell, cost=cost, lead_time_days=None, safety_stock=None)
            revenue_at_risk += stockout.revenue_at_risk
            gross_profit_at_risk += stockout.gross_profit_at_risk
            reorder_qty = max(Decimal("0"), daily_velocity * Decimal("7") - stock).quantize(Decimal("1"))
            actions.append({
                "action_type": "reorder", "priority": 2,
                "title": f"Review stockout risk on {entry['name']}",
                "description": f"Only {(stock / daily_velocity).quantize(Decimal('0.1'))} days of cover; supplier lead time is unavailable.",
                "expected_recovery_sar": None, "recoverable_value_low_sar": 0.0, "recoverable_value_high_sar": 0.0,
                "recovery_confidence": "LOW", "quantity": float(reorder_qty),
            })

        if qty_30d > 0 and cost > 0 and sell > 0:
            margin_pct = (sell - cost) / sell
            if margin_pct < TARGET_MARGIN_PCT:
                target_price = (cost / (Decimal("1") - TARGET_MARGIN_PCT)).quantize(Decimal("0.01"))
                leakage = max(Decimal("0"), target_price - sell) * qty_30d
                if leakage > 0:
                    gross_profit_at_risk += leakage
                    actions.append({
                        "action_type": "margin_fix", "priority": 2,
                        "title": f"Review margin on {entry['name']}",
                        "description": "Theoretical gross-profit opportunity; not cash recovered.",
                        "expected_recovery_sar": None, "recoverable_value_low_sar": 0.0,
                        "recoverable_value_high_sar": float(leakage), "recovery_confidence": "LOW",
                        "quantity": float(qty_30d),
                    })

    actions = sorted(actions, key=lambda a: (a["priority"], -(a.get("recoverable_value_high_sar") or 0)))[:MAX_GUEST_ACTIONS]
    has_sales = any(e["qty_30d"] > 0 for e in ledger.values())
    has_cost = any(e["cost"] > 0 for e in ledger.values())
    has_stock = any(e["stock"] > 0 for e in ledger.values())
    confidence = Decimal("30") + (Decimal("30") if has_sales else 0) + (Decimal("20") if has_cost else 0) + (Decimal("20") if has_stock else 0)

    summary = {
        "financial_model_version": "v2",
        "money_at_risk_sar": float(capital_at_risk),
        "inventory_value_sar": float(inventory_value),
        "capital_at_risk_sar": float(capital_at_risk),
        "revenue_at_risk_sar": float(revenue_at_risk),
        "gross_profit_at_risk_sar": float(gross_profit_at_risk),
        "recoverable_value_low_sar": float(recoverable_low),
        "recoverable_value_high_sar": float(recoverable_high),
        "expected_recovery_sar": None,
        "recovery_confidence": "LOW" if actions else "INSUFFICIENT DATA",
        "dead_stock_value_sar": float(dead_stock_value), "stockout_risk_value_sar": float(revenue_at_risk),
        "margin_leakage_sar": float(gross_profit_at_risk), "overstock_value_sar": float(overstock_value),
        "action_count": len(actions), "row_count": len(df), "file_kind": file_kind,
        "confidence_score": float(confidence.quantize(Decimal("0.01"))),
        "detected_columns": {"name": name_col, "quantity": qty_col, "price": price_col, "cost": cost_col, "stock": stock_col, "date": date_col},
        "headline_note": "Revenue/profit at risk are not cash recovered. Expected recovery is withheld until observed outcomes exist.",
        "generated_at": datetime.utcnow().isoformat(), "guest_session_id": str(uuid4()),
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
                "expected_recovery_sar": None,
                "recoverable_value_low_sar": 0.0,
                "recoverable_value_high_sar": 0.0,
                "recovery_confidence": "INSUFFICIENT DATA",
            }
        ],
        "missing_data": [{"code": "parse_issue", "message": message}],
    }
