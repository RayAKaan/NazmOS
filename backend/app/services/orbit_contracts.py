"""Orbit Audit Contracts — standardized, versioned, privacy-safe output types.

This module defines the canonical output contracts for the Orbit audit layer.
All three audit paths (guest single-file, guest two-file, authenticated)
MUST produce outputs conforming to these types.

Versioning: bump ORBIT_AUDIT_VERSION on any structural change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

D = Decimal
ZERO = D("0")


ORBIT_AUDIT_VERSION = "v1"


@dataclass(frozen=True)
class MetricValue:
    """A single financial metric with full provenance."""
    value: float
    currency: str = "SAR"
    basis: str = ""  # e.g., "stock * cost", "velocity * lead_time * sell"
    period: str = ""  # e.g., "2024-01-01..2024-01-30"
    confidence: str = "MEDIUM"  # HIGH / MEDIUM / LOW / UNKNOWN
    evidence_ids: list[str] = field(default_factory=list)  # links to audit_evidence


@dataclass(frozen=True)
class ExposureBreakdown:
    """Money-at-risk redesign: explicit, separated exposures."""
    capital_exposed_sar: MetricValue
    revenue_at_risk_sar: MetricValue
    gross_profit_at_risk_sar: MetricValue
    recoverable_range_sar: dict[str, MetricValue]  # {"low": ..., "high": ...}


@dataclass(frozen=True)
class DomainScore:
    """Per-domain health contribution."""
    score: int  # 0-100
    confidence: str
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HealthBreakdown:
    sales: DomainScore
    inventory: DomainScore
    margins: DomainScore
    procurement: DomainScore
    data_quality: DomainScore


@dataclass(frozen=True)
class FindingEvidence:
    """Evidence-first finding structure."""
    what: str
    why: str
    financial_impact: MetricValue
    confidence: str  # HIGH / MEDIUM / LOW
    period: str
    evidence_ids: list[str]
    recommended_next_step: str
    missing_data: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OpportunityCard:
    """Top 3 opportunities with full context."""
    rank: int
    title: str
    exposure_sar: MetricValue
    unit_count: int
    recoverable_range_sar: dict[str, MetricValue]  # {"low": ..., "high": ...}
    confidence: str


@dataclass(frozen=True)
class DataLimitations:
    """Explicit data limitations per §41."""
    we_know: list[str]
    we_estimate: list[str]
    we_dont_know: list[str]
    upload_next: list[str]


@dataclass(frozen=True)
class OrbitAuditResult:
    """Canonical Orbit audit output — single source of truth for all paths."""
    version: str = ORBIT_AUDIT_VERSION
    audit_id: str = ""
    business_id: str | None = None
    business_type: str = "retail"
    period: dict[str, str] = field(default_factory=dict)  # {"start": "...", "end": "..."}
    health_score: int = 0
    health_breakdown: HealthBreakdown | None = None
    exposures: ExposureBreakdown | None = None
    metrics: dict[str, MetricValue] = field(default_factory=dict)
    findings: list[FindingEvidence] = field(default_factory=list)
    opportunities: list[OpportunityCard] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)  # evidence_id -> {type, source_ref, calculation}
    limitations: DataLimitations | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)  # ingestion manifests
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_api_response(self) -> dict[str, Any]:
        """Privacy-safe serialization for API responses."""
        def _serialize(obj: Any) -> Any:
            if isinstance(obj, (str, int, float, bool)) or obj is None:
                return obj
            if isinstance(obj, Decimal):
                return float(obj)
            if isinstance(obj, (list, tuple)):
                return [_serialize(i) for i in obj]
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            if hasattr(obj, "__dataclass_fields__"):
                return {k: _serialize(v) for k, v in obj.__dict__.items()}
            return str(obj)
        return _serialize(self)


# --- Type aliases for internal use ---
EvidenceId = str
FindingId = str


@dataclass
class BusinessSnapshot:
    """Canonical intermediate representation between ingestion and audit.

    This is the SINGLE intermediate form that all three audit paths
    (guest single-file, guest two-file, authenticated) must produce
    before calling the canonical audit engine.
    """
    business_id: str | None = None
    business_type: str = "retail"
    period_start: datetime | None = None
    period_end: datetime | None = None
    branches: list[dict[str, Any]] = field(default_factory=list)
    products: list[dict[str, Any]] = field(default_factory=list)
    sales: list[dict[str, Any]] = field(default_factory=list)
    inventory: list[dict[str, Any]] = field(default_factory=list)
    purchases: list[dict[str, Any]] = field(default_factory=list)
    suppliers: list[dict[str, Any]] = field(default_factory=list)
    expenses: list[dict[str, Any]] = field(default_factory=list)
    data_quality: dict[str, Any] = field(default_factory=dict)
    evidence_ids: dict[str, str] = field(default_factory=dict)  # product_name -> evidence_id
    ingestion_manifests: list[dict[str, Any]] = field(default_factory=list)

    def to_product_metrics_list(self) -> list[dict[str, Any]]:
        """Convert to list of ProductMetrics-compatible dicts for audit_core.analyze_product."""
        out: list[dict[str, Any]] = []
        for p in self.products:
            # Merge sales + inventory + purchases data for this product
            sales_data = next((s for s in self.sales if s.get("product_name") == p.get("name")), {})
            inv_data = next((i for i in self.inventory if i.get("product_name") == p.get("name")), {})
            purch_data = next((p_ for p_ in self.purchases if p_.get("product_name") == p.get("name")), {})

            out.append({
                "name": p.get("name", ""),
                "stock": p.get("stock", sales_data.get("stock", inv_data.get("stock", 0))),
                "cost": p.get("cost", purch_data.get("cost", 0)),
                "sell": p.get("sell", sales_data.get("sell", inv_data.get("sell", 0))),
                "recent_qty_30": sales_data.get("qty_30d", 0),
                "prior_qty_30": sales_data.get("prior_qty_30", 0),
                "last_sold_days": sales_data.get("last_sold_days"),
                "inventory_age_days": inv_data.get("age_days"),
                "monthly_concentrations": sales_data.get("monthly_concentrations"),
                "calibration_discount_rates": inv_data.get("calibration_discount_rates"),
                "projected_stock": p.get("projected_stock"),
                "lead_time_days": purch_data.get("lead_time"),
                "safety_stock": inv_data.get("safety_stock"),
                "recent_coverage_days": sales_data.get("coverage_days"),
            })
        return out