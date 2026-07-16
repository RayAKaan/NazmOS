from datetime import datetime
from typing import Dict, List, Tuple
import re

import pandas as pd


def is_date_like(value) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, (datetime, pd.Timestamp)):
        return True
    if isinstance(value, (int, float)) and value > 20000:
        return True
    if isinstance(value, str):
        date_patterns = [
            r"\d{4}-\d{2}-\d{2}",
            r"\d{2}/\d{2}/\d{4}",
            r"\d{2}-\d{2}-\d{4}",
            r"\d{2}-[A-Za-z]{3}-\d{4}",
            r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}",
            r"\d{4}/\d{2}/\d{2}",
        ]
        return any(re.search(pattern, value) for pattern in date_patterns)
    return False


def is_positive_numeric(value) -> bool:
    if pd.isna(value):
        return False
    try:
        cleaned = re.sub(r"(SAR|S\.A\.R|ر\.س|ريال|﷼|,)", "", str(value), flags=re.IGNORECASE)
        cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
        return float(cleaned) >= 0
    except (ValueError, TypeError):
        return False


def is_text(value) -> bool:
    return isinstance(value, str) and len(str(value).strip()) > 1


FIELD_PATTERNS = {
    "expiry_date": {
        "name_hints": [
            "expiry", "expiration", "expires", "best_before", "bestbefore", "use_by", "exp_date",
            "تاريخ_الصلاحية", "صلاحية", "انتهاء", "تاريخ الانتهاء",
        ],
        "sample_validator": is_date_like,
    },
    "transaction_at": {
        "name_hints": [
            "date", "time", "datetime", "transaction_date", "sale_date", "sales_date",
            "billing_date", "invoice_date", "bill_date", "dt", "day", "sold_at",
            "التاريخ", "تاريخ", "وقت", "تاريخ البيع",
        ],
        "sample_validator": is_date_like,
    },
    "item_name": {
        "name_hints": [
            "item", "product", "name", "description", "item_name", "product_name", "particulars",
            "goods", "article", "items", "material", "اسم", "اسم الصنف", "اسم المنتج", "منتج", "صنف", "المادة",
        ],
        "sample_validator": is_text,
    },
    "barcode": {
        "name_hints": ["barcode", "bar_code", "ean", "upc", "gtin", "باركود"],
        "sample_validator": lambda x: len(str(x).strip()) >= 6,
    },
    "item_sku": {
        "name_hints": [
            "sku", "item_sku", "product_sku", "code", "item_code", "product_code", "article_code",
            "part_no", "item_no", "كود", "رمز", "رمز الصنف",
        ],
        "sample_validator": lambda x: len(str(x).strip()) > 1,
    },
    "brand": {
        "name_hints": ["brand", "make", "manufacturer", "ماركة", "علامة", "الشركة"],
        "sample_validator": is_text,
    },
    "pack_size": {
        "name_hints": ["pack", "pack_size", "size", "uom", "unit_size", "case_pack", "عبوة", "حجم", "وحدة"],
        "sample_validator": is_text,
    },
    "storage_type": {
        "name_hints": ["storage", "storage_type", "temperature", "ambient", "chilled", "frozen", "تخزين", "حرارة"],
        "sample_validator": is_text,
    },
    "current_stock": {
        "name_hints": [
            "current_stock", "stock", "stock_qty", "current_qty", "available", "available_qty",
            "on_hand", "onhand", "balance", "inventory", "closing_stock", "رصيد", "مخزون", "الكمية المتوفرة",
        ],
        "sample_validator": is_positive_numeric,
    },
    "quantity": {
        "name_hints": ["qty", "quantity", "sold_qty", "sales_qty", "units", "pieces", "pcs", "nos", "qnty", "كمية", "الكمية"],
        "sample_validator": is_positive_numeric,
    },
    "reorder_level": {
        "name_hints": ["reorder", "reorder_level", "reorder_point", "min_stock", "minimum_stock", "min", "حد الطلب", "الحد الادنى"],
        "sample_validator": is_positive_numeric,
    },
    "max_stock": {
        "name_hints": ["max_stock", "maximum_stock", "max", "par_level", "capacity", "الحد الاعلى"],
        "sample_validator": is_positive_numeric,
    },
    "unit_price": {
        "name_hints": [
            "price", "rate", "unit_price", "mrp", "selling_price", "sale_price", "retail_price",
            "sp", "unit_rate", "per_unit", "selling", "سعر", "سعر البيع",
        ],
        "sample_validator": is_positive_numeric,
    },
    "cost_price": {
        "name_hints": ["cost", "cost_price", "purchase_price", "cp", "buy_price", "landed_cost", "purchase_rate", "تكلفة", "سعر الشراء"],
        "sample_validator": is_positive_numeric,
    },
    "total_amount": {
        "name_hints": ["total", "amount", "net_amount", "gross_amount", "total_amount", "bill_amount", "net", "value", "revenue", "sale_value", "amt", "اجمالي", "المبلغ"],
        "sample_validator": is_positive_numeric,
    },
    "category_name": {
        "name_hints": ["category", "cat", "department", "dept", "group", "section", "type", "class", "division", "grp", "تصنيف", "قسم", "فئة"],
        "sample_validator": is_text,
    },
    "batch_number": {
        "name_hints": ["batch", "batch_no", "batch_number", "lot", "lot_no", "lot_number", "تشغيلة", "دفعة"],
        "sample_validator": lambda x: len(str(x).strip()) > 0,
    },
}


class SchemaDetector:
    # ── POS export signatures ──────────────────────────────────────
    FOODICS_MARKERS = {"date", "item", "qty", "amount", "cost"}
    SALLA_MARKERS = {"order", "product", "quantity", "price", "total"}

    @classmethod
    def detect_pos_signature(cls, columns: list) -> str | None:
        """Detect Foodics/Salla export by column name signature."""
        cleaned = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in columns]
        flat = set()
        for c in cleaned:
            for word in c.split("_"):
                flat.add(word)

        foodics_score = sum(1 for m in cls.FOODICS_MARKERS if m in flat)
        if foodics_score >= 4:
            return "foodics_export"

        salla_score = sum(1 for m in cls.SALLA_MARKERS if m in flat)
        if salla_score >= 4:
            return "salla_export"

        return None

    def detect(self, df: pd.DataFrame) -> Dict:
        result = {}
        confidence = {}
        used_targets = set()

        # Check for known POS export signatures first
        pos_signature = self.detect_pos_signature(list(df.columns))
        if pos_signature:
            # For known POS exports, boost confidence for matching columns
            pass

        for col in df.columns:
            best_field, best_score = self._score_column(col, df[col], used_targets)
            if best_field and best_score >= 0.4:
                result[col] = best_field
                confidence[col] = best_score
                used_targets.add(best_field)

        # If the file has no sale date, merchant "quantity" columns are usually stock-on-hand.
        has_sales_date = "transaction_at" in result.values()
        if not has_sales_date:
            for col, target in list(result.items()):
                if target == "quantity":
                    result[col] = "current_stock"

        unmapped = [c for c in df.columns if c not in result]

        return {
            "detected_columns": result,
            "confidence_scores": confidence,
            "unmapped_columns": unmapped,
            "sample_rows": df.head(5).fillna("").to_dict(orient="records"),
            "total_rows": len(df),
            "suggested_file_kind": pos_signature or ("sales_history" if has_sales_date else "inventory_snapshot"),
        }


    def detect_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        """Backward-compatible detector API used by older tests/tools."""
        legacy_result: Dict[str, str] = {}
        used = set()
        for col in df.columns:
            c = self._clean(col)
            target = None
            if any(x in c for x in ["category", "cat", "department", "dept", "item_type", "product_type", "type"]):
                target = "category"
            elif any(x in c for x in ["product_name", "item_name", "description", "product", "item", "name"]):
                target = "product_name"
            elif any(x in c for x in ["qty", "quantity", "sold_qty", "sales_qty", "units"]):
                target = "quantity"
            elif any(x in c for x in ["price", "rate", "selling_price", "sale_price", "unit_price"]):
                target = "unit_price"
            elif any(x in c for x in ["sku", "code"]):
                target = "sku"
            elif any(x in c for x in ["stock", "on_hand", "available", "inventory"]):
                target = "current_stock"
            if target and target not in used:
                legacy_result[col] = target
                used.add(target)
        if legacy_result:
            return legacy_result
        detected = self.detect(df)["detected_columns"]
        legacy = {"item_name": "product_name", "item_sku": "sku", "category_name": "category", "sell_price": "unit_price"}
        return {source: legacy.get(target, target) for source, target in detected.items()}

    def get_confidence_scores(self, df: pd.DataFrame) -> Dict[str, float]:
        """Backward-compatible confidence API: source column -> score."""
        return {source: 1.0 for source in self.detect_columns(df).keys()}

    def _score_column(self, col_name: str, series: pd.Series, used: set) -> Tuple[str | None, float]:
        best_field = None
        best_score = 0.0
        col_lower = self._clean(col_name)
        samples = series.dropna().head(20).tolist()

        for field_name, field_info in FIELD_PATTERNS.items():
            if field_name in used:
                continue

            # A generic "date" column in sales exports should not become expiry_date.
            if field_name == "expiry_date" and not any(token in col_lower for token in ["exp", "expiry", "expiration", "best_before", "bestbefore", "صلاح", "انتهاء"]):
                continue

            # Generic qty in sales files should map to quantity, not current stock. Stock exports usually say stock/balance/on hand.
            if field_name == "current_stock" and col_lower in {"qty", "quantity", "qnty", "units", "كمية", "الكمية"}:
                continue

            # Purchase/cost columns often include Arabic "سعر" too; do not let unit_price steal them.
            if field_name == "unit_price" and any(token in col_lower for token in ["cost", "purchase", "buy", "landed", "شراء", "تكلفة"]):
                continue

            name_score = self._name_similarity(col_lower, field_info["name_hints"])
            sample_score = self._sample_match(samples, field_info["sample_validator"])
            combined = (name_score * 0.7) + (sample_score * 0.3)

            if combined > best_score:
                best_score = combined
                best_field = field_name

        return best_field, best_score

    def _clean(self, col_name: str) -> str:
        return str(col_name).lower().strip().replace(" ", "_").replace("-", "_")

    def _name_similarity(self, col_name: str, hints: List[str]) -> float:
        col_lower = col_name.lower()
        for hint in hints:
            hint_lower = self._clean(hint)
            if hint_lower in col_lower or col_lower in hint_lower:
                return 1.0
            if self._levenshtein_similarity(col_lower, hint_lower) > 0.82:
                return 0.82
        return 0.0

    def _sample_match(self, samples: List, validator) -> float:
        if not samples:
            return 0.0
        matches = sum(1 for s in samples if validator(s))
        return matches / len(samples)

    def _levenshtein_similarity(self, s1: str, s2: str) -> float:
        if len(s1) < len(s2):
            return self._levenshtein_similarity(s2, s1)
        if len(s2) == 0:
            return 0.0
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        distance = previous_row[-1]
        max_len = max(len(s1), len(s2))
        return 1 - (distance / max_len) if max_len > 0 else 1.0
