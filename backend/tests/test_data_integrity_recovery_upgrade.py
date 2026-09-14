import importlib.util
from pathlib import Path

import pandas as pd
import pytest

MODULE = Path(__file__).parents[1] / "app" / "services" / "data_normalizer.py"
spec = importlib.util.spec_from_file_location("nazmos_data_normalizer_v2", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_invalid_date_is_rejected_in_strict_mode():
    df = pd.DataFrame({"date": ["not-a-date"], "product": ["A"], "qty": [1]})
    with pytest.raises(mod.DataQualityError) as exc:
        mod.normalize_dataframe(df, {"date": "transaction_at", "product": "item_name", "qty": "quantity"}, strict=True)
    assert any(x["reason"] == "invalid_date" for x in exc.value.report["rejected"])


def test_negative_quantity_requires_explicit_return_type():
    df = pd.DataFrame({"date": ["2026-08-24"], "product": ["A"], "qty": [-2]})
    with pytest.raises(mod.DataQualityError) as exc:
        mod.normalize_dataframe(df, {"date": "transaction_at", "product": "item_name", "qty": "quantity"}, strict=True)
    assert any(x["reason"] == "negative_quantity_requires_explicit_transaction_type" for x in exc.value.report["rejected"])


def test_return_is_normalized_as_positive_units_with_explicit_type():
    df = pd.DataFrame({"date": ["2026-08-24"], "product": ["A"], "qty": [-2], "price": [10], "type": ["refund"]})
    out = mod.normalize_dataframe(
        df,
        {"date": "transaction_at", "product": "item_name", "qty": "quantity", "price": "unit_price", "type": "transaction_type"},
        strict=True,
    )
    assert out.iloc[0]["quantity"] == 2
    assert out.iloc[0]["transaction_type"] == "return"


def test_duplicate_rows_are_reported():
    df = pd.DataFrame({"date": ["2026-08-24", "2026-08-24"], "product": ["A", "A"], "qty": [2, 2]})
    with pytest.raises(mod.DataQualityError) as exc:
        mod.normalize_dataframe(df, {"date": "transaction_at", "product": "item_name", "qty": "quantity"}, strict=True)
    assert exc.value.report["duplicate_rows"] == 1


def test_sales_without_price_basis_is_rejected_in_strict_mode():
    df = pd.DataFrame({"date": ["2026-08-24"], "product": ["A"], "qty": [3]})
    with pytest.raises(mod.DataQualityError) as exc:
        mod.normalize_dataframe(df, {"date": "transaction_at", "product": "item_name", "qty": "quantity"}, strict=True)
    assert any(x["reason"] == "missing_price_basis" for x in exc.value.report["rejected"])


def test_sales_without_price_basis_allowed_when_non_strict():
    df = pd.DataFrame({"date": ["2026-08-24"], "product": ["A"], "qty": [3]})
    out = mod.normalize_dataframe(df, {"date": "transaction_at", "product": "item_name", "qty": "quantity"})
    assert len(out) == 1


def test_negative_current_stock_is_rejected_in_strict_mode():
    df = pd.DataFrame({"product": ["A"], "stock": [-5]})
    with pytest.raises(mod.DataQualityError) as exc:
        mod.normalize_dataframe(df, {"product": "item_name", "stock": "current_stock"}, strict=True)
    assert any(x["reason"] == "negative_current_stock" for x in exc.value.report["rejected"])


def test_blank_money_cell_is_rejected_in_strict_mode():
    df = pd.DataFrame({"date": ["2026-08-24"], "product": ["A"], "qty": [2], "price": [None]})
    with pytest.raises(mod.DataQualityError) as exc:
        mod.normalize_dataframe(
            df,
            {"date": "transaction_at", "product": "item_name", "qty": "quantity", "price": "unit_price"},
            strict=True,
        )
    assert any(x["reason"] == "blank_required_value" for x in exc.value.report["rejected"])


def test_blank_cost_in_inventory_is_accepted_in_strict_mode():
    df = pd.DataFrame({"product": ["A"], "stock": [52], "cost": [None]})
    out = mod.normalize_dataframe(
        df,
        {"product": "item_name", "stock": "current_stock", "cost": "cost_price"},
        strict=True,
    )
    assert len(out) == 1


def test_blank_current_stock_is_rejected_in_strict_mode():
    df = pd.DataFrame({"product": ["A"], "stock": [None], "cost": [5]})
    with pytest.raises(mod.DataQualityError) as exc:
        mod.normalize_dataframe(df, {"product": "item_name", "stock": "current_stock", "cost": "cost_price"}, strict=True)
    assert any(x["reason"] == "blank_required_value" for x in exc.value.report["rejected"])


def test_duplicate_sku_alias_names_stay_warning_in_strict_mode():
    df = pd.DataFrame(
        {"product": ["Mineral Water 0.5L", "Mineral Water 500ml"], "sku": ["SKU-1001", "SKU-1001"], "stock": [5, 5]}
    )
    out = mod.normalize_dataframe(df, {"product": "item_name", "sku": "item_sku", "stock": "current_stock"}, strict=True)
    report = out.attrs["data_quality_report"]
    assert not report["rejected"]
    assert any(w["reason"] == "duplicate_sku_multiple_names" for w in report["warnings"])
