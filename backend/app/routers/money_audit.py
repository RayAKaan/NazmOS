from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import User, get_db
from app.config import get_settings
from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access
from app.services.recovery_intelligence import money, simulate_action_options
from app.services.money_audit_service import (
    generate_money_audit,
    get_latest_money_audit,
    get_money_audit,
    printable_html,
    update_action_status,
    whatsapp_summary,
)
from app.services.intelligence_api_client import IntelligenceAPIClient
from app.utils.clock import utcnow
from app.services.action_executor import ActionExecutor
from app.services.evidence_package import AuditEvidencePackage
from app.services.llm_orchestrator import LLMOrchestrator

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/money-audit", tags=["Money Audit"])
settings = get_settings()


class GenerateAuditRequest(BaseModel):
    business_id: UUID


class ABCompareRequest(BaseModel):
    max_ai_calls: int = Field(default=4, ge=0, le=25)


class ActionStatusRequest(BaseModel):
    business_id: UUID
    notes: Optional[str] = None
    completed_value_sar: Optional[float] = Field(default=None, ge=0)
    approval_channel: str = "dashboard"


async def _audit_business_id(db: AsyncSession, audit_id: UUID | str) -> str:
    result = await db.execute(text("SELECT business_id FROM money_audits WHERE id = :id"), {"id": str(audit_id)})
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Money Audit not found")
    return str(row.business_id)


async def _recalculate_audit_totals(db: AsyncSession, audit_id: str) -> None:
    """Recompute approved/recovered totals on money_audits from action rows."""
    await db.execute(text("""
        UPDATE money_audits SET
            money_approved_sar = (
                SELECT COALESCE(SUM(expected_recovery_sar_v2), 0)
                FROM money_audit_actions
                WHERE audit_id = :id AND status IN ('approved', 'executed', 'completed')
            ),
            money_recovered_sar = (
                SELECT COALESCE(SUM(completed_value_sar), 0)
                FROM money_audit_actions
                WHERE audit_id = :id AND status = 'completed'
            )
        WHERE id = :id
    """), {"id": str(audit_id)})


async def _enrich_audit_with_intelligence(
    db: AsyncSession,
    business_id: UUID,
    audit: dict,
) -> dict:
    """Phase 7: enrich a Money Audit with intelligence-driven insights."""
    try:
        client = IntelligenceAPIClient(db, business_id)
        analysis = await client.analyze(query="Money audit recovery actions")
        decision = analysis.get("decision")
        intelligence_actions = []
        if decision:
            ranked = decision.ranked_action
            if ranked:
                intelligence_actions.append({
                    "action_type": ranked.get("action_type"),
                    "title": ranked.get("title"),
                    "confidence": float(decision.confidence) if decision.confidence else None,
                    "expected_roi": ranked.get("expected_roi"),
                    "reasons": ranked.get("reasons", []),
                })
            for candidate in (decision.candidate_actions or [])[:3]:
                if candidate != ranked:
                    intelligence_actions.append({
                        "action_type": candidate.get("action_type"),
                        "title": candidate.get("title"),
                        "confidence": candidate.get("confidence"),
                        "expected_roi": candidate.get("expected_roi"),
                        "reasons": candidate.get("reasons", []),
                    })
        audit["intelligence_summary"] = analysis.get("summary")
        audit["intelligence_actions"] = intelligence_actions
        audit["intelligence_sources"] = analysis.get("sources", [])
    except Exception:
        # Intelligence enrichment is best-effort; never break the audit.
        audit["intelligence_summary"] = None
        audit["intelligence_actions"] = []
        audit["intelligence_sources"] = []
    return audit


@router.get("/current")
async def current_money_audit(
    business_id: UUID = Query(...),
    auto_generate: bool = Query(default=True, description="Generate first audit if no audit exists yet."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, str(business_id), current_user)
    audit = await get_latest_money_audit(db, business_id)
    if audit:
        return await _enrich_audit_with_intelligence(db, business_id, audit)
    if not auto_generate:
        return {"audit": None, "message": "No Money Audit generated yet."}
    audit = await generate_money_audit(db, business_id, current_user.id)
    return await _enrich_audit_with_intelligence(db, business_id, audit)


@router.post("/generate")
async def generate_audit(
    payload: GenerateAuditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, str(payload.business_id), current_user)
    audit = await generate_money_audit(db, payload.business_id, current_user.id)
    return await _enrich_audit_with_intelligence(db, payload.business_id, audit)


@router.get("/{audit_id}")
async def read_money_audit(
    audit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business_id = await _audit_business_id(db, audit_id)
    await assert_business_access(db, business_id, current_user)
    try:
        return await get_money_audit(db, audit_id)
    except ValueError:
        raise HTTPException(404, "Money Audit not found")


@router.get("/{audit_id}/whatsapp-summary", response_class=PlainTextResponse)
async def read_whatsapp_summary(
    audit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business_id = await _audit_business_id(db, audit_id)
    await assert_business_access(db, business_id, current_user)
    audit = await get_money_audit(db, audit_id)
    return whatsapp_summary(audit)


@router.get("/{audit_id}/print", response_class=HTMLResponse)
async def read_printable_report(
    audit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business_id = await _audit_business_id(db, audit_id)
    await assert_business_access(db, business_id, current_user)
    audit = await get_money_audit(db, audit_id)
    return HTMLResponse(printable_html(audit))




@router.post("/actions/{action_id}/simulate")
async def simulate_action(
    action_id: UUID,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return transparent action scenarios. Every value is explicitly an estimate."""
    business_id = payload.get("business_id")
    if not business_id:
        raise HTTPException(422, "business_id is required")
    await assert_business_access(db, str(business_id), current_user)
    result = await db.execute(text("""
        SELECT a.action_type, a.item_id, i.cost_price, i.sell_price, inv.current_stock
        FROM money_audit_actions a
        LEFT JOIN items i ON i.id = a.item_id
        LEFT JOIN inventory inv ON inv.item_id = a.item_id AND inv.business_id = a.business_id
        WHERE a.id = :id AND a.business_id = :business_id
    """), {"id": str(action_id), "business_id": str(business_id)})
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Money Audit action not found")
    prices = await db.execute(text("""
        SELECT unit_price FROM transactions
        WHERE business_id = :business_id AND item_id = :item_id AND transaction_type = 'sale' AND unit_price > 0
        ORDER BY transaction_at DESC LIMIT 200
    """), {"business_id": str(business_id), "item_id": str(row.item_id)})
    historical_prices = [money(r.unit_price) for r in prices.fetchall()]
    options = simulate_action_options(
        action_type=row.action_type, stock=money(row.current_stock), cost=money(row.cost_price),
        sell=money(row.sell_price), historical_prices=historical_prices,
        branch_demand_units=money(payload["branch_demand_units"]) if payload.get("branch_demand_units") is not None else None,
    )
    return {"action_id": str(action_id), "estimate_only": True, "options": options}

@router.post("/actions/{action_id}/approve")
async def approve_action(
    action_id: UUID,
    payload: ActionStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, str(payload.business_id), current_user)
    try:
        return await update_action_status(
            db,
            action_id,
            payload.business_id,
            "approved",
            notes=payload.notes,
            approval_channel=payload.approval_channel,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/actions/{action_id}/reject")
async def reject_action(
    action_id: UUID,
    payload: ActionStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, str(payload.business_id), current_user)
    try:
        return await update_action_status(
            db,
            action_id,
            payload.business_id,
            "rejected",
            notes=payload.notes,
            approval_channel=payload.approval_channel,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/actions/{action_id}/complete")
async def complete_action(
    action_id: UUID,
    payload: ActionStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, str(payload.business_id), current_user)
    try:
        result = await update_action_status(
            db,
            action_id,
            payload.business_id,
            "completed",
            notes=payload.notes,
            completed_value_sar=payload.completed_value_sar,
            approval_channel=payload.approval_channel,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))

    # Record the predicted-vs-actual outcome so future audits calibrate.
    try:
        await _record_outcome_for_action(db, action_id, payload)
    except Exception:
        logger.exception("Failed to persist outcome feedback for action %s", action_id)

    return result


async def _record_outcome_for_action(
    db: AsyncSession, action_id: UUID, payload: ActionStatusRequest
) -> None:
    """Build an OutcomeRecord from the action row and persist it."""
    from app.services.outcome_tracker import OutcomeTracker, OutcomeRecord

    row_result = await db.execute(text("""
        SELECT a.business_id, a.item_id, a.action_type, a.expected_recovery_sar_v2,
               a.recoverable_value_low_sar, a.recoverable_value_high_sar,
               a.evidence, a.notes, a.audit_id, i.sku
        FROM money_audit_actions a
        LEFT JOIN items i ON i.id = a.item_id
        WHERE a.id = :id
    """), {"id": str(action_id)})
    action = row_result.fetchone()
    if not action:
        return

    evidence = action.evidence if isinstance(action.evidence, dict) else {}
    actual = float(payload.completed_value_sar) if payload.completed_value_sar is not None else 0.0
    # Predicted-basis chain (deterministic, mirrors money_audit_service):
    #   explicit v2 estimate > midpoint of recoverable range > audit-level
    #   risk category total for this action type. The last resort keeps the
    #   prediction error meaningful when per-action estimates were never set.
    expected = float(action.expected_recovery_sar_v2) if action.expected_recovery_sar_v2 is not None else None
    if expected is None:
        low = float(action.recoverable_value_low_sar or 0)
        high = float(action.recoverable_value_high_sar or 0)
        if high > 0:
            expected = round((low + high) / 2, 2)
    if expected is None:
        audit_risk_result = await db.execute(text("""
            SELECT stockout_risk_value_sar, dead_stock_value_sar, overstock_value_sar,
                   margin_leakage_sar
            FROM money_audits WHERE id = :id
        """), {"id": str(action.audit_id)})
        audit_row = audit_risk_result.fetchone()
        if audit_row:
            category_map = {
                "reorder": "stockout_risk_value_sar",
                "restock": "stockout_risk_value_sar",
                "reorder_critical": "stockout_risk_value_sar",
                "discount": "dead_stock_value_sar",
                "clearance": "dead_stock_value_sar",
                "transfer": "overstock_value_sar",
                "margin_fix": "margin_leakage_sar",
                "price_change": "margin_leakage_sar",
            }
            attr = category_map.get(action.action_type or "")
            if attr:
                candidate = getattr(audit_row, attr, None)
                if candidate is not None and float(candidate) > 0:
                    expected = round(float(candidate), 2)

    record = OutcomeRecord(
        action_id=str(action_id),
        sku=action.sku or "",
        business_id=str(action.business_id),
        action_type=action.action_type or "",
        decision_source=str(evidence.get("decision_source", "DETERMINISTIC")),
        ai_confidence=float(evidence.get("ai_confidence") or 0.0),
        recoverable_low_sar=float(action.recoverable_value_low_sar or 0),
        recoverable_high_sar=float(action.recoverable_value_high_sar or 0),
        expected_recovery_sar=expected,
        recovery_confidence=str(evidence.get("recovery_confidence", "MEDIUM")),
        actual_recovery_sar=actual,
        execution_success=True,
        owner_accepted=True,
        mode="EXECUTED",
        is_simulated=False,
        completed_at=datetime.now(timezone.utc).isoformat(),
    )
    tracker = OutcomeTracker()
    tracker.record(record)
    await tracker.record_and_persist(record, db)


class ExecuteActionRequest(BaseModel):
    business_id: UUID
    quantity: Optional[float] = Field(default=None, ge=0)


@router.post("/actions/{action_id}/execute")
async def execute_action(
    action_id: UUID,
    payload: ExecuteActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute an approved money audit action.

    For supported action types (reorder/restock, price_change), this triggers
    the ActionExecutor to update inventory or prices in the database.

    For manual action types (discount, recovery_match, margin_fix), this marks
    the action as executed with a note that external execution is required.

    Every execution is recorded as a SIMULATION / ESTIMATE unless actual
    recovery is measured through the complete endpoint.
    """
    await assert_business_access(db, str(payload.business_id), current_user)

    # Fetch the action and validate status
    result = await db.execute(text("""
        SELECT id, audit_id, business_id, item_id, action_type, status,
               expected_recovery_sar_v2, recoverable_value_low_sar, recoverable_value_high_sar
        FROM money_audit_actions
        WHERE id = :id AND business_id = :business_id
    """), {"id": str(action_id), "business_id": str(payload.business_id)})
    action = result.fetchone()
    if not action:
        raise HTTPException(404, "Money Audit action not found")
    if action.status != "approved":
        raise HTTPException(400, f"Action must be approved before execution. Current status: {action.status}")

    # Map money audit action types to ActionExecutor action types
    action_type_map = {
        "reorder": "RESTOCK",
        "restock": "RESTOCK",
        "price_change": "PRICE_CHANGE",
        "pricing_increase": "PRICE_CHANGE",
        "pricing_decrease": "PRICE_CHANGE",
        "discount": "DISCOUNT",
    }
    executor_type = action_type_map.get(action.action_type)

    if executor_type is None:
        # Unsupported action type for automated execution — mark as executed manually
        await db.execute(text("""
            UPDATE money_audit_actions
            SET status = 'completed',
                completed_at = NOW(),
                completed_value_sar = 0,
                notes = COALESCE(notes, '') || ' [Executed manually — action type not automated]',
                updated_at = NOW()
            WHERE id = :id
        """), {"id": str(action_id)})
        await _recalculate_audit_totals(db, str(action.audit_id))
        await db.commit()
        return await get_money_audit(db, str(action.audit_id))

    if not action.item_id:
        raise HTTPException(400, "Action has no linked item; automated execution requires an item")

    # Build previous/new state for ActionExecutor
    item_result = await db.execute(text("""
        SELECT i.cost_price, i.sell_price, inv.current_stock,
               inv.safety_stock, sup.min_order_sar AS supplier_moq
        FROM items i
        LEFT JOIN inventory inv ON inv.item_id = i.id AND inv.business_id = :business_id
        LEFT JOIN suppliers sup ON sup.id = inv.supplier_id
        WHERE i.id = :item_id
    """), {"business_id": str(payload.business_id), "item_id": str(action.item_id)})
    item_row = item_result.fetchone()

    previous_state: dict = {}
    new_state: dict = {}
    current_stock = float(item_row.current_stock) if item_row and item_row.current_stock is not None else 0.0
    sell_price = float(item_row.sell_price) if item_row and item_row.sell_price is not None else 0.0

    # Reorder quantity policy (deterministic):
    #   explicit request quantity > replenish-to-safety-stock > supplier MOQ > 10-unit default
    moq = float(item_row.supplier_moq) if item_row and item_row.supplier_moq else 0.0
    safety = float(item_row.safety_stock) if item_row and item_row.safety_stock else 0.0
    derived_qty = max(moq, safety - current_stock, moq if moq > 0 else 10.0)
    quantity = float(payload.quantity) if payload.quantity is not None else round(derived_qty, 2)

    if executor_type == "RESTOCK":
        previous_state = {"current_stock": current_stock}
        new_state = {"current_stock": round(current_stock + quantity, 2)}
    elif executor_type == "PRICE_CHANGE":
        previous_state = {"sell_price": sell_price}
        new_state = {"sell_price": sell_price}
    elif executor_type == "DISCOUNT":
        previous_state = {"sell_price": sell_price}
        new_state = {"sell_price": sell_price}

    executor = ActionExecutor(db)
    exec_result = await executor.execute_action(
        business_id=UUID(str(payload.business_id)),
        action_type=executor_type,
        entity_type="item",
        entity_id=UUID(str(action.item_id)),
        previous_state=previous_state,
        new_state=new_state,
        user_id=current_user.id,
        source="money_audit",
    )

    if not exec_result.success:
        raise HTTPException(500, f"Execution failed: {exec_result.message}")

    # NOTE: ActionExecutor has already applied the business-state mutation
    # (_execute_restock updates inventory.current_stock; _execute_price_change
    # updates items.sell_price) and recorded it in executed_actions.

    # Update money audit action status
    await db.execute(text("""
        UPDATE money_audit_actions
        SET status = 'completed',
            completed_at = NOW(),
            completed_value_sar = 0,
            notes = COALESCE(notes, '') || ' [Executed via NazmOS — actual recovery pending measurement]',
            updated_at = NOW()
        WHERE id = :id
    """), {"id": str(action_id)})
    await _recalculate_audit_totals(db, str(action.audit_id))
    await db.commit()

    return await get_money_audit(db, str(action.audit_id))


@router.get("/{audit_id}/evidence")
async def get_audit_evidence(
    audit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the structured evidence package for an audit.

    This is the deterministic evidence that AI reasoning receives.
    Contains ONLY trusted structured facts — no untrusted text fields
    become AI instructions.
    """
    business_id = await _audit_business_id(db, audit_id)
    await assert_business_access(db, business_id, current_user)

    from app.services.evidence_package import build_item_evidence, AuditEvidencePackage, BusinessContext

    # Fetch audit actions with item data
    result = await db.execute(text("""
        SELECT a.id, a.item_id, a.action_type, a.title, a.description,
               a.expected_recovery_sar_v2, a.recoverable_value_low_sar, a.recoverable_value_high_sar,
               a.recovery_confidence, a.evidence,
               i.sku, i.name AS item_name, i.cost_price, i.sell_price,
               COALESCE(inv.current_stock, 0) AS current_stock,
               inv.safety_stock, inv.last_restocked, inv.lead_time_days,
               sup.name_en AS supplier_name, sup.lead_time_days AS supplier_lead_time_days,
               sup.min_order_sar AS supplier_moq
        FROM money_audit_actions a
        LEFT JOIN items i ON i.id = a.item_id
        LEFT JOIN inventory inv ON inv.item_id = a.item_id AND inv.business_id = :business_id
        LEFT JOIN suppliers sup ON sup.id = inv.supplier_id
        WHERE a.audit_id = :audit_id AND a.business_id = :business_id
        ORDER BY a.priority, a.created_at
    """), {"audit_id": str(audit_id), "business_id": business_id})
    rows = result.fetchall()

    # Fetch business context
    biz_result = await db.execute(text("""
        SELECT type, constraints_json FROM businesses WHERE id = :business_id
    """), {"business_id": business_id})
    biz = biz_result.fetchone()
    business_type = biz.type if biz else "retail"
    constraints = biz.constraints_json if biz and isinstance(biz.constraints_json, dict) else {}

    # Fetch audit summary for totals
    audit_result = await db.execute(text("""
        SELECT inventory_value_sar, capital_at_risk_sar, recoverable_value_high_sar
        FROM money_audits WHERE id = :audit_id
    """), {"audit_id": str(audit_id)})
    audit_row = audit_result.fetchone()

    # Fetch historical outcomes for this business (real outcome_feedback schema)
    outcomes_result = await db.execute(text("""
        SELECT decision_type, predicted_outcome, actual_outcome, delta
        FROM outcome_feedback
        WHERE business_id = :business_id AND decision_type IS NOT NULL
        ORDER BY created_at DESC LIMIT 20
    """), {"business_id": business_id})
    historical_outcomes = []
    for o in outcomes_result.fetchall():
        predicted = o.predicted_outcome if isinstance(o.predicted_outcome, dict) else {}
        actual = o.actual_outcome if isinstance(o.actual_outcome, dict) else {}
        delta = o.delta if isinstance(o.delta, dict) else {}
        historical_outcomes.append({
            "action_type": o.decision_type,
            # §2 Financial Semantic Safety: this is a recovery estimate, not an impact.
            "expected_recovery_sar": float(predicted.get("expected_recovery_sar") or 0),
            "actual_recovery_sar": float(actual.get("actual_recovery_sar") or 0),
            "prediction_error_pct": delta.get("prediction_error_pct"),
            "sku": str(predicted.get("sku", "")),
        })

    # Build evidence for each item
    from app.services.po_service import get_confirmed_inbound_map
    inbound_map = await get_confirmed_inbound_map(db, business_id=business_id, as_of=utcnow().date())
    items = []
    for row in rows:
        evidence_data = row.evidence if isinstance(row.evidence, dict) else {}
        qty_30d = Decimal(str(evidence_data.get("qty_30d", 0)))
        qty_prior = Decimal(str(evidence_data.get("qty_30d", 0)))  # Use same as approximation
        days_since = evidence_data.get("last_sold_days")
        _inbound_entry = inbound_map.get(str(row.item_id))

        item_evidence = build_item_evidence(
            sku=row.sku or "",
            product_name=row.item_name or "",
            classification=evidence_data.get("classification", "UNKNOWN"),
            stock=Decimal(str(row.current_stock)),
            cost=Decimal(str(row.cost_price)) if row.cost_price else Decimal("0"),
            sell=Decimal(str(row.sell_price)) if row.sell_price else Decimal("0"),
            qty_30d=qty_30d,
            qty_prior=qty_prior,
            days_since_last_sale=days_since,
            inventory_age_days=None,
            confirmed_inbound=_inbound_entry.confirmed_inbound_qty if _inbound_entry else Decimal("0"),
            ghost_po_risk=bool(_inbound_entry and _inbound_entry.ghost_po_risk),
            supplier_lead_time=row.supplier_lead_time_days,
            supplier_moq=Decimal(str(row.supplier_moq)) if row.supplier_moq else None,
            supplier_name=row.supplier_name,
            candidate_actions=[row.action_type] if row.action_type else [],
            historical_outcomes=historical_outcomes[:5],
        )
        items.append(item_evidence.to_dict())

    business_ctx = BusinessContext(
        business_id=business_id,
        business_type=business_type,
        total_inventory_value_sar=float(audit_row.inventory_value_sar) if audit_row and audit_row.inventory_value_sar else 0,
        total_capital_at_risk_sar=float(audit_row.capital_at_risk_sar) if audit_row and audit_row.capital_at_risk_sar else 0,
        total_recoverable_high_sar=float(audit_row.recoverable_value_high_sar) if audit_row and audit_row.recoverable_value_high_sar else 0,
        cash_budget=constraints.get("cash_budget"),
        max_discount_pct=constraints.get("max_discount_pct"),
        blocked_discount_products=list(map(str, constraints.get("blocked_discount_products", []))),
        strategic_products=list(map(str, constraints.get("strategic_products", []))),
        blocked_transfer_routes=list(constraints.get("blocked_transfer_routes", [])),
        minimum_margin_pct=constraints.get("minimum_margin_pct"),
        previous_outcomes=historical_outcomes,
    )

    package = AuditEvidencePackage(
        business=business_ctx,
        items=[],
        classification_summary={},
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    # Manually set items since we already built them
    package_dict = package.to_dict()
    package_dict["items"] = items
    package_dict["business"] = business_ctx.to_dict()
    package_dict["historical_outcomes"] = historical_outcomes

    return package_dict


@router.post("/{audit_id}/ab-compare")
async def ab_compare_audit(
    audit_id: UUID,
    payload: Optional[ABCompareRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run A/B/C counterfactual comparison for an audit.

    MODE_A: Deterministic only
    MODE_B: Deterministic + AI reasoning
    MODE_C: Deterministic + AI + historical outcomes

    All three modes receive the SAME business state.
    Returns decision distributions and comparison metrics.

    Optional body {"max_ai_calls": 1-10} caps triaged AI calls for this run
    (V9 experiment quota control). Default comes from settings.
    """
    business_id = await _audit_business_id(db, audit_id)
    await assert_business_access(db, business_id, current_user)

    from app.services.ab_decision_framework import run_counterfactual_audit, compare_modes
    from app.services.evidence_package import build_item_evidence, BusinessContext

    # Fetch audit actions
    result = await db.execute(text("""
        SELECT a.id, a.item_id, a.action_type, a.title, a.description,
               a.expected_recovery_sar_v2, a.recoverable_value_low_sar, a.recoverable_value_high_sar,
               a.recovery_confidence, a.evidence,
               i.sku, i.name AS item_name, i.cost_price, i.sell_price,
               COALESCE(inv.current_stock, 0) AS current_stock,
               inv.safety_stock, inv.last_restocked, inv.lead_time_days,
               sup.name_en AS supplier_name, sup.lead_time_days AS supplier_lead_time_days,
               sup.min_order_sar AS supplier_moq
        FROM money_audit_actions a
        LEFT JOIN items i ON i.id = a.item_id
        LEFT JOIN inventory inv ON inv.item_id = a.item_id AND inv.business_id = :business_id
        LEFT JOIN suppliers sup ON sup.id = inv.supplier_id
        WHERE a.audit_id = :audit_id AND a.business_id = :business_id
    """), {"audit_id": str(audit_id), "business_id": business_id})
    rows = result.fetchall()

    # Fetch business context
    biz_result = await db.execute(text("""
        SELECT type, constraints_json FROM businesses WHERE id = :business_id
    """), {"business_id": business_id})
    biz = biz_result.fetchone()
    business_type = biz.type if biz else "retail"
    constraints = biz.constraints_json if biz and isinstance(biz.constraints_json, dict) else {}

    # Build evidence items — ONE per unique SKU (an item may have multiple
    # suggested actions; the A/B/C comparison must score each ITEM once).
    from app.services.po_service import get_confirmed_inbound_map
    inbound_map = await get_confirmed_inbound_map(db, business_id=business_id, as_of=utcnow().date())
    items = []
    seen_skus: set[str] = set()
    for row in rows:
        sku_key = (row.sku or "").strip()
        if sku_key and sku_key in seen_skus:
            continue
        if sku_key:
            seen_skus.add(sku_key)
        evidence_data = row.evidence if isinstance(row.evidence, dict) else {}
        qty_30d = Decimal(str(evidence_data.get("qty_30d", 0)))
        _inbound_entry = inbound_map.get(str(row.item_id))

        item_evidence = build_item_evidence(
            sku=row.sku or "",
            product_name=row.item_name or "",
            classification=evidence_data.get("classification", "UNKNOWN"),
            stock=Decimal(str(row.current_stock)),
            cost=Decimal(str(row.cost_price)) if row.cost_price else Decimal("0"),
            sell=Decimal(str(row.sell_price)) if row.sell_price else Decimal("0"),
            qty_30d=qty_30d,
            qty_prior=qty_30d,
            days_since_last_sale=evidence_data.get("last_sold_days"),
            inventory_age_days=None,
            confirmed_inbound=_inbound_entry.confirmed_inbound_qty if _inbound_entry else Decimal("0"),
            ghost_po_risk=bool(_inbound_entry and _inbound_entry.ghost_po_risk),
            supplier_lead_time=row.supplier_lead_time_days,
            supplier_moq=Decimal(str(row.supplier_moq)) if row.supplier_moq else None,
            supplier_name=row.supplier_name,
        )
        items.append(item_evidence)

    business_ctx = BusinessContext(
        business_id=business_id,
        business_type=business_type,
        total_inventory_value_sar=0,
        total_capital_at_risk_sar=0,
        total_recoverable_high_sar=0,
        cash_budget=constraints.get("cash_budget"),
        max_discount_pct=constraints.get("max_discount_pct"),
        blocked_discount_products=list(map(str, constraints.get("blocked_discount_products", []))),
        strategic_products=list(map(str, constraints.get("strategic_products", []))),
        blocked_transfer_routes=list(constraints.get("blocked_transfer_routes", [])),
        minimum_margin_pct=constraints.get("minimum_margin_pct"),
    )

    # Historical outcomes keyed by SKU for MODE_C (real outcome_feedback schema)
    outcomes_result = await db.execute(text("""
        SELECT decision_type, predicted_outcome, actual_outcome, delta
        FROM outcome_feedback
        WHERE business_id = :business_id AND decision_type IS NOT NULL
        ORDER BY created_at DESC LIMIT 50
    """), {"business_id": business_id})
    historical_by_sku: dict[str, list[dict]] = {}
    try:
        outcome_rows = outcomes_result.fetchall()
    except Exception:
        outcome_rows = []
    for o in outcome_rows:
        predicted = o.predicted_outcome if isinstance(o.predicted_outcome, dict) else {}
        actual = o.actual_outcome if isinstance(o.actual_outcome, dict) else {}
        delta = o.delta if isinstance(o.delta, dict) else {}
        sku = str(predicted.get("sku", "") or "")
        entry = {
            "action_type": o.decision_type,
            # §2 Financial Semantic Safety: this is a recovery estimate, not an impact.
            "expected_recovery_sar": float(predicted.get("expected_recovery_sar") or 0),
            "actual_recovery_sar": float(actual.get("actual_recovery_sar") or 0),
            "prediction_error_pct": delta.get("prediction_error_pct"),
        }
        if sku:
            historical_by_sku.setdefault(sku, []).append(entry)
        else:
            historical_by_sku.setdefault("*", []).append(entry)

    package = AuditEvidencePackage(
        business=business_ctx,
        items=items,
        classification_summary={},
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    orchestrator = LLMOrchestrator()

    async def llm_caller(system_prompt: str, user_prompt: str) -> str:
        response_text = await orchestrator.chat_completion(system_prompt, user_prompt)
        if response_text is None:
            raise RuntimeError("LLM unavailable (all providers failed or circuit open)")
        return response_text

    try:
        requested_budget = payload.max_ai_calls if payload else getattr(settings, "AI_MAX_CALLS_PER_AUDIT", 4)
        ab_result = await run_counterfactual_audit(
            package,
            llm_caller=llm_caller,
            historical_outcomes=historical_by_sku,
            max_ai_calls=max(0, min(int(requested_budget), 25)),
            include_mode_c=True,
            # Provider free tiers are RPM-limited; pace so one A/B run stays
            # far under quota and the circuit breaker never trips.
            ai_call_delay_s=2.0,
        )
        comparison = compare_modes(ab_result)
        return {
            "audit_id": str(audit_id),
            "mode_a": [r.to_dict() for r in ab_result.mode_a],
            "mode_b": [r.to_dict() for r in ab_result.mode_b],
            "mode_c": [r.to_dict() for r in ab_result.mode_c],
            "comparison": comparison,
        }
    except Exception as e:
        logger.exception("ab-compare failed for audit %s", audit_id)
        return {
            "audit_id": str(audit_id),
            "error": str(e),
            "mode_a": [],
            "mode_b": [],
            "mode_c": [],
            "comparison": {},
        }


class TimeMachineRequest(BaseModel):
    business_id: UUID
    horizon_days: int = Field(default=30, ge=1, le=90)


@router.post("/{audit_id}/time-machine")
async def time_machine(
    audit_id: UUID,
    payload: TimeMachineRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Simulate 'What happens if I do nothing?' vs 'NazmOS recommendation'.

    Every result is labeled:
      SIMULATION / ESTIMATE

    Never call simulated money ACTUAL RECOVERY.
    Supports 30, 60, or 90 day horizons.
    """
    business_id = await _audit_business_id(db, audit_id)
    await assert_business_access(db, business_id, current_user)

    from app.services.time_machine import simulate_time_machine

    # Fetch audit actions with item data
    result = await db.execute(text("""
        SELECT a.id, a.item_id, a.action_type, a.title, a.description,
               a.expected_recovery_sar_v2, a.recoverable_value_low_sar, a.recoverable_value_high_sar,
               a.recovery_confidence, a.evidence,
               i.sku, i.name AS item_name, i.cost_price, i.sell_price,
               COALESCE(inv.current_stock, 0) AS current_stock,
               inv.safety_stock, inv.lead_time_days,
               sup.name_en AS supplier_name, sup.lead_time_days AS supplier_lead_time_days
        FROM money_audit_actions a
        LEFT JOIN items i ON i.id = a.item_id
        LEFT JOIN inventory inv ON inv.item_id = a.item_id AND inv.business_id = :business_id
        LEFT JOIN suppliers sup ON sup.id = inv.supplier_id
        WHERE a.audit_id = :audit_id AND a.business_id = :business_id
    """), {"audit_id": str(audit_id), "business_id": business_id})
    rows = result.fetchall()

    # Build item data for time machine
    items = []
    for row in rows:
        evidence_data = row.evidence if isinstance(row.evidence, dict) else {}
        daily_velocity = float(evidence_data.get("qty_30d", 0)) / 30 if evidence_data.get("qty_30d") else 0

        items.append({
            "sku": row.sku or "",
            "product_name": row.item_name or "",
            "classification": evidence_data.get("classification", "UNKNOWN"),
            "current_stock": float(row.current_stock) if row.current_stock else 0,
            "cost_price_sar": float(row.cost_price) if row.cost_price else 0,
            "sell_price_sar": float(row.sell_price) if row.sell_price else 0,
            "daily_velocity": daily_velocity,
            "days_of_supply": float(row.current_stock) / daily_velocity if daily_velocity > 0 and row.current_stock else None,
            "action_type": row.action_type,
            "recoverable_low_sar": float(row.recoverable_value_low_sar) if row.recoverable_value_low_sar else 0,
            "recoverable_high_sar": float(row.recoverable_value_high_sar) if row.recoverable_value_high_sar else 0,
        })

    tm_result = simulate_time_machine(items=items, horizon_days=payload.horizon_days)
    return tm_result.to_dict()
