"""Canonical semantic vocabulary and result types for universal data ingestion.

The ingestion layer maps *flexible* merchant column names onto a *strict*,
deterministic internal vocabulary. The audit engine consumes only canonical
fields; every nuance of "the user called it Retail / RSP / سعر البيع" is the
responsibility of ingestion.

This module defines:

- the canonical role vocabulary (identity / sales / inventory / cost / purchasing
  / financial) grouped into logical domains,
- the centralized, testable confidence thresholds,
- the structured result/diagnostic types returned to the API and frontend,
- the ingestion engine version string.

Deterministic, no AI. Financial arithmetic elsewhere stays in ``Decimal``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Version of the semantic ingestion engine. Bump on any change that alters how
# source columns map to canonical roles, so outputs/provenance stay traceable.
INGESTION_ENGINE_VERSION = "v2"

# Audits that the guest flow can produce. A single file may combine multiple
# semantic domains (e.g. sales fields AND inventory fields).
SALES_DOMAIN = "sales"
INVENTORY_DOMAIN = "inventory"
PURCHASING_DOMAIN = "purchasing"
FINANCIAL_DOMAIN = "financial"
IDENTITY_DOMAIN = "identity"

# Canonical roles grouped by domain. ``DERIVED_*`` roles are never inferred from
# a source column; they are computed downstream from valid source fields.
ROLES: dict[str, tuple[str, ...]] = {
    IDENTITY_DOMAIN: ("product_name", "sku", "barcode", "category", "subcategory", "brand"),
    SALES_DOMAIN: ("date", "transaction_id", "quantity", "unit_price", "revenue", "discount", "customer_id", "branch", "warehouse"),
    INVENTORY_DOMAIN: ("stock", "opening_stock", "closing_stock", "available_stock", "reserved_stock", "inbound_stock", "damaged_stock"),
    "cost": ("cost", "unit_cost", "cogs"),
    PURCHASING_DOMAIN: ("purchase_quantity", "purchase_price", "supplier", "purchase_order", "lead_time"),
    FINANCIAL_DOMAIN: ("revenue", "gross_profit", "gross_margin", "expense", "tax", "discount", "total_amount"),
}

ALL_CANONICAL_ROLES: frozenset[str] = frozenset(
    role for roles in ROLES.values() for role in roles if not role.startswith("derived_")
)

# Confidence thresholds. Centralized so they can be tested in one place.
CONFIDENCE_HIGH = 0.90
CONFIDENCE_MEDIUM = 0.75
# Minimum margin between the top candidate and the runner-up required to treat a
# role as confidently resolved (role competition, Phase 7 / 32).
MIN_CONFIDENCE_MARGIN = 0.15


def role_band(confidence: float) -> str:
    """Return the confidence band label for a score (HIGH / MEDIUM / LOW)."""
    if confidence >= CONFIDENCE_HIGH:
        return "HIGH"
    if confidence >= CONFIDENCE_MEDIUM:
        return "MEDIUM"
    return "LOW"


# -------- Required fields per audit shape (Phase 2) --------
#
# Two-file guest audit minimums (Phase 19):
#   Sales:     product identifier + quantity (+ date or usable temporal info)
#   Inventory: product identifier + stock (+ cost or usable valuation basis)
# Single-file flows derive their own requirements from the detected domain.
REQUIRED_SALES_FIELDS: tuple[str, ...] = ("product_name", "quantity")
REQUIRED_INVENTORY_FIELDS: tuple[str, ...] = ("product_name", "stock")

# Roles whose absence must NOT silently exercise the zero-substitution path in
# the guest audit when they are genuinely required but uninterpreted.
FINANCIAL_SENSITIVE_ROLES: frozenset[str] = frozenset({"stock", "cost", "unit_price", "revenue", "quantity"})


# -------- Result / diagnostic types (Phases 12, 24, 40, 41) --------
INGESTION_STATUS_READY = "ready"
INGESTION_STATUS_NEEDS_REVIEW = "needs_review"
INGESTION_STATUS_INSUFFICIENT_DATA = "insufficient_data"
INGESTION_STATUS_INVALID_FILE = "invalid_file"
INGESTION_STATUS_UNSUPPORTED_FILE = "unsupported_file"
INGESTION_STATUS_PROCESSING_ERROR = "processing_error"

INGESTION_STATUSES = frozenset({
    INGESTION_STATUS_READY,
    INGESTION_STATUS_NEEDS_REVIEW,
    INGESTION_STATUS_INSUFFICIENT_DATA,
    INGESTION_STATUS_INVALID_FILE,
    INGESTION_STATUS_UNSUPPORTED_FILE,
    INGESTION_STATUS_PROCESSING_ERROR,
})

# Machine-readable error/diagnostic codes the frontend can branch on (Phase 41).
ERROR_CODE_UNSUPPORTED_FORMAT = "unsupported_format"
ERROR_CODE_EMPTY_FILE = "empty_file"
ERROR_CODE_MISSING_REQUIRED_FIELD = "missing_required_field"
ERROR_CODE_AMBIGUOUS_FIELD = "ambiguous_field"
ERROR_CODE_AMBIGUOUS_DATE_FORMAT = "ambiguous_date_format"
ERROR_CODE_AMBIGUOUS_NUMERIC_FORMAT = "ambiguous_numeric_format"
ERROR_CODE_INSUFFICIENT_MATCHING = "insufficient_matching_products"
ERROR_CODE_SERVER_FAILURE = "server_failure"

# Evidence categories used in observability (Phase 33). These are safe labels --
# never raw cell contents.
EVIDENCE_HEADER_MATCH = "header_match"
EVIDENCE_NUMERIC_SHAPE = "numeric_shape"
EVIDENCE_CURRENCY_SIGNAL = "currency_signal"
EVIDENCE_DATE_SIGNAL = "date_signal"
EVIDENCE_IDENTIFIER_SIGNAL = "identifier_signal"
EVIDENCE_RELATIONSHIP_SIGNAL = "relationship_signal"
EVIDENCE_LANGUAGE_SIGNAL = "language_signal"
EVIDENCE_VALUE_DISTRIBUTION = "value_distribution"


# The canonical output of ingestion. Contains enough structure for the frontend
# to render "We understood your file" or "We need one quick confirmation"
# without making the frontend do semantic inference.
@dataclass
class ColumnMapping:
    source_column: str
    role: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    alternatives: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class IngestionResult:
    status: str = INGESTION_STATUS_READY
    confidence: float = 0.0
    version: str = INGESTION_ENGINE_VERSION
    mappings: list[ColumnMapping] = field(default_factory=list)
    missing_required_fields: list[str] = field(default_factory=list)
    ambiguous_fields: list[str] = field(default_factory=list)
    file_classification: list[str] = field(default_factory=list)
    human_message: str | None = None
    error_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def role_map(self) -> dict[str, str]:
        """Return {role: source_column} for confidently mapped roles."""
        return {m.role: m.source_column for m in self.mappings}

    def column_map(self) -> dict[str, str]:
        """Return {source_column: role} for confidently mapped roles."""
        return {m.source_column: m.role for m in self.mappings}

    def as_dict(self) -> dict[str, Any]:
        """Privacy-safe serialization for the API/telemetry (no raw values)."""
        return {
            "status": self.status,
            "confidence": round(self.confidence, 3),
            "version": self.version,
            "mapping": [
                {
                    "source_column": m.source_column,
                    "role": m.role,
                    "confidence": round(m.confidence, 3),
                    "evidence": list(m.evidence),
                    "alternatives": [
                        {"role": a["role"], "confidence": round(a["confidence"], 3)}
                        for a in m.alternatives
                    ],
                }
                for m in self.mappings
            ],
            "missing_required_fields": list(self.missing_required_fields),
            "ambiguous_fields": list(self.ambiguous_fields),
            "file_classification": list(self.file_classification),
            "error_code": self.error_code,
        }
