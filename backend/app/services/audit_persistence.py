"""Orbit Audit Persistence Service — stores and retrieves audit snapshots with full history."""
from __future__ import annotations

from dataclasses import is_dataclass
from datetime import date, datetime
import json
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orbit_contracts import OrbitAuditResult, BusinessSnapshot
from app.services.orbit_financial_xray import run_orbit_financial_xray


class AuditPersistenceService:
    """Service for persisting and retrieving Orbit audit runs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _to_date(value: Any) -> date | None:
        """Coerce a period boundary to a date.

        ``OrbitAuditResult.period`` uses the empty string to mean "unknown", so
        blank and unparseable values must become NULL rather than reach the
        DATE columns.
        """
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    @staticmethod
    def _jsonable(value: Any) -> Any:
        """Recursively convert dataclasses/containers into JSON-safe values.

        ``.__dict__`` is a shallow copy, so nested contract dataclasses
        (DomainScore, MetricValue, FindingEvidence, ...) would otherwise reach
        the JSON columns unserialized.
        """
        if is_dataclass(value) and not isinstance(value, type):
            return {
                k: AuditPersistenceService._jsonable(v)
                for k, v in vars(value).items()
            }
        if isinstance(value, dict):
            return {k: AuditPersistenceService._jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [AuditPersistenceService._jsonable(v) for v in value]
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, UUID):
            return str(value)
        return value

    @classmethod
    def _dumps(cls, value: Any, empty: Any = None) -> str:
        """JSON-encode a value for a jsonb bind parameter."""
        safe = cls._jsonable(value)
        if safe is None or safe == {} or safe == []:
            safe = empty if empty is not None else {}
        return json.dumps(safe, default=str)

    async def _ensure_ingestion_run(
        self,
        orbit_result: OrbitAuditResult,
        business_id: UUID | str | None,
    ) -> UUID:
        """Return the ingestion run this audit belongs to, creating one if needed.

        ``orbit_audit_runs.run_id`` is NOT NULL, so an audit can never be
        persisted without a parent ingestion run.
        """
        run_id = uuid4()
        await self.db.execute(
            text("""
                INSERT INTO orbit_ingestion_runs (
                    id, business_id, status, business_type,
                    created_at, completed_at
                ) VALUES (
                    :id, :business_id, 'completed', :business_type,
                    :created_at, :completed_at
                )
            """),
            {
                "id": run_id,
                "business_id": business_id,
                "business_type": orbit_result.business_type,
                "created_at": datetime.utcnow(),
                "completed_at": datetime.utcnow(),
            },
        )
        return run_id

    async def save_audit_run(
        self,
        orbit_result: OrbitAuditResult,
        ingestion_run_id: UUID | None = None,
        business_id: UUID | str | None = None,
    ) -> UUID:
        """Persist a complete Orbit audit result to the database."""
        audit_id = orbit_result.audit_id if isinstance(orbit_result.audit_id, UUID) else uuid4()

        if ingestion_run_id is None:
            ingestion_run_id = await self._ensure_ingestion_run(orbit_result, business_id)

        # Insert audit run
        await self.db.execute(
            text("""
                INSERT INTO orbit_audit_runs (
                    id, run_id, business_id, business_type,
                    period_start, period_end,
                    health_score, health_breakdown, exposures,
                    findings, opportunities, evidence, limitations, sources,
                    created_at
                ) VALUES (
                    :id, :run_id, :business_id, :business_type,
                    :period_start, :period_end,
                    :health_score,
                    CAST(:health_breakdown AS jsonb), CAST(:exposures AS jsonb),
                    CAST(:findings AS jsonb), CAST(:opportunities AS jsonb),
                    CAST(:evidence AS jsonb), CAST(:limitations AS jsonb),
                    CAST(:sources AS jsonb),
                    :created_at
                )
            """),
            {
                "id": orbit_result.audit_id,
                "run_id": ingestion_run_id,
                "business_id": business_id,
                "business_type": orbit_result.business_type,
                "period_start": self._to_date(
                    orbit_result.period.get("start") if orbit_result.period else None
                ),
                "period_end": self._to_date(
                    orbit_result.period.get("end") if orbit_result.period else None
                ),
                "health_score": orbit_result.health_score,
                "health_breakdown": self._dumps(orbit_result.health_breakdown),
                "exposures": self._dumps(orbit_result.exposures),
                "findings": self._dumps(orbit_result.findings, empty=[]),
                "opportunities": self._dumps(orbit_result.opportunities, empty=[]),
                "evidence": self._dumps(orbit_result.evidence, empty={}),
                "limitations": self._dumps(orbit_result.limitations),
                "sources": self._dumps(orbit_result.sources, empty=[]),
                "created_at": datetime.utcnow(),
            }
        )

        # Insert evidence records
        if orbit_result.evidence:
            for evidence_id, evidence_data in orbit_result.evidence.items():
                await self.db.execute(
                    text("""
                        INSERT INTO orbit_evidence (
                            id, audit_id, finding_id, metric_name,
                            evidence_type, source_ref, calculation, created_at
                        ) VALUES (
                            :id, :audit_id, :finding_id, :metric_name,
                            :evidence_type,
                            CAST(:source_ref AS jsonb), CAST(:calculation AS jsonb),
                            :created_at
                        )
                    """),
                    {
                        "id": uuid4(),
                        "audit_id": orbit_result.audit_id,
                        "finding_id": str(evidence_data.get("finding_id") or "")[:255],
                        "metric_name": str(evidence_data.get("metric_name") or "")[:255],
                        "evidence_type": evidence_data.get("source_type", "calculation"),
                        "source_ref": self._dumps(evidence_data.get("source_ref"), empty={}),
                        "calculation": self._dumps(evidence_data.get("calculation"), empty={}),
                        "created_at": datetime.utcnow(),
                    }
                )

        await self.db.commit()
        return orbit_result.audit_id

    async def get_audit_run(self, audit_id: UUID) -> OrbitAuditResult | None:
        """Retrieve a single audit run by ID."""
        result = await self.db.execute(
            text("SELECT * FROM orbit_audit_runs WHERE id = :id"),
            {"id": audit_id}
        )
        row = result.mappings().first()
        if not row:
            return None
        return self._row_to_orbit_result(row)

    async def get_latest_audit_for_business(
        self,
        business_id: UUID | str,
    ) -> OrbitAuditResult | None:
        """Return the most recent persisted Orbit audit for a business.

        This is the canonical entry point for downstream consumers (notably the
        Intelligence layer): Orbit owns the reading of its own tables, so
        Intelligence never re-implements this query. Returns ``None`` when the
        business has no persisted audit yet, which callers MUST surface as a
        missing-data condition rather than fabricating a zero-valued state.
        """
        result = await self.db.execute(
            text("""
                SELECT id FROM orbit_audit_runs
                WHERE business_id = :business_id
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"business_id": business_id},
        )
        row = result.mappings().first()
        if not row:
            return None
        return await self.get_audit_run(row["id"])

    async def get_audit_history(
        self,
        business_id: UUID | str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get audit history with health trend for a business."""
        query = """
            SELECT id, business_id, business_type, period_start, period_end,
                   health_score, health_breakdown, created_at
            FROM orbit_audit_runs
        """
        params = {"limit": limit, "offset": offset}
        if business_id:
            query += " WHERE business_id = :business_id"
            params["business_id"] = business_id
        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

        result = await self.db.execute(text(query), params)
        return [dict(row) for row in result.mappings().all()]

    async def get_audit_comparison(
        self,
        current_audit_id: UUID,
        previous_audit_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Compare current audit with previous (or auto-find previous)."""
        current = await self.get_audit_run(current_audit_id)
        if not current:
            return {"error": "Current audit not found"}

        if previous_audit_id:
            previous = await self.get_audit_run(previous_audit_id)
        else:
            # Auto-find most recent previous audit for same business
            if current.business_id:
                result = await self.db.execute(
                    text("""
                        SELECT id FROM orbit_audit_runs
                        WHERE business_id = :business_id
                        AND created_at < :created_at
                        ORDER BY created_at DESC LIMIT 1
                    """),
                    {"business_id": current.business_id, "created_at": current.generated_at}
                )
                prev_row = result.mappings().first()
                if prev_row:
                    previous = await self.get_audit_run(prev_row["id"])
                else:
                    previous = None
            else:
                previous = None

        if not previous:
            return {
                "current": self._audit_to_comparison_dict(current),
                "previous": None,
                "delta": None,
                "message": "No previous audit found for comparison"
            }

        return {
            "current": self._audit_to_comparison_dict(current),
            "previous": self._audit_to_comparison_dict(previous),
            "delta": self._compute_delta(current, previous),
        }

    async def get_finding_drilldown(
        self,
        audit_id: UUID,
        finding_id: str,
    ) -> dict[str, Any] | None:
        """Drill down from finding → products → evidence → source rows."""
        audit = await self.get_audit_run(audit_id)
        if not audit:
            return None

        # Find the finding
        finding = next((f for f in audit.findings if f.get("evidence_ids", []) and f.get("evidence_ids")[0] == finding_id), None)
        if not finding:
            # Try direct match on evidence_ids
            for f in audit.findings:
                if finding_id in f.get("evidence_ids", []):
                    break
            else:
                return None

        # Get evidence records for this finding
        evidence_ids = finding.get("evidence_ids", [])
        evidence_records = await self.db.execute(
            text("SELECT * FROM orbit_evidence WHERE audit_id = :audit_id AND finding_id = :finding_id"),
            {"audit_id": audit.audit_id, "finding_id": finding_id}
        )

        # Build drill-down structure
        return {
            "finding": finding,
            "products": self._get_products_for_finding(audit, finding),
            "evidence": [dict(r) for r in evidence_records.mappings().all()],
            "source_rows": await self._get_source_rows_for_finding(audit, finding),
        }

    async def get_data_quality_history(
        self,
        business_id: UUID | str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get data quality score trend over time."""
        query = """
            SELECT dq.run_id, dq.overall_score, dq.domain_scores, dq.created_at,
                   ar.business_id, ar.period_start, ar.period_end
            FROM orbit_data_quality dq
            JOIN orbit_audit_runs ar ON ar.run_id = dq.run_id
        """
        params = {"limit": limit}
        if business_id:
            query += " WHERE ar.business_id = :business_id"
            params["business_id"] = business_id
        query += " ORDER BY dq.created_at DESC LIMIT :limit"

        result = await self.db.execute(text(query), params)
        return [dict(r) for r in result.mappings().all()]

    # =========================================================================
    # Private Helpers
    # =========================================================================

    def _row_to_orbit_result(self, row) -> OrbitAuditResult:
        """Convert database row to OrbitAuditResult."""
        from app.services.orbit_contracts import (
            OrbitAuditResult, MetricValue, ExposureBreakdown,
            HealthBreakdown, DomainScore, FindingEvidence,
            OpportunityCard, DataLimitations
        )
        # Simplified reconstruction - in practice would need full deserialization
        return OrbitAuditResult(
            version=row.get("version", "v1"),
            audit_id=row["id"],
            business_id=row.get("business_id"),
            business_type=row.get("business_type", "retail"),
            period={"start": str(row.get("period_start", "")), "end": str(row.get("period_end", ""))},
            health_score=row.get("health_score", 0),
            health_breakdown=row.get("health_breakdown", {}),
            exposures=row.get("exposures", {}),
            findings=row.get("findings", []),
            opportunities=row.get("opportunities", []),
            evidence=row.get("evidence", {}),
            limitations=row.get("limitations", {}),
            sources=row.get("sources", []),
            generated_at=row.get("created_at", datetime.utcnow()).isoformat() if isinstance(row.get("created_at"), datetime) else str(row.get("created_at", "")),
        )

    def _audit_to_comparison_dict(self, audit: OrbitAuditResult) -> dict[str, Any]:
        """Convert audit to simplified dict for comparison."""
        return {
            "audit_id": str(audit.audit_id),
            "health_score": audit.health_score,
            "health_breakdown": audit.health_breakdown.__dict__ if audit.health_breakdown else {},
            "exposures": {
                "capital_exposed_sar": audit.exposures.capital_exposed_sar.value if audit.exposures else 0,
                "revenue_at_risk_sar": audit.exposures.revenue_at_risk_sar.value if audit.exposures else 0,
                "gross_profit_at_risk_sar": audit.exposures.gross_profit_at_risk_sar.value if audit.exposures else 0,
                "recoverable_range_sar": {
                    "low": audit.exposures.recoverable_range_sar["low"].value if audit.exposures else 0,
                    "high": audit.exposures.recoverable_range_sar["high"].value if audit.exposures else 0,
                }
            } if audit.exposures else {},
            "findings_count": len(audit.findings) if audit.findings else 0,
            "top_opportunities": len(audit.opportunities) if audit.opportunities else 0,
            "data_quality": 91,  # placeholder
            "generated_at": audit.generated_at,
        }

    def _compute_delta(self, current: OrbitAuditResult, previous: OrbitAuditResult) -> dict[str, Any]:
        """Compute delta between two audits."""
        delta = {}

        # Health score delta
        delta["health_score"] = current.health_score - (previous.health_score if previous else 0)

        # Exposure deltas
        if current.exposures and previous.exposures:
            delta["capital_exposed"] = current.exposures.capital_exposed_sar.value - previous.exposures.capital_exposed_sar.value
            delta["revenue_at_risk"] = current.exposures.revenue_at_risk_sar.value - previous.exposures.revenue_at_risk_sar.value
            delta["profit_at_risk"] = current.exposures.gross_profit_at_risk_sar.value - previous.exposures.gross_profit_at_risk_sar.value
            delta["recoverable_low"] = current.exposures.recoverable_range_sar["low"].value - previous.exposures.recoverable_range_sar["low"].value
            delta["recoverable_high"] = current.exposures.recoverable_range_sar["high"].value - previous.exposures.recoverable_range_sar["high"].value

        # Findings delta
        delta["findings_count"] = len(current.findings) - len(previous.findings) if previous.findings else len(current.findings)

        # Findings delta by category
        current_cats = {}
        for f in current.findings:
            cat = f.get("category", "UNKNOWN")
            current_cats[cat] = current_cats.get(cat, 0) + 1
        prev_cats = {}
        for f in previous.findings:
            cat = f.get("category", "UNKNOWN")
            prev_cats[cat] = prev_cats.get(cat, 0) + 1

        all_cats = set(current_cats.keys()) | set(prev_cats.keys())
        delta["findings_by_category"] = {
            cat: current_cats.get(cat, 0) - prev_cats.get(cat, 0) for cat in all_cats
        }

        return delta

    def _get_products_for_finding(self, audit, finding) -> list[dict]:
        """Get products associated with a finding."""
        evidence_ids = finding.get("evidence_ids", [])
        products = []
        for ev_id in finding.get("evidence_ids", []):
            # Extract product name from evidence_id (format: ev-{product_name}-{type})
            parts = ev_id.split("-")
            if len(parts) >= 3:
                product_name = "-".join(parts[1:-1])
                products.append({"name": product_name, "evidence_id": ev_id})
        return products

    async def _get_source_rows_for_finding(self, audit, finding) -> list[dict]:
        """Get source rows for a finding from evidence records."""
        # In a full implementation, this would query orbit_evidence for source_ref
        return []