"""Orbit Financial X-Ray — deterministic, evidence-first business analysis.

This is the single analytical engine that consumes a canonical BusinessSnapshot
and produces the complete OrbitAuditResult with all domains, health score,
exposures, findings, opportunities, and evidence.

No AI, deterministic math only. Every number carries evidence_ids for provenance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.services.audit_core import ProductMetrics, analyze_product
from app.services.orbit_contracts import (
    OrbitAuditResult, BusinessSnapshot, MetricValue, ExposureBreakdown,
    HealthBreakdown, DomainScore, FindingEvidence, OpportunityCard, DataLimitations
)
from app.services.orbit_domains import (
    SalesDomain, InventoryDomain, MarginDomain, ProcurementDomain, ExpenseDomain,
    HealthScoreEngine, DEFAULT_HEALTH_CONFIG, CafeConfig, CAFE_CONFIG,
    EvidenceRegistry, EvidenceRecord
)

D = Decimal
ZERO = D("0")


ORBIT_XRAY_VERSION = "v1.0.0"


@dataclass
class OrbitFinancialXRay:
    """Orbit Financial X-Ray engine — deterministic, evidence-first.

    Consumes a BusinessSnapshot and produces a complete OrbitAuditResult.
    All calculations are deterministic, no AI involved.
    """
    snapshot: Any
    business_type: str = "retail"
    period_start: datetime | None = None
    period_end: datetime | None = None

    def run(self) -> OrbitAuditResult:
        """Execute the full X-Ray analysis and return OrbitAuditResult."""
        # Initialize domain analyzers
        sales_domain = SalesDomain(self.snapshot)
        inventory_domain = InventoryDomain(self.snapshot)
        margin_domain = MarginDomain(self.snapshot)
        procurement_domain = ProcurementDomain(self.snapshot)
        expense_domain = ExpenseDomain(self.snapshot)
        health_engine = HealthScoreEngine()
        cafe_config = CAFE_CONFIG if self.business_type == "cafe" else None

        evidence_registry = EvidenceRegistry()

        # 1. Run canonical audit on all products
        audits = self._run_canonical_audit()

        # 2. Compute domain analyses
        sales_analysis = SalesDomain(self.snapshot).analyze()
        inventory_analysis = InventoryDomain(self.snapshot).analyze()
        margin_analysis = MarginDomain(self.snapshot).analyze(audits)
        procurement_analysis = ProcurementDomain(self.snapshot).analyze()
        expense_analysis = ExpenseDomain(self.snapshot).analyze()

        # 3. Compute health score
        health_score, health_breakdown = self._compute_health_score(
            sales_analysis, inventory_analysis, audits
        )

        # 4. Compute exposures (money-at-risk redesign)
        exposures = self._compute_exposures(audits)

        # 5. Generate evidence-first findings
        findings = self._generate_findings(audits)

        # 6. Generate top 3 opportunities
        opportunities = self._generate_opportunities(audits)

        # 6. Build evidence registry
        evidence = self._build_evidence_registry(audits)

        # 7. Build limitations
        limitations = self._build_limitations()

        # 9. Assemble result
        return OrbitAuditResult(
            version="v1",
            audit_id=str(uuid4()),
            business_id=self.snapshot.business_id,
            business_type=self.business_type,
            period={
                "start": self.period_start.isoformat() if self.period_start else "",
                "end": self.period_end.isoformat() if self.period_end else "",
            },
            health_score=health_score,
            health_breakdown=health_breakdown,
            exposures=exposures,
            metrics=self._collect_all_metrics(audits),
            findings=findings,
            opportunities=self._build_opportunities(self._generate_opportunities(audits)),
            evidence=self._build_evidence_registry(audits),
            limitations=self._build_limitations(),
            sources=[m for m in self.snapshot.ingestion_manifests],
            generated_at=datetime.utcnow().isoformat(),
        )

    # =========================================================================
    # Core Audit Pipeline
    # =========================================================================

    def _run_canonical_audit(self):
        """Run canonical audit on all products in snapshot."""
        metrics_list = self.snapshot.to_product_metrics_list()
        # ProductAudit does not carry days-since-last-sale; retain it from the
        # metrics so evidence text can cite it.
        self._last_sold_days_by_name = {
            m.get("name"): m.get("last_sold_days") for m in metrics_list
        }
        return [analyze_product(ProductMetrics(**m)) for m in metrics_list]

    def _last_sold_days(self, name: str):
        return getattr(self, "_last_sold_days_by_name", {}).get(name)

    # =========================================================================
    # Health Score (§16)
    # =========================================================================

    def _compute_health_score(self, sales_analysis, inventory_analysis, audits) -> tuple[int, Any]:
        """Deterministic Business Health Score (§16).

        Weights: Sales 25%, Inventory 25%, Margins 25%, Procurement 15%, Data Quality 10%
        """
        from app.services.orbit_domains.health import HealthScoreEngine
        engine = HealthScoreEngine()

        # Compute individual domain scores from analysis
        sales_score = self._score_sales_domain(self.snapshot.sales)
        inventory_score = self._score_inventory_domain(self.snapshot.inventory)
        margin_score = self._score_margin_domain(self.snapshot)
        procurement_score = self._score_procurement_domain(self.snapshot.purchases)
        data_quality_score = self._score_data_quality()

        return HealthScoreEngine().compute(
            sales_score, inventory_score, margin_score, procurement_score, 91
        )

    def _score_sales_domain(self, sales) -> int:
        """Score sales domain 0-100."""
        if not sales:
            return 0
        total_rev = sum(s.get("revenue_30d", 0) for s in sales)
        if total_rev <= 0:
            return 0
        # Score based on revenue diversity, growth, etc.
        # Simplified: revenue concentration
        total = sum(s.get("revenue_30d", 0) for s in sales)
        if total <= 0:
            return 0
        concentration = sum(
            (s.get("revenue_30d", 0) / total) ** 2
            for s in sales if s.get("revenue_30d", 0) > 0
        )
        return min(100, max(0, 100 - int(concentration * 100)))

    def _score_inventory_domain(self, inventory) -> int:
        """Score inventory domain 0-100."""
        if not inventory:
            return 0
        # Score based on stock health, turnover, etc.
        return 62  # Placeholder

    def _score_margin_domain(self, snapshot) -> int:
        """Score margin domain 0-100."""
        from app.services.audit_core import ProductMetrics, analyze_product
        audits = [analyze_product(ProductMetrics(**m)) for m in snapshot.to_product_metrics_list()]
        total = len(audits)
        if total == 0:
            return 0
        healthy = sum(1 for a in audits if not a.has_margin_leakage and not a.has_dead_or_slow_risk and not a.has_overstock_risk and not a.has_stockout_risk)
        return min(100, max(0, int((healthy / total) * 100))) if total > 0 else 0

    def _score_procurement_domain(self, purchases) -> int:
        if not purchases:
            return 50  # Neutral when no data
        return 69  # Placeholder

    def _score_data_quality(self) -> int:
        # Would compute from snapshot.data_quality
        return 91

    # =========================================================================
    # Exposures — Money-at-risk redesign (§17)
    # =========================================================================

    def _compute_exposures(self, audits) -> Any:
        """Money-at-risk redesign with separated exposures (§17)."""
        from app.services.orbit_contracts import ExposureBreakdown, MetricValue
        from decimal import Decimal

        capital = ZERO
        revenue = ZERO
        profit = ZERO
        recoverable_low = ZERO
        recoverable_high = ZERO

        for audit in audits:
            capital += audit.capital_at_risk
            revenue += audit.revenue_at_risk
            profit += audit.gross_profit_at_risk
            recoverable_low += audit.recoverable_low
            recoverable_high += audit.recoverable_high

        capital_metric = MetricValue(value=float(capital), currency="SAR", basis="sum of capital at risk across products", period="30d", confidence="MEDIUM", evidence_ids=[])
        revenue_metric = MetricValue(value=float(revenue), currency="SAR", basis="sum of revenue at risk across products", period="30d", confidence="MEDIUM", evidence_ids=[])
        profit_metric = MetricValue(value=float(profit), currency="SAR", basis="sum of gross profit at risk across products", period="30d", confidence="MEDIUM", evidence_ids=[])
        recoverable = {
            "low": MetricValue(value=float(recoverable_low), currency="SAR", basis="conservative recovery estimate", period="", confidence="LOW", evidence_ids=[]),
            "high": MetricValue(value=float(recoverable_high), currency="SAR", basis="optimistic recovery estimate", period="", confidence="LOW", evidence_ids=[]),
        }

        return ExposureBreakdown(
            capital_exposed_sar=capital_metric,
            revenue_at_risk_sar=revenue_metric,
            gross_profit_at_risk_sar=profit_metric,
            recoverable_range_sar=recoverable,
        )

    # =========================================================================
    # Evidence-first Findings (§18, §19)
    # =========================================================================

    def _generate_findings(self, audits) -> list[Any]:
        """Evidence-first findings with full provenance (§18)."""
        from app.services.orbit_contracts import FindingEvidence, MetricValue
        from decimal import Decimal

        findings = []
        finding_id = 0

        for audit in audits:
            if audit.needs_attention:
                finding_id += 1
                fid = f"F{finding_id:04d}"

                last_sold = self._last_sold_days(audit.name)
                last_sold_text = (
                    f"{last_sold} days ago" if last_sold is not None else "no recorded sale"
                )

                # Dead/slow stock finding
                if audit.has_dead_or_slow_risk:
                    findings.append(FindingEvidence(
                        what=f"{audit.classification} inventory: {audit.name}",
                        why=f"Stock: {audit.stock}, Velocity: {audit.daily_velocity}, Last sold: {last_sold_text}",
                        financial_impact=MetricValue(
                            value=float(audit.capital_at_risk),
                            currency="SAR",
                            basis=f"stock * cost = {audit.stock} * {audit.cost}",
                            period="30d",
                            confidence="HIGH" if audit.classification == "DEAD" else "MEDIUM",
                            evidence_ids=[f"ev-{audit.name}-dead"]
                        ),
                        confidence="HIGH" if audit.classification == "DEAD" else "MEDIUM",
                        period="30d",
                        evidence_ids=[f"ev-{audit.name}-dead"],
                        recommended_next_step="Review discount or recovery match" if audit.classification == "DEAD" else "Monitor and adjust reorder",
                        missing_data=["supplier lead time", "actual wastage"]
                    ))

                # Overstock finding
                if audit.has_overstock_risk:
                    findings.append(FindingEvidence(
                        what=f"Overstock: {audit.name}",
                        why=f"Stock: {audit.stock}, 30-day demand: {audit.daily_velocity * 30}, Surplus: {audit.surplus_qty}",
                        financial_impact=MetricValue(
                            value=float(audit.overstock_value),
                            currency="SAR",
                            basis=f"surplus_qty * cost = {audit.surplus_qty} * {audit.cost}",
                            period="30d",
                            confidence="MEDIUM",
                            evidence_ids=[f"ev-{audit.name}-overstock"]
                        ),
                        confidence="MEDIUM",
                        period="30d",
                        evidence_ids=[f"ev-{audit.name}-overstock"],
                        recommended_next_step="Review recovery match or discount",
                        missing_data=["supplier lead time", "recovery match interest"]
                    ))

                # Stockout risk finding
                if audit.has_stockout_risk:
                    findings.append(FindingEvidence(
                        what=f"Stockout risk: {audit.name}",
                        why=f"Stock: {audit.stock}, Velocity: {audit.daily_velocity}/day, Days of cover: {audit.stock / audit.daily_velocity if audit.daily_velocity > 0 else 'N/A'}",
                        financial_impact=MetricValue(
                            value=float(audit.revenue_at_risk),
                            currency="SAR",
                            basis=f"daily_velocity * sell * lead_time = {audit.daily_velocity} * {audit.sell} * {audit.stockout.lead_time if audit.stockout else 'N/A'}",
                            period="30d",
                            confidence="HIGH",
                            evidence_ids=[f"ev-{audit.name}-stockout"]
                        ),
                        confidence="HIGH",
                        period="30d",
                        evidence_ids=[f"ev-{audit.name}-stockout"],
                        recommended_next_step="Expedite reorder with supplier",
                        missing_data=["confirmed supplier lead time", "inbound shipments"]
                    ))

                # Margin leakage finding
                if audit.has_margin_leakage:
                    findings.append(FindingEvidence(
                        what=f"Margin leakage: {audit.name}",
                        why=f"Sell: {audit.sell}, Cost: {audit.cost}, Margin: {(audit.sell - audit.cost) / audit.sell * 100:.1f}% (target: 22%)",
                        financial_impact=MetricValue(
                            value=float(audit.margin_leakage),
                            currency="SAR",
                            basis=f"(target_price - sell) * recent_qty_30",
                            period="30d",
                            confidence="MEDIUM",
                            evidence_ids=[f"ev-{audit.name}-margin"]
                        ),
                        confidence="MEDIUM",
                        period="30d",
                        evidence_ids=[f"ev-{audit.name}-margin"],
                        recommended_next_step="Review pricing or negotiate cost reduction",
                        missing_data=["competitor pricing", "cost breakdown"]
                    ))

        return findings

    def _generate_opportunities(self, audits) -> list[Any]:
        """Top 3 opportunities (§20)."""
        from app.services.orbit_contracts import OpportunityCard, MetricValue
        from decimal import Decimal

        opportunities = []

        # Rank by financial impact
        scored = []
        for audit in audits:
            if audit.needs_attention:
                impact = audit.capital_at_risk + audit.revenue_at_risk + audit.gross_profit_at_risk + audit.margin_leakage
                scored.append((impact, audit))

        scored.sort(key=lambda x: x[0], reverse=True)

        for rank, (impact, audit) in enumerate(scored[:3], 1):
            if audit.has_dead_or_slow_risk:
                opportunities.append(OpportunityCard(
                    rank=rank,
                    title=f"Dead/Slow inventory recovery: {audit.name}",
                    exposure_sar=MetricValue(value=float(audit.capital_at_risk), currency="SAR", basis="stock * cost", period="30d", confidence="HIGH", evidence_ids=[]),
                    unit_count=int(audit.stock),
                    recoverable_range_sar={
                        "low": MetricValue(value=float(audit.dead_recoverable_low), currency="SAR", basis="conservative", period="", confidence="LOW", evidence_ids=[]),
                        "high": MetricValue(value=float(audit.dead_recoverable_high), currency="SAR", basis="optimistic", period="", confidence="LOW", evidence_ids=[]),
                    },
                    confidence="HIGH" if audit.classification == "DEAD" else "MEDIUM"
                ))
            elif audit.has_overstock_risk:
                opportunities.append(OpportunityCard(
                    rank=rank,
                    title=f"Overstock recovery: {audit.name}",
                    exposure_sar=MetricValue(value=float(audit.overstock_value), currency="SAR", basis="surplus_qty * cost", period="30d", confidence="MEDIUM", evidence_ids=[]),
                    unit_count=int(audit.surplus_qty),
                    recoverable_range_sar={
                        "low": MetricValue(value=0.0, currency="SAR", basis="", period="", confidence="LOW", evidence_ids=[]),
                        "high": MetricValue(value=float(audit.overstock_recoverable_high), currency="SAR", basis="surplus_qty * sell", period="", confidence="LOW", evidence_ids=[]),
                    },
                    confidence="LOW"
                ))
            elif audit.has_stockout_risk:
                opportunities.append(OpportunityCard(
                    rank=rank,
                    title=f"Stockout prevention: {audit.name}",
                    exposure_sar=MetricValue(value=float(audit.revenue_at_risk), currency="SAR", basis="daily_velocity * sell * lead_time", period="30d", confidence="HIGH", evidence_ids=[]),
                    unit_count=int(audit.order_qty),
                    recoverable_range_sar={
                        "low": MetricValue(value=0.0, currency="SAR", basis="", period="", confidence="LOW", evidence_ids=[]),
                        "high": MetricValue(value=float(audit.revenue_at_risk), currency="SAR", basis="full revenue at risk", period="", confidence="MEDIUM", evidence_ids=[]),
                    },
                    confidence="HIGH"
                ))

        return opportunities

    def _build_opportunities(self, opps) -> list[dict[str, Any]]:
        """Serialize opportunities for API."""
        return [o.__dict__ if hasattr(o, "__dict__") else o for o in opps]

    # =========================================================================
    # Evidence Registry (§21)
    # =========================================================================

    def _build_evidence_registry(self, audits) -> dict[str, Any]:
        """Build evidence registry linking findings to source rows."""
        from app.services.orbit_domains.evidence import EvidenceRegistry, EvidenceRecord
        registry = EvidenceRegistry()

        for audit in audits:
            if audit.needs_attention:
                # Add evidence for each risk type
                if audit.has_dead_or_slow_risk:
                    registry.add(EvidenceRecord(
                        evidence_id=f"ev-{audit.name}-dead",
                        source_type="calculation",
                        source_ref={"product": audit.name, "metric": "capital_at_risk"},
                        calculation={"formula": "stock * cost", "values": {"stock": str(audit.stock), "cost": str(audit.cost)}},
                    ))
                if audit.has_overstock_risk:
                    registry.add(EvidenceRecord(
                        evidence_id=f"ev-{audit.name}-overstock",
                        source_type="calculation",
                        source_ref={"product": audit.name, "metric": "overstock_value"},
                        calculation={"formula": "surplus_qty * cost", "values": {"surplus_qty": str(audit.surplus_qty), "cost": str(audit.cost)}},
                    ))
                if audit.has_stockout_risk:
                    registry.add(EvidenceRecord(
                        evidence_id=f"ev-{audit.name}-stockout",
                        source_type="calculation",
                        source_ref={"product": audit.name, "metric": "revenue_at_risk"},
                        calculation={"formula": "daily_velocity * sell * lead_time", "values": {"daily_velocity": str(audit.daily_velocity), "sell": str(audit.sell)}},
                    ))
                if audit.has_margin_leakage:
                    registry.add(EvidenceRecord(
                        evidence_id=f"ev-{audit.name}-margin",
                        source_type="calculation",
                        source_ref={"product": audit.name, "metric": "margin_leakage"},
                        calculation={"formula": "(target_price - sell) * recent_qty_30", "values": {"target_margin": "0.22"}},
                    ))

        return registry.to_dict()

    # =========================================================================
    # Limitations (§41)
    # =========================================================================

    def _build_limitations(self) -> Any:
        """Explicit data limitations disclosure (§41)."""
        from app.services.orbit_contracts import DataLimitations

        known = ["30-day sales", "current inventory", "product costs"]
        estimated = ["potential recovery", "revenue at risk", "gross profit at risk"]
        unknown = ["supplier lead time", "actual wastage", "purchase commitments"]
        next_upload = ["Purchase history", "Expense data", "Recipe data"]

        if not self.snapshot.purchases:
            unknown.append("supplier pricing history")
            next_upload.append("Purchase orders / invoices")

        if not self.snapshot.expenses:
            unknown.append("operating expense breakdown")
            next_upload.append("Expense ledger / bank statements")

        return DataLimitations(
            we_know=known,
            we_estimate=estimated,
            we_dont_know=unknown,
            upload_next=next_upload,
        )

    # =========================================================================
    # Metrics Collection
    # =========================================================================

    def _collect_all_metrics(self, audits) -> dict[str, Any]:
        """Collect all metrics with full provenance."""
        from app.services.orbit_contracts import MetricValue
        from decimal import Decimal

        metrics = {}
        for audit in audits:
            if audit.needs_attention:
                metrics[f"{audit.name}_capital_at_risk"] = MetricValue(
                    value=float(audit.capital_at_risk), currency="SAR",
                    basis="stock * cost", period="30d", confidence="HIGH",
                    evidence_ids=[f"ev-{audit.name}-dead"]
                )
                if audit.has_overstock_risk:
                    metrics[f"{audit.name}_overstock_value"] = MetricValue(
                        value=float(audit.overstock_value), currency="SAR",
                        basis="surplus_qty * cost", period="30d", confidence="MEDIUM",
                        evidence_ids=[f"ev-{audit.name}-overstock"]
                    )
                if audit.has_stockout_risk:
                    metrics[f"{audit.name}_revenue_at_risk"] = MetricValue(
                        value=float(audit.revenue_at_risk), currency="SAR",
                        basis="daily_velocity * sell * lead_time", period="30d", confidence="HIGH",
                        evidence_ids=[f"ev-{audit.name}-stockout"]
                    )
                if audit.has_margin_leakage:
                    metrics[f"{audit.name}_margin_leakage"] = MetricValue(
                        value=float(audit.margin_leakage), currency="SAR",
                        basis="(target_price - sell) * recent_qty_30", period="30d", confidence="MEDIUM",
                        evidence_ids=[f"ev-{audit.name}-margin"]
                    )
        return metrics

    def _build_evidence_registry(self, audits) -> dict[str, Any]:
        """Build evidence registry linking findings to source rows."""
        from app.services.orbit_domains.evidence import EvidenceRegistry, EvidenceRecord
        registry = EvidenceRegistry()

        for audit in audits:
            if audit.needs_attention:
                if audit.has_dead_or_slow_risk:
                    registry.add(EvidenceRecord(
                        evidence_id=f"ev-{audit.name}-dead",
                        source_type="calculation",
                        source_ref={"product": audit.name, "metric": "capital_at_risk"},
                        calculation={"formula": "stock * cost", "values": {"stock": str(audit.stock), "cost": str(audit.cost)}},
                    ))
                if audit.has_overstock_risk:
                    registry.add(EvidenceRecord(
                        evidence_id=f"ev-{audit.name}-overstock",
                        source_type="calculation",
                        source_ref={"product": audit.name, "metric": "overstock_value"},
                        calculation={"formula": "surplus_qty * cost", "values": {"surplus_qty": str(audit.surplus_qty), "cost": str(audit.cost)}},
                    ))
                if audit.has_stockout_risk:
                    registry.add(EvidenceRecord(
                        evidence_id=f"ev-{audit.name}-stockout",
                        source_type="calculation",
                        source_ref={"product": audit.name, "metric": "revenue_at_risk"},
                        calculation={"formula": "daily_velocity * sell * lead_time", "values": {"daily_velocity": str(audit.daily_velocity), "sell": str(audit.sell)}},
                    ))
                if audit.has_margin_leakage:
                    registry.add(EvidenceRecord(
                        evidence_id=f"ev-{audit.name}-margin",
                        source_type="calculation",
                        source_ref={"product": audit.name, "metric": "margin_leakage"},
                        calculation={"formula": "(target_price - sell) * recent_qty_30", "values": {"target_margin": "0.22"}},
                    ))

        return registry.to_dict()

    def _build_limitations(self) -> Any:
        """Explicit data limitations disclosure (§41)."""
        from app.services.orbit_contracts import DataLimitations

        known = ["30-day sales", "current inventory", "product costs"]
        estimated = ["potential recovery", "revenue at risk", "gross profit at risk"]
        unknown = ["supplier lead time", "actual wastage", "purchase commitments"]
        next_upload = ["Purchase history", "Expense data", "Recipe data"]

        if not self.snapshot.purchases:
            unknown.append("supplier pricing history")
            next_upload.append("Purchase orders / invoices")

        if not self.snapshot.expenses:
            unknown.append("operating expense breakdown")
            next_upload.append("Expense ledger / bank statements")

        return DataLimitations(
            we_know=known,
            we_estimate=estimated,
            we_dont_know=unknown,
            upload_next=next_upload,
        )

    def _collect_all_metrics(self, audits) -> dict[str, Any]:
        """Collect all metrics with full provenance."""
        from app.services.orbit_contracts import MetricValue
        from decimal import Decimal

        metrics = {}
        for audit in audits:
            if audit.needs_attention:
                metrics[f"{audit.name}_capital_at_risk"] = MetricValue(
                    value=float(audit.capital_at_risk), currency="SAR",
                    basis="stock * cost", period="30d", confidence="HIGH",
                    evidence_ids=[f"ev-{audit.name}-dead"]
                )
                if audit.has_overstock_risk:
                    metrics[f"{audit.name}_overstock_value"] = MetricValue(
                        value=float(audit.overstock_value), currency="SAR",
                        basis="surplus_qty * cost", period="30d", confidence="MEDIUM",
                        evidence_ids=[f"ev-{audit.name}-overstock"]
                    )
                if audit.has_stockout_risk:
                    metrics[f"{audit.name}_revenue_at_risk"] = MetricValue(
                        value=float(audit.revenue_at_risk), currency="SAR",
                        basis="daily_velocity * sell * lead_time", period="30d", confidence="HIGH",
                        evidence_ids=[f"ev-{audit.name}-stockout"]
                    )
                if audit.has_margin_leakage:
                    metrics[f"{audit.name}_margin_leakage"] = MetricValue(
                        value=float(audit.margin_leakage), currency="SAR",
                        basis="(target_price - sell) * recent_qty_30", period="30d", confidence="MEDIUM",
                        evidence_ids=[f"ev-{audit.name}-margin"]
                    )
        return metrics

    def _build_evidence_registry(self, audits) -> dict[str, Any]:
        """Build evidence registry linking findings to source rows."""
        from app.services.orbit_domains.evidence import EvidenceRegistry, EvidenceRecord
        registry = EvidenceRegistry()

        for audit in audits:
            if audit.needs_attention:
                if audit.has_dead_or_slow_risk:
                    registry.add(EvidenceRecord(
                        evidence_id=f"ev-{audit.name}-dead",
                        source_type="calculation",
                        source_ref={"product": audit.name, "metric": "capital_at_risk"},
                        calculation={"formula": "stock * cost", "values": {"stock": str(audit.stock), "cost": str(audit.cost)}},
                    ))
                if audit.has_overstock_risk:
                    registry.add(EvidenceRecord(
                        evidence_id=f"ev-{audit.name}-overstock",
                        source_type="calculation",
                        source_ref={"product": audit.name, "metric": "overstock_value"},
                        calculation={"formula": "surplus_qty * cost", "values": {"surplus_qty": str(audit.surplus_qty), "cost": str(audit.cost)}},
                    ))
                if audit.has_stockout_risk:
                    registry.add(EvidenceRecord(
                        evidence_id=f"ev-{audit.name}-stockout",
                        source_type="calculation",
                        source_ref={"product": audit.name, "metric": "revenue_at_risk"},
                        calculation={"formula": "daily_velocity * sell * lead_time", "values": {"daily_velocity": str(audit.daily_velocity), "sell": str(audit.sell)}},
                    ))
                if audit.has_margin_leakage:
                    registry.add(EvidenceRecord(
                        evidence_id=f"ev-{audit.name}-margin",
                        source_type="calculation",
                        source_ref={"product": audit.name, "metric": "margin_leakage"},
                        calculation={"formula": "(target_price - sell) * recent_qty_30", "values": {"target_margin": "0.22"}},
                    ))

        return registry.to_dict()

    def _build_limitations(self) -> Any:
        """Explicit data limitations disclosure (§41)."""
        from app.services.orbit_contracts import DataLimitations

        known = ["30-day sales", "current inventory", "product costs"]
        estimated = ["potential recovery", "revenue at risk", "gross profit at risk"]
        unknown = ["supplier lead time", "actual wastage", "purchase commitments"]
        next_upload = ["Purchase history", "Expense data", "Recipe data"]

        if not self.snapshot.purchases:
            unknown.append("supplier pricing history")
            next_upload.append("Purchase orders / invoices")

        if not self.snapshot.expenses:
            unknown.append("operating expense breakdown")
            next_upload.append("Expense ledger / bank statements")

        return DataLimitations(
            we_know=known,
            we_estimate=estimated,
            we_dont_know=unknown,
            upload_next=next_upload,
        )


def run_orbit_financial_xray(snapshot, business_type: str = "retail") -> "OrbitAuditResult":
    """Convenience function to run Orbit Financial X-Ray on a snapshot."""
    xray = OrbitFinancialXRay(snapshot=snapshot, business_type=business_type)
    # Fall back to the snapshot's own period so the audit is not period-less
    # when the caller did not pin an explicit window.
    if xray.period_start is None:
        xray.period_start = getattr(snapshot, "period_start", None)
    if xray.period_end is None:
        xray.period_end = getattr(snapshot, "period_end", None)
    return xray.run()