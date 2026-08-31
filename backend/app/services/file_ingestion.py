"""Bilingual (Arabic / English / transliterated) column detection and value
normalization for guest uploads.

Deterministic, no AI. Every Arabic label maps to the same canonical field the
English labels do, so a merchant's exported spreadsheet drives the same audit
regardless of the language of its headers.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd

D = Decimal
ZERO = D("0")

# Columns a product ledger needs, with English, Arabic and common
# transliterated aliases (normalized the same way every header is).
COLUMN_ALIASES: dict[str, set[str]] = {
    "product_name": {
        "product_name",
        "item_name",
        "name",
        "product",
        "item",
        "title",
        "product_name_ar",
        "اسم المنتج",
        "اسم الصنف",
        "اسم السلعة",
        "اسم_المنتج",
        "المنتج",
        "الاسم",
        "الصنف",
        "السلعة",
        "البند",
        "اسم",
    },
    "quantity": {
        "quantity",
        "qty",
        "sold_quantity",
        "units",
        "amount",
        "quantity_sold",
        "qty_sold",
        "units_sold",
        "quantityar",
        "الكمية",
        "كمية",
        "الكمية المباعة",
        "الكيمة المباعة",
        "الكمية_المباعة",
        "عدد",
        "العدد",
        "الوحدات",
        "المبيعات",
        "الكميه",
    },
    "price": {
        "unit_price",
        "price",
        "sale_price",
        "sell_price",
        "selling_price",
        "revenue",
        "total_amount",
        "unit_price_sar",
        "amount_sar",
        "السعر",
        "سعر البيع",
        "سعر البيع للوحدة",
        "سعر_البيع",
        "سعر الوحدة",
        "إيراد",
        "الإيراد",
        "الايراد",
        "المبلغ",
        "المبلغ الكلي",
        "مبلغ",
        "قيمة البيع",
    },
    "cost": {
        "cost_price",
        "cost",
        "purchase_price",
        "buy_price",
        "unit_cost",
        "costar",
        "التكلفة",
        "سعر التكلفة",
        "سعر الشراء",
        "تكلفة",
        "التكلفه",
        "سعر_التكلفة",
        "سعر_الشراء",
        "كلفة",
    },
    "stock": {
        "current_stock",
        "stock",
        "stock_quantity",
        "quantity_on_hand",
        "on_hand",
        "on_hand_qty",
        "stock_level",
        "inventory",
        "المخزون الحالي",
        "المخزون",
        "الرصيد",
        "الكمية المتاحة",
        "الكمية بالمخزن",
        "الكميه المتاحه",
        "رصيد المخزون",
        "التوفر",
        "المتوفر",
    },
    "date": {
        "date",
        "sale_date",
        "transaction_date",
        "order_date",
        "created_at",
        "invoice_date",
        "created_date",
        "التاريخ",
        "تاريخ البيع",
        "تاريخ العملية",
        "تاريخ الاوردر",
        "التاريخ",
        "تاريخ",
        "تاريخ الفاتورة",
    },
}

CANONICAL_FIELDS = tuple(COLUMN_ALIASES.keys())

# Normalization passes that must be applied in this order.
_ARABIC_DIACRITICS = {"\u064b", "\u064c", "\u064d", "\u064e", "\u064f", "\u0650", "\u0651", "\u0652"}
_ARABIC_NORMALIZED = {
    "\u0621": "\u0627",  # hamza above -> alef
    "\u0622": "\u0627",  # alef madda -> alef
    "\u0623": "\u0627",  # alef hamza above -> alef
    "\u0625": "\u0627",  # alef hamza below -> alef
    "\u0649": "\u064a",  # alef maksura -> yeh
    "\u0671": "\u0627",  # alef wasla -> alef
    "\u0629": "\u0647",  # teh marbuta -> heh
}
# Arabic-Indic (Eastern Arabic) and extended Arabic-Indic (Persian) digits.
_ARABIC_DIGIT_MAP = {
    "\u0660": "0", "\u0661": "1", "\u0662": "2", "\u0663": "3", "\u0664": "4",
    "\u0665": "5", "\u0666": "6", "\u0667": "7", "\u0668": "8", "\u0669": "9",
    "\u06f0": "0", "\u06f1": "1", "\u06f2": "2", "\u06f3": "3", "\u06f4": "4",
    "\u06f5": "5", "\u06f6": "6", "\u06f7": "7", "\u06f8": "8", "\u06f9": "9",
}


def normalize_text(value: Any) -> str:
    """Normalize a header or product name for matching.

    - Canonic Unicode decomposition (NFKC)
    - Arabic digits -> ASCII digits
    - Strip Hebrew/Arabic diacritics and normalize letter variants
    - Punctuation becomes spaces; runs of whitespace collapse
    """
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = "".join(_ARABIC_DIGIT_MAP.get(ch, ch) for ch in text)
    for ch in _ARABIC_DIACRITICS:
        text = text.replace(ch, "")
    for src, dst in _ARABIC_NORMALIZED.items():
        text = text.replace(src, dst)
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE).lower()
    return re.sub(r"\s+", " ", text).strip()


def normalize_header(value: Any) -> str:
    """Header name -> canonical matching key (same path as normalize_text)."""
    return normalize_text(value)


# Aliases normalized the same way every incoming header is, so "product_name"
# and "product name" and "اسم المنتج" all resolve to the same canonical field.
NORMALIZED_ALIASES: dict[str, tuple[str, ...]] = {
    key: tuple(sorted({normalize_header(a) for a in aliases if normalize_header(a)}, key=len, reverse=True))
    for key, aliases in COLUMN_ALIASES.items()
}


def to_ascii_digits(value: Any) -> str:
    if value is None:
        return ""
    text = "".join(_ARABIC_DIGIT_MAP.get(ch, ch) for ch in str(value))
    return text


def coerce_numeric(value: Any) -> Decimal:
    """Parse one cell into a Decimal, tolerating Arabic/regional formats.

    Accepts: Arabic-Indic digits, Persian digits, Arabic thousand separator
    (U+066C), Arabic decimal separator (U+066B), commas, parentheses negatives,
    and a leading/trailing SAR / ر.س / ﷼ prefix or suffix.
    """
    if value is None or value == "":
        return ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        try:
            return ZERO if pd.isna(value) else D(str(value))
        except Exception:
            return ZERO
    text = to_ascii_digits(value)
    text = text.replace("\u066c", "").strip()  # Arabic thousands separator
    if "\u066b" in text:  # Arabic decimal separator
        text = text.replace("\u066b", ".")
    text = re.sub(r"[,\s]", "", text)
    text = text.replace("﷼", "").replace("ر.س", "").replace("ر.س.", "").replace("ريال", "")
    text = re.sub(r"(?i)(sar|s\.a\.r|usd)", "", text).strip()
    if re.fullmatch(r"\(-?[\d.]+\)", text):
        text = "-" + text.strip("()")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return ZERO
    try:
        return D(text)
    except InvalidOperation:
        return ZERO


def coerce_numeric_series(series: pd.Series) -> pd.Series:
    """Vectorized numeric coercion for a frame column."""
    return series.map(coerce_numeric)


def is_arabic(text: Any) -> bool:
    """True when a string contains Arabic script characters."""
    if text is None:
        return False
    return bool(re.search(r"[\u0600-\u06ff]", str(text)))


@dataclass
class ColumnResolution:
    mapping: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    is_arabic: bool = False
    detected_fields: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def resolve_columns(df: pd.DataFrame) -> ColumnResolution:
    """Map actual columns to canonical ledger fields.

    Deterministic: each canonical field takes the first best alias found,
    scanning exact normalized matches first, then substring containment.
    """
    columns = [normalize_header(c) for c in df.columns]
    by_key: dict[str, list[str]] = {key: list(aliases) for key, aliases in NORMALIZED_ALIASES.items()}

    mapping: dict[str, str] = {}
    exact_used: set[int] = set()
    for key, aliases in by_key.items():
        for alias in aliases:
            for idx, col in enumerate(columns):
                if idx in exact_used:
                    continue
                if col == alias:
                    mapping[key] = df.columns[idx]
                    exact_used.add(idx)
                    break
            if key in mapping:
                break

    fuzzy_used: set[int] = set(exact_used)
    for key in CANONICAL_FIELDS:
        if key in mapping:
            continue
        best_idx = None
        for idx, col in enumerate(columns):
            if idx in fuzzy_used or not col:
                continue
            if any(alias in col for alias in NORMALIZED_ALIASES[key]) or col.split()[0] == key:
                best_idx = idx
                break
        if best_idx is not None:
            mapping[key] = df.columns[best_idx]
            fuzzy_used.add(best_idx)

    detected = [k for k in CANONICAL_FIELDS if k in mapping]
    confidence = max(0.0, (len(detected) / min(len(CANONICAL_FIELDS), max(1, len(df.columns)))) * 100)
    arabic = any(is_arabic(c) for c in df.columns)

    needed: list[str] = []
    for key in ("product_name", "quantity", "price", "cost", "stock", "date"):
        if key not in mapping:
            needed.append(key)
    return ColumnResolution(
        mapping=mapping,
        confidence=round(confidence, 1),
        is_arabic=arabic,
        detected_fields=detected,
        missing=needed,
    )


@dataclass
class FileMetadata:
    file_type: str
    detected_columns: list[str]
    column_confidence: float
    is_arabic_headers: bool
    is_arabic_data: bool
    sheet_count: int | None = None
    selected_sheet: str | None = None
    header_row_index: int | None = None


def analyze_file_metadata(df: pd.DataFrame, file_type: str, extras: dict[str, Any] | None = None) -> FileMetadata:
    """Build the privacy-safe metadata record for one uploaded file.

    Only column names and shape-level facts are reported — never row contents,
    product names, customers, or values.
    """
    resolution = resolve_columns(df)
    sample_text = ""
    for col in df.columns:
        for value in df[col].head(20).dropna():
            if isinstance(value, str) and is_arabic(value):
                sample_text = value
                break
        if sample_text:
            break
    extras = extras or {}
    return FileMetadata(
        file_type=file_type,
        detected_columns=resolution.detected_fields,
        column_confidence=resolution.confidence,
        is_arabic_headers=resolution.is_arabic,
        is_arabic_data=bool(sample_text),
        sheet_count=extras.get("sheet_count"),
        selected_sheet=extras.get("selected_sheet"),
        header_row_index=extras.get("header_row_index"),
    )