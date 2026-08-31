"""Phase C2 — bilingual file ingestion: Arabic/English/transliterated headers,
Arabic-Indic digits, Arabic separators, RTL metadata. Deterministic, no LLM.
"""
from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from app.services.file_ingestion import (
    analyze_file_metadata,
    coerce_numeric,
    is_arabic,
    normalize_text,
    resolve_columns,
)


def test_arabic_headers_map_to_canonical_fields():
    df = pd.DataFrame([
        {"اسم المنتج": "حليب", "الكمية": "١٠", "سعر البيع": "12", "التكلفة": "8", "المخزون الحالي": "20", "التاريخ": "2026-08-01"},
    ])
    res = resolve_columns(df)
    assert res.mapping.get("product_name") == "اسم المنتج"
    assert res.mapping.get("quantity") == "الكمية"
    assert res.mapping.get("price") == "سعر البيع"
    assert res.mapping.get("cost") == "التكلفة"
    assert res.mapping.get("stock") == "المخزون الحالي"
    assert res.mapping.get("date") == "التاريخ"
    assert res.is_arabic is True


def test_transliterated_and_underscored_headers():
    df = pd.DataFrame([{"Product Name": "X", "Sold Quantity": "1", "Unit Price": "5"}])
    res = resolve_columns(df)
    assert res.mapping.get("product_name") == "Product Name"
    assert res.mapping.get("quantity") == "Sold Quantity"
    assert res.mapping.get("price") == "Unit Price"


def test_header_normalization_handles_diacritics_and_hamza_variants():
    df = pd.DataFrame([{" الكَمِّيَّة ": "1", "اسمٌ المنتج": "X", "المخزون": "5"}])
    res = resolve_columns(df)
    assert res.mapping.get("quantity") is not None
    assert res.mapping.get("product_name") is not None
    assert res.mapping.get("stock") is not None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("١٠٠", Decimal("100")),
        ("100", Decimal("100")),
        ("1٬000٫50", Decimal("1000.50")),
        ("1,000.75", Decimal("1000.75")),
        ("SAR 12.5", Decimal("12.5")),
        ("12.5 SAR", Decimal("12.5")),
        ("ر.س ٤٥", Decimal("45")),
        ("(20)", Decimal("-20")),
        ("-7", Decimal("-7")),
        ("3.5", Decimal("3.5")),
        ("", Decimal("0")),
        (None, Decimal("0")),
        ("٤٥٫٢٥", Decimal("45.25")),
    ],
)
def test_coerce_numeric_handles_regional_formats(raw, expected):
    assert coerce_numeric(raw) == expected


def test_coerce_numeric_rejects_garbage():
    assert coerce_numeric("abc") == Decimal("0")
    assert coerce_numeric("N/A") == Decimal("0")
    assert coerce_numeric("--") == Decimal("0")


def test_is_arabic_and_normalized_digits():
    assert is_arabic("اسم المنتج") is True
    assert is_arabic("Product") is False
    assert normalize_text("كوكا_كولا‎") == "كوكا كولا"


def test_metadata_is_privacy_safe_and_deterministic():
    df = pd.DataFrame([{"اسم المنتج": "حليب طازج", "الكمية": "10", "السعر": "12", "التكلفة": "8", "المخزون الحالي": "50"}])
    meta = analyze_file_metadata(df, "csv")
    assert meta.detected_columns == ["product_name", "quantity", "price", "cost", "stock"]
    assert meta.is_arabic_headers is True
    assert meta.is_arabic_data is True

    df2 = pd.DataFrame([{"Product": "Milk", "Qty": "10", "Price": "12"}])
    meta2 = analyze_file_metadata(df2, "csv")
    assert meta2.detected_columns == ["product_name", "quantity", "price"]
    assert meta2.is_arabic_data is False


def test_merge_quantity_arabic_indic_digits_in_numeric_cell():
    assert coerce_numeric("١٬٢٣٤٫٥") == Decimal("1234.5")