"""Deterministic semantic mapping from flexible merchant columns to canonical roles.

The mapper combines several independent evidence sources and never relies on a
single weak clue (Phase 32):

    A. HEADER SEMANTICS     -- reusable token/pattern rules (NOT an infinite alias list)
    B. VALUE SHAPE          -- numeric/integer/date/text/currency/identifier profiles
    C. CROSS-COLUMN RELATIONSHIPS -- qty*price~revenue, cost<price, opening+in-sales~closing
    D. TEMPORAL / LANGUAGE   -- date ratio, Arabic/mixed headers

Role competition: each column gets a confidence vector across candidate roles;
the winner is only accepted when the margin over the runner-up is strong enough.
Where context cannot resolve a column, it is left ambiguous so the caller can ask
the user rather than guess.

Deterministic, no AI, pure Decimal/std-lib/pandas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pandas as pd

from app.services.column_profiling import ColumnProfile, profile_frame
from app.services.file_ingestion import coerce_numeric, normalize_header
from app.services.ingestion_schema import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    MIN_CONFIDENCE_MARGIN,
    ColumnMapping,
    EVIDENCE_CURRENCY_SIGNAL,
    EVIDENCE_DATE_SIGNAL,
    EVIDENCE_HEADER_MATCH,
    EVIDENCE_IDENTIFIER_SIGNAL,
    EVIDENCE_LANGUAGE_SIGNAL,
    EVIDENCE_NUMERIC_SHAPE,
    EVIDENCE_RELATIONSHIP_SIGNAL,
    EVIDENCE_VALUE_DISTRIBUTION,
    IngestionResult,
    INGESTION_STATUS_READY,
    INGESTION_STATUS_NEEDS_REVIEW,
    INGESTION_STATUS_INSUFFICIENT_DATA,
    REQUIRED_INVENTORY_FIELDS,
    REQUIRED_SALES_FIELDS,
)

# ---------------------------------------------------------------------------
# Header semantics: reusable token rules. Lowercase, punctuation-folding tokens
# (via file_ingestion.normalize_header). Weights express how strongly a token
# implies a role. This is a rule vocabulary, not a giant enumerated alias list;
# "current-stock-qty", "Current Stock Qty" and "CURRENT STOCK QUANTITY" all fold
# to the same tokens and therefore the same signal.
# ---------------------------------------------------------------------------

_TOKEN_AR = {
    "name": "اسم", "product": "منتج", "item": "صنف", "desc": "وصف", "description": "وصف",
    "qty": "كمية", "quantity": "كمية", "units": "وحدات", "pcs": "قطعة", "pieces": "قطعة",
    "sold": "مباع", "count": "عدد", "price": "سعر", "retail": "تجزئة", "rsp": "سعر",
    "sell": "بيع", "sale": "بيع", "selling": "بيع", "cost": "تكلفة", "cogs": "تكلفة",
    "buy": "شراء", "buying": "شراء", "purchase": "شراء", "landed": "تكلفة",
    "stock": "مخزون", "inventory": "مخزون", "balance": "رصيد", "available": "متاح",
    "closing": "مخزون", "opening": "مخزون", "date": "تاريخ", "timestamp": "تاريخ",
    "created": "تاريخ", "posted": "تاريخ", "invoice": "فاتورة", "transaction": "عملية",
    "revenue": "ايراد", "total": "اجمالي", "gross": "اجمالي", "net": "صافي",
    "amount": "مبلغ", "sales": "مبيعات", "sku": "رمز", "barcode": "باركود",
    "category": "فئة", "brand": "ماركة",
}

SEMANTIC_SIGNATURES: dict[str, dict[str, float]] = {
    "product_name": {
        "name": 3.0, "product": 2.5, "item": 2.5, "description": 2.5, "desc": 2.0,
        "particulars": 2.0, "label": 1.5, "details": 1.5, "title": 1.5,
        "اسم": 3.0, "منتج": 2.5, "صنف": 2.5, "وصف": 2.5, "سلعة": 2.5, "بند": 2.0,
    },
    "sku": {
        "sku": 3.5, "stockcode": 3.0, "itemcode": 2.5, "productcode": 2.5,
        "code": 2.0, "ref": 1.5, "article": 2.0, "itemno": 2.5, "reference": 1.5,
        "barcode": 2.0, "رمز": 3.0, "كود": 2.5, "باركود": 2.0,
    },
    "barcode": {
        "barcode": 3.5, "upc": 3.0, "ean": 3.0, "gtin": 3.0, "باركود": 3.0, "رمز": 1.0,
    },
    "quantity": {
        "qty": 3.5, "quantity": 3.5, "units": 2.5, "pieces": 2.5, "pcs": 2.5,
        "sold": 1.5, "count": 2.0, "unitssold": 3.0, "soldunits": 3.0, "number": 1.0,
        "كمية": 3.5, "كميه": 3.5, "وحدات": 2.5, "قطع": 2.0, "عدد": 2.0, "مباع": 1.0,
    },
    "price": {
        "price": 3.0, "retail": 3.5, "rsp": 3.5, "selling": 2.5, "sell": 2.5,
        "sale": 2.0, "unitprice": 2.5, "priceperunit": 2.5, "sellingprice": 3.0,
        "salevalue": 1.0, "سعر": 3.0, "بيع": 2.5, "تجزئة": 3.0, "سعرالبيع": 3.0,
    },
    "cost": {
        "cost": 3.5, "cogs": 3.5, "unitcost": 3.0, "purchasecost": 3.0,
        "buying": 2.5, "buyingrate": 2.5, "purchaseprice": 2.5, "landed": 2.5,
        "buyrate": 2.5, "buypackage": 1.0, "تكلفة": 3.5, "تكلفه": 3.5,
        "كلفة": 3.0, "شراء": 2.0, "سعرالشراء": 3.0,
    },
    "stock": {
        "stock": 3.0, "inventory": 3.0, "balance": 2.5, "onhand": 3.0,
        "onhandqty": 3.0, "stockqty": 3.0, "currentstock": 3.0, "qtyonhand": 3.0,
        "available": 2.5, "availableqty": 2.5, "closing": 2.5, "opening": 2.5,
        "stocklevel": 2.5, "quantity": 1.0, "inhand": 2.5,
        "مخزون": 3.0, "رصيد": 2.5, "متاح": 2.5, "توفر": 2.0, "مخزونحالي": 3.0,
    },
    # Inventory-policy thresholds. Recognized so they are mapped to a distinct
    # role and never mis-fill the core sales ``quantity`` or primary ``stock``.
    "reorder_point": {
        "reorder": 3.5, "reorderpoint": 3.0, "reorderqty": 3.0, "reorderlevel": 3.0,
        "minstock": 3.0, "minimum": 2.5, "minqty": 2.5, "safetystock": 3.0,
        "نقطةاعادة": 3.0, "اعادةالطلب": 2.5, "حدادنى": 2.5,
    },
    "target_stock": {
        "target": 3.5, "targetstock": 3.0, "targetqty": 3.0, "maxtock": 3.0,
        "maximum": 2.5, "maxstock": 3.0, "maxqty": 2.5, "targetlevel": 3.0,
        "مخزونمستهدف": 3.0, "حداقصى": 2.5,
    },
    "date": {
        "date": 3.5, "timestamp": 3.5, "datetime": 3.0, "createdat": 3.0,
        "transactionat": 3.0, "transactiondate": 3.0, "saledate": 3.0,
        "orderdate": 3.0, "invoicedate": 3.0, "postingdate": 3.0, "entrydate": 3.0,
        "created": 2.0, "posted": 2.0, "invoice": 2.0, "day": 1.5, "entry": 1.5,
        "transaction": 1.5, "تاريخ": 3.5, "يوم": 1.5, "عملية": 1.0, "فاتورة": 2.0,
    },
    "revenue": {
        "revenue": 3.5, "salesamount": 3.0, "salesvalue": 3.0, "total": 2.5,
        "gross": 2.5, "grossamount": 2.5, "net": 2.0, "amount": 1.0, "sales": 1.5,
        "turnover": 2.5, "ايراد": 3.5, "اجمالي": 2.5, "مبيعات": 2.0, "مبلغ": 1.0,
    },
    "discount": {
        "discount": 3.5, "discountpct": 3.0, "discountvalue": 2.5, "خصم": 3.0,
    },
    "category": {
        "category": 3.5, "department": 2.5, "group": 2.0, "فئة": 3.0, "قسم": 2.0,
    },
    "brand": {
        "brand": 3.5, "make": 2.0, "manufacturer": 2.5, "ماركة": 3.0,
    },
    "purchase_quantity": {
        "purchaseqty": 3.0, "purchasedqty": 3.0, "receivedqty": 2.5, "كميةالشراء": 3.0,
    },
    "inbound_stock": {
        "inbound": 3.0, "inboundqty": 3.0, "incoming": 2.5, "received": 2.0, "وارد": 2.5,
    },
    "opening_stock": {
        "opening": 3.0, "openingstock": 3.0, "openingbalance": 3.0, "مخزونافتتاحي": 3.0,
    },
    "closing_stock": {
        "closing": 2.5, "closingstock": 3.0, "closingbalance": 3.0, "مخزوناغلاق": 3.0,
    },
    "total_amount": {
        "totalamount": 3.5, "grandtotal": 3.0, "netamount": 2.5, "total": 2.0,
        "اجمالي": 2.0, "مبلغ": 1.0,
    },
    "unit_price": {
        "unitprice": 3.5, "priceperunit": 3.0, "unitcost": 0.5, "sellprice": 3.0,
    },
    "transaction_id": {"transactionid": 3.0, "invoiceid": 3.0, "invoiceno": 2.5, "receipt": 2.0, "refid": 2.0},
}

# Roles allowed to fill the guest ledger's core slots.
_LEDGER_ROLES = ("product_name", "quantity", "price", "cost", "stock", "date")


@dataclass
class _Candidate:
    role: str
    header_score: float = 0.0
    value_score: float = 0.0
    relationship_bonus: float = 0.0

    @property
    def confidence(self) -> float:
        return min(1.0, self.header_score + self.value_score + self.relationship_bonus)


def _tokens(header: Any) -> list[str]:
    toks = [t for t in normalize_header(header).split() if t]
    out: list[str] = []
    for t in toks:
        # Strip the Arabic definite article "ال" so "التكلفة"/"المخزون"/"البيع"
        # match the vocabulary keys ("تكلفة"/"مخزون"/"بيع").
        if t.startswith("ال") and len(t) > 3:
            t = t[2:]
        if t:
            out.append(t)
    return out


def _detect_english(header: str) -> bool:
    return not any("\u0600" <= ch <= "\u06ff" for ch in header)


def header_match_score(header: Any, role: str) -> tuple[float, list[str]]:
    """Return (weighted-score, matched-token-evidence) for a header vs a role.

    A column is normally *one* canonical role, but the internal signature table
    uses downstream role names (``sku``, ``unit_price``, ``total_amount``). We
    keep them separate for vocabulary richness and fold ``sell/unit price`` and
    ``total/amount`` back into the ledger-facing ``price``/``revenue`` roles.
    """
    tok = _tokens(header)
    if not tok:
        return 0.0, []
    sig = SEMANTIC_SIGNATURES.get(role, {})
    score = 0.0
    matched: list[str] = []
    for t in tok:
        w = sig.get(t)
        if w:
            score += w
            matched.append(t)
    # two-token phrase bonus, e.g. "sold units", "unit price", "on hand"
    pairs = [(tok[i], tok[i + 1]) for i in range(len(tok) - 1)]
    phrase = {
        ("on", "hand"): ("stock", 1.0), ("unit", "price"): ("price", 1.0),
        ("sell", "price"): ("price", 1.0), ("sale", "price"): ("price", 1.0),
        ("qty", "sold"): ("quantity", 1.0), ("units", "sold"): ("quantity", 1.0),
        ("pcs", "sold"): ("quantity", 1.0), ("stock", "qty"): ("stock", 1.0),
        ("current", "stock"): ("stock", 1.0), ("cost", "price"): ("cost", 1.0),
        ("purchase", "cost"): ("cost", 1.0), ("buy", "rate"): ("cost", 1.0),
        ("sell", "value"): ("revenue", 1.0), ("net", "sales"): ("revenue", 1.0),
        ("gross", "amount"): ("revenue", 1.0), ("sold", "qty"): ("quantity", 1.0),
        ("item", "code"): ("sku", 1.0), ("product", "code"): ("sku", 1.0),
        ("item", "no"): ("sku", 1.0), ("item", "name"): ("product_name", 1.0),
    }
    for (a, b), (p_role, p_w) in phrase.items():
        if (a, b) in pairs and p_role == role:
            score += p_w
            matched.append(f"{a}_{b}")
    return score, matched


def value_evidence(profile: ColumnProfile, role: str) -> tuple[float, list[str]]:
    """Return (0..1 value-shape evidence, evidence-labels) for a role.

    Value shape is a *secondary* signal that must never, on its own, turn an
    ambiguous header into a confident financial role. It tunes the final
    confidence of an already-header-signaled candidate and helps break ties only
    when the header is weak. We therefore keep the numeric-shape bonuses modest
    so an integer column does not auto-win ``quantity`` purely for being integer.
    """
    p = profile
    score = 0.0
    ev: list[str] = []
    numeric = p.numeric_ratio >= 0.7
    if role == "product_name":
        # High text ratio (no parser hit) or many identifiers -> product identity.
        if p.numeric_ratio < 0.5 and (p.text_ratio >= 0.5 or p.identifier_ratio >= 0.3):
            score += 0.4
            ev.append(EVIDENCE_VALUE_DISTRIBUTION)
        if p.unique_ratio >= 0.8:
            score += 0.15
    elif role in ("sku", "barcode"):
        if p.identifier_ratio >= 0.6:
            score += 0.45
            ev.append(EVIDENCE_IDENTIFIER_SIGNAL)
        if p.non_null_ratio >= 0.7:
            score += 0.1
    elif role in ("quantity", "purchase_quantity"):
        # Plain integer-ness is a weak, generic clue. Only add a modest bump.
        if numeric and p.integer_ratio >= 0.7 and p.currency_ratio < 0.1:
            score += 0.12
            ev.append(EVIDENCE_NUMERIC_SHAPE)
        if numeric and p.negative_ratio < 0.1:
            score += 0.04
    elif role in ("price", "unit_price", "cost", "revenue", "total_amount"):
        if numeric:
            score += 0.12
            ev.append(EVIDENCE_NUMERIC_SHAPE)
        if p.currency_ratio >= 0.15 or (p.two_dp_ratio >= 0.5 and p.decimal_ratio >= 0.3):
            score += 0.2
            ev.append(EVIDENCE_CURRENCY_SIGNAL)
        if role in ("price", "unit_price") and p.median_value is not None and Decimal("0") < p.median_value < Decimal("5000"):
            score += 0.08
        if role == "revenue" and p.max_value is not None and p.median_value is not None and p.max_value >= p.median_value * 3:
            score += 0.08
    elif role in ("stock", "opening_stock", "closing_stock", "inbound_stock"):
        if numeric and p.integer_ratio >= 0.6:
            score += 0.12
            ev.append(EVIDENCE_NUMERIC_SHAPE)
        if p.negative_ratio < 0.2:
            score += 0.06
    elif role == "date":
        if p.date_ratio >= 0.7:
            score += 0.5
            ev.append(EVIDENCE_DATE_SIGNAL)
        elif p.date_ratio > 0.0:
            score += 0.3 * p.date_ratio
            ev.append(EVIDENCE_DATE_SIGNAL)
    return min(1.0, score), ev


# ---------------------------------------------------------------------------
# Cross-column relationship evidence (Phase 8). Evidence only: we never invent
# data, we only raise/lower the confidence of an already-candidate role.
# ---------------------------------------------------------------------------

def _numeric_series(df: pd.DataFrame, col: str, n: int) -> list[Decimal]:
    out: list[Decimal] = []
    for v in df[col].head(n):
        out.append(coerce_numeric(v))
    return out


def _close(a: Decimal, b: Decimal) -> bool:
    if b == 0:
        return a == 0
    return abs(a - b) <= max(abs(b) * Decimal("0.05"), Decimal("0.5"))


def relationship_adjust(
    df: pd.DataFrame,
    profiles: dict[str, ColumnProfile],
    *,
    sample: int = 200,
) -> dict[str, dict[str, float]]:
    """Return {column: {role: bonus}} computed from cross-column relationships."""
    out: dict[str, dict[str, float]] = {
        col: {r: 0.0 for r in ("quantity", "price", "cost", "revenue", "stock", "opening_stock", "purchase_quantity", "closing_stock")}
        for col in df.columns
    }
    col_list = list(df.columns)
    numeric_cols = [c for c in col_list if profiles.get(str(c)) and profiles[str(c)].numeric_ratio >= 0.7]
    if len(numeric_cols) < 2:
        return out

    n = min(sample, len(df))
    # 1) qty * price ~= revenue/total: find three numeric columns where
    #    product of two approximates the third.
    for i in range(len(col_list)):
        for j in range(i + 1, len(col_list)):
            a, b = col_list[i], col_list[j]
            pa = profiles.get(str(a), ColumnProfile(""))
            pb = profiles.get(str(b), ColumnProfile(""))
            if pa.numeric_ratio < 0.5 or pb.numeric_ratio < 0.5:
                continue
            a_rows = _numeric_series(df, a, n)
            b_rows = _numeric_series(df, b, n)
            for k_idx in range(len(col_list)):
                if k_idx == i or k_idx == j:
                    continue
                c = col_list[k_idx]
                pc = profiles.get(str(c), ColumnProfile(""))
                if pc.numeric_ratio < 0.7:
                    continue
                c_rows = _numeric_series(df, c, n)
                hits = 0
                checked = 0
                for k in range(min(len(a_rows), len(b_rows), len(c_rows))):
                    if a_rows[k] == 0 or b_rows[k] == 0:
                        continue
                    checked += 1
                    product = a_rows[k] * b_rows[k]
                    if _close(product, c_rows[k]):
                        hits += 1
                if checked and hits / checked >= 0.8:
                    # a * b ~= c. The pair (a,b) is likely (qty, price) and c is revenue/total.
                    out[a].setdefault("quantity", 0.0)
                    out[b].setdefault("price", 0.0)
                    out[a]["quantity"] += 0.15
                    out[b]["price"] += 0.15
                    out[c].setdefault("revenue", 0.0)
                    out[c]["revenue"] += 0.15
                    break  # this triple is resolved; move on

    # 2) cost < price across rows. Conservative: only fire when at least one
    #    member of the pair carries an explicit cost or price header token, so we
    #    never turn stock/threshold columns into cost or price purely because one
    #    integer column happens to be smaller than another.
    _COST_TOKENS = ("cost", "cogs", "تكلفه", "تكلفة", "شراء", "buy", "purchase", "landed")
    _PRICE_TOKENS = ("price", "retail", "rsp", "sell", "sale", "بيع", "سعر", "تجزئة")
    for i in range(len(col_list)):
        for j in range(len(col_list)):
            if i == j:
                continue
            a, b = col_list[i], col_list[j]
            pa = profiles.get(str(a), ColumnProfile("")); pb = profiles.get(str(b), ColumnProfile(""))
            if pa.numeric_ratio < 0.7 or pb.numeric_ratio < 0.7:
                continue
            ta = _tokens(str(a)); tb = _tokens(str(b))
            a_costish = any(t in _COST_TOKENS for t in ta)
            a_priceish = any(t in _PRICE_TOKENS for t in ta)
            b_costish = any(t in _COST_TOKENS for t in tb)
            b_priceish = any(t in _PRICE_TOKENS for t in tb)
            # Require the smaller column to look like a cost and the larger to
            # look like a price (or at least one explicit side + a clean ordering).
            cost_side = a if a_costish else (b if b_costish else None)
            price_side = b if a_costish and b_priceish else (a if b_costish and a_priceish else None)
            if cost_side is None:
                continue
            if pa.median_value is None or pb.median_value is None:
                continue
            smaller, larger = (a, b) if pa.median_value < pb.median_value else (b, a)
            # Only treat as cost<price when the cost-named column is the smaller one.
            if cost_side != smaller:
                continue
            if price_side is not None and price_side != larger:
                continue
            if Decimal("0") >= pa.median_value or Decimal("0") >= pb.median_value:
                continue
            if pa.median_value >= pb.median_value:
                continue
            a_rows = _numeric_series(df, a, n); b_rows = _numeric_series(df, b, n)
            cnt = sum(1 for ax, bx in zip(a_rows, b_rows) if bx > 0 and ax < bx)
            if cnt / max(1, min(n, len(a_rows))) >= 0.8:
                out[smaller]["cost"] = out[smaller].get("cost", 0.0) + 0.15
                out[larger]["price"] = out[larger].get("price", 0.0) + 0.15
    return out


# ---------------------------------------------------------------------------
# Domain/classification detection (Phase 9).
# ---------------------------------------------------------------------------

def classify_file(mapped: dict[str, str]) -> list[str]:
    domains: list[str] = []
    stock_like = any(k in mapped for k in ("stock", "opening_stock", "closing_stock", "inbound_stock"))
    sales_like = any(k in mapped for k in ("quantity", "revenue", "unit_price", "price", "date"))
    if sales_like and stock_like:
        domains.append("combined_inventory_sales")
    elif sales_like:
        domains.append("sales_history")
    elif stock_like:
        domains.append("inventory_snapshot")
    else:
        domains.append("unknown")
    if "purchase_quantity" in mapped:
        domains.append("purchases")
    return domains


# ---------------------------------------------------------------------------
# Main entry point.
# ---------------------------------------------------------------------------

@dataclass
class _RoleScores:
    header: dict[str, float]
    value: dict[str, float]
    relationships: dict[str, float]

    def total(self, role: str) -> float:
        return min(1.0, self.header.get(role, 0.0) + self.value.get(role, 0.0) + self.relationships.get(role, 0.0))


def _score_column_candidates(
    col: str,
    profile: ColumnProfile,
    relationships: dict[str, dict[str, float]],
) -> dict[str, _RoleScores]:
    candidates: dict[str, _RoleScores] = {}
    for role in SEMANTIC_SIGNATURES:
        hs, _hev = header_match_score(col, role)
        vs, _vev = value_evidence(profile, role)
        rs = relationships.get(str(col), {}).get(role, 0.0)
        candidates[role] = _RoleScores(header={role: hs / 4.0}, value={role: vs}, relationships={role: rs})
    return candidates


# Stock-family tokens that mark a column as an inventory *policy* threshold
# (reorder point, target/max stock, safety stock) rather than a sales quantity
# or the primary current-stock count.
_POLICY_TOKENS_HEADERS = ("reorder", "target", "minimum", "maximum", "min", "max", "safety")
# Tokens that bind a column to the inventory family (not sales quantity) when
# combined with a qty token. e.g. "Inbound Qty", "Opening Qty", "Closing Qty".
_INVENTORY_BOUND = ("stock", "inventory", "inbound", "incoming", "received", "opening", "closing", "onhand", "balance", "available", "warehouse", "مخزون", "رصيد", "متاح", "وارد")


def _is_inventory_policy_header(tokens: list[str]) -> bool:
    return any(t in _POLICY_TOKENS_HEADERS for t in tokens) and any(
        t in ("stock", "qty", "quantity", "level", "مخزون", "كمية") for t in tokens
    )


def _is_inventory_bound_quantity(tokens: list[str]) -> bool:
    """True when a header mixes a stock/inventory token with a qty token, so the
    column should map to an inventory-family role, never to sales ``quantity``."""
    has_qty = any(t in ("qty", "quantity", "كمية") for t in tokens)
    has_inventory = any(t in _INVENTORY_BOUND for t in tokens)
    return has_qty and has_inventory


def infer_schema(df: pd.DataFrame) -> IngestionResult:
    """Infer the canonical role of each column and return an IngestionResult."""
    profiles = profile_frame(df)
    relationships = relationship_adjust(df, profiles)

    used: set[int] = set()
    mappings: list[ColumnMapping] = []
    columns = list(df.columns)

    # Pass 1: best role per column with strong margin.
    ranked: list[tuple[float, str, str, list[str], list[tuple[str, float]]]] = []
    for i, col in enumerate(columns):
        cands = _score_column_candidates(str(col), profiles.get(str(col), ColumnProfile("")), relationships)
        tok = _tokens(str(col))

        if _is_inventory_policy_header(tok):
            # Policy thresholds never become a sales quantity; they should bind to
            # their own role or stay unrecognized rather than polluting the ledger.
            cands.pop("quantity", None)
            cands.pop("purchase_quantity", None)
            # Down-rank generic stock so a true "current stock" wins the role.
            for rname in ("stock", "opening_stock", "closing_stock", "inbound_stock"):
                if rname in cands:
                    cands[rname].header[rname] = 0.0
        elif _is_inventory_bound_quantity(tok):
            # "Inbound Qty", "Closing Qty", ... belong to the inventory family,
            # not sales quantity.
            cands.pop("quantity", None)
            cands.pop("purchase_quantity", None)

        scores = [
            (r, cands[r].total(r), cands[r].header.get(r, 0.0), cands[r].value.get(r, 0.0), cands[r].relationships.get(r, 0.0))
            for r in cands
        ]
        scores.sort(key=lambda x: (-x[1], -x[2], -x[3]))
        if not scores:
            continue
        top = scores[0]
        runner = scores[1][1] if len(scores) > 1 else 0.0
        margin = top[1] - runner
        evidence: list[str] = []
        if top[2] > 0:
            evidence.append(EVIDENCE_HEADER_MATCH)
        if top[3] > 0:
            evidence.append(EVIDENCE_VALUE_DISTRIBUTION)
        if top[4] > 0:
            evidence.append(EVIDENCE_RELATIONSHIP_SIGNAL)
        alts = [{"role": scores[k][0], "confidence": round(scores[k][1], 3)} for k in range(1, min(3, len(scores))) if scores[k][1] > 0]
        ranked.append((top[1], str(col), top[0], evidence, alts, margin))

    # Select greedily so a column is only used once (highest scoring first).
    ranked.sort(key=lambda x: (-x[0], x[1]))
    for entry in ranked:
        conf, col, role, evidence, alts, margin = entry[0], entry[1], entry[2], entry[3], entry[4], entry[5]
        idx = columns.index(col)
        if idx in used:
            continue
        if margin < MIN_CONFIDENCE_MARGIN and conf < CONFIDENCE_MEDIUM:
            # Not confident enough: leave for ambiguity pass.
            continue
        used.add(idx)
        mappings.append(ColumnMapping(source_column=col, role=role, confidence=conf, evidence=evidence, alternatives=alts))

    role_map: dict[str, str] = {m.role: m.source_column for m in mappings}
    file_classification = classify_file(role_map)

    result = IngestionResult(file_classification=file_classification, version="v2")
    for m in mappings:
        result.mappings.append(m)

    # Compute overall mapping confidence as the mean of confident mappings.
    if result.mappings:
        result.confidence = round(sum(m.confidence for m in result.mappings) / len(result.mappings), 3)

    # Report required fields that are genuinely absent so the caller never
    # silently substitutes zeros (Phase 2 / 24 / 41). Sales fields are required
    # only for sales-y files, inventory fields only for inventory-y files.
    required: set[str] = set()
    if any(c in file_classification for c in ("sales_history", "combined_inventory_sales")):
        required |= set(REQUIRED_SALES_FIELDS)
    if any(c in file_classification for c in ("inventory_snapshot", "combined_inventory_sales")):
        required |= set(REQUIRED_INVENTORY_FIELDS)
    if "purchases" in file_classification:
        required.add("product_name")
        required.add("purchase_quantity")
    missing = sorted(r for r in required if r not in role_map)
    if missing:
        result.missing_required_fields = missing
        result.error_code = "missing_required_field"

    # Status: ready only when all required fields for the detected domain map
    # confidently and there is no ambiguity; otherwise surface for review or
    # declare insufficient data (never a silent zero-substitution path).
    if result.missing_required_fields:
        required_present = sum(1 for r in required if r in role_map)
        if required_present == 0:
            result.status = INGESTION_STATUS_INSUFFICIENT_DATA
        else:
            result.status = INGESTION_STATUS_NEEDS_REVIEW
    else:
        # All required roles mapped. Flag for review only when a required role's
        # own confidence is weak (the audit depends on it), not for low-confidence
        # optional extras.
        required_conf_map = {m.role: m.confidence for m in mappings if m.role in required}
        if required_conf_map and any(c < CONFIDENCE_MEDIUM for c in required_conf_map.values()):
            result.status = INGESTION_STATUS_NEEDS_REVIEW
        else:
            result.status = INGESTION_STATUS_READY
    return result


# Backwards-compatible alias for the orchestrator.
def infer_columns(df: pd.DataFrame) -> IngestionResult:
    return infer_schema(df)
