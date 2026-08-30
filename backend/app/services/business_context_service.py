"""Business Context Service — assembles all memory into a structured context.

Phase 2 §16-18: Expose a simple internal service/API that returns structured business context.
The StructuredBusinessContext is the contract between NazmOS and the future AI brain.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.clock import utcnow

logger = logging.getLogger("business_context_service")


# ── Structured Context Object ───────────────────────────────────────────────

@dataclass
class BusinessInfo:
    business_id: str
    name: str
    business_type: str
    city: str | None
    currency: str
    timezone: str
    is_demo: bool
    total_items: int
    total_inventory_value_sar: float
    constraints: dict[str, Any]
    owner_preferences: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActionHistoryItem:
    action_type: str
    action_date: str
    reason: str | None
    expected_recovery_sar: float | None
    actual_recovery_sar: float | None
    execution_status: str
    prediction_error_pct: float | None
    product_name: str | None
    product_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OutcomeHistoryItem:
    action_type: str
    action_date: str
    expected_impact_sar: float | None
    actual_impact_sar: float | None
    success: bool | None
    prediction_error_pct: float | None
    time_to_outcome_days: int | None
    product_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StructuredBusinessContext:
    """Complete structured context for a business. §18 spec.

    Deterministic, serializable, traceable, bounded, tenant-safe.
    This is the contract between NazmOS and the future AI brain.
    """
    business: BusinessInfo
    products: list[dict[str, Any]]  # ProductMemory dicts
    suppliers: list[dict[str, Any]]  # SupplierMemory dicts
    branches: list[dict[str, Any]]  # BranchMemory dicts
    constraints: dict[str, Any]
    recent_actions: list[dict[str, Any]]  # ActionHistoryItem dicts
    outcomes: list[dict[str, Any]]  # OutcomeHistoryItem dicts
    generated_at: str
    source_period: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, ensure_ascii=False)


# ── Context Builder ─────────────────────────────────────────────────────────

async def build_business_context(
    db: AsyncSession,
    business_id: UUID | str,
    max_products: int = 100,
    max_suppliers: int = 50,
    max_actions: int = 20,
    max_outcomes: int = 20,
) -> StructuredBusinessContext:
    """Build complete structured context for a business. §16 spec."""
    from app.services.product_memory import build_product_memory
    from app.services.supplier_memory import build_supplier_memory
    from app.services.branch_memory import build_branch_memory

    b = str(business_id)
    now = utcnow()
    anchor = now.date()

    # ── Business info ───────────────────────────────────────────────────
    biz_res = await db.execute(text("""
        SELECT id, name, type, city, currency, timezone, is_demo, constraints_json
        FROM businesses WHERE id = :b
    """), {"b": b})
    biz = biz_res.fetchone()
    if not biz:
        raise ValueError(f"Business {business_id} not found")

    # Inventory aggregate
    inv_res = await db.execute(text("""
        SELECT COUNT(*) AS items,
               COALESCE(SUM(inv.current_stock * COALESCE(i.cost_price, 0)), 0) AS value
        FROM inventory inv
        JOIN items i ON i.id = inv.item_id
        WHERE inv.business_id = :b AND i.is_active = true
    """), {"b": b})
    inv = inv_res.fetchone()

    constraints = biz.constraints_json if isinstance(biz.constraints_json, dict) else {}
    # Distinguish hard constraints from preferences
    hard_constraints = {}
    preferences = {}
    hard_keys = {"cash_budget", "maximum_purchase_amount", "minimum_margin_pct",
                 "maximum_discount_pct", "blocked_discount_products", "strategic_products"}
    for k, v in constraints.items():
        if k in hard_keys:
            hard_constraints[k] = v
        else:
            preferences[k] = v

    business = BusinessInfo(
        business_id=b,
        name=biz.name or "",
        business_type=biz.type or "",
        city=biz.city,
        currency=biz.currency or "SAR",
        timezone=biz.timezone or "Asia/Riyadh",
        is_demo=bool(biz.is_demo),
        total_items=int(inv.items or 0) if inv else 0,
        total_inventory_value_sar=float(inv.value or 0) if inv else 0,
        constraints=hard_constraints,
        owner_preferences=preferences,
    )

    # ── Products (top N by inventory value) ─────────────────────────────
    products_res = await db.execute(text("""
        SELECT i.id
        FROM items i
        JOIN inventory inv ON inv.item_id = i.id AND inv.business_id = i.business_id
        WHERE i.business_id = :b AND i.is_active = true
        ORDER BY (inv.current_stock * COALESCE(i.cost_price, 0)) DESC
        LIMIT :limit
    """), {"b": b, "limit": max_products})
    product_ids = [str(r.id) for r in products_res.fetchall()]

    products = []
    for pid in product_ids:
        try:
            pm = await build_product_memory(db, business_id, UUID(pid))
            products.append(pm.to_dict())
        except Exception as exc:
            logger.warning("Product memory build failed for %s: %s", pid, exc)

    # ── Suppliers ───────────────────────────────────────────────────────
    suppliers_res = await db.execute(text("""
        SELECT po.supplier_id
        FROM purchase_orders po
        WHERE po.business_id = :b AND po.supplier_id IS NOT NULL
        GROUP BY po.supplier_id
        ORDER BY MAX(po.created_at) DESC
        LIMIT :limit
    """), {"b": b, "limit": max_suppliers})
    supplier_ids = [str(r.supplier_id) for r in suppliers_res.fetchall() if r.supplier_id]

    suppliers = []
    for sid in supplier_ids:
        try:
            sm = await build_supplier_memory(db, business_id, UUID(sid))
            suppliers.append(sm.to_dict())
        except Exception as exc:
            logger.warning("Supplier memory build failed for %s: %s", sid, exc)

    # ── Branches ────────────────────────────────────────────────────────
    branches = await build_branch_memory(db, business_id)
    branch_dicts = [br.to_dict() for br in branches]

    # ── Recent actions ──────────────────────────────────────────────────
    actions_res = await db.execute(text("""
        SELECT aa.action_type, aa.created_at, aa.status, aa.outcome_json,
               aa.estimated_value_sar, aa.payload,
               maa.action_type AS money_action, maa.title,
               maa.expected_recovery_sar, maa.completed_value_sar,
               maa.evidence
        FROM agent_actions aa
        LEFT JOIN money_audit_actions maa ON maa.item_id = (aa.payload->>'item_id')::uuid
            AND maa.business_id = aa.business_id
        WHERE aa.business_id = :b
        ORDER BY aa.created_at DESC
        LIMIT :limit
    """), {"b": b, "limit": max_actions})
    action_rows = actions_res.fetchall()

    recent_actions = []
    for ar in action_rows:
        payload = ar.payload if isinstance(ar.payload, dict) else {}
        outcome = ar.outcome_json if isinstance(ar.outcome_json, dict) else {}
        evidence = ar.evidence if isinstance(ar.evidence, dict) else {}
        recent_actions.append(ActionHistoryItem(
            action_type=ar.action_type or ar.money_action or "unknown",
            action_date=ar.created_at.isoformat() if ar.created_at else "",
            reason=evidence.get("reason") or evidence.get("classification"),
            expected_recovery_sar=float(ar.expected_recovery_sar or 0) if ar.expected_recovery_sar else None,
            actual_recovery_sar=float(ar.completed_value_sar or 0) if ar.completed_value_sar else None,
            execution_status=ar.status or "unknown",
            prediction_error_pct=None,
            product_name=ar.title,
            product_id=payload.get("item_id"),
        ).to_dict())

    # ── Outcomes ────────────────────────────────────────────────────────
    outcomes_res = await db.execute(text("""
        SELECT ofb.decision_type, ofb.predicted_outcome, ofb.actual_outcome,
               ofb.delta, ofb.recorded_at
        FROM outcome_feedback ofb
        WHERE ofb.business_id = :b
        ORDER BY ofb.recorded_at DESC
        LIMIT :limit
    """), {"b": b, "limit": max_outcomes})
    outcome_rows = outcomes_res.fetchall()

    outcomes = []
    for oir in outcome_rows:
        predicted = oir.predicted_outcome if isinstance(oir.predicted_outcome, dict) else {}
        actual = oir.actual_outcome if isinstance(oir.actual_outcome, dict) else {}
        delta = oir.delta if isinstance(oir.delta, dict) else {}
        outcomes.append(OutcomeHistoryItem(
            action_type=oir.decision_type or "unknown",
            action_date=oir.recorded_at.isoformat() if oir.recorded_at else "",
            expected_impact_sar=float(predicted.get("expected_recovery_sar", 0) or 0),
            actual_impact_sar=float(actual.get("actual_recovery_sar", 0) or 0),
            success=actual.get("execution_success"),
            prediction_error_pct=delta.get("prediction_error_pct"),
            time_to_outcome_days=delta.get("time_to_outcome_days"),
            product_id=predicted.get("sku"),
        ).to_dict())

    # ── Assemble ────────────────────────────────────────────────────────
    return StructuredBusinessContext(
        business=business,
        products=products,
        suppliers=suppliers,
        branches=branch_dicts,
        constraints=constraints,
        recent_actions=recent_actions,
        outcomes=outcomes,
        generated_at=now.isoformat(),
        source_period={
            "start": (anchor - timedelta(days=90)).isoformat(),
            "end": anchor.isoformat(),
        },
    )


# ── Product Context ─────────────────────────────────────────────────────────

async def build_product_context(
    db: AsyncSession,
    business_id: UUID | str,
    item_id: UUID | str,
) -> dict[str, Any]:
    """Build focused context for one product. §17 spec.

    Answers: What is happening? Why? What happened before?
    What constraints apply? What did we do previously? What happened?
    """
    from app.services.product_memory import build_product_memory

    b = str(business_id)
    i = str(item_id)
    now = utcnow()

    # Product memory
    pm = await build_product_memory(db, business_id, item_id)

    # Owner constraints for this product
    biz_res = await db.execute(text("""
        SELECT constraints_json FROM businesses WHERE id = :b
    """), {"b": b})
    biz_row = biz_res.fetchone()
    constraints = biz_row.constraints_json if biz_row and isinstance(biz_row.constraints_json, dict) else {}
    product_constraints = {}
    blocked = constraints.get("blocked_discount_products", [])
    strategic = constraints.get("strategic_products", [])
    if i in blocked:
        product_constraints["discount_blocked"] = True
    if i in strategic:
        product_constraints["strategic"] = True
    if constraints.get("minimum_margin_pct"):
        product_constraints["minimum_margin_pct"] = constraints["minimum_margin_pct"]

    # Previous actions for this product
    actions_res = await db.execute(text("""
        SELECT action_type, created_at, status, outcome_json, estimated_value_sar, payload
        FROM agent_actions
        WHERE business_id = :b AND payload->>'item_id' = :i
        ORDER BY created_at DESC LIMIT 10
    """), {"b": b, "i": i})
    action_rows = actions_res.fetchall()
    previous_actions = []
    for ar in action_rows:
        outcome = ar.outcome_json if isinstance(ar.outcome_json, dict) else {}
        previous_actions.append({
            "action_type": ar.action_type,
            "date": ar.created_at.isoformat() if ar.created_at else None,
            "status": ar.status,
            "result": outcome.get("executed"),
            "recovery_sar": outcome.get("recovery_sar"),
        })

    # Related findings
    findings_res = await db.execute(text("""
        SELECT f.title, f.severity, f.estimated_financial_impact_sar, f.status, f.created_at
        FROM findings f
        WHERE f.business_id = :b
          AND f.affected_entities::jsonb @> CAST(:entity AS JSONB)
        ORDER BY f.created_at DESC LIMIT 5
    """), {"b": b, "entity": json.dumps([{"type": "item", "id": i}])})
    finding_rows = findings_res.fetchall()
    related_findings = [{
        "title": fr.title,
        "severity": fr.severity,
        "impact_sar": float(fr.estimated_financial_impact_sar or 0),
        "status": fr.status,
        "date": fr.created_at.isoformat() if fr.created_at else None,
    } for fr in finding_rows]

    return {
        "product": pm.to_dict(),
        "constraints": product_constraints,
        "previous_actions": previous_actions,
        "related_findings": related_findings,
        "generated_at": now.isoformat(),
    }
