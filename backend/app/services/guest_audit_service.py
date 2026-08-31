"""Guest Money Audit — public, auth-free "front door" value demonstration.

Accepts a small CSV/Excel/JSON payload — one file (sales OR inventory) or two
files (sales + inventory, paired by fuzzy product-name matching) — and returns
a simplified Money Audit estimate built on the SAME deterministic math as the
authenticated audit (``audit_core``). The goal is to show trapped cash in under
60 seconds without requiring account creation.

No AI, deterministic math. Recovery numbers are evidence-bounded, never fabricated.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import uuid4

import pandas as pd

from app.services.audit_core import ProductMetrics, analyze_product, money
from app.services.file_ingestion import ColumnResolution, coerce_numeric, normalize_text, resolve_columns
from app.services.product_pairing import PairingReport, pair_products

MAX_GUEST_ACTIONS = 8
GUEST_CONFIDENCE_BASE = Decimal("30")


def _parse_date(value: Any) -> datetime | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return pd.to_datetime(value, errors="coerce").to_pydatetime()
    except Exception:
        return None


def _detect_file_kind(resolution: ColumnResolution) -> str:
    mapped = resolution.mapping
    has_stock = "stock" in mapped
    has_quantity = "quantity" in mapped
    has_date = "date" in mapped
    if has_stock and has_quantity and not has_date:
        return "inventory_snapshot"
    if has_date and (has_quantity or "price" in mapped):
        return "sales_history"
    if has_stock:
        return "inventory_snapshot"
    if has_quantity:
        return "sales_history"
    return "unknown"


def _audit_ledger(ledger: dict[str, dict[str, Any]], today: datetime) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    aggregates = {
        "inventory_value": Decimal("0"),
        "capital_at_risk": Decimal("0"),
        "revenue_at_risk": Decimal("0"),
        "gross_profit_at_risk": Decimal("0"),
        "recoverable_low": Decimal("0"),
        "recoverable_high": Decimal("0"),
        "dead_stock_value": Decimal("0"),
        "overstock_value": Decimal("0"),
        "margin_leakage": Decimal("0"),
        "products_with_risk": 0,
    }
    actions: list[dict[str, Any]] = []

    for entry in ledger.values():
        latest = entry.get("last_sold_at")
        last_sold_days = (today - latest).days if latest else None
        metrics = ProductMetrics(
            name=entry["name"],
            stock=money(entry.get("stock")),
            cost=money(entry.get("cost")),
            sell=money(entry.get("sell")),
            recent_qty_30=money(entry.get("qty_30d")),
            prior_qty_30=money(entry.get("prior_qty_30")),
            last_sold_days=last_sold_days,
        )
        audit = analyze_product(metrics)

        aggregates["inventory_value"] += audit.stock_value
        if audit.needs_attention:
            aggregates["products_with_risk"] += 1
        if audit.has_dead_or_slow_risk:
            aggregates["capital_at_risk"] += audit.capital_at_risk
            aggregates["dead_stock_value"] += audit.dead_stock_value
            aggregates["recoverable_low"] += audit.dead_recoverable_low
            aggregates["recoverable_high"] += audit.dead_recoverable_high
            priority = 1 if audit.stock_value >= Decimal("5000") else 2
            actions.append({
                "action_type": "discount", "priority": priority,
                "title": f"Review {audit.name} inventory",
                "description": f"{audit.stock} units are classified {audit.classification.lower()}; recovery is not estimated without observed outcomes.",
                "expected_recovery_sar": None,
                "recoverable_value_low_sar": float(audit.dead_recoverable_low),
                "recoverable_value_high_sar": float(audit.dead_recoverable_high),
                "recovery_confidence": "MEDIUM" if audit.classification == "DEAD" else "LOW",
                "quantity": float(audit.stock),
            })
        if audit.has_overstock_risk:
            aggregates["capital_at_risk"] += audit.overstock_value
            aggregates["overstock_value"] += audit.overstock_value
            aggregates["recoverable_high"] += audit.overstock_recoverable_high
            actions.append({
                "action_type": "recovery_match", "priority": 3,
                "title": f"Review {audit.name} for excess inventory",
                "description": f"{audit.surplus_qty.quantize(Decimal('0.01'))} units exceed 30-day demand cover.",
                "expected_recovery_sar": None, "recoverable_value_low_sar": 0.0,
                "recoverable_value_high_sar": float(audit.overstock_recoverable_high),
                "recovery_confidence": "LOW", "quantity": float(audit.surplus_qty),
            })
        if audit.has_stockout_risk:
            aggregates["revenue_at_risk"] += audit.revenue_at_risk
            aggregates["gross_profit_at_risk"] += audit.gross_profit_at_risk
            priority = 1 if (audit.stock > 0 and audit.daily_velocity > 0 and audit.stock / audit.daily_velocity < Decimal("2")) else 2
            actions.append({
                "action_type": "reorder", "priority": priority,
                "title": f"Review stockout risk on {audit.name}",
                "description": f"Only {(audit.stock / audit.daily_velocity).quantize(Decimal('0.1'))} days of cover; supplier lead time is unavailable.",
                "expected_recovery_sar": None, "recoverable_value_low_sar": 0.0, "recoverable_value_high_sar": 0.0,
                "recovery_confidence": "LOW", "quantity": float(audit.order_qty.quantize(Decimal("1"))),
            })
        if audit.has_margin_leakage:
            aggregates["gross_profit_at_risk"] += audit.margin_leakage
            aggregates["margin_leakage"] += audit.margin_leakage
            actions.append({
                "action_type": "margin_fix", "priority": 2,
                "title": f"Review margin on {audit.name}",
                "description": "Theoretical gross-profit opportunity; not cash recovered.",
                "expected_recovery_sar": None, "recoverable_value_low_sar": 0.0,
                "recoverable_value_high_sar": float(audit.margin_leakage), "recovery_confidence": "LOW",
                "quantity": float(metrics.recent_qty_30),
            })

    actions = sorted(actions, key=lambda a: (a["priority"], -(float(a.get("recoverable_value_high_sar") or 0))))[:MAX_GUEST_ACTIONS]
    aggregates["actions"] = actions
    return actions, aggregates


def _single_file_ledger(df: pd.DataFrame, resolution: ColumnResolution, file_kind: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    mapping = resolution.mapping
    ledger: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    name_col = mapping.get("product_name")
    if not name_col:
        return {}, ["Product name column not found. Expected one of: product_name, item_name, name, اسم المنتج."]

    qty_col = mapping.get("quantity")
    price_col = mapping.get("price")
    cost_col = mapping.get("cost")
    stock_col = mapping.get("stock")
    date_col = mapping.get("date")
    if file_kind == "sales_history" and not qty_col:
        missing.append("Quantity column not found for sales history.")
    if file_kind == "inventory_snapshot" and not stock_col:
        missing.append("Current stock column not found for inventory snapshot.")
    if missing:
        return {}, missing

    if file_kind == "sales_history":
        for _, row in df.iterrows():
            name = str(row.get(name_col) or "").strip()
            if not name:
                continue
            qty = coerce_numeric(row.get(qty_col))
            price = coerce_numeric(row.get(price_col)) if price_col else Decimal("0")
            cost = coerce_numeric(row.get(cost_col)) if cost_col else Decimal("0")
            tx_date = _parse_date(row.get(date_col)) if date_col else None

            entry = ledger.setdefault(name, {
                "name": name, "stock": Decimal("0"), "cost": Decimal("0"), "sell": Decimal("0"),
                "qty_30d": Decimal("0"), "prior_qty_30": Decimal("0"),
                "revenue_30d": Decimal("0"), "last_sold_at": None, "records": 0,
            })
            entry["qty_30d"] += qty
            entry["revenue_30d"] += qty * price
            entry["records"] += 1
            if cost > 0 and entry["cost"] == 0:
                entry["cost"] = cost
            if price > 0 and entry["sell"] == 0:
                entry["sell"] = price
            if tx_date and (entry["last_sold_at"] is None or tx_date > entry["last_sold_at"]):
                entry["last_sold_at"] = tx_date
    else:
        for _, row in df.iterrows():
            name = str(row.get(name_col) or "").strip()
            if not name:
                continue
            ledger[name] = {
                "name": name,
                "stock": coerce_numeric(row.get(stock_col)),
                "cost": coerce_numeric(row.get(cost_col)) if cost_col else Decimal("0"),
                "sell": coerce_numeric(row.get(price_col)) if price_col else Decimal("0"),
                "qty_30d": Decimal("0"), "prior_qty_30": Decimal("0"),
                "revenue_30d": Decimal("0"), "last_sold_at": None, "records": 1,
            }
    return ledger, []


def _confidence(ledger: dict[str, dict[str, Any]]) -> Decimal:
    has_sales = any(e["qty_30d"] > 0 for e in ledger.values())
    has_cost = any(e["cost"] > 0 for e in ledger.values())
    has_stock = any(e["stock"] > 0 for e in ledger.values())
    confidence = GUEST_CONFIDENCE_BASE
    confidence += Decimal("30") if has_sales else 0
    confidence += Decimal("20") if has_cost else 0
    confidence += Decimal("20") if has_stock else 0
    return confidence


def _summary(ledger: dict[str, dict[str, Any]], actions: list[dict[str, Any]], aggregates: dict[str, Any],
             file_kind: str, row_count: int, detected_columns: dict[str, str | None], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    rev_risk = aggregates["revenue_at_risk"]
    summary = {
        "financial_model_version": "v2",
        "money_at_risk_sar": float(aggregates["capital_at_risk"]),
        "inventory_value_sar": float(aggregates["inventory_value"]),
        "capital_at_risk_sar": float(aggregates["capital_at_risk"]),
        "revenue_at_risk_sar": float(rev_risk),
        "gross_profit_at_risk_sar": float(aggregates["gross_profit_at_risk"]),
        "recoverable_value_low_sar": float(aggregates["recoverable_low"]),
        "recoverable_value_high_sar": float(aggregates["recoverable_high"]),
        "expected_recovery_sar": None,
        "recovery_confidence": "LOW" if actions else "INSUFFICIENT DATA",
        "dead_stock_value_sar": float(aggregates["dead_stock_value"]),
        "stockout_risk_value_sar": float(rev_risk),
        "margin_leakage_sar": float(aggregates["margin_leakage"]),
        "overstock_value_sar": float(aggregates["overstock_value"]),
        "action_count": len(actions),
        "row_count": row_count,
        "file_kind": file_kind,
        "confidence_score": float(_confidence(ledger).quantize(Decimal("0.01"))),
        "detected_columns": detected_columns,
        "products_needing_attention": aggregates["products_with_risk"],
        "headline_note": "Revenue/profit at risk are not cash recovered. Expected recovery is withheld until observed outcomes exist.",
        "generated_at": datetime.utcnow().isoformat(),
        "guest_session_id": str(uuid4()),
    }
    if extra:
        summary.update(extra)
    return summary


def _detected_column_indices(resolution: ColumnResolution) -> dict[str, str | None]:
    return {field: (resolution.mapping.get(field) or None) for field in ("name", "quantity", "price", "cost", "stock", "date")}


async def run_guest_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Run a simplified Money Audit over raw uploaded rows (single file)."""
    if not rows:
        return _empty_audit("No data received. Upload a CSV with sales or inventory rows.")

    import pandas as pd_local
    df = pd_local.DataFrame(rows).replace({pd_local.NaT: None})
    if len(df) == 0:
        return _empty_audit("No rows found in the uploaded file.")

    resolution = resolve_columns(df)
    file_kind = _detect_file_kind(resolution)
    ledger, missing = _single_file_ledger(df, resolution, file_kind)
    if missing:
        return _empty_audit(" ".join(missing))
    if not ledger:
        return _empty_audit("Could not recognize any products in the uploaded file.")

    today = datetime.utcnow()
    actions, aggregates = _audit_ledger(ledger, today)
    detected = _detected_column_indices(resolution)
    summary = _summary(ledger, actions, aggregates, file_kind, len(df), detected)
    return {"summary": summary, "actions": actions, "missing_data": []}


def _build_sales_ledger(df: pd.DataFrame, resolution: ColumnResolution, *, sales_history: bool | None = None) -> dict[str, dict[str, Any]]:
    mapping = resolution.mapping
    ledger: dict[str, dict[str, Any]] = {}
    name_col = mapping.get("product_name")
    if not name_col:
        return ledger
    file_kind = _detect_file_kind(resolution) if sales_history is None else ("sales_history" if sales_history else "inventory_snapshot")

    qty_col = mapping.get("quantity")
    price_col = mapping.get("price")
    cost_col = mapping.get("cost")
    stock_col = mapping.get("stock")
    date_col = mapping.get("date")

    if file_kind == "sales_history":
        dates = df[date_col].map(_parse_date) if date_col else None
        today = datetime.utcnow()
        for idx, row in df.iterrows():
            name = str(row.get(name_col) or "").strip()
            if not name:
                continue
            qty = coerce_numeric(row.get(qty_col)) if qty_col else Decimal("0")
            price = coerce_numeric(row.get(price_col)) if price_col else Decimal("0")
            cost = coerce_numeric(row.get(cost_col)) if cost_col else Decimal("0")
            tx_date = dates.iloc[idx] if dates is not None else None
            in_recent = tx_date is None or (today - tx_date).days <= 30
            in_prior = tx_date is not None and 30 < (today - tx_date).days <= 60

            entry = ledger.setdefault(name, {
                "name": name, "stock": Decimal("0"), "cost": Decimal("0"), "sell": Decimal("0"),
                "qty_30d": Decimal("0"), "prior_qty_30": Decimal("0"),
                "revenue_30d": Decimal("0"), "last_sold_at": None, "records": 0,
            })
            if in_recent:
                entry["qty_30d"] += qty
            elif in_prior:
                entry["prior_qty_30"] += qty
            entry["revenue_30d"] += qty * price
            entry["records"] += 1
            if cost > 0 and entry["cost"] == 0:
                entry["cost"] = _coerce_cost(cost)
            if price > 0 and entry["sell"] == 0:
                entry["sell"] = price
            if tx_date and (entry["last_sold_at"] is None or tx_date > entry["last_sold_at"]):
                entry["last_sold_at"] = tx_date
        return ledger

    for _, row in df.iterrows():
        name = str(row.get(name_col) or "").strip()
        if not name:
            continue
        ledger[name] = {
            "name": name,
            "stock": coerce_numeric(row.get(stock_col)) if stock_col else Decimal("0"),
            "cost": coerce_numeric(row.get(cost_col)) if cost_col else Decimal("0"),
            "sell": coerce_numeric(row.get(price_col)) if price_col else Decimal("0"),
            "qty_30d": Decimal("0"), "prior_qty_30": Decimal("0"),
            "revenue_30d": Decimal("0"), "last_sold_at": None, "records": 1,
        }
    return ledger


def _coerce_cost(value: Decimal) -> Decimal:
    return value


def _pair_ledgers(
    sales_ledger: dict[str, dict[str, Any]], inventory_ledger: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    pairing = pair_products(list(sales_ledger.keys()), list(inventory_ledger.keys()))
    merged: dict[str, dict[str, Any]] = {}
    used_sales: set[str] = set()
    for p in pairing.paired:
        sales_entry = sales_ledger[p.sales_name]
        inv_entry = inventory_ledger.get(p.inventory_name, {})
        merged[p.sales_name] = {
            "name": p.sales_name,
            "stock": money(inv_entry.get("stock")),
            "cost": money(inv_entry.get("cost")) or money(sales_entry.get("cost")),
            "sell": money(inv_entry.get("sell")) or money(sales_entry.get("sell")),
            "qty_30d": money(sales_entry.get("qty_30d")),
            "prior_qty_30": money(sales_entry.get("prior_qty_30")),
            "revenue_30d": money(sales_entry.get("revenue_30d")),
            "last_sold_at": sales_entry.get("last_sold_at"),
            "records": sales_entry.get("records", 0) + inv_entry.get("records", 0),
            "pair_score": p.score,
            "pair_tier": p.tier,
        }
        used_sales.add(p.sales_name)
    for name, sales_entry in sales_ledger.items():
        if name in used_sales:
            continue
        merged[name] = {
            "name": name,
            "stock": Decimal("0"),
            "cost": money(sales_entry.get("cost")),
            "sell": money(sales_entry.get("sell")),
            "qty_30d": money(sales_entry.get("qty_30d")),
            "prior_qty_30": money(sales_entry.get("prior_qty_30")),
            "revenue_30d": money(sales_entry.get("revenue_30d")),
            "last_sold_at": sales_entry.get("last_sold_at"),
            "records": sales_entry.get("records", 0),
            "pair_score": None,
            "pair_tier": "UNPAIRED_SALES",
        }
    for name, inv_entry in inventory_ledger.items():
        paired_to = next((p.sales_name for p in pairing.paired if p.inventory_name == name), None)
        if paired_to:
            continue
        merged[name] = {
            "name": name,
            "stock": money(inv_entry.get("stock")),
            "cost": money(inv_entry.get("cost")),
            "sell": money(inv_entry.get("sell")),
            "qty_30d": Decimal("0"),
            "prior_qty_30": Decimal("0"),
            "revenue_30d": Decimal("0"),
            "last_sold_at": None,
            "records": inv_entry.get("records", 0),
            "pair_score": None,
            "pair_tier": "UNPAIRED_INVENTORY",
        }
    return {"merged": merged, "report": pairing}


def run_two_file_audit(
    sales_df: pd.DataFrame,
    inventory_df: pd.DataFrame,
    sales_resolution: ColumnResolution,
    inventory_resolution: ColumnResolution,
) -> dict[str, Any]:
    """Publicly callable two-file audit returning summary + actions."""
    sales_ledger = _build_sales_ledger(sales_df, sales_resolution)
    inventory_ledger = _build_sales_ledger(inventory_df, inventory_resolution, sales_history=False)
    pairing = _pair_ledgers(sales_ledger, inventory_ledger)
    merged = pairing["merged"]
    report = pairing["report"]

    today = datetime.utcnow()
    actions, aggregates = _audit_ledger(merged, today)
    detected = {
        "sales": _detected_column_indices(sales_resolution),
        "inventory": _detected_column_indices(inventory_resolution),
    }
    pairing_extra = {
        "pairing": {
            "attempted": report.attempted,
            "paired": len(report.paired),
            "high": sum(1 for p in report.paired if p.tier == "HIGH"),
            "medium": sum(1 for p in report.paired if p.tier == "MEDIUM"),
            "unmatched_sales": len(report.unmatched_sales),
            "unmatched_inventory": len(report.unmatched_inventory),
            "success_rate": report.success_rate,
            "truncated": report.truncated,
        },
        "is_two_file": True,
        "row_count": int(len(sales_df)) + int(len(inventory_df)),
        "column_confidence_sales": sales_resolution.confidence,
        "column_confidence_inventory": inventory_resolution.confidence,
        "is_arabic": sales_resolution.is_arabic or inventory_resolution.is_arabic,
    }
    summary = _summary(merged, actions, aggregates, "paired_two_file", pairing_extra["row_count"], detected, extra=pairing_extra)
    return {"summary": summary, "actions": actions, "missing_data": []}


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


normalize_product_name = normalize_text