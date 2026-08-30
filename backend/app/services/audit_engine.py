"""Reusable Business Audit Engine (Phase 1).

The audit engine is deliberately NOT hardcoded around Money Audit. It owns:
  - a registry of audit domains (money_audit, inventory, recovery_match, compliance, …);
  - the AuditRun lifecycle (pending → running → completed | failed);
  - canonical Finding persistence.

Each domain is a thin ADAPTER over existing services — no business logic is
duplicated here (brief §2 "use the existing Money Audit implementation … do not
duplicate its logic").

Adding a new audit domain = register a name + a `run()` callable. Nothing else changes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AuditRun, Finding
from app.utils.clock import utcnow

logger = logging.getLogger("audit_engine")

DomainRunner = Callable[[AsyncSession, UUID], Awaitable[list[dict[str, Any]]]]


def compute_urgency(severity: str, estimated_impact_sar: Any, recurring: bool = False) -> str:
    """Phase 9 §11: deterministic urgency from severity + financial exposure + recurrence.

    Never invented from a high estimate alone — severity is the primary signal; a very
    large financial exposure escalates medium → high, and recurrence escalates one band.
    """
    base = {"critical": "critical", "high": "high", "medium": "medium", "low": "low"}.get(severity, "medium")
    try:
        impact = float(estimated_impact_sar or 0)
    except (TypeError, ValueError):
        impact = 0.0

    # Large exposure escalates medium → high (but never low → high on value alone).
    if base == "medium" and impact >= 20_000:
        base = "high"
    # Recurrence escalates one band.
    if recurring:
        base = {"critical": "critical", "high": "critical", "medium": "high", "low": "medium"}.get(base, base)
    return base


# ── Domain adapters ────────────────────────────────────────────────────────

async def _run_money_audit_domain(db: AsyncSession, business_id: UUID) -> list[dict[str, Any]]:
    """Reuse the existing Money Audit service; surface its actions as findings."""
    from app.services.money_audit_service import generate_money_audit, list_money_audit_actions

    audit = await generate_money_audit(db, business_id)
    if not audit:
        return []
    actions = await list_money_audit_actions(db, audit["id"])
    data_quality = audit.get("data_quality_score")
    findings: list[dict[str, Any]] = []
    for a in actions:
        findings.append({
            "domain": "money_audit",
            "category": a.get("action_type", "review"),
            "severity": "high" if (a.get("expected_recovery_sar") or 0) >= 5000 else "medium",
            "title": a.get("title", "Recovery action"),
            "explanation": a.get("description"),
            "evidence": {"money_audit_id": audit["id"], "action_id": a.get("id")},
            "affected_entities": [{"type": "item", "id": a.get("item_id")}],
            # §2 Financial Semantic Safety: estimated_financial_impact_sar is EXPOSURE
            # (capital/revenue/profit at risk), NOT expected recovery. These are distinct
            # semantic layers: Exposure → Recoverable Opportunity → Expected Recovery → Actual.
            "estimated_financial_impact_sar": (
                a.get("financial_model", {}).get("capital_at_risk")
                or a.get("financial_model", {}).get("revenue_at_risk")
                or a.get("financial_model", {}).get("gross_profit_at_risk")
                or 0
            ),
            "financial_impact_type": a.get("financial_model", {}).get("financial_impact_type", "UNKNOWN"),
            "recoverable_value_low_sar": a.get("recoverable_value_low_sar"),
            "recoverable_value_high_sar": a.get("recoverable_value_high_sar"),
            # Store recovery estimate in evidence (findings table lacks a dedicated column).
            # Downstream consumers must read evidence["expected_recovery_sar"], NOT
            # estimated_financial_impact_sar, when they need the recovery estimate.
            "expected_recovery_sar": a.get("expected_recovery_sar"),
            "confidence": a.get("confidence", 0.8),
            "data_quality_score": data_quality,  # §12: propagate real data-quality info
            "recommended_action": {"type": a.get("action_type"), "payload": a.get("payload", {}), "why": a.get("description")},
            "action_risk": "low" if a.get("action_type") in ("discount", "margin_fix") else "medium",
            "source": "money_audit",
        })
    # A domain-level finding carries the headline money-at-risk figure.
    if audit.get("money_at_risk_sar"):
        findings.append({
            "domain": "money_audit",
            "category": "audit_summary",
            "severity": "high",
            "title": "Money Audit summary",
            "explanation": "Financial exposures are intentionally kept separate; review capital, revenue and profit-at-risk fields individually.",
            "evidence": {"money_audit_id": audit["id"], "capital_at_risk_sar": audit.get("capital_at_risk_sar"), "revenue_at_risk_sar": audit.get("revenue_at_risk_sar"), "gross_profit_at_risk_sar": audit.get("gross_profit_at_risk_sar")},
            "affected_entities": [],
            "estimated_financial_impact_sar": None,
            "financial_impact_type": "MULTI_METRIC_SUMMARY",
            "confidence": audit.get("confidence_score"),
            "recommended_action": {"type": "review", "payload": {}, "why": "Open the Money Audit to review each financial exposure separately."},
            "action_risk": "low",
            "source": "money_audit",
        })
    return findings


async def _run_inventory_domain(db: AsyncSession, business_id: UUID) -> list[dict[str, Any]]:
    """Reuse the existing dead-stock analytics AND add deterministic stockout detection.
    Phase 12: the inventory audit domain previously only found dead stock; stockout risk
    (days-of-supply < 7) is now surfaced too, so the closed-loop stockout scenario is
    auditable end-to-end."""
    from app.services.agent_tools import execute_agent_tool
    from app.utils.clock import utcnow
    from datetime import datetime, timedelta, timezone

    findings: list[dict[str, Any]] = []
    try:
        dead = await execute_agent_tool("get_dead_stock_summary", {"days_no_sale": 30}, business_id, db)
        if isinstance(dead, dict) and dead.get("dead_stock_items"):
            for item in dead["dead_stock_items"]:
                findings.append({
                    "domain": "inventory",
                    "category": "dead_stock",
                    "severity": "high" if (item.get("stuck_sar") or 0) >= 5000 else "medium",
                    "title": f"Dead stock: {item.get('name')}",
                    "explanation": "No meaningful sales in 30 days; capital is trapped.",
                    "evidence": {"item": item},
                    "affected_entities": [{"type": "item", "name": item.get("name")}],
                    "estimated_financial_impact_sar": item.get("stuck_sar"),
                    "confidence": 0.85,
                    "recommended_action": {"type": "discount", "payload": {"item_name": item.get("name")}, "why": "Recover stuck capital via controlled discount or transfer."},
                    "action_risk": "low",
                    "source": "inventory_analysis",
                })
    except Exception as exc:  # tool may be unavailable on sparse data
        logger.warning("inventory dead-stock scan skipped: %s", exc)

    # Stockout-risk scan (dialect-safe, Phase 12): items with < 7 days of supply.
    # days_of_supply computed in Python (SQLite lacks GREATEST/NULLIF).
    try:
        cutoff = utcnow() - timedelta(days=30)
        stockout = await db.execute(text("""
            SELECT i.id AS item_id, i.name, inv.current_stock,
                   COALESCE((SELECT SUM(t.quantity) FROM transactions t
                             WHERE t.item_id = i.id AND t.business_id = :b AND t.transaction_at >= :cutoff AND t.transaction_type = 'sale'), 0) AS qty_30d
            FROM items i
            JOIN inventory inv ON inv.item_id = i.id AND inv.business_id = :b
            WHERE i.business_id = :b AND i.is_active = true AND inv.current_stock > 0
            LIMIT 500
        """), {"b": str(business_id), "cutoff": cutoff})
        from app.services.po_service import get_confirmed_inbound_map
        _inbound_map = await get_confirmed_inbound_map(db, business_id=business_id, as_of=utcnow().date())
        for r in stockout.fetchall():
            stock = float(r.current_stock or 0)
            qty_30d = float(r.qty_30d or 0)
            _inb = _inbound_map.get(str(r.item_id))
            inbound = float(_inb.confirmed_inbound_qty) if _inb else 0.0
            ghost_po = bool(_inb and _inb.ghost_po_risk)
            velocity = max(qty_30d / 30.0, 0.01)
            projected_stock = stock + inbound
            days = projected_stock / velocity if velocity > 0 else 999.0
            if days >= 7:
                continue
            findings.append({
                "domain": "inventory",
                "category": "stockout_risk",
                "severity": "high" if days < 2 else "medium",
                "title": f"Stockout risk: {r.name}",
                "explanation": f"~{days:.1f} days of supply left at current velocity.",
                "evidence": {"item_id": str(r.item_id), "current_stock": stock, "confirmed_inbound": inbound, "ghost_po_risk": ghost_po, "projected_available": projected_stock, "daily_velocity": velocity, "days_of_supply": days},
                "affected_entities": [{"type": "item", "id": str(r.item_id), "name": r.name}],
                "estimated_financial_impact_sar": None,
                "financial_impact_type": "REVENUE_AT_RISK",
                "confidence": 0.85,
                "recommended_action": {"type": "restock", "payload": {"item_id": str(r.item_id)}, "why": "Replenish before stockout only after confirmed inbound inventory is considered."},
                "action_risk": "medium",
                "source": "inventory_analysis",
            })
    except Exception as exc:
        logger.warning("inventory stockout scan skipped: %s", exc)

    return findings


async def _run_recovery_match_domain(db: AsyncSession, business_id: UUID) -> list[dict[str, Any]]:
    """Surface Recovery Match preview opportunities as findings (read-only)."""
    from app.services.recovery_match_service import generate_preview

    try:
        opportunities = await generate_preview(db, business_id)
    except Exception as exc:
        logger.warning("recovery-match preview skipped: %s", exc)
        return []
    findings: list[dict[str, Any]] = []
    for opp in opportunities or []:
        findings.append({
            "domain": "recovery_match",
            "category": "surplus_recovery",
            "severity": "medium",
            "title": f"Surplus recoverable: {opp.get('item_name')}",
            "explanation": "Healthy surplus stock that could be recovered via nearby opted-in stores.",
            "evidence": {"opportunity": opp},
            "affected_entities": [{"type": "item", "id": opp.get("item_id"), "name": opp.get("item_name")}],
            "estimated_financial_impact_sar": None,
            "financial_impact_type": "RECOVERABLE_OPPORTUNITY",
            "recoverable_value_high_sar": opp.get("estimated_recovery_value_sar"),
            "confidence": 0.8,
            "recommended_action": {"type": "recovery_match", "payload": {"item_id": opp.get("item_id")}, "why": "Create a listing and suggest nearby buyers."},
            "action_risk": "low",
            "source": "recovery_match",
        })
    return findings


async def _run_compliance_domain(db: AsyncSession, business_id: UUID) -> list[dict[str, Any]]:
    """Read-only expiry/recall reminders — informational findings only (brief §13)."""
    rows = await db.execute(text("""
        SELECT pl.id AS lot_id, i.name AS item_name, pl.expiry_date,
               CAST(pl.expiry_date - CURRENT_DATE AS INT) AS days_to_expiry
        FROM pharmacy_lots pl
        JOIN items i ON i.id = pl.item_id
        WHERE pl.business_id = :b AND pl.expiry_date IS NOT NULL
          AND pl.expiry_date <= CURRENT_DATE + INTERVAL '45 days'
        ORDER BY pl.expiry_date ASC
        LIMIT 50
    """), {"b": str(business_id)})
    findings: list[dict[str, Any]] = []
    for r in rows.fetchall():
        days = int(r.days_to_expiry or 0)
        findings.append({
            "domain": "compliance",
            "category": "expiry",
            "severity": "high" if days <= 7 else "medium",
            "title": f"Expiring soon: {r.item_name}",
            "explanation": f"Lot expires in {days} day(s).",
            "evidence": {"lot_id": str(r.lot_id), "expiry_date": str(r.expiry_date)},
            "affected_entities": [{"type": "lot", "id": str(r.lot_id), "name": r.item_name}],
            "estimated_financial_impact_sar": None,
            "confidence": 0.95,
            "recommended_action": {"type": "expiry_alert", "payload": {"lot_id": str(r.lot_id)}, "why": "Review shelf life; this is an informational reminder, not legal advice."},
            "action_risk": "low",
            "source": "compliance_radar",
        })
    return findings


# ── Registry ───────────────────────────────────────────────────────────────

AUDIT_DOMAINS: dict[str, DomainRunner] = {
    "money_audit": _run_money_audit_domain,
    "inventory": _run_inventory_domain,
    "recovery_match": _run_recovery_match_domain,
    "compliance": _run_compliance_domain,
}


def list_domains() -> list[str]:
    return list(AUDIT_DOMAINS.keys())


# ── Orchestration ──────────────────────────────────────────────────────────

async def run_audit(
    db: AsyncSession,
    business_id: UUID | str,
    domain: str,
    trigger: str = "manual",
    trigger_event_type: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    """Run one audit domain for a business and persist an AuditRun + Findings."""
    runner = AUDIT_DOMAINS.get(domain)
    if not runner:
        raise ValueError(f"Unknown audit domain: {domain} (known: {list_domains()})")

    now = utcnow()
    run_id = uuid4()
    await db.execute(text("""
        INSERT INTO audit_runs (id, business_id, domain, status, trigger, trigger_event_type, started_at, created_at)
        VALUES (:id, :b, :domain, 'running', :trigger, :event, :started, :created)
    """), {
        "id": str(run_id),
        "b": str(business_id),
        "domain": domain,
        "trigger": trigger,
        "event": trigger_event_type,
        "started": now,
        "created": now,
    })

    try:
        findings = await runner(db, UUID(str(business_id)))
        await _persist_findings(db, business_id, run_id, findings)
        await db.execute(text("""
            UPDATE audit_runs SET status = 'completed', completed_at = :now,
                summary = CAST(:summary AS JSON)
            WHERE id = :id
        """), {
            "id": str(run_id),
            "now": utcnow(),
            "summary": _json({"findings": len(findings)}),
        })
        status = "completed"
    except Exception as exc:
        logger.exception("audit domain %s failed for business %s", domain, business_id)
        await db.execute(text("""
            UPDATE audit_runs SET status = 'failed', completed_at = :now, error = :err
            WHERE id = :id
        """), {"id": str(run_id), "now": utcnow(), "err": str(exc)[:1000]})
        status = "failed"
        findings = []

    if commit:
        await db.commit()

    return {"audit_run_id": str(run_id), "domain": domain, "status": status, "findings": len(findings)}


def _json(value: Any) -> str:
    import json
    return json.dumps(value, default=str)


async def _persist_findings(
    db: AsyncSession,
    business_id: UUID | str,
    run_id: UUID,
    findings: list[dict[str, Any]],
) -> None:
    now = utcnow()
    for f in findings:
        fid = str(uuid4())
        urgency = compute_urgency(f.get("severity", "medium"), f.get("estimated_financial_impact_sar"),
                                  recurring=bool(f.get("recurring")))
        data_quality = f.get("data_quality_score")  # e.g. from money_audit's data_quality_score
        await db.execute(text("""
            INSERT INTO findings
                (id, business_id, audit_id, domain, category, severity, title, explanation,
                 evidence, affected_entities, estimated_financial_impact_sar, confidence,
                 urgency, data_quality_score, recommended_action, action_risk, status, source,
                 created_at, updated_at)
            VALUES
                (:id, :b, :audit_id, :domain, :category, :severity, :title, :explanation,
                 CAST(:evidence AS JSON), CAST(:entities AS JSON), :impact, :confidence,
                 :urgency, :dq, CAST(:recommended AS JSON), :risk, 'detected', :source, :now, :now)
        """), {
            "id": fid,
            "b": str(business_id),
            "audit_id": str(run_id),
            "domain": f["domain"],
            "category": f.get("category", "general"),
            "severity": f.get("severity", "medium"),
            "title": f["title"],
            "explanation": f.get("explanation"),
            # §2 Financial Semantic Safety: carry expected_recovery_sar in evidence so
            # downstream consumers can access recovery estimates. The findings table
            # has no dedicated column for recovery — only estimated_financial_impact_sar
            # (which is exposure, NOT recovery). Never conflate the two.
            "evidence": _json({**(f.get("evidence") or {}),
                               "expected_recovery_sar": f.get("expected_recovery_sar"),
                               "recoverable_value_low_sar": f.get("recoverable_value_low_sar"),
                               "recoverable_value_high_sar": f.get("recoverable_value_high_sar")}),
            "entities": _json(f.get("affected_entities") or []),
            "impact": f.get("estimated_financial_impact_sar"),
            "confidence": f.get("confidence"),
            "urgency": urgency,
            "dq": data_quality,
            "recommended": _json(f.get("recommended_action") or {}),
            "risk": f.get("action_risk", "low"),
            "source": f.get("source", "audit_engine"),
            "now": now,
        })

        # §15: project the finding into the KG (finding → affected entity AFFECTS).
        try:
            from app.services.knowledge_graph import project_finding_to_graph
            await project_finding_to_graph(
                db, business_id, fid, domain=f["domain"],
                category=f.get("category", "general"), severity=f.get("severity", "medium"),
                title=f["title"], affected_entities=f.get("affected_entities") or [],
            )
        except Exception as exc:  # graph projection must never fail the audit
            logger.warning("finding graph projection skipped: %s", exc)
