"""Universal semantic vocabulary (spec §12).

This module is the **single authority** for what a column means. It supersedes:

* ``file_ingestion.COLUMN_ALIASES``      (6 roles, ~99 aliases)
* ``semantic_mapping.SEMANTIC_SIGNATURES`` (20 roles, weighted tokens)
* ``schema_detector.FIELD_PATTERNS``     (23 fields, name hints + validators)
* ``data_normalizer.FIELD_TARGETS``      (25 targets)
* ``etl_pipeline`` inline mapping dict   (10 pairs)

Those modules now delegate here; none of them defines its own namespace.

Design rules:

* A role declares its **domain**, its **aliases** (English and Arabic), the value
  **types** it may legitimately hold, its **unit dimension** when relevant, and
  its **currency behaviour** when relevant.
* ``amount``-like roles are deliberately kept distinct. "Amount" on a sales sheet
  is revenue; on a purchase sheet it is spend; on a bank sheet it is a movement.
  Collapsing them into one role is what produced fictional margins.
* Unknown means unknown. A header that matches nothing is ``UNMAPPED``, never
  silently coerced into the nearest role.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional

from app.services.orbit.contracts import DomainCapability, normalize_text


class ValueType(str, Enum):
    """Value shapes a role may legitimately contain."""

    TEXT = "text"
    IDENTIFIER = "identifier"
    NUMERIC = "numeric"
    QUANTITY = "quantity"
    CURRENCY = "currency"
    PERCENTAGE = "percentage"
    DATE = "date"
    DATETIME = "datetime"
    BOOLEAN = "boolean"


class CurrencyBehaviour(str, Enum):
    """How a role participates in currency handling.

    ``STRICT_CURRENCY`` means a value without a currency is incomplete and must
    not be normalised into a base currency by assumption.
    """

    #: Carries money. A bare number here is not enough to normalise currency.
    STRICT_CURRENCY = "strict_currency"
    #: May carry money but often holds a count or a rate instead.
    MAYBE_CURRENCY = "maybe_currency"
    #: Never money, even if the value is numeric.
    NEVER_CURRENCY = "never_currency"


class UnitDimension(str, Enum):
    MASS = "mass"
    VOLUME = "volume"
    COUNT = "count"
    LENGTH = "length"
    TIME = "time"
    CURRENCY = "currency"


@dataclass(frozen=True)
class SemanticRole:
    """One canonical meaning a column can carry."""

    canonical_name: str
    domain: DomainCapability
    value_type: ValueType
    aliases: tuple[str, ...] = ()
    #: Weighted tokens used for deterministic header scoring. Higher = stronger.
    tokens: tuple[tuple[str, float], ...] = ()
    unit_dimension: Optional[UnitDimension] = None
    currency_behaviour: CurrencyBehaviour = CurrencyBehaviour.NEVER_CURRENCY
    #: True for roles that make a row a *transaction* rather than a reference row.
    transactional: bool = False
    #: Roles that identify an entity of this kind, keyed by EntityKind value.
    entity_kind: Optional[str] = None
    description: str = ""
    #: A deliberately broad role that exists only as a last resort. These are
    #: allowed to overlap a specific role's alias (``amount`` is both a generic
    #: money column *and* an alias of ``sale_amount``): the specific role always
    #: wins the lookup, and the generic one only appears when nothing else fits.
    is_generic_fallback: bool = False

    @property
    def all_aliases(self) -> tuple[str, ...]:
        return (self.canonical_name, *self.aliases)

    def matches(self, normalized_header: str) -> float:
        """Deterministic 0..1 match of a normalized header against this role."""
        if not normalized_header:
            return 0.0
        header = normalize_text(normalized_header)
        for alias in self.all_aliases:
            if header == normalize_text(alias):
                return 1.0
        best = 0.0
        header_tokens = set(header.split())
        for token, weight in self.tokens:
            if not token:
                continue
            token_n = normalize_text(token)
            if header == token_n:
                best = max(best, weight)
            elif token_n in header_tokens:
                best = max(best, weight * 0.95)
            elif len(token_n) >= 4 and token_n in header:
                best = max(best, weight * 0.7)
        return best


# ─────────────────────────────────────────────────────────────────────────────
# The vocabulary
# ─────────────────────────────────────────────────────────────────────────────

def _role(*args, **kwargs) -> SemanticRole:
    return SemanticRole(*args, **kwargs)


_ROLES: tuple[SemanticRole, ...] = (
    # ── identity ──────────────────────────────────────────────────────────────
    _role(
        "product_name", DomainCapability.SALES, ValueType.TEXT,
        aliases=(
            "item", "item name", "product", "product name", "description",
            "sku name", "article", "article name", "commodity", "goods",
            "اسم المنتج", "اسم الصنف", "الصنف", "المنتج", "وصف", "سلعة", "بند",
            "الوصف", "اسم السلعة", "اسم البند",
        ),
        tokens=(("product", 0.95), ("item", 0.9), ("article", 0.85), ("name", 0.5),
                ("منتج", 0.9), ("صنف", 0.9), ("اسم", 0.4)),
        entity_kind="product",
        description="Human-readable product or item name.",
    ),
    _role(
        "sku", DomainCapability.SALES, ValueType.IDENTIFIER,
        aliases=(
            "sku", "sku code", "item code", "product code", "article number",
            "item no", "code", "reference", "ref",
            "رمز المنتج", "الرمز", "كود", "الكود", "رقم الصنف", "كود المنتج",
        ),
        tokens=(("sku", 1.0), ("barcode", 0.6), ("code", 0.7), ("رقم", 0.5), ("كود", 0.6)),
        entity_kind="product",
        description="Stable product identifier. Preferable to a name for entity identity.",
    ),
    _role(
        "barcode", DomainCapability.SALES, ValueType.IDENTIFIER,
        aliases=("barcode", "bar code", "ean", "upc", "ean13", "isbn", "الباركود", "البار كود"),
        tokens=(("barcode", 1.0), ("ean", 0.95), ("upc", 0.95), ("باركود", 1.0)),
        entity_kind="product",
        description="Scannable product identifier.",
    ),
    _role(
        "transaction_id", DomainCapability.SALES, ValueType.IDENTIFIER,
        aliases=(
            "transaction id", "transaction_id", "order id", "order number", "order no",
            "invoice number", "invoice no", "invoice #", "receipt no", "reference no",
            "رقم الفاتورة", "رقم الطلب", "رقم العملية", "رقم العملية",
        ),
        tokens=(("transaction", 0.95), ("order", 0.9), ("invoice", 0.9),
                ("receipt", 0.8), ("رقم", 0.4)),
        entity_kind="product",
        description="Identifier for a single transaction or order.",
    ),
    _role(
        "category", DomainCapability.SALES, ValueType.TEXT,
        aliases=("category", "category name", "department", "group", "section",
                 "التصنيف", "القسم", "الفئة", "مجموعة"),
        tokens=(("category", 0.95), ("department", 0.85), ("class", 0.5),
                ("تصنيف", 0.9), ("قسم", 0.8)),
        entity_kind="category",
        description="Product grouping.",
    ),
    _role(
        "brand", DomainCapability.SALES, ValueType.TEXT,
        aliases=("brand", "manufacturer", "vendor brand", "العلامة التجارية", "الماركة", "الشركة المصنعة"),
        tokens=(("brand", 0.95), ("manufacturer", 0.85), ("ماركة", 0.9), ("علامة", 0.7)),
        description="Product brand.",
    ),
    _role(
        "supplier_name", DomainCapability.PROCUREMENT, ValueType.TEXT,
        aliases=("supplier", "supplier name", "vendor", "vendor name", "distributor",
                 "المورد", "اسم المورد", "الموردين", "اسم المورد", "التاجر"),
        tokens=(("supplier", 0.95), ("vendor", 0.95), ("distributor", 0.8),
                ("مورد", 0.95), ("تاجر", 0.6)),
        entity_kind="supplier",
        description="Supplier or vendor name.",
    ),
    _role(
        "customer_name", DomainCapability.CUSTOMER, ValueType.TEXT,
        aliases=("customer", "customer name", "client", "buyer", "customer id",
                 "العميل", "اسم العميل", "المشتري"),
        tokens=(("customer", 0.95), ("client", 0.85), ("buyer", 0.8),
                ("عميل", 0.95), ("مشتري", 0.8)),
        entity_kind="customer",
        description="Customer or buyer name.",
    ),
    _role(
        "customer_phone", DomainCapability.CUSTOMER, ValueType.IDENTIFIER,
        aliases=("phone", "customer phone", "mobile", "telephone", "contact number",
                 "الهاتف", "رقم الهاتف", "الجوال", "الهاتف المحمول"),
        tokens=(("phone", 0.95), ("mobile", 0.9), ("telephone", 0.95), ("هاتف", 0.95), ("جوال", 0.9)),
        entity_kind="customer",
        description="Customer contact phone. Strong entity-resolution signal.",
    ),
    _role(
        "customer_email", DomainCapability.CUSTOMER, ValueType.IDENTIFIER,
        aliases=("email", "e-mail", "customer email", "mail",
                 "البريد الإلكتروني", "البريد"),
        tokens=(("email", 1.0), ("mail", 0.8), ("بريد", 0.9)),
        entity_kind="customer",
        description="Customer email address.",
    ),
    _role(
        "employee_name", DomainCapability.WORKFORCE, ValueType.TEXT,
        aliases=("employee", "employee name", "staff", "staff name", "worker",
                 "الموظف", "اسم الموظف", "الموظفين", "العامل"),
        tokens=(("employee", 0.95), ("staff", 0.9), ("worker", 0.8),
                ("موظف", 0.95), ("عامل", 0.7)),
        entity_kind="employee",
        description="Employee or staff member name.",
    ),
    _role(
        "branch_name", DomainCapability.SALES, ValueType.TEXT,
        aliases=("branch", "branch name", "store", "store name", "outlet",
                 "الفرع", "اسم الفرع", "المتجر", "المحل"),
        tokens=(("branch", 0.95), ("store", 0.9), ("outlet", 0.9), ("shop", 0.85),
                ("فرع", 0.95), ("متجر", 0.9)),
        entity_kind="branch",
        description="Branch, store or outlet.",
    ),
    _role(
        "location_name", DomainCapability.SALES, ValueType.TEXT,
        aliases=("location", "location name", "warehouse", "site", "الموقع", "المستودع", "المخزن"),
        tokens=(("location", 0.9), ("warehouse", 0.9), ("موقع", 0.9), ("مخزن", 0.9)),
        entity_kind="location",
        description="Physical location or warehouse.",
    ),

    # ── time ──────────────────────────────────────────────────────────────────
    _role(
        "date", DomainCapability.SALES, ValueType.DATE,
        aliases=(
            "date", "transaction date", "sale date", "order date", "invoice date",
            "posting date", "business date", "day", "timestamp", "datetime",
            "transaction_at", "التاريخ", "تاريخ البيع", "تاريخ الفاتورة",
            "تاريخ العملية", "التاريخ transact", "اليوم",
        ),
        tokens=(("date", 0.95), ("datetime", 0.9), ("timestamp", 0.9),
                ("day", 0.7), ("تاريخ", 0.95)),
        description="Transaction or observation date.",
    ),
    _role(
        "period_start", DomainCapability.FINANCE, ValueType.DATE,
        aliases=("period start", "from date", "start date", "opening date",
                 "تاريخ البداية", "من تاريخ"),
        tokens=(("period start", 1.0), ("from", 0.5), ("start", 0.8)),
        description="Start of a reporting period.",
    ),
    _role(
        "period_end", DomainCapability.FINANCE, ValueType.DATE,
        aliases=("period end", "to date", "end date", "closing date",
                 "تاريخ النهاية", "الى تاريخ"),
        tokens=(("period end", 1.0), ("end", 0.8), ("closing", 0.8)),
        description="End of a reporting period.",
    ),

    # ── sales / quantity ──────────────────────────────────────────────────────
    _role(
        "quantity", DomainCapability.SALES, ValueType.QUANTITY,
        aliases=(
            "quantity", "qty", "quantity sold", "sold qty", "units", "units sold",
            "الكمية", "الكمية المباعة", "الكميه", "الكمية المباعة",
            "عدد", "العدد",
        ),
        tokens=(("quantity", 0.95), ("qty", 1.0), ("units", 0.85), ("count", 0.6),
                ("كمية", 0.95), ("عدد", 0.7)),
        unit_dimension=UnitDimension.COUNT,
        transactional=True,
        description="Number of units sold or moved.",
    ),
    _role(
        "unit_price", DomainCapability.SALES, ValueType.CURRENCY,
        aliases=(
            "unit price", "price", "sell price", "selling price", "sale price",
            "price per unit", "rate", "unit cost sold", "retail price",
            "السعر", "سعر البيع", "سعر البيع للوحدة", "سعر الوحدة", "السعر للوحدة",
            "سعر الوحدة", "سعر البيع للوحدة",
        ),
        tokens=(("unit price", 1.0), ("price", 0.9), ("sell", 0.85), ("retail", 0.8),
                ("السعر", 0.9), ("سعر البيع", 0.95)),
        currency_behaviour=CurrencyBehaviour.STRICT_CURRENCY,
        unit_dimension=UnitDimension.CURRENCY,
        transactional=True,
        description="Price charged per unit.",
    ),
    _role(
        "sale_amount", DomainCapability.SALES, ValueType.CURRENCY,
        aliases=(
            "amount", "total", "total amount", "net", "net amount", "gross",
            "gross amount", "line total", "sales", "sale amount", "revenue",
            "subtotal", "total sales", "total net",
            "المبلغ", "المبلغ الإجمالي", "الإجمالي", "الاجمالي", "صافي",
            "الإيراد", "المبيعات", "إجمالي المبيعات",
        ),
        tokens=(("amount", 0.7), ("total", 0.7), ("net", 0.75), ("gross", 0.75),
                ("revenue", 0.95), ("sales", 0.7), ("subtotal", 0.6),
                ("مبلغ", 0.8), ("اجمالي", 0.85), ("صافي", 0.8), ("ايراد", 0.95)),
        currency_behaviour=CurrencyBehaviour.STRICT_CURRENCY,
        unit_dimension=UnitDimension.CURRENCY,
        transactional=True,
        description=(
            "Money received from customers. Distinct from payment_amount and "
            "expense: a bare 'Amount' column is a *candidate* for several of these."
        ),
    ),
    _role(
        "discount", DomainCapability.SALES, ValueType.CURRENCY,
        aliases=("discount", "discount amount", "discount value", "markdown",
                 "الخصم", "قيمة الخصم", "خصم"),
        tokens=(("discount", 0.95), ("markdown", 0.9), ("خصم", 0.95)),
        currency_behaviour=CurrencyBehaviour.STRICT_CURRENCY,
        unit_dimension=UnitDimension.CURRENCY,
        transactional=True,
        description="Discount applied to a sale.",
    ),
    _role(
        "tax_amount", DomainCapability.FINANCE, ValueType.CURRENCY,
        aliases=("tax", "tax amount", "vat", "vat amount", "gst", "sales tax",
                 "الضريبة", "قيمة الضريبة", "ضريبة القيمة المضافة", "الضريبه"),
        tokens=(("tax", 0.95), ("vat", 0.95), ("gst", 0.9), ("ضريبة", 0.95)),
        currency_behaviour=CurrencyBehaviour.STRICT_CURRENCY,
        unit_dimension=UnitDimension.CURRENCY,
        transactional=True,
        description="Tax charged or paid.",
    ),
    _role(
        "cost", DomainCapability.PROCUREMENT, ValueType.CURRENCY,
        aliases=("cost", "unit cost", "cost price", "buy price", "purchase price",
                 "cost per unit", "avg cost", "average cost", "landed cost",
                 "unit cost price", "التكلفة", "سعر الشراء", "تكلفة الوحدة",
                 "متوسط التكلفة", "تكلفة", "سعر التكلفة"),
        tokens=(("cost", 0.95), ("purchase price", 0.9), ("تكلفة", 0.95)),
        currency_behaviour=CurrencyBehaviour.STRICT_CURRENCY,
        unit_dimension=UnitDimension.CURRENCY,
        transactional=True,
        description="Cost paid to acquire goods. Required for margin.",
    ),

    # ── inventory ─────────────────────────────────────────────────────────────
    _role(
        "stock", DomainCapability.INVENTORY, ValueType.QUANTITY,
        aliases=(
            "stock", "current stock", "stock level", "quantity on hand", "on hand",
            "inventory level", "available stock", "stock in hand",
            "المخزون", "المخزون الحالي", "الكمية بالمخزن", "المتاح",
            "الكمية المتوفرة", "رصيد المخزون",
        ),
        tokens=(("stock", 0.95), ("inventory", 0.85), ("balance", 0.7),
                ("on hand", 0.9), ("مخزون", 0.95), ("رصيد", 0.8), ("الرصيد", 0.8)),
        unit_dimension=UnitDimension.COUNT,
        description="Stock on hand at a point in time. An observation, not a movement.",
    ),
    _role(
        "opening_stock", DomainCapability.INVENTORY, ValueType.QUANTITY,
        aliases=("opening stock", "begin stock", "initial stock",
                  "المخزون الافتتاحي", "الرصيد الإفتتاحي"),
        tokens=(("opening", 0.95), ("begin", 0.8), ("stock in", 0.9)),
        unit_dimension=UnitDimension.COUNT,
        description="Stock at the start of a period.",
    ),
    _role(
        "closing_stock", DomainCapability.INVENTORY, ValueType.QUANTITY,
        aliases=("closing stock", "end stock", "ending stock",
                  "الرصيد الختامي", "المخزون الختامي"),
        tokens=(("closing", 0.95), ("end", 0.7), ("stock out", 0.9)),
        unit_dimension=UnitDimension.COUNT,
        description="Stock at the end of a period.",
    ),
    _role(
        "waste_quantity", DomainCapability.INVENTORY, ValueType.QUANTITY,
        aliases=("waste", "waste qty", "spoilage", "damaged", "expired", "shrinkage",
                 "الهدر", "quantity هدر", "تالف", "منتهي", "هالك"),
        tokens=(("waste", 0.95), ("spoilage", 0.95), ("damaged", 0.85),
                ("expired", 0.9), ("هدر", 0.95), ("تالف", 0.9)),
        unit_dimension=UnitDimension.COUNT,
        description="Stock written off as waste.",
    ),
    _role(
        "transfer_in_quantity", DomainCapability.INVENTORY, ValueType.QUANTITY,
        aliases=("transfer in", "transfer in qty", "inbound transfer", "stock transfer in",
                 "منقول من", "وارد من فرع", "تحويل وارد"),
        tokens=(("transfer", 0.7), ("inbound", 0.9), ("in", 0.4)),
        unit_dimension=UnitDimension.COUNT,
        description="Quantity transferred in from another location.",
    ),
    _role(
        "transfer_out_quantity", DomainCapability.INVENTORY, ValueType.QUANTITY,
        aliases=("transfer out", "transfer out qty", "outbound transfer", "stock transfer out",
                 "منقول الى", "صادر الى فرع", "تحويل صادر"),
        tokens=(("transfer", 0.7), ("outbound", 0.9), ("out", 0.4)),
        unit_dimension=UnitDimension.COUNT,
        description="Quantity transferred out to another location.",
    ),
    _role(
        "adjustment_quantity", DomainCapability.INVENTORY, ValueType.QUANTITY,
        aliases=("adjustment", "adjustment qty", "stock adjustment", "variance",
                 "count adjustment", "التعديل", "تسوية", "فرق الجرد", "تعديل المخزون"),
        tokens=(("adjustment", 0.95), ("variance", 0.9), ("تعديل", 0.9), ("تسوية", 0.9)),
        unit_dimension=UnitDimension.COUNT,
        description="Manual stock correction.",
    ),
    _role(
        "reorder_point", DomainCapability.INVENTORY, ValueType.QUANTITY,
        aliases=("reorder point", "reorder level", "min stock", "minimum stock",
                 "threshold", "safety stock", "حد الطلب", "حد إعادة الطلب",
                 "الحد الأدنى", "المخزون الآمن"),
        tokens=(("reorder", 0.95), ("safety stock", 0.9), ("minimum", 0.7),
                ("الحد الأدنى", 0.9)),
        unit_dimension=UnitDimension.COUNT,
        description="Replenishment policy threshold. A policy, not an observation.",
    ),
    _role(
        "days_of_cover", DomainCapability.INVENTORY, ValueType.NUMERIC,
        aliases=("days of cover", "days cover", "stock cover", "days remaining",
                 "أيام التغطية", "مدة التغطية"),
        tokens=(("days of cover", 1.0), ("cover", 0.8), ("أيام", 0.6)),
        description="Derived: how long stock lasts at the current sales rate.",
    ),

    # ── procurement ───────────────────────────────────────────────────────────
    _role(
        "purchase_quantity", DomainCapability.PROCUREMENT, ValueType.QUANTITY,
        aliases=("purchase qty", "purchased qty", "received qty", "po qty",
                 "كمية الشراء", "الكمية المشتراة", "كمية التوريد"),
        tokens=(("purchase", 0.8), ("received", 0.9), ("po", 0.6), ("شراء", 0.9)),
        unit_dimension=UnitDimension.COUNT,
        transactional=True,
        description="Quantity purchased or received from a supplier.",
    ),
    _role(
        "purchase_amount", DomainCapability.PROCUREMENT, ValueType.CURRENCY,
        aliases=("purchase amount", "purchase total", "order value", "po value",
                 "order total", "total purchase",
                 "قيمة الشراء", "مبلغ الشراء", "قيمة الطلب", "إجمالي الشراء"),
        tokens=(("purchase", 0.8), ("order value", 0.9), ("شراء", 0.85)),
        currency_behaviour=CurrencyBehaviour.STRICT_CURRENCY,
        unit_dimension=UnitDimension.CURRENCY,
        transactional=True,
        description="Money spent with a supplier.",
    ),
    _role(
        "lead_time_days", DomainCapability.PROCUREMENT, ValueType.NUMERIC,
        aliases=("lead time", "lead time days", "delivery days", "delivery time",
                 "مدة التوريد", "مدة التوصيل", "أيام التوريد"),
        tokens=(("lead time", 1.0), ("delivery", 0.8), ("مدة التوريد", 1.0)),
        unit_dimension=UnitDimension.TIME,
        description="Time between order and delivery.",
    ),
    _role(
        "minimum_order_quantity", DomainCapability.PROCUREMENT, ValueType.QUANTITY,
        aliases=("moq", "minimum order quantity", "min order qty", "min order",
                 "الحد الأدنى للطلب", "أقل كمية طلب"),
        tokens=(("moq", 1.0), ("minimum order", 1.0), ("الحد الأدنى للطلب", 1.0)),
        unit_dimension=UnitDimension.COUNT,
        description="Supplier minimum order quantity.",
    ),

    # ── finance ───────────────────────────────────────────────────────────────
    _role(
        "payment_amount", DomainCapability.FINANCE, ValueType.CURRENCY,
        aliases=("payment", "paid", "payment amount", "paid amount", "settlement",
                 "value", "credit", "debit", "deposit",
                 "المبلغ المدفوع", "الدفعة", "دفعة", "المبلغ المحصل", "قيمة الدفعة"),
        tokens=(("payment", 0.95), ("paid", 0.9), ("settlement", 0.9),
                ("deposit", 0.8), ("دفعة", 0.95)),
        currency_behaviour=CurrencyBehaviour.STRICT_CURRENCY,
        unit_dimension=UnitDimension.CURRENCY,
        transactional=True,
        description="Money actually paid or collected, e.g. a bank movement.",
    ),
    _role(
        "expense_amount", DomainCapability.FINANCE, ValueType.CURRENCY,
        aliases=("expense", "expenses", "expense amount", "cost of expense",
                 "spend", "expenditure", "المصروف", "المصروفات", "المصروفات",
                 "قيمة المصروف", "الإنفاق"),
        tokens=(("expense", 0.95), ("spend", 0.85), ("expenditure", 0.95),
                ("مصروف", 0.95), ("انفاق", 0.9)),
        currency_behaviour=CurrencyBehaviour.STRICT_CURRENCY,
        unit_dimension=UnitDimension.CURRENCY,
        transactional=True,
        description="An operating expense.",
    ),
    _role(
        "balance", DomainCapability.FINANCE, ValueType.CURRENCY,
        aliases=("balance", "closing balance", "running balance", "account balance",
                 "الرصيد", "رصيد الحساب"),
        tokens=(("balance", 0.95), ("الرصيد", 0.9)),
        currency_behaviour=CurrencyBehaviour.STRICT_CURRENCY,
        unit_dimension=UnitDimension.CURRENCY,
        description="Account balance at a point in time.",
    ),
    _role(
        "opening_balance", DomainCapability.FINANCE, ValueType.CURRENCY,
        aliases=("opening balance", "opening bank balance", "balance b/f",
                 "الرصيد الافتتاحي", "رصيد أول المدة"),
        tokens=(("opening balance", 1.0), ("balance b/f", 1.0), ("الرصيد الافتتاحي", 1.0)),
        currency_behaviour=CurrencyBehaviour.STRICT_CURRENCY,
        unit_dimension=UnitDimension.CURRENCY,
        description="Account balance at period start.",
    ),
    _role(
        "bank_account", DomainCapability.FINANCE, ValueType.IDENTIFIER,
        aliases=("account number", "iban", "account no", "account", "bank account",
                 "رقم الحساب", "الحساب", "الآيبان", "ايبان"),
        tokens=(("iban", 1.0), ("account", 0.8), ("حساب", 0.9), ("ايبان", 1.0)),
        entity_kind="business",
        description="Bank account identifier.",
    ),

    # ── workforce ─────────────────────────────────────────────────────────────
    _role(
        "shift_date", DomainCapability.WORKFORCE, ValueType.DATE,
        aliases=("shift date", "shift", "rota", "duty date", "تاريخ الوردية", "الوردية"),
        tokens=(("shift", 0.9), ("rota", 0.95), ("duty", 0.85), ("وردية", 0.95)),
        description="Date of a work shift.",
    ),
    _role(
        "shift_hours", DomainCapability.WORKFORCE, ValueType.NUMERIC,
        aliases=("hours", "shift hours", "worked hours", "duration", "hours worked",
                 "ساعات", "ساعات العمل", "مدة الوردية"),
        tokens=(("hours", 0.9), ("ساعات", 0.95)),
        unit_dimension=UnitDimension.TIME,
        description="Hours worked.",
    ),
    _role(
        "attendance_status", DomainCapability.WORKFORCE, ValueType.TEXT,
        aliases=("status", "attendance", "attendance status", "presence",
                 "الحضور", "حالة الحضور", "الحالة"),
        tokens=(("attendance", 0.95), ("presence", 0.9), ("حضور", 0.95)),
        description="Attendance status for a shift.",
    ),

    # ── marketing ─────────────────────────────────────────────────────────────
    _role(
        "campaign_name", DomainCapability.MARKETING, ValueType.TEXT,
        aliases=("campaign", "campaign name", "promotion", "offer", "marketing campaign",
                 "الحملة", "اسم الحملة", "حملة تسويقية", "عرض"),
        tokens=(("campaign", 0.95), ("promotion", 0.9), ("offer", 0.8),
                ("حملة", 0.95)),
        description="Marketing campaign name.",
    ),
    _role(
        "channel", DomainCapability.MARKETING, ValueType.TEXT,
        aliases=("channel", "platform", "medium", "source", "traffic source",
                 "القناة", "المنصة", "مصدر", "وسيلة"),
        tokens=(("channel", 0.9), ("platform", 0.9), ("medium", 0.7), ("قناة", 0.9)),
        entity_kind="channel",
        description="Sales or marketing channel.",
    ),
    _role(
        "ad_spend", DomainCapability.MARKETING, ValueType.CURRENCY,
        aliases=("ad spend", "advertising spend", "campaign cost", "budget spent",
                 "الإنفاق الإعلاني", "ميزانية الإعلان", "تكلفة الحملة"),
        tokens=(("ad spend", 1.0), ("advertising", 0.95), ("campaign cost", 0.95),
                ("إنفاق إعلاني", 1.0)),
        currency_behaviour=CurrencyBehaviour.STRICT_CURRENCY,
        unit_dimension=UnitDimension.CURRENCY,
        description="Advertising expenditure.",
    ),
    _role(
        "impressions", DomainCapability.MARKETING, ValueType.NUMERIC,
        aliases=("impressions", "reach", "views", "clicks", "clicks count",
                 "الظهور", "الوصول", "المشاهدات", "النقرات"),
        tokens=(("impressions", 0.95), ("reach", 0.9), ("views", 0.8),
                ("clicks", 0.95), ("ظهور", 0.9), ("مشاهدات", 0.9)),
        unit_dimension=UnitDimension.COUNT,
        description="Marketing reach metrics.",
    ),

    # ── units / generic numeric ──────────────────────────────────────────────
    _role(
        "unit", DomainCapability.INVENTORY, ValueType.TEXT,
        aliases=("unit", "uom", "unit of measure", "uom name", "packing unit",
                 "الوحدة", "وحدة القياس", "الوحده"),
        tokens=(("unit", 0.8), ("uom", 1.0), ("packing", 0.7), ("وحدة", 0.95)),
        description="Unit of measure for quantities.",
    ),
    _role(
        "amount", DomainCapability.FINANCE, ValueType.CURRENCY,
        aliases=(),
        tokens=(("amount", 0.55), ("value", 0.4), ("total", 0.4),
                ("مبلغ", 0.55), ("قيمة", 0.4), ("المجموع", 0.4)),
        currency_behaviour=CurrencyBehaviour.MAYBE_CURRENCY,
        unit_dimension=UnitDimension.CURRENCY,
        transactional=True,
        is_generic_fallback=True,
        description=(
            "Generic money column, deliberately weak scoring. 'Amount' is genuinely "
            "ambiguous between revenue, spend, payment and expense, so it only wins "
            "when no specific role fits — see GENERIC_MONEY_HEADERS in the column "
            "mapper, which reports it as ambiguous rather than guessing."
        ),
    ),
    _role(
        "count", DomainCapability.SALES, ValueType.NUMERIC,
        aliases=(),
        tokens=(("count", 0.55), ("records", 0.5), ("عدد", 0.5)),
        unit_dimension=UnitDimension.COUNT,
        is_generic_fallback=True,
        description="Generic count column, deliberately weak scoring.",
    ),
    _role(
        "notes", DomainCapability.SALES, ValueType.TEXT,
        aliases=("notes", "note", "comment", "comments", "remarks", "description line",
                 "ملاحظات", "ملاحظة", "تعليقات", "remark"),
        tokens=(("note", 0.9), ("comment", 0.9), ("remark", 0.9), ("ملاحظات", 0.95)),
        description="Free-text annotation.",
    ),
)

#: Canonical name -> role
ROLE_BY_NAME: dict[str, SemanticRole] = {r.canonical_name: r for r in _ROLES}

#: All roles, deterministically ordered by canonical name.
ALL_ROLES: tuple[SemanticRole, ...] = tuple(sorted(_ROLES, key=lambda r: r.canonical_name))

#: Roles that carry money. Used by the currency normalizer to decide strictness.
CURRENCY_ROLES: tuple[str, ...] = tuple(
    sorted(r.canonical_name for r in _ROLES
           if r.currency_behaviour is CurrencyBehaviour.STRICT_CURRENCY)
)

#: Normalized alias -> canonical role name. Built once; the single alias index.
#: Generic fallback roles never win this lookup — they are reached by scoring, not
#: by an exact alias claim, so a specific role always takes priority.
ALIAS_INDEX: dict[str, str] = {}
for _r in _ROLES:
    if _r.is_generic_fallback:
        continue
    for _a in _r.all_aliases:
        _n = normalize_text(_a)
        if _n and _n not in ALIAS_INDEX:
            ALIAS_INDEX[_n] = _r.canonical_name

#: Roles that can identify an entity, per EntityKind value.
ENTITY_ROLES: dict[str, tuple[str, ...]] = {}
for _r in _ROLES:
    if _r.entity_kind:
        ENTITY_ROLES.setdefault(_r.entity_kind, tuple())
        ENTITY_ROLES[_r.entity_kind] = ENTITY_ROLES[_r.entity_kind] + (_r.canonical_name,)

#: Roles whose presence makes a row transactional.
TRANSACTIONAL_ROLES: frozenset[str] = frozenset(
    r.canonical_name for r in _ROLES if r.transactional
)

#: Roles carrying a date.
DATE_ROLES: frozenset[str] = frozenset(
    r.canonical_name for r in _ROLES if r.value_type in (ValueType.DATE, ValueType.DATETIME)
)

#: Per-artifact-kind role allowlists. The artifact classifier determines the
#: kind; the mapper then refuses to assign roles that make no sense for it. This
#: is how "Amount" stops being an unanswerable question on a bank statement.
#: Roles not listed remain available as candidates so the exclusion is visible.
ROLES_BY_ARTIFACT_KIND: dict[str, tuple[str, ...]] = {
    "pos_export": (
        "date", "product_name", "sku", "barcode", "category", "brand",
        "quantity", "unit_price", "sale_amount", "discount", "tax_amount",
        "transaction_id", "branch_name", "location_name", "customer_name",
        "payment_amount", "cost", "notes",
    ),
    "inventory_export": (
        "sku", "barcode", "product_name", "category", "brand", "stock",
        "opening_stock", "closing_stock", "adjustment_quantity", "waste_quantity",
        "transfer_in_quantity", "transfer_out_quantity", "reorder_point",
        "cost", "unit_price", "unit", "location_name", "branch_name", "date",
    ),
    "bank_statement": (
        "date", "transaction_id", "payment_amount", "balance", "opening_balance",
        "bank_account", "notes", "branch_name", "period_start", "period_end",
    ),
    "supplier_quote": (
        "date", "supplier_name", "product_name", "sku", "purchase_quantity",
        "cost", "unit_price", "purchase_amount", "tax_amount", "notes",
    ),
    "invoice": (
        "date", "supplier_name", "customer_name", "transaction_id", "product_name",
        "sku", "quantity", "unit_price", "sale_amount", "tax_amount", "notes",
    ),
    "purchase_order": (
        "date", "supplier_name", "product_name", "sku", "purchase_quantity",
        "cost", "unit_price", "purchase_amount", "minimum_order_quantity",
        "lead_time_days", "notes",
    ),
    "staff_schedule": (
        "shift_date", "employee_name", "shift_hours", "attendance_status",
        "branch_name", "notes",
    ),
    "marketing_report": (
        "date", "campaign_name", "channel", "ad_spend", "impressions",
        "sale_amount", "branch_name", "notes",
    ),
    "expense_report": (
        "date", "expense_amount", "tax_amount", "payment_amount", "notes",
        "branch_name", "supplier_name",
    ),
}


#: The domain each artifact kind primarily carries. This is what disambiguates a
#: generic money header: "Amount" on a sales export is revenue, on a bank
#: statement it is a movement. It is *not* a claim that the artifact contains no
#: other domains' data.
PRIMARY_DOMAIN_BY_ARTIFACT_KIND: dict[str, DomainCapability] = {
    "pos_export": DomainCapability.SALES,
    "inventory_export": DomainCapability.INVENTORY,
    "bank_statement": DomainCapability.FINANCE,
    "supplier_quote": DomainCapability.PROCUREMENT,
    "invoice": DomainCapability.SALES,
    "purchase_order": DomainCapability.PROCUREMENT,
    "staff_schedule": DomainCapability.WORKFORCE,
    "marketing_report": DomainCapability.MARKETING,
    "expense_report": DomainCapability.FINANCE,
}


#: Which money role a generic money header means on each artifact kind. This is
#: deliberately explicit rather than inferred from scores: a POS export's
#: "Amount" is revenue and a bank statement's "Amount" is a movement, and that
#: fact comes from what the artifact *is*, not from how its headers happen to
#: score. Absent an entry, a generic money header stays ambiguous.
GENERIC_MONEY_ROLE_BY_ARTIFACT_KIND: dict[str, str] = {
    "pos_export": "sale_amount",
    "invoice": "sale_amount",
    "marketing_report": "sale_amount",
    "bank_statement": "payment_amount",
    "expense_report": "expense_amount",
    "purchase_order": "purchase_amount",
    "supplier_quote": "purchase_amount",
}

#: Headers that name money without naming *what kind*. A bare "Amount" is
#: genuinely revenue on a sales sheet, spend on a purchase sheet and a movement on
#: a bank sheet. Without an artifact hint these are reported as ambiguous rather
#: than resolved to whichever role happened to score highest.
GENERIC_MONEY_HEADERS: frozenset[str] = frozenset({
    "amount", "total", "value", "sum", "total amount", "total value", "amount value",
    "net", "amount paid", "price", "money", "cost",
    "المبلغ", "القيمة", "المجموع", "اجمالي", "المبلغ الاجمالي", "سعر", "تكلفة",
})

#: The same idea for quantity headers. "Qty" on a purchase order is a purchase
#: quantity; on an inventory sheet it is stock on hand.
GENERIC_QUANTITY_ROLE_BY_ARTIFACT_KIND: dict[str, str] = {
    "pos_export": "quantity",
    "invoice": "quantity",
    "marketing_report": "quantity",
    "purchase_order": "purchase_quantity",
    "supplier_quote": "purchase_quantity",
    "inventory_export": "stock",
}

#: Headers that name a quantity without naming which quantity.
GENERIC_QUANTITY_HEADERS: frozenset[str] = frozenset({
    "qty", "quantity", "units", "unit count", "count", "number", "no", "الكمية", "العدد", "عدد",
})


def designated_role_for(normalized_header: str, artifact_kind: Optional[str]) -> Optional[str]:
    """The role a generic header denotes on a given artifact kind, if known.

    Checked *before* score filtering, because a generic header legitimately has
    no header-level evidence for the specific role: "Qty" scores nothing for
    ``purchase_quantity``, yet on a purchase order it can only mean that.
    """
    if not artifact_kind:
        return None
    if normalized_header in GENERIC_MONEY_HEADERS:
        return GENERIC_MONEY_ROLE_BY_ARTIFACT_KIND.get(artifact_kind)
    if normalized_header in GENERIC_QUANTITY_HEADERS:
        return GENERIC_QUANTITY_ROLE_BY_ARTIFACT_KIND.get(artifact_kind)
    return None


def get_role(name: str) -> Optional[SemanticRole]:
    """Look up a role by canonical name."""
    return ROLE_BY_NAME.get(name)


def roles_for_domain(domain: DomainCapability) -> tuple[SemanticRole, ...]:
    """All roles belonging to a domain."""
    return tuple(r for r in ALL_ROLES if r.domain is domain)


def domain_of(role_name: str) -> Optional[DomainCapability]:
    role = ROLE_BY_NAME.get(role_name)
    return role.domain if role else None


def unit_dimension_of(role_name: str) -> Optional[UnitDimension]:
    role = ROLE_BY_NAME.get(role_name)
    return role.unit_dimension if role else None


def is_currency_role(role_name: str) -> bool:
    role = ROLE_BY_NAME.get(role_name)
    return bool(role and role.currency_behaviour is CurrencyBehaviour.STRICT_CURRENCY)


def exact_alias_lookup(normalized_header: str) -> Optional[str]:
    """Deterministic exact alias hit, if any. Generic fallbacks are excluded."""
    return ALIAS_INDEX.get(normalize_text(normalized_header))


def validate_vocabulary() -> list[str]:
    """Self-check used by tests: the vocabulary must be internally consistent.

    A collision between two *specific* roles is a genuine bug: the index would
    resolve it by dict order, i.e. arbitrarily. A collision involving a generic
    fallback role is intentional and permitted.
    """
    problems: list[str] = []
    names = [r.canonical_name for r in _ROLES]
    if len(names) != len(set(names)):
        problems.append("duplicate canonical role names")

    seen: dict[str, str] = {}
    generic = {r.canonical_name for r in _ROLES if r.is_generic_fallback}
    for role in _ROLES:
        if role.is_generic_fallback:
            continue
        for alias in role.all_aliases:
            key = normalize_text(alias)
            if key in seen and seen[key] != role.canonical_name:
                problems.append(
                    f"alias {alias!r} claimed by both {seen[key]!r} and {role.canonical_name!r}"
                )
            seen.setdefault(key, role.canonical_name)

    # A generic fallback must not appear in the alias index at all.
    for key, owner in ALIAS_INDEX.items():
        if owner in generic:
            problems.append(f"generic role {owner!r} captured alias {key!r}")

    for name in CURRENCY_ROLES:
        role = ROLE_BY_NAME[name]
        if role.unit_dimension is not UnitDimension.CURRENCY:
            problems.append(f"currency role {name!r} lacks the CURRENCY unit dimension")

    for role in _ROLES:
        if role.value_type is ValueType.QUANTITY and role.unit_dimension is None:
            problems.append(f"quantity role {role.canonical_name!r} lacks a unit dimension")

    return problems