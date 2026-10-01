"""Phase 1 canonical business-reality contracts.

These are the only authoritative types for the Business Reality Layer. Every
ingestion path, every normalizer, and every API response is built from them.

Design rules encoded here (not merely documented):

1. **unknown != zero.** A value carries an explicit :class:`FieldStatus`. There is
   no way to express "we do not know" as ``0``/``[]``/``{}`` — the convenience of a
   bare number is deliberately unavailable.
2. **No provenance, no fact.** Every canonical value carries ``evidence_ids``.
   :func:`Measured.without_evidence` refuses to produce a usable fact.
3. **Evidence is immutable and content-addressed.** Identical ``content_hash``
   means identical evidence, which is what makes re-ingestion idempotent.
4. **Conflicts are first class.** Disagreeing sources produce a
   :class:`Conflict`; they never overwrite one another.
5. **Determinism first.** JEV may *classify* ambiguity but every artifact records
   whether it came from a deterministic rule or from a judgment, and a judgment
   can never create a value without evidence.

Versioned by ``PHASE_1_CONTRACT_VERSION``; bump on any structural change so
historical artifacts stay distinguishable from new ones.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field, replace
# ``Conflict`` declares a domain attribute named ``field``, which shadows
# ``dataclasses.field`` inside that class body. Use the alias wherever a field
# specifier is needed in a class that has a ``field`` attribute.
from dataclasses import field as dc_field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping, Optional, Sequence
from uuid import UUID, uuid4

PHASE_1_CONTRACT_VERSION = "phase1-v1"

D = Decimal


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Missingness — the single most important type in this module
# ─────────────────────────────────────────────────────────────────────────────

class FieldStatus(str, Enum):
    """How do we know a value (or that we do not)?

    ``MISSING`` means the source did not contain the field.
    ``UNKNOWN`` means a value exists but its meaning could not be established.
    These are deliberately distinct: conflating them is how systems end up
    asserting ``0`` for something nobody reported.
    """

    PRESENT = "present"
    MISSING = "missing"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"
    NOT_APPLICABLE = "not_applicable"


class ContractViolation(ValueError):
    """Raised when a Phase 1 contract invariant is violated.

    These are programming errors, not business conditions. Business conditions
    (missing data, ambiguity, conflict) are represented as data — see
    :class:`FieldStatus` — never as exceptions.
    """


class ContentHashError(ContractViolation):
    """An artifact was constructed without a usable content hash."""


#: Backwards-compatible alias used inside this module.
ValueError_ = ContractViolation


@dataclass(frozen=True)
class Measured:
    """A single measured value with explicit status and provenance.

    The whole point: you cannot hold a ``Measured`` whose status is ``MISSING``
    and read it as a number without explicitly acknowledging it.
    """

    value: Optional[Decimal] = None
    status: FieldStatus = FieldStatus.MISSING
    unit: Optional[str] = None
    currency: Optional[str] = None
    evidence_ids: tuple[str, ...] = ()

    @property
    def is_known(self) -> bool:
        return self.status is FieldStatus.PRESENT and self.value is not None

    def __post_init__(self) -> None:
        # A present value must have a number; a non-present value must not
        # masquerade as one.
        if self.status is FieldStatus.PRESENT and self.value is None:
            raise ValueError_("status PRESENT requires a value")
        if self.status is not FieldStatus.PRESENT and self.value is not None:
            raise ValueError_(
                f"status {self.status.value} must not carry a value "
                f"(got {self.value!r}) — unknown is not zero"
            )
        if self.status is FieldStatus.PRESENT and not self.evidence_ids:
            raise ValueError_("a PRESENT value requires evidence_ids (no provenance, no fact)")

    @classmethod
    def present(
        cls,
        value: Any,
        *,
        unit: Optional[str] = None,
        currency: Optional[str] = None,
        evidence_ids: Sequence[str] = (),
    ) -> "Measured":
        return cls(
            value=_to_decimal(value),
            status=FieldStatus.PRESENT,
            unit=unit,
            currency=currency,
            evidence_ids=tuple(dict.fromkeys(str(e) for e in evidence_ids)),
        )

    @classmethod
    def missing(cls) -> "Measured":
        return cls(status=FieldStatus.MISSING)

    @classmethod
    def unknown(cls, *, evidence_ids: Sequence[str] = ()) -> "Measured":
        return cls(status=FieldStatus.UNKNOWN, evidence_ids=tuple(evidence_ids))

    @classmethod
    def conflict(cls, *, evidence_ids: Sequence[str] = ()) -> "Measured":
        return cls(status=FieldStatus.CONFLICT, evidence_ids=tuple(evidence_ids))

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": None if self.value is None else float(self.value),
            "status": self.status.value,
            "unit": self.unit,
            "currency": self.currency,
            "evidence_ids": list(self.evidence_ids),
        }


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError_("booleans are not numeric measures")
    if isinstance(value, int):
        return D(value)
    if isinstance(value, float):
        return D(str(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return D(text)
        except Exception as exc:  # noqa: BLE001
            raise ValueError_(f"not numeric: {value!r}") from exc
    raise ValueError_(f"cannot coerce to Decimal: {value!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Vocabularies
# ─────────────────────────────────────────────────────────────────────────────

class SourceType(str, Enum):
    FILE = "file"
    API = "api"
    DATABASE = "database"
    IMPORT = "import"
    MANUAL_UPLOAD = "manual_upload"
    SYSTEM_EXPORT = "system_export"


class ArtifactType(str, Enum):
    """Canonical artifact classification vocabulary."""

    CSV = "csv"
    XLSX = "xlsx"
    XLS = "xls"
    JSON = "json"
    PDF = "pdf"
    DOCX = "docx"
    IMAGE = "image"
    TEXT = "text"
    BANK_STATEMENT = "bank_statement"
    POS_EXPORT = "pos_export"
    SUPPLIER_QUOTE = "supplier_quote"
    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"
    INVENTORY_EXPORT = "inventory_export"
    STAFF_SCHEDULE = "staff_schedule"
    MARKETING_REPORT = "marketing_report"
    CONTRACT = "contract"
    UNKNOWN = "unknown"


class IngestionStatus(str, Enum):
    RECEIVED = "received"
    CLASSIFYING = "classifying"
    EXTRACTING = "extracting"
    NORMALIZING = "normalizing"
    RESOLVING = "resolving"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class ExtractionMethod(str, Enum):
    """How a value was read out of its source. Never 'model guessed'."""

    SPREADSHEET_CELL = "spreadsheet_cell"
    SPREADSHEET_HEADER = "spreadsheet_header"
    CSV_FIELD = "csv_field"
    JSON_PATH = "json_path"
    DOCUMENT_TEXT = "document_text"
    DOCUMENT_TABLE = "document_table"
    OCR = "ocr"
    API_FIELD = "api_field"
    MANUAL_ENTRY = "manual_entry"
    DERIVED = "derived"


class RowRole(str, Enum):
    DATA = "data"
    HEADER = "header"
    SUBTOTAL = "subtotal"
    TOTAL = "total"
    FOOTER = "footer"
    NOTE = "note"
    SECTION = "section"
    METADATA = "metadata"
    UNKNOWN = "unknown"


class EntityKind(str, Enum):
    PRODUCT = "product"
    SUPPLIER = "supplier"
    CUSTOMER = "customer"
    EMPLOYEE = "employee"
    BRANCH = "branch"
    LOCATION = "location"
    BUSINESS = "business"
    CHANNEL = "channel"
    CATEGORY = "category"
    CONTRACT = "contract"


class MatchMethod(str, Enum):
    EXACT_ID = "exact_id"
    NORMALIZED_ID = "normalized_id"
    EXACT_NORMALIZED_NAME = "exact_normalized_name"
    ALIAS = "alias"
    SKU = "sku"
    BARCODE = "barcode"
    PHONE = "phone"
    EMAIL = "email"
    FUZZY = "fuzzy"
    JEV = "jev"
    MANUAL = "manual"
    UNRESOLVED = "unresolved"


class ResolutionOutcome(str, Enum):
    SAME_ENTITY = "same_entity"
    DIFFERENT_ENTITY = "different_entity"
    AMBIGUOUS = "ambiguous"


class ConflictRelationship(str, Enum):
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    DUPLICATES = "duplicates"
    PARTIALLY_OVERLAPS = "partially_overlaps"
    TEMPORAL_VALID = "temporal_valid"
    UNKNOWN = "unknown"


class ConflictSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConflictResolution(str, Enum):
    UNRESOLVED = "unresolved"
    RESOLVED_DETERMINISTIC = "resolved_deterministic"
    RESOLVED_MANUAL = "resolved_manual"
    NEEDS_REVIEW = "needs_review"


class QualityDimension(str, Enum):
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    VALIDITY = "validity"
    UNIQUENESS = "uniqueness"
    TIMELINESS = "timeliness"
    COVERAGE = "coverage"
    SEMANTIC_CONFIDENCE = "semantic_confidence"
    ENTITY_RESOLUTION_QUALITY = "entity_resolution_quality"
    SOURCE_RELIABILITY = "source_reliability"
    CONFLICT_RATE = "conflict_rate"


class QualityIssueKind(str, Enum):
    DUPLICATE = "duplicate"
    MISSING = "missing"
    SUSPECT = "suspect"
    CONFLICT = "conflict"
    SOURCE_LAG = "source_lag"
    PARSING_ERROR = "parsing_error"
    SEMANTIC_AMBIGUITY = "semantic_ambiguity"
    UNSUPPORTED = "unsupported"


class FreshnessState(str, Enum):
    FRESH = "fresh"
    RECENT = "recent"
    STALE = "stale"
    MISSING = "missing"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


class DecisionOrigin(str, Enum):
    """Who decided a value — determinism first, judgment only for ambiguity."""

    DETERMINISTIC = "deterministic"
    JEV = "jev"
    MANUAL = "manual"
    DERIVED = "derived"
    NONE = "none"


class BusinessType(str, Enum):
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    RETAIL = "retail"
    GROCERY = "grocery"
    BAQALA = "baqala"
    PHARMACY = "pharmacy"
    HOTEL = "hotel"
    SERVICES = "services"
    WHOLESALE = "wholesale"
    DISTRIBUTION = "distribution"
    OTHER = "other"
    UNKNOWN = "unknown"


class DomainCapability(str, Enum):
    SALES = "sales"
    INVENTORY = "inventory"
    PROCUREMENT = "procurement"
    FINANCE = "finance"
    WORKFORCE = "workforce"
    MARKETING = "marketing"
    CUSTOMER = "customer"


class SourceReliability(str, Enum):
    """Feeds confidence and conflict handling; never silently overwrites facts."""

    OFFICIAL_POS_EXPORT = "official_pos_export"
    BANK_EXPORT = "bank_export"
    SUPPLIER_QUOTE = "supplier_quote"
    SYSTEM_EXPORT = "system_export"
    MANUAL_SPREADSHEET = "manual_spreadsheet"
    OCR_DOCUMENT = "ocr_document"
    USER_ENTERED = "user_entered"
    UNKNOWN_SOURCE = "unknown_source"


# ─────────────────────────────────────────────────────────────────────────────
# Error classification (spec §53 — never collapse everything to 500)
# ─────────────────────────────────────────────────────────────────────────────

class ErrorCategory(str, Enum):
    PARSE_ERROR = "parse_error"
    SCHEMA_ERROR = "schema_error"
    SEMANTIC_ERROR = "semantic_error"
    ENTITY_ERROR = "entity_error"
    TIME_ERROR = "time_error"
    UNIT_ERROR = "unit_error"
    CURRENCY_ERROR = "currency_error"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    SECURITY_ERROR = "security_error"
    UNSUPPORTED_FORMAT = "unsupported_format"
    SOURCE_ERROR = "source_error"
    JEV_ERROR = "jev_error"
    INTERNAL_ERROR = "internal_error"


class IngestionError(Exception):
    """Structured, categorised ingestion failure (never a bare 500)."""

    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        *,
        locator: Optional[str] = None,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(f"{category.value}: {message}")
        self.category = category
        self.message = message
        self.locator = locator
        self.detail = detail or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "message": self.message,
            "locator": self.locator,
            "detail": self.detail,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Normalization primitives (shared by every normalizer)
# ─────────────────────────────────────────────────────────────────────────────

_ARABIC_DIGITS = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_ARABIC_DECIMAL = {ord("٫"): ".", ord("٬"): "", ord("،"): ""}
_DIACRITICS = "ًٌٍَُِّْٰٕٓٔ"
_NON_ALNUM = re.compile(r"[^\w\s]+", re.UNICODE)
_WS = re.compile(r"\s+")

# Conservative total-row detection. Deliberately narrow: a false positive turns a
# total into a fake transaction, which is worse than leaving it unclassified.
_TOTAL_TOKENS = {
    "total", "totals", "grand total", "subtotal", "sub total", "net total",
    "المجموع", "اجمالي", "إجمالي", "المجموع الكلي", "المجموع الفرعي",
    "اجمالي المبيعات", "صافي",
}
_SECTION_TOKENS = {
    "notes", "note", "comment", "comments", "remark", "remarks", "disclaimer",
    "ملاحظات", "ملاحظه", "تعليق",
}


def normalize_text(value: Any) -> str:
    """Conservative text normalization that preserves the original elsewhere.

    NFKC, Arabic-Indic digits → ASCII, Arabic diacritics stripped, punctuation
    → space, whitespace collapsed, lowercased.
    """
    if value is None:
        return ""
    text = str(value)
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_ARABIC_DIGITS).translate(_ARABIC_DECIMAL)
    text = "".join(ch for ch in text if ch not in _DIACRITICS)
    text = _NON_ALNUM.sub(" ", text)
    return _WS.sub(" ", text).strip().lower()


def normalize_identifier(value: Any) -> str:
    """Aggressive key form for exact-match identifier comparison."""
    return re.sub(r"[^a-z0-9؀-ۿ]+", "", normalize_text(value))


def content_hash(*parts: Any) -> str:
    """Stable content hash used for idempotent ingestion and evidence identity."""
    payload = json.dumps(
        [None if p is None else str(p) for p in parts],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def deterministic_fingerprint(*parts: Any) -> str:
    """Short stable fingerprint for dedup keys."""
    return content_hash(*parts)[:24]


def looks_arabic(value: Any) -> bool:
    text = str(value or "")
    return bool(re.search(r"[؀-ۿ]", text))


# ─────────────────────────────────────────────────────────────────────────────
# Artifacts (§5)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SourceLocator:
    """Where inside an artifact a piece of evidence came from.

    A developer must be able to trace any canonical number back to a sheet, row
    and column (or a page and character offset for documents).
    """

    sheet: Optional[str] = None
    page: Optional[int] = None
    table: Optional[int] = None
    row: Optional[int] = None
    column: Optional[str] = None
    char_offset: Optional[int] = None
    locator: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass(frozen=True)
class UniversalArtifact:
    """One external piece of business evidence. Content-addressed and immutable."""

    artifact_id: UUID = field(default_factory=uuid4)
    business_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    ingestion_run_id: Optional[UUID] = None
    parent_artifact_id: Optional[UUID] = None

    source_type: SourceType = SourceType.FILE
    source_name: str = ""
    source_location: Optional[str] = None
    mime_type: Optional[str] = None

    artifact_type: ArtifactType = ArtifactType.UNKNOWN
    classification_confidence: float = 0.0
    classification_origin: DecisionOrigin = DecisionOrigin.DETERMINISTIC
    classification_alternatives: tuple[dict[str, Any], ...] = ()
    #: True when deterministic signals could not decide and the result came from
    #: (or still needs) bounded judgment. Never silently presented as certain.
    classification_needs_review: bool = False

    content_hash: str = ""
    size_bytes: Optional[int] = None
    version: int = 1

    received_at: datetime = field(default_factory=_utcnow)
    observed_at: Optional[datetime] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None

    timezone: Optional[str] = None
    currency: Optional[str] = None
    language: Optional[str] = None

    status: IngestionStatus = IngestionStatus.RECEIVED
    confidence: float = 0.0
    quality: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.content_hash:
            raise ContentHashError("artifact requires a content_hash (idempotency anchor)")

    def with_status(self, status: IngestionStatus, **kw: Any) -> "UniversalArtifact":
        return replace(self, status=status, **kw)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in self.__dict__.items():
            if isinstance(v, Enum):
                out[k] = v.value
            elif isinstance(v, (UUID, datetime, date)):
                out[k] = v.isoformat() if v is not None else None
            elif isinstance(v, tuple):
                out[k] = list(v)
            else:
                out[k] = v
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Evidence (§12)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Evidence:
    """Append-only, content-addressed provenance for one extracted value."""

    evidence_id: str = ""
    artifact_id: Optional[UUID] = None
    business_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None

    source_type: SourceType = SourceType.FILE
    source_locator: SourceLocator = field(default_factory=SourceLocator)

    raw_value: Optional[str] = None
    normalized_value: Optional[str] = None
    semantic_role: Optional[str] = None
    entity_ref: Optional[str] = None

    observed_at: Optional[datetime] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None

    confidence: float = 0.0
    quality: dict[str, Any] = field(default_factory=dict)
    extraction_method: ExtractionMethod = ExtractionMethod.SPREADSHEET_CELL
    #: True for OCR-derived evidence. Low-confidence OCR must never be treated as
    #: unquestioned truth, so this flag is explicit rather than implied.
    is_ocr: bool = False
    created_at: datetime = field(default_factory=_utcnow)
    hash: str = ""

    def __post_init__(self) -> None:
        if not self.hash:
            object.__setattr__(self, "hash", self.compute_hash())
        if not self.evidence_id:
            object.__setattr__(self, "evidence_id", f"ev-{self.hash[:24]}")

    def compute_hash(self) -> str:
        return content_hash(
            self.artifact_id,
            self.source_locator.to_dict(),
            self.raw_value,
            self.normalized_value,
            self.semantic_role,
            self.observed_at,
            self.period_start,
            self.period_end,
        )

    @property
    def is_trusted_fact(self) -> bool:
        """A fact we may build canonical state on."""
        if self.is_ocr and self.confidence < 0.8:
            return False
        return self.confidence > 0.0

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in self.__dict__.items():
            if isinstance(v, Enum):
                out[k] = v.value
            elif isinstance(v, (UUID, datetime, date)):
                out[k] = v.isoformat() if v is not None else None
            elif isinstance(v, SourceLocator):
                out[k] = v.to_dict()
            else:
                out[k] = v
        return out


class EvidenceRegistry:
    """In-memory append-only evidence store.

    Immutable: re-registering the same content hash returns the existing record
    (idempotent re-ingestion) instead of overwriting it. Conflicts are recorded,
    never resolved by overwriting.
    """

    def __init__(self) -> None:
        self._by_hash: dict[str, Evidence] = {}
        self._order: list[str] = []

    def register(self, evidence: Evidence) -> tuple[Evidence, bool]:
        """Return ``(evidence, created)``. ``created=False`` means idempotent reuse."""
        existing = self._by_hash.get(evidence.hash)
        if existing is not None:
            return existing, False
        self._by_hash[evidence.hash] = evidence
        self._order.append(evidence.evidence_id)
        return evidence, True

    def get(self, evidence_id: str) -> Optional[Evidence]:
        for ev in self._by_hash.values():
            if ev.evidence_id == evidence_id:
                return ev
        return None

    def by_hash(self, value: str) -> Optional[Evidence]:
        return self._by_hash.get(value)

    def all(self) -> list[Evidence]:
        return [self._by_hash[h] for h in self._order]

    def ids(self) -> list[str]:
        return list(self._order)

    def __len__(self) -> int:
        return len(self._order)


# ─────────────────────────────────────────────────────────────────────────────
# Entities + resolution (§13)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Entity:
    kind: EntityKind
    business_id: Optional[UUID] = None
    canonical_name: Optional[str] = None
    normalized_name: Optional[str] = None
    raw_names: tuple[str, ...] = ()
    identifiers: dict[str, str] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    language: Optional[str] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    confidence: float = 0.0
    #: Set when a human corrected a resolution. A correction never rewrites the
    #: source evidence; it adds a decision on top of it.
    correction_note: Optional[str] = None

    @property
    def entity_id(self) -> str:
        """Deterministic identity so reprocessing yields the same id."""
        if self.identifiers:
            for key in sorted(self.identifiers):
                return f"{self.kind.value}:{key}:{normalize_identifier(self.identifiers[key])}"
        return (
            f"{self.kind.value}:name:"
            f"{content_hash(self.business_id, self.kind.value, self.normalized_name or self.canonical_name)[:20]}"
        )


@dataclass(frozen=True)
class EntityResolution:
    """Outcome of resolving one observed reference against canonical entities."""

    entity_resolution_id: str = ""
    query: str = ""
    kind: EntityKind = EntityKind.PRODUCT
    outcome: ResolutionOutcome = ResolutionOutcome.AMBIGUOUS
    match_method: MatchMethod = MatchMethod.UNRESOLVED
    selected_entity: Optional[Entity] = None
    candidates: tuple[Entity, ...] = ()
    confidence: float = 0.0
    evidence_ids: tuple[str, ...] = ()
    origin: DecisionOrigin = DecisionOrigin.DETERMINISTIC
    resolved_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.entity_resolution_id:
            object.__setattr__(
                self,
                "entity_resolution_id",
                f"er-{deterministic_fingerprint(self.kind.value, self.query, self.outcome.value)}",
            )

    @property
    def requires_review(self) -> bool:
        return self.outcome is ResolutionOutcome.AMBIGUOUS


# ─────────────────────────────────────────────────────────────────────────────
# Business events (§22)
# ─────────────────────────────────────────────────────────────────────────────

class BusinessEventType(str, Enum):
    SALE = "sale"
    REFUND = "refund"
    RETURN = "return"
    PURCHASE = "purchase"
    STOCK_RECEIPT = "stock_receipt"
    STOCK_ADJUSTMENT = "stock_adjustment"
    STOCK_TRANSFER = "stock_transfer"
    STOCKOUT = "stockout"
    PRICE_CHANGE = "price_change"
    DISCOUNT = "discount"
    PAYMENT = "payment"
    EXPENSE = "expense"
    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"
    SHIFT = "shift"
    ATTENDANCE = "attendance"
    CAMPAIGN = "campaign"
    CONTRACT_EVENT = "contract_event"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class BusinessEvent:
    """An observation, not an interpretation.

    Events record what a source asserted. Meaning is assigned later by the
    semantic layer; an event never embeds a conclusion.
    """

    event_id: str = ""
    business_id: Optional[UUID] = None
    event_type: BusinessEventType = BusinessEventType.UNKNOWN
    event_time: Optional[datetime] = None
    #: Business-local date derived from ``event_time`` plus the business timezone.
    business_local_date: Optional[date] = None
    timezone: Optional[str] = None

    entity_refs: dict[str, str] = field(default_factory=dict)
    quantity: Measured = field(default_factory=Measured.missing)
    amount: Measured = field(default_factory=Measured.missing)
    unit_price: Measured = field(default_factory=Measured.missing)
    location_ref: Optional[str] = None
    source_type: SourceType = SourceType.FILE
    source_locator: SourceLocator = field(default_factory=SourceLocator)
    evidence_ids: tuple[str, ...] = ()
    confidence: float = 0.0
    state: FieldStatus = FieldStatus.PRESENT
    external_reference: Optional[str] = None
    #: Stable hash used for idempotent ingestion of the same observation.
    row_hash: str = ""

    def __post_init__(self) -> None:
        if not self.row_hash:
            object.__setattr__(
                self,
                "row_hash",
                content_hash(
                    self.business_id,
                    self.event_type.value,
                    self.event_time,
                    self.entity_refs,
                    self.quantity.value,
                    self.amount.value,
                    self.external_reference,
                ),
            )
        if not self.event_id:
            object.__setattr__(self, "event_id", f"ev-{self.row_hash[:24]}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "business_id": str(self.business_id) if self.business_id else None,
            "event_type": self.event_type.value,
            "event_time": self.event_time.isoformat() if self.event_time else None,
            "business_local_date": (
                self.business_local_date.isoformat() if self.business_local_date else None
            ),
            "timezone": self.timezone,
            "entity_refs": dict(self.entity_refs),
            "quantity": self.quantity.to_dict(),
            "amount": self.amount.to_dict(),
            "unit_price": self.unit_price.to_dict(),
            "location_ref": self.location_ref,
            "source_type": self.source_type.value,
            "source_locator": self.source_locator.to_dict(),
            "evidence_ids": list(self.evidence_ids),
            "confidence": self.confidence,
            "state": self.state.value,
            "external_reference": self.external_reference,
            "row_hash": self.row_hash,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Conflicts (§19)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Conflict:
    """Two sources disagreeing about the same entity field.

    Never auto-resolved by picking a side or averaging. Resolution is recorded
    explicitly, with the method that produced it.
    """

    conflict_id: str = ""
    business_id: Optional[UUID] = None
    entity_ref: Optional[str] = None
    field: str = ""
    evidence_a: str = ""
    evidence_b: str = ""
    value_a: Optional[str] = None
    value_b: Optional[str] = None
    relationship: ConflictRelationship = ConflictRelationship.UNKNOWN
    severity: ConflictSeverity = ConflictSeverity.MEDIUM
    #: Periods of the two sides. Differing periods usually mean temporal variation
    #: rather than a true contradiction.
    period_a: Optional[tuple[date, date]] = None
    period_b: Optional[tuple[date, date]] = None
    classification: Optional[str] = None
    classification_origin: DecisionOrigin = DecisionOrigin.DETERMINISTIC
    detected_at: datetime = dc_field(default_factory=_utcnow)
    status: ConflictResolution = ConflictResolution.UNRESOLVED
    resolution_method: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.conflict_id:
            object.__setattr__(
                self,
                "conflict_id",
                f"cf-{deterministic_fingerprint(self.business_id, self.entity_ref, self.field, self.evidence_a, self.evidence_b)}",
            )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in self.__dict__.items():
            if isinstance(v, Enum):
                out[k] = v.value
            elif isinstance(v, (datetime, date, UUID)):
                out[k] = v.isoformat() if v is not None else None
            else:
                out[k] = v
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Data quality (§20)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class QualityDimensionScore:
    dimension: QualityDimension
    #: ``None`` means the dimension could not be evaluated. Never coerced to 0.
    score: Optional[float]
    weight: float = 0.0
    reason: str = ""
    evidence_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.score is not None and not (0.0 <= self.score <= 1.0):
            raise ValueError_(f"{self.dimension.value} score must be within [0,1]")


@dataclass(frozen=True)
class QualityIssue:
    issue_id: str = ""
    kind: QualityIssueKind = QualityIssueKind.SUSPECT
    severity: ConflictSeverity = ConflictSeverity.MEDIUM
    message: str = ""
    entity_ref: Optional[str] = None
    locator: Optional[str] = None
    evidence_ids: tuple[str, ...] = ()
    origin: DecisionOrigin = DecisionOrigin.DETERMINISTIC
    domain: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.issue_id:
            object.__setattr__(
                self, "issue_id", f"qi-{deterministic_fingerprint(self.kind.value, self.message, self.locator)}"
            )


@dataclass(frozen=True)
class DataQualityReport:
    """Multi-dimensional quality assessment.

    ``overall_score`` is never the only output — every dimension, its weight, its
    reason and its limitations are exposed so a number can always be explained.
    """

    report_id: str = ""
    business_id: Optional[UUID] = None
    ingestion_run_id: Optional[UUID] = None
    artifact_ids: tuple[UUID, ...] = ()
    state_version: Optional[str] = None

    overall_score: Optional[float] = None
    dimensions: tuple[QualityDimensionScore, ...] = ()
    issues: tuple[QualityIssue, ...] = ()

    critical_issues: tuple[QualityIssue, ...] = ()
    warnings: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    affected_domains: tuple[str, ...] = ()
    affected_entities: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.report_id:
            object.__setattr__(
                self,
                "report_id",
                f"dq-{deterministic_fingerprint(self.business_id, self.state_version, self.artifact_ids)}",
            )

    @property
    def unevaluated_dimensions(self) -> list[str]:
        return [d.dimension.value for d in self.dimensions if d.score is None]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "business_id": str(self.business_id) if self.business_id else None,
            "ingestion_run_id": str(self.ingestion_run_id) if self.ingestion_run_id else None,
            "artifact_ids": [str(a) for a in self.artifact_ids],
            "state_version": self.state_version,
            "overall_score": self.overall_score,
            "dimensions": [
                {
                    "dimension": d.dimension.value,
                    "score": d.score,
                    "weight": d.weight,
                    "reason": d.reason,
                    "evidence_ids": list(d.evidence_ids),
                    "limitations": list(d.limitations),
                }
                for d in self.dimensions
            ],
            "issues": [
                {
                    "issue_id": i.issue_id,
                    "kind": i.kind.value,
                    "severity": i.severity.value,
                    "message": i.message,
                    "entity_ref": i.entity_ref,
                    "locator": i.locator,
                    "evidence_ids": list(i.evidence_ids),
                    "origin": i.origin.value,
                    "domain": i.domain,
                }
                for i in self.issues
            ],
            "critical_issues": [i.issue_id for i in self.critical_issues],
            "warnings": list(self.warnings),
            "unknowns": list(self.unknowns),
            "affected_domains": list(self.affected_domains),
            "affected_entities": list(self.affected_entities),
            "limitations": list(self.limitations),
            "unevaluated_dimensions": self.unevaluated_dimensions,
            "created_at": self.created_at.isoformat(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Business profile (§17, §18)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DomainCapabilityFlag:
    """What the business *has data for* — not what it does.

    ``observed_capability`` describes the business; ``data_available`` describes
    the evidence. They are stored separately because conflating them produces
    confident nonsense in later phases.
    """

    domain: DomainCapability
    observed_capability: bool = False
    data_available: bool = False
    artifact_count: int = 0
    evidence_count: int = 0
    confidence: float = 0.0
    first_observed_at: Optional[datetime] = None
    last_observed_at: Optional[datetime] = None

    @property
    def has_evidence(self) -> bool:
        return self.evidence_count > 0


@dataclass(frozen=True)
class BusinessProfile:
    business_id: Optional[UUID] = None
    business_type: BusinessType = BusinessType.UNKNOWN
    business_type_confidence: float = 0.0
    business_type_origin: DecisionOrigin = DecisionOrigin.NONE
    observed_business_types: tuple[str, ...] = ()

    operating_channels: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    branches: tuple[str, ...] = ()
    product_count: Optional[int] = None
    service_count: Optional[int] = None
    supplier_count: Optional[int] = None
    employee_count: Optional[int] = None
    currencies: tuple[str, ...] = ()
    countries: tuple[str, ...] = ()
    source_systems: tuple[str, ...] = ()
    capabilities: tuple[DomainCapabilityFlag, ...] = ()
    observed_patterns: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    confidence: float = 0.0
    limitations: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=_utcnow)

    def capability(self, domain: DomainCapability) -> Optional[DomainCapabilityFlag]:
        for flag in self.capabilities:
            if flag.domain is domain:
                return flag
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Freshness (§44) — centralized, never re-implemented per service
# ─────────────────────────────────────────────────────────────────────────────

FRESH_HOURS = 24.0
RECENT_HOURS = 72.0
STALE_HOURS = 24.0 * 30


def evaluate_freshness(
    last_observed_at: Optional[datetime],
    *,
    now: Optional[datetime] = None,
    conflicted: bool = False,
    fresh_hours: float = FRESH_HOURS,
    recent_hours: float = RECENT_HOURS,
    stale_hours: float = STALE_HOURS,
) -> FreshnessState:
    """Single source of truth for freshness. Stale data is never reported as fresh."""
    if conflicted:
        return FreshnessState.CONFLICT
    if last_observed_at is None:
        return FreshnessState.MISSING
    reference = now or _utcnow()
    observed = last_observed_at
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    age_hours = (reference - observed).total_seconds() / 3600.0
    if age_hours <= fresh_hours:
        return FreshnessState.FRESH
    if age_hours <= recent_hours:
        return FreshnessState.RECENT
    if age_hours <= stale_hours:
        return FreshnessState.STALE
    return FreshnessState.STALE


@dataclass(frozen=True)
class DomainFreshness:
    domain: str
    freshness: FreshnessState = FreshnessState.UNKNOWN
    last_observed_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None
    source_age_hours: Optional[float] = None
    reason: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Canonical state + version (§23, §27)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CanonicalBusinessState:
    """The single authoritative statement of observed business reality."""

    business_id: Optional[UUID] = None
    state_version: str = ""
    previous_state_version: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)

    business_type: BusinessType = BusinessType.UNKNOWN
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    timezone: Optional[str] = None

    entities: tuple[Entity, ...] = ()
    events: tuple[BusinessEvent, ...] = ()
    conflicts: tuple[Conflict, ...] = ()
    relationships: tuple[dict[str, Any], ...] = ()

    #: Domain aggregates. Empty collections mean "genuinely none observed";
    #: absent evidence is recorded in ``evidence_coverage`` and ``limitations``.
    financial_state: dict[str, Measured] = field(default_factory=dict)
    inventory_state: dict[str, Measured] = field(default_factory=dict)
    procurement_state: dict[str, Measured] = field(default_factory=dict)
    workforce_state: dict[str, Measured] = field(default_factory=dict)
    marketing_state: dict[str, Measured] = field(default_factory=dict)
    customer_state: dict[str, Measured] = field(default_factory=dict)

    evidence_coverage: dict[str, str] = field(default_factory=dict)
    freshness: tuple[DomainFreshness, ...] = ()
    capabilities: tuple[DomainCapabilityFlag, ...] = ()

    artifact_ids: tuple[UUID, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    ingestion_run_ids: tuple[UUID, ...] = ()
    source_systems: tuple[str, ...] = ()
    historical_coverage: dict[str, Any] = field(default_factory=dict)

    #: Explicit, user-visible limitations. Never empty-by-default.
    limitations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def evidence_for_domain(self, domain: str) -> int:
        return sum(
            1 for f in self.freshness if f.domain == domain and f.freshness is not FreshnessState.MISSING
        )

    def to_dict(self) -> dict[str, Any]:
        def _m(mapping: Mapping[str, Measured]) -> dict[str, Any]:
            return {k: v.to_dict() for k, v in mapping.items()}

        return {
            "business_id": str(self.business_id) if self.business_id else None,
            "state_version": self.state_version,
            "previous_state_version": self.previous_state_version,
            "created_at": self.created_at.isoformat(),
            "business_type": self.business_type.value,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "timezone": self.timezone,
            "entity_count": len(self.entities),
            "event_count": len(self.events),
            "conflict_count": len(self.conflicts),
            "financial_state": _m(self.financial_state),
            "inventory_state": _m(self.inventory_state),
            "procurement_state": _m(self.procurement_state),
            "workforce_state": _m(self.workforce_state),
            "marketing_state": _m(self.marketing_state),
            "customer_state": _m(self.customer_state),
            "evidence_coverage": dict(self.evidence_coverage),
            "freshness": [
                {
                    "domain": f.domain,
                    "freshness": f.freshness.value,
                    "last_observed_at": f.last_observed_at.isoformat() if f.last_observed_at else None,
                    "source_age_hours": f.source_age_hours,
                    "reason": f.reason,
                }
                for f in self.freshness
            ],
            "capabilities": [
                {
                    "domain": c.domain.value,
                    "observed_capability": c.observed_capability,
                    "data_available": c.data_available,
                    "evidence_count": c.evidence_count,
                    "confidence": c.confidence,
                }
                for c in self.capabilities
            ],
            "artifact_ids": [str(a) for a in self.artifact_ids],
            "evidence_ids": list(self.evidence_ids),
            "ingestion_run_ids": [str(r) for r in self.ingestion_run_ids],
            "source_systems": list(self.source_systems),
            "historical_coverage": dict(self.historical_coverage),
            "limitations": list(self.limitations),
            "warnings": list(self.warnings),
            "contract_version": PHASE_1_CONTRACT_VERSION,
        }


def compute_state_version(
    business_id: Optional[UUID],
    artifact_content_hashes: Iterable[str],
    entity_ids: Iterable[str],
    event_row_hashes: Iterable[str],
) -> str:
    """Deterministic state version.

    Derived from content, not time, so re-ingesting the same artifacts produces
    the *same* version. This is what makes reprocessing idempotent (§27, §28).
    """
    digest = content_hash(
        business_id,
        sorted(set(artifact_content_hashes)),
        len(set(entity_ids)),
        content_hash(*sorted(set(event_row_hashes))),
    )
    return f"sv-{digest[:32]}"


# ─────────────────────────────────────────────────────────────────────────────
# Ingestion run (§52)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IngestionRun:
    """Operational traceability for one ingestion operation."""

    run_id: UUID = field(default_factory=uuid4)
    business_id: Optional[UUID] = None
    artifact_ids: list[UUID] = field(default_factory=list)
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: Optional[datetime] = None
    status: IngestionStatus = IngestionStatus.RECEIVED

    records_seen: int = 0
    records_accepted: int = 0
    records_rejected: int = 0
    records_ambiguous: int = 0
    conflicts_detected: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    state_version_before: Optional[str] = None
    state_version_after: Optional[str] = None

    def record_error(self, error: IngestionError) -> None:
        self.errors.append(error.to_dict())
        self.warnings.append(f"{error.category.value}: {error.message}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "business_id": str(self.business_id) if self.business_id else None,
            "artifact_ids": [str(a) for a in self.artifact_ids],
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status.value,
            "records_seen": self.records_seen,
            "records_accepted": self.records_accepted,
            "records_rejected": self.records_rejected,
            "records_ambiguous": self.records_ambiguous,
            "conflicts_detected": self.conflicts_detected,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "state_version_before": self.state_version_before,
            "state_version_after": self.state_version_after,
        }


# ─────────────────────────────────────────────────────────────────────────────
# BusinessContext (§26) — what Phase 2 receives
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BusinessContext:
    """Canonical, fully-populated business context.

    Empty collections are used only when genuinely empty. Unavailable data is
    represented by ``limitations`` plus explicit statuses, never by pretending
    absence means zero.
    """

    business_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    state_version: str = ""
    previous_state_version: Optional[str] = None
    snapshot_timestamp: datetime = field(default_factory=_utcnow)

    business_profile: Optional[BusinessProfile] = None
    freshness: tuple[DomainFreshness, ...] = ()
    data_quality: Optional[DataQualityReport] = None

    entities: tuple[Entity, ...] = ()
    events: tuple[BusinessEvent, ...] = ()
    relationships: tuple[dict[str, Any], ...] = ()
    conflicts: tuple[Conflict, ...] = ()

    financial_state: dict[str, Measured] = field(default_factory=dict)
    inventory_state: dict[str, Measured] = field(default_factory=dict)
    procurement_state: dict[str, Measured] = field(default_factory=dict)
    workforce_state: dict[str, Measured] = field(default_factory=dict)
    marketing_state: dict[str, Measured] = field(default_factory=dict)
    customer_state: dict[str, Measured] = field(default_factory=dict)
    external_context: dict[str, Any] = field(default_factory=dict)

    capabilities: tuple[DomainCapabilityFlag, ...] = ()
    active_constraints: dict[str, Any] = field(default_factory=dict)
    active_goals: dict[str, Any] = field(default_factory=dict)
    open_recommendations: tuple[Any, ...] = ()
    previous_outcomes: tuple[Any, ...] = ()

    evidence_ids: tuple[str, ...] = ()
    source_artifacts: tuple[UUID, ...] = ()
    ingestion_run_ids: tuple[UUID, ...] = ()
    historical_coverage: dict[str, Any] = field(default_factory=dict)
    evidence_coverage: dict[str, str] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()

    contract_version: str = PHASE_1_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "business_id": str(self.business_id) if self.business_id else None,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "state_version": self.state_version,
            "previous_state_version": self.previous_state_version,
            "snapshot_timestamp": self.snapshot_timestamp.isoformat(),
            "business_profile": (
                {
                    "business_type": self.business_profile.business_type.value,
                    "business_type_confidence": self.business_profile.business_type_confidence,
                    "business_type_origin": self.business_profile.business_type_origin.value,
                    "currencies": list(self.business_profile.currencies),
                    "source_systems": list(self.business_profile.source_systems),
                    "capabilities": [
                        {
                            "domain": c.domain.value,
                            "observed_capability": c.observed_capability,
                            "data_available": c.data_available,
                            "evidence_count": c.evidence_count,
                            "confidence": c.confidence,
                        }
                        for c in self.capabilities
                    ],
                }
                if self.business_profile
                else None
            ),
            "freshness": [
                {
                    "domain": f.domain,
                    "freshness": f.freshness.value,
                    "last_observed_at": f.last_observed_at.isoformat() if f.last_observed_at else None,
                    "source_age_hours": f.source_age_hours,
                    "reason": f.reason,
                }
                for f in self.freshness
            ],
            "data_quality": self.data_quality.to_dict() if self.data_quality else None,
            "entity_count": len(self.entities),
            "event_count": len(self.events),
            "conflict_count": len(self.conflicts),
            "entities": [
                {
                    "entity_id": e.entity_id,
                    "kind": e.kind.value,
                    "canonical_name": e.canonical_name,
                    "normalized_name": e.normalized_name,
                    "raw_names": list(e.raw_names),
                    "aliases": list(e.aliases),
                    "identifiers": dict(e.identifiers),
                    "confidence": e.confidence,
                }
                for e in self.entities
            ],
            "events": [e.to_dict() for e in self.events],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "financial_state": {k: v.to_dict() for k, v in self.financial_state.items()},
            "inventory_state": {k: v.to_dict() for k, v in self.inventory_state.items()},
            "procurement_state": {k: v.to_dict() for k, v in self.procurement_state.items()},
            "workforce_state": {k: v.to_dict() for k, v in self.workforce_state.items()},
            "marketing_state": {k: v.to_dict() for k, v in self.marketing_state.items()},
            "customer_state": {k: v.to_dict() for k, v in self.customer_state.items()},
            "external_context": dict(self.external_context),
            "capabilities": [
                {
                    "domain": c.domain.value,
                    "observed_capability": c.observed_capability,
                    "data_available": c.data_available,
                }
                for c in self.capabilities
            ],
            "evidence_ids": list(self.evidence_ids),
            "source_artifacts": [str(a) for a in self.source_artifacts],
            "ingestion_run_ids": [str(r) for r in self.ingestion_run_ids],
            "historical_coverage": dict(self.historical_coverage),
            "evidence_coverage": dict(self.evidence_coverage),
            "limitations": list(self.limitations),
            "contract_version": self.contract_version,
        }