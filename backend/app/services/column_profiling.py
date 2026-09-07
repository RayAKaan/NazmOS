"""Deterministic per-column profiling for semantic ingestion.

For every candidate column we build a small, privacy-safe profile describing its
*shape*: numeric/datetime/text composition, magnitude ranges, currency and
identifier signals, and so on. These profiles let the semantic mapper
distinguish ``quantity`` from ``price`` from ``stock`` from ``SKU`` without
depending on header text alone.

Safety properties:

- Only *bounded samples* are inspected (never the whole sheet for every stat).
- Only shape-level facts and binned/aggregate signals are retained. Raw cell
  values are used transiently inside the trusted ingestion process and are never
  returned by ``profile_frame``, logged, or telemetry'd.

Deterministic, no AI.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from statistics import median
from typing import Any

import pandas as pd

from app.services.file_ingestion import to_ascii_digits

# Bounded profiling limits (Phase 42): enough signal for real exports, cheap for
# large files. Exact statistics are only computed on the bounded sample.
MAX_SAMPLE_SIZE = 600
MAX_STRIDE_SCAN = 10_000
MAX_CELL_LEN = 300

_CURRENCY_SYMBOLS = ("sar", "ر.س", "ريال", "﷼", "usd", "s.a.r", "دولار")
_PERCENT_SYMBOLS = ("%", "٪", "pct", "percent", "ratio")
_PORTION_WORDS = ("%", "split", "commission", "margin")


@dataclass
class ColumnProfile:
    name: str  # original column header
    non_null_ratio: float = 0.0
    numeric_ratio: float = 0.0
    integer_ratio: float = 0.0  # of non-null values that parse & are integral
    decimal_ratio: float = 0.0  # of non-null values with a fractional part
    two_dp_ratio: float = 0.0
    date_ratio: float = 0.0
    text_ratio: float = 0.0
    negative_ratio: float = 0.0
    zero_ratio: float = 0.0
    unique_ratio: float = 1.0
    currency_ratio: float = 0.0
    percent_ratio: float = 0.0
    identifier_ratio: float = 0.0
    min_value: Decimal | None = None
    max_value: Decimal | None = None
    median_value: Decimal | None = None
    sample_count: int = 0
    patterns: list[str] = field(default_factory=list)


def _strip_currency(text: str) -> str:
    lowered = text.lower()
    for sym in _CURRENCY_SYMBOLS:
        lowered = lowered.replace(sym, "")
        text = text.replace(sym, "")
    return text


def _try_number(value: Any) -> Decimal | None:
    """Parse one cell to Decimal, or return None if it is not numeric.

    Distinguishes genuine zeros from unparseable garbage (unlike ``coerce_numeric``
    which maps both to Decimal(0) -- that is fine for value consumption but wrong
    for profiling ratios).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        if float(value) != value and str(value) in ("nan", "inf", "-inf"):
            return None
        return Decimal(str(value))
    text = to_ascii_digits(value).strip()
    if not text:
        return None
    has_currency = any(sym in text for sym in ("﷼", "ر.س"))
    text = _strip_currency(to_ascii_digits(value))
    # Replace Arabic thousands separators, then normalize separators.
    text = text.replace("\u066c", "").replace(",", "")
    text = text.replace("\u066b", ".")
    text = re.sub(r"\s+", "", text)
    text = text.replace("﷼", "").replace("ر.س", "").replace("ر.س.", "").replace("ريال", "")
    if has_currency:
        text = text.replace("س", "")  # stray remainder of ر.س after strip
    text = re.sub(r"(?i)(sar|s\.a\.r|usd)", "", text).strip()
    if re.fullmatch(r"\(-?[\d.]+\)", text):
        text = "-" + text.strip("()")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return None
    try:
        return Decimal(text)
    except Exception:
        return None


def _is_identifier_like(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text or len(text) > MAX_CELL_LEN:
        return False
    # A SKU / product code is alphanumeric with a strong alphabetic or "-"/"_"
    # component and NOT a plain integer/float (so "42" is not an identifier).
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return False
    alpha = sum(1 for ch in text if ch.isalpha())
    digit = sum(1 for ch in text if ch.isdigit())
    total = len([ch for ch in text if (ch.isalnum() or ch in "-_/.")])
    if total == 0:
        return False
    if alpha == 0:
        return False
    if digit == 0 and alpha <= 2:
        return False
    # Skip long prose / descriptions.
    if len(text.split()) > 4:
        return False
    return True


def _sample_values(series: pd.Series) -> list[Any]:
    non_null = series.dropna()
    total = len(non_null)
    if total == 0:
        return []
    if total <= MAX_SAMPLE_SIZE:
        return list(non_null)
    # Bounded: first chunk + evenly strided rest up to a cap.
    step = max(1, total // MAX_SAMPLE_SIZE)
    picks: list[Any] = []
    for i in range(0, min(total, MAX_STRIDE_SCAN), step):
        picks.append(non_null.iloc[i])
        if len(picks) >= MAX_SAMPLE_SIZE:
            break
    return picks


_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو",
    "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
)


def _try_date_token(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Excel serial dates: > 20000 is a plausible date serial in retail data.
        return 20000 <= float(value) <= 15_000_000
    text = str(value).strip()
    if not text:
        return False
    if len(text) > 40:
        return False
    # Reject plainly-numeric and alphanumeric SKU/transaction-id style tokens.
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return False
    lowered = text.lower()
    # Require a genuine date structure: a digit date component, a separator, or
    # a recognized (possibly localized) month name. Bare ids like "T1"/"R2",
    # words like "pcs", or plain prose are NOT dates.
    has_month_name = any(m in lowered for m in _MONTH_NAMES)
    has_digits = any(ch.isdigit() for ch in text)
    has_sep = any(ch in text for ch in "/-.") or ":" in text
    # ISO-ish like 2026-08-01 or 20260801, or 01/08, or "August 2026"
    if not (has_digits and (has_sep or has_month_name)):
        return False
    try:
        parsed = pd.to_datetime(text, errors="coerce")
    except Exception:
        return False
    if pd.isna(parsed):
        return False
    # Reject pandas' spurious year-0001 fill (bare text ids parsed to year 1).
    if getattr(parsed, "year", 0) < 1900:
        return False
    return True


def profile_column(name: Any, series: pd.Series) -> ColumnProfile:
    """Build a deterministic profile for one column (bounded sampling)."""
    profile = ColumnProfile(name=str(name))
    samples = _sample_values(series)
    profile.sample_count = len(samples)
    if not samples:
        return profile

    total = len(series)
    non_null = int(series.notna().sum()) if total else 0
    profile.non_null_ratio = round(non_null / total, 4) if total else 0.0

    numbers: list[Decimal] = []
    n_numeric = n_int = n_decimal = n_two_dp = 0
    n_date = n_text = n_negative = n_zero = n_currency = n_percent = n_id = 0
    seen: set[str] = set()
    n_uniq = 0
    pattern_counter: dict[str, int] = {}

    for v in samples:
        s = to_ascii_digits(v) if v is not None else ""
        key = "none" if v is None else str(v)[:80]
        if key not in seen:
            seen.add(key)
            n_uniq += 1

        if isinstance(v, str):
            low = v.lower()
            if any(sym in low for sym in _CURRENCY_SYMBOLS):
                n_currency += 1
            if any(sym in low for sym in _PERCENT_SYMBOLS):
                n_percent += 1

        num = _try_number(v)
        if num is not None:
            n_numeric += 1
            numbers.append(num)
            if num == num.to_integral_value():
                n_int += 1
            else:
                n_decimal += 1
            if -num == -num.quantize(Decimal("0.01")) and num != num.to_integral_value():
                n_two_dp += 1
            if num < 0:
                n_negative += 1
            if num == 0:
                n_zero += 1
        elif _try_date_token(v):
            n_date += 1
            pattern_counter.setdefault("date", 0)
            pattern_counter["date"] += 1
        elif isinstance(v, str) and _is_identifier_like(v):
            n_id += 1
            pattern_counter.setdefault("identifier", 0)
            pattern_counter["identifier"] += 1
        elif isinstance(v, str) and _is_identifier_like(v) is False and str(v).strip():
            n_text += 1

    denom = len(samples) or 1
    profile.numeric_ratio = round(n_numeric / denom, 4)
    profile.integer_ratio = round(n_int / denom, 4)
    profile.decimal_ratio = round(n_decimal / denom, 4)
    profile.two_dp_ratio = round(n_two_dp / denom, 4)
    profile.date_ratio = round(n_date / denom, 4)
    profile.text_ratio = round(n_text / denom, 4)
    profile.negative_ratio = round(n_negative / denom, 4)
    profile.zero_ratio = round(n_zero / denom, 4)
    profile.unique_ratio = round(n_uniq / denom, 4)
    profile.currency_ratio = round(n_currency / denom, 4)
    profile.percent_ratio = round(n_percent / denom, 4)
    profile.identifier_ratio = round(n_id / denom, 4)

    if numbers:
        profile.min_value = min(numbers)
        profile.max_value = max(numbers)
        try:
            profile.median_value = Decimal(str(median([float(n) for n in numbers])))
        except Exception:
            profile.median_value = None

    top = sorted(pattern_counter.items(), key=lambda kv: -kv[1])[:3]
    profile.patterns = [k for k, _ in top]
    return profile


def profile_frame(df: pd.DataFrame) -> dict[str, ColumnProfile]:
    """Profile every column in a frame. Returns {original_header: ColumnProfile}."""
    out: dict[str, ColumnProfile] = {}
    for col in df.columns:
        out[str(col)] = profile_column(col, df[col])
    return out
