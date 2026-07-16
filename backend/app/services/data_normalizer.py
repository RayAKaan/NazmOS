import re
from datetime import datetime
from typing import Dict, List

import pandas as pd


DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%d-%b-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%Y/%m/%d",
    "%d/%m/%y",
    "%d-%m-%y",
    "%Y%m%d",
    "%b %d, %Y",
    "%B %d, %Y",
]

FIELD_TARGETS = [
    "transaction_at",
    "item_name",
    "item_sku",
    "barcode",
    "brand",
    "pack_size",
    "storage_type",
    "category_name",
    "quantity",
    "current_stock",
    "reorder_level",
    "max_stock",
    "unit_price",
    "sell_price",
    "cost_price",
    "total_amount",
    "expiry_date",
    "batch_number",
    "payment_method",
    "customer_id",
]

NUMERIC_COLUMNS = {
    "quantity",
    "current_stock",
    "reorder_level",
    "max_stock",
    "unit_price",
    "sell_price",
    "cost_price",
    "total_amount",
}

DATE_COLUMNS = {"transaction_at", "expiry_date"}


def parse_date(value) -> datetime | None:
    if pd.isna(value):
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()

    if isinstance(value, (int, float)):
        # Most POS Excel exports store dates as Excel serial numbers.
        # 25569 = 1970-01-01 in Excel's date system; realistic retail data is usually > 35,000.
        try:
            if value > 20000:
                return pd.to_datetime(value, unit="D", origin="1899-12-30").to_pydatetime()
        except Exception:
            pass

    value_str = str(value).strip()
    if not value_str:
        return None

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value_str, fmt)
        except ValueError:
            continue

    try:
        parsed = pd.to_datetime(value_str, errors="coerce", dayfirst=True)
        if pd.isna(parsed):
            return None
        return parsed.to_pydatetime()
    except Exception:
        return None


def parse_number(value) -> float:
    if pd.isna(value):
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return 0.0

    # Accept merchant exports like "SAR 1,250.50", "1,250 ر.س", "﷼ 99".
    text = text.replace(",", "")
    text = re.sub(r"(SAR|S\.A\.R|ر\.س|ريال|﷼)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[^0-9.\-]", "", text)

    if text in {"", "-", ".", "-."}:
        return 0.0

    try:
        return float(text)
    except ValueError:
        return 0.0


def _coalesce_duplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """When two source columns are mapped to one target, keep the first non-empty value."""
    if not df.columns.duplicated().any():
        return df

    out = {}
    seen = []
    for col in df.columns:
        if col in seen:
            continue
        seen.append(col)
        same = df.loc[:, df.columns == col]
        if same.shape[1] == 1:
            out[col] = same.iloc[:, 0]
        else:
            out[col] = same.replace("", pd.NA).bfill(axis=1).iloc[:, 0]
    return pd.DataFrame(out)


def normalize_dataframe(df: pd.DataFrame, column_mapping: Dict[str, str]) -> pd.DataFrame:
    normalized = df.copy()

    rename_map = {}
    for col, target in (column_mapping or {}).items():
        if target and target in FIELD_TARGETS and col in normalized.columns:
            rename_map[col] = target

    normalized = normalized.rename(columns=rename_map)
    normalized = _coalesce_duplicate_columns(normalized)

    for col in list(normalized.columns):
        if col in DATE_COLUMNS:
            normalized[col] = normalized[col].apply(parse_date)
            if col == "transaction_at":
                normalized = normalized[normalized[col].notna()]
        elif col in NUMERIC_COLUMNS:
            normalized[col] = normalized[col].apply(parse_number)
        elif col in FIELD_TARGETS:
            normalized[col] = normalized[col].astype(str).str.strip().replace({"nan": "", "None": ""})

    if "item_name" not in normalized.columns:
        raise ValueError("Missing required column: item_name")

    normalized["item_name"] = normalized["item_name"].astype(str).str.strip()
    normalized = normalized[normalized["item_name"] != ""]

    has_sales_history = "transaction_at" in normalized.columns
    has_inventory_snapshot = "current_stock" in normalized.columns
    if not has_sales_history and not has_inventory_snapshot:
        raise ValueError("Upload must include either sales date (transaction_at) or current stock (current_stock).")

    if "quantity" not in normalized.columns and has_sales_history:
        normalized["quantity"] = 1.0

    if "unit_price" not in normalized.columns and "sell_price" in normalized.columns:
        normalized["unit_price"] = normalized["sell_price"]

    if "sell_price" not in normalized.columns and "unit_price" in normalized.columns:
        normalized["sell_price"] = normalized["unit_price"]

    if "unit_price" not in normalized.columns and "total_amount" in normalized.columns and "quantity" in normalized.columns:
        qty = normalized["quantity"].replace(0, 1)
        normalized["unit_price"] = normalized["total_amount"] / qty
        normalized["sell_price"] = normalized["unit_price"]

    if "total_amount" not in normalized.columns and "unit_price" in normalized.columns and "quantity" in normalized.columns:
        normalized["total_amount"] = normalized["unit_price"] * normalized["quantity"]

    return normalized


class DataNormalizer:
    """Backward-compatible wrapper for older ETL tests/tools.

    Production code uses `normalize_dataframe`, which expects current NazmOS
    fields. This class preserves the old product_name/category naming expected
    by legacy tests without weakening production normalization.
    """

    def normalize(self, df: pd.DataFrame, column_mapping: Dict[str, str]) -> pd.DataFrame:
        normalized = df.copy().rename(columns={k: v for k, v in (column_mapping or {}).items() if k in df.columns and v})
        if "product_name" in normalized.columns:
            normalized = normalized[normalized["product_name"].notna()].copy()
            normalized["product_name"] = normalized["product_name"].astype(str).str.strip()
            normalized = normalized[normalized["product_name"] != ""]
        for col in ["quantity", "unit_price", "price", "cost_price", "total_amount", "current_stock"]:
            if col in normalized.columns:
                normalized[col] = pd.to_numeric(normalized[col], errors="coerce").fillna(0)
        return normalized.reset_index(drop=True)

    def validate(self, df: pd.DataFrame, numeric_columns: List[str]) -> List[dict]:
        errors = []
        for col in numeric_columns:
            if col not in df.columns:
                errors.append({"column": col, "error": "missing_column"})
                continue
            converted = pd.to_numeric(df[col], errors="coerce")
            bad = converted.isna() & df[col].notna()
            for idx in df.index[bad].tolist():
                errors.append({"row": int(idx), "column": col, "value": df.loc[idx, col], "error": "invalid_number"})
        return errors
