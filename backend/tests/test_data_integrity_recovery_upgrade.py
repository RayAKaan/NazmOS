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
    df = pd.DataFrame({"date": ["2026-08-24"], "product": ["A"], "qty": [-2], "type": ["refund"]})
    out = mod.normalize_dataframe(
        df,
        {"date": "transaction_at", "product": "item_name", "qty": "quantity", "type": "transaction_type"},
        strict=True,
    )
    assert out.iloc[0]["quantity"] == 2
    assert out.iloc[0]["transaction_type"] == "return"


def test_duplicate_rows_are_reported():
    df = pd.DataFrame({"date": ["2026-08-24", "2026-08-24"], "product": ["A", "A"], "qty": [2, 2]})
    with pytest.raises(mod.DataQualityError) as exc:
        mod.normalize_dataframe(df, {"date": "transaction_at", "product": "item_name", "qty": "quantity"}, strict=True)
    assert exc.value.report["duplicate_rows"] == 1
