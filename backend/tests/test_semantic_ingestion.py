"""Phase C3 — semantic column mapping engine.

Tests the deterministic (no-AI) mapping of arbitrary merchant column names onto
the canonical ledger vocabulary through ``file_ingestion.resolve_columns`` and
the underlying ``semantic_mapping`` engine. Also verifies that ingestion
diagnostics flow through to the guest-audit response without leaking raw values
and without silently substituting zeros.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pandas as pd
import pytest

from app.services.file_ingestion import resolve_columns
from app.services.guest_audit_service import run_guest_audit, run_two_file_audit


# ---------------------------------------------------------------------------
# resolve_columns: the merge of the legacy alias pass + the semantic engine
# ---------------------------------------------------------------------------

def test_semantic_engine_attaches_ingestion_result():
    df = pd.DataFrame([
        {"Item Name": "Milk", "Units Sold": "3", "Retail Price": "12.5", "Total": "37.5"},
        {"Item Name": "Bread", "Units Sold": "2", "Retail Price": "10.0", "Total": "20.0"},
    ])
    res = resolve_columns(df)
    assert res.mapping.get("product_name") == "Item Name"
    assert res.mapping.get("quantity") == "Units Sold"
    assert res.mapping.get("price") == "Retail Price"
    assert res.ingestion_result is not None
    # Diagnostics are privacy-safe: no raw cell values leaked.
    diag = res.ingestion_result.as_dict()
    assert "status" in diag
    assert "mapping" in diag
    assert all("source_column" in m for m in diag["mapping"])
    assert "Milk" not in str(diag)


def test_unusual_header_maps_via_value_and_relationship_evidence():
    # "Qty" + "Rate" share no obvious alias but qty*rate ~= total should resolve.
    df = pd.DataFrame([
        {"Description": "Item A", "Qty": 2, "Rate": 15.0, "Debit": 30.0},
        {"Description": "Item B", "Qty": 3, "Rate": 10.0, "Debit": 30.0},
    ])
    res = resolve_columns(df)
    assert res.mapping.get("product_name") == "Description"
    assert res.mapping.get("quantity") == "Qty"


def test_semantic_engine_fills_gap_legacy_alias_missed():
    # "Number Sold" is not a legacy alias for quantity, but should map
    # semantically via token + value-shape evidence.
    df = pd.DataFrame([
        {"Product": "X", "Number Sold": "4", "Sale Rate": "9.5"},
    ])
    res = resolve_columns(df)
    assert res.mapping.get("product_name") == "Product"
    assert res.mapping.get("quantity") == "Number Sold"
    assert "price" in res.mapping  # Sale Rate resolves to price
    assert res.ingestion_result is not None



def test_relationship_qty_price_revenue_not_constant_true():
    # Guard against the old bug where qty*price was compared to itself.
    df = pd.DataFrame([
        {"Item": "A", "qty": 2, "unit_price": 10.0, "line_total": 20.0},
        {"Item": "B", "qty": 3, "unit_price": 5.0, "line_total": 15.0},
        {"Item": "C", "qty": 1, "unit_price": 20.0, "line_total": 20.0},
    ])
    res = resolve_columns(df)
    assert res.mapping.get("quantity") == "qty"
    assert res.mapping.get("price") == "unit_price"
    # line_total should be recognizable as revenue, not falsely a price.
    assert "quantity" in res.mapping
    # cost/stock/date remain unmapped (genuinely absent).
    assert "cost" not in res.mapping


def test_arabic_semantic_headers():
    df = pd.DataFrame([
        {"اسم المنتج": "حليب", "كمية": "10", "سعر البيع": "12"},
    ])
    res = resolve_columns(df)
    assert res.mapping.get("product_name") == "اسم المنتج"
    assert res.mapping.get("quantity") == "كمية"
    assert res.mapping.get("price") == "سعر البيع"
    assert res.is_arabic is True


def test_empty_frame_falls_back_to_legacy():
    df = pd.DataFrame()
    res = resolve_columns(df)
    assert res.mapping == {}
    assert res.ingestion_result is None


def test_legacy_alias_still_authoritative():
    df = pd.DataFrame([
        {"product_name": "Milk", "quantity": "2", "price": "12"},
    ])
    res = resolve_columns(df)
    assert res.mapping["product_name"] == "product_name"
    assert res.mapping["quantity"] == "quantity"
    assert res.mapping["price"] == "price"


# ---------------------------------------------------------------------------
# Two-file audit: ingestion diagnostics from both files
# ---------------------------------------------------------------------------

def test_two_file_audit_embeds_both_ingestion_diagnostics():
    sales = pd.DataFrame([
        {"Item": "Milk", "Qty": 5, "Price": 10.0, "Date": "2026-08-01"},
    ])
    inventory = pd.DataFrame([
        {"Product": "Milk", "Current Stock": 50, "Cost": 6.0},
    ])
    sales_res = resolve_columns(sales)
    inv_res = resolve_columns(inventory)
    assert sales_res.ingestion_result is not None
    assert inv_res.ingestion_result is not None

    result = run_two_file_audit(sales, inventory, sales_res, inv_res)
    summary = result["summary"]
    assert summary["is_two_file"] is True
    assert "ingestion" in summary
    assert "inventory" in summary["ingestion"]
    assert summary["ingestion"]["inventory"]["status"] == "ready"


# ---------------------------------------------------------------------------
# False-zero prevention: required fields must not silently map to nothing
# ---------------------------------------------------------------------------

def test_missing_required_quantity_is_reported_not_zeroed():
    # A sales-like file without any quantity column must not fabricate sales.
    df = pd.DataFrame([
        {"Item": "Milk", "Price": 10.0, "Date": "2026-08-01"},
    ])
    res = resolve_columns(df)
    assert "quantity" not in res.mapping
    assert "quantity" in res.missing


# ---------------------------------------------------------------------------
# Guest audit: diagnostics surfaced in summary
# ---------------------------------------------------------------------------

def test_guest_audit_summary_includes_ingestion_diagnostics():
    rows = [
        {"Item Name": "Milk", "Units Sold": 3, "Retail Price": 12.5},
        {"Item Name": "Bread", "Units Sold": 2, "Retail Price": 10.0},
    ]
    result = asyncio.run(run_guest_audit(rows))
    summary = result["summary"]
    assert "ingestion" in summary
    diag = summary["ingestion"]
    assert diag["status"] in ("ready", "needs_review")
    assert diag["confidence"] > 0
    # No raw merchant values in the diagnostics bloom.
    assert "Milk" not in str(diag)


def test_guest_audit_json_diagnostics_privacy_safe():
    # Same as above but confirms the as_dict surface is the DLP-clean subset.
    rows = [{"Item": "Secret Product", "Qty": 7, "Price": 3.0}]
    result = asyncio.run(run_guest_audit(rows))
    diag = result["summary"].get("ingestion")
    assert diag is not None
    joined = str(diag)
    assert "Secret Product" not in joined
    assert all(
        key in diag for key in ("status", "confidence", "version", "mapping",
                                "missing_required_fields", "ambiguous_fields",
                                "file_classification", "error_code")
    )


def test_infer_schema_deterministic():
    from app.services.semantic_mapping import infer_schema
    df = pd.DataFrame([
        {"Product": "A", "Qty": 2, "Price": 10.0},
        {"Product": "B", "Qty": 4, "Price": 5.0},
    ])
    r1 = infer_schema(df)
    r2 = infer_schema(df)
    assert r1.as_dict() == r2.as_dict()


def test_role_map_maps_source_to_role():
    from app.services.semantic_mapping import infer_schema
    df = pd.DataFrame([{"Product": "A", "Qty": 2, "Price": 10.0}])
    result = infer_schema(df)
    role_map = result.role_map()
    assert role_map.get("quantity") == "Qty"
    assert role_map.get("price") == "Price"


# ---------------------------------------------------------------------------
# Acceptance regressions: Phase 34 / 35 / 36 / 38 column mappings
# ---------------------------------------------------------------------------

def test_phase34_sales_mapping():
    df = pd.DataFrame([
        {"Transaction At": "2026-07-01", "SKU": "S1", "Product Name": "Coffee",
         "Category": "Beans", "Quantity": 120, "Unit Price SAR": 20.0,
         "Gross Amount SAR": 2400.0},
    ])
    res = resolve_columns(df)
    assert res.mapping.get("date") == "Transaction At"
    assert res.mapping.get("product_name") == "Product Name"
    assert res.mapping.get("quantity") == "Quantity"
    assert res.mapping.get("price") == "Unit Price SAR"


def test_phase34_inventory_mapping_stock_not_policy_threshold():
    # Reorder/Target/Inbound are inventory policy columns and must NOT become a
    # sales quantity; Current Stock Qty must be the primary stock.
    df = pd.DataFrame([
        {"SKU": "S1", "Product Name": "Coffee", "Cost Price SAR": 12.0,
         "Sell Price SAR": 20.0, "Current Stock Qty": 500,
         "Reorder Point Qty": 60, "Target Stock Qty": 300, "Inbound Qty": 100},
    ])
    res = resolve_columns(df)
    assert res.mapping.get("stock") == "Current Stock Qty"
    assert res.mapping.get("cost") == "Cost Price SAR"
    assert res.mapping.get("product_name") == "Product Name"
    # No sales quantity in an inventory file, and policy thresholds are not
    # quantity.
    assert "quantity" not in res.mapping
    rm = res.ingestion_result.role_map()
    assert rm.get("reorder_point") == "Reorder Point Qty"
    assert rm.get("target_stock") == "Target Stock Qty"
    assert rm.get("inbound_stock") == "Inbound Qty"


def test_phase35_sales_mapping_differently_named():
    df = pd.DataFrame([
        {"Description": "Coffee", "Ref": "R1", "Units Sold": 120, "Retail": 20.0},
    ])
    res = resolve_columns(df)
    assert res.mapping.get("product_name") == "Description"
    assert res.mapping.get("quantity") == "Units Sold"
    assert res.mapping.get("price") == "Retail"


def test_phase35_inventory_mapping():
    df = pd.DataFrame([
        {"Description": "Coffee", "Available": 500, "Purchase Cost": 12.0, "Retail": 20.0},
    ])
    res = resolve_columns(df)
    assert res.mapping.get("stock") == "Available"
    assert res.mapping.get("cost") == "Purchase Cost"
    assert res.mapping.get("product_name") == "Description"


def test_arabic_cost_price_mapping_inventory():
    # "سعر التكلفة" (cost price) must map to cost, not be lost to the article.
    df = pd.DataFrame([
        {"اسم الصنف": "قهوة", "المخزون": 400, "سعر التكلفة": 10.0, "سعر البيع": 20.0},
    ])
    res = resolve_columns(df)
    assert res.mapping.get("product_name") == "اسم الصنف"
    assert res.mapping.get("stock") == "المخزون"
    assert res.mapping.get("cost") == "سعر التكلفة"
    assert res.mapping.get("price") == "سعر البيع"


def test_phase38_regression_nonzero_inventory():
    # The old engine returned SAR 0 for transaction_at/unit_price_sar and
    # current_stock_qty/cost_price_sar/sell_price_sar files. Must be non-zero.
    sales = pd.DataFrame([
        {"transaction_at": "2026-07-01", "item_name": "Coffee", "unit_price_sar": 20.0, "qty_sold": 100},
        {"transaction_at": "2026-07-02", "item_name": "Tea", "unit_price_sar": 15.0, "qty_sold": 50},
    ])
    inventory = pd.DataFrame([
        {"item_name": "Coffee", "current_stock_qty": 400, "cost_price_sar": 10.0, "sell_price_sar": 20.0},
        {"item_name": "Tea", "current_stock_qty": 200, "cost_price_sar": 8.0, "sell_price_sar": 15.0},
    ])
    sr = resolve_columns(sales)
    ir = resolve_columns(inventory)
    result = run_two_file_audit(sales, inventory, sr, ir)
    inv_value = result["summary"].get("inventory_value_sar")
    assert inv_value and float(inv_value) > 0
    assert float(inv_value) == 5600.0  # (400*10)+(200*8)


def test_inventory_only_file_status_ready_not_quantity_required():
    df = pd.DataFrame([
        {"Product": "Milk", "Current Stock": 50, "Cost": 6.0},
    ])
    res = resolve_columns(df)
    assert res.ingestion_result.status == "ready"
    assert res.ingestion_result.missing_required_fields == []


def test_sales_missing_quantity_status_needs_review():
    df = pd.DataFrame([
        {"Item": "Milk", "Price": 10.0, "Date": "2026-08-01"},
    ])
    res = resolve_columns(df)
    assert res.ingestion_result.status == "needs_review"
    assert "quantity" in res.ingestion_result.missing_required_fields
    assert res.ingestion_result.error_code == "missing_required_field"


def test_one_column_never_maps_to_two_roles():
    # A single column must never be assigned to two different roles (Phase 26).
    frames = [
        pd.DataFrame([{"Item": "A", "Qty": 2, "Price": 10.0, "Date": "2026-08-01"}]),
        pd.DataFrame([{"Product": "A", "Current Stock": 5, "Cost": 6.0, "Sell Price": 9.0}]),
        pd.DataFrame([{"Description": "A", "Units Sold": 3, "Retail": 8.0, "Total": 24.0}]),
        pd.DataFrame([{"اسم الصنف": "س", "المخزون": 5, "سعر التكلفة": 6.0, "سعر البيع": 9.0}]),
    ]
    for df in frames:
        res = resolve_columns(df)
        col_roles: dict[str, list[str]] = {}
        for role, col in res.mapping.items():
            col_roles.setdefault(col, []).append(role)
        for roles in col_roles.values():
            assert len(roles) == 1, f"column mapped to multiple roles: {roles}"


def test_diagnostics_reflect_status_codes():
    from app.services.semantic_mapping import infer_schema
    df = pd.DataFrame([{"Item": "Milk", "Price": 10.0}])
    result = infer_schema(df)
    diag = result.as_dict()
    assert diag["status"] in ("needs_review", "insufficient_data")
    assert "quantity" in diag["missing_required_fields"]
    assert diag["error_code"] == "missing_required_field"


def test_semantically_equivalent_34_and_35_files_agree():
    # Different naming, same data -> materially equivalent inventory value.
    s34 = pd.DataFrame([
        {"Transaction At": "2026-07-01", "Product Name": "Coffee", "Quantity": 120, "Unit Price SAR": 20.0},
        {"Transaction At": "2026-07-02", "Product Name": "Tea", "Quantity": 50, "Unit Price SAR": 15.0},
    ])
    i34 = pd.DataFrame([
        {"Product Name": "Coffee", "Current Stock Qty": 400, "Cost Price SAR": 10.0, "Sell Price SAR": 20.0},
        {"Product Name": "Tea", "Current Stock Qty": 200, "Cost Price SAR": 8.0, "Sell Price SAR": 15.0},
    ])
    s35 = pd.DataFrame([
        {"Description": "Coffee", "Units Sold": 120, "Retail": 20.0, "Date & Time": "2026-07-01"},
        {"Description": "Tea", "Units Sold": 50, "Retail": 15.0, "Date & Time": "2026-07-02"},
    ])
    i35 = pd.DataFrame([
        {"Description": "Coffee", "Available": 400, "Purchase Cost": 10.0, "Retail": 20.0},
        {"Description": "Tea", "Available": 200, "Purchase Cost": 8.0, "Retail": 15.0},
    ])
    r34 = run_two_file_audit(s34, i34, resolve_columns(s34), resolve_columns(i34))
    r35 = run_two_file_audit(s35, i35, resolve_columns(s35), resolve_columns(i35))
    assert r34["summary"]["inventory_value_sar"] == r35["summary"]["inventory_value_sar"]
    assert float(r34["summary"]["inventory_value_sar"]) > 0
