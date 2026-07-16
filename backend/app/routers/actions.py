from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.database.connection import get_db
from app.database.models import ExecutedAction, DecisionLog
from app.services.action_executor import ActionExecutor
from app.services.audit_service import AuditService
from app.services.multi_tenant import TenantContext
from app.schemas.action import (
    ActionExecuteRequest, ActionResponse, ActionReverseRequest,
    ActionHistoryItem, ActionDetailResponse, DecisionApplyRequest, DecisionApplyResponse,
)

router = APIRouter(prefix="/api/v1/actions", tags=["actions"])


def get_current_tenant(request: Request) -> TenantContext:
    if not hasattr(request.state, "tenant_context"):
        raise HTTPException(401, "Not authenticated")
    return request.state.tenant_context


@router.post("/execute", response_model=ActionResponse)
async def execute_action(
    data: ActionExecuteRequest,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    executor = ActionExecutor(db)
    
    item_result = await db.execute(
        select(DecisionLog).where(DecisionLog.id == data.entity_id)
    )
    item = item_result.scalar_one_or_none()
    
    previous_state = {}
    if data.entity_type == "item" and item:
        previous_state = {
            "name": item.item_name,
            "quantity": float(item.quantity) if item.quantity else 0,
        }
    elif data.entity_type == "inventory":
        previous_state = data.new_state
    
    result = await executor.execute_action(
        business_id=tenant.business_id,
        action_type=data.action_type,
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        previous_state=previous_state,
        new_state=data.new_state,
        user_id=tenant.user_id,
        source="manual",
    )
    
    if not result.success:
        raise HTTPException(400, result.message)
    
    audit = AuditService(db)
    await audit.log_decision(
        business_id=tenant.business_id,
        user_id=tenant.user_id,
        decision_id=data.entity_id if data.entity_type == "item" else None,
        decision_type=data.action_type,
        item_id=data.entity_id,
        item_name=data.new_state.get("name", "Unknown"),
        action_taken="executed",
        old_value=previous_state,
        new_value=data.new_state,
    )
    
    return result


@router.post("/{action_id}/reverse", response_model=ActionResponse)
async def reverse_action(
    action_id: UUID,
    data: ActionReverseRequest,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    action = await db.get(ExecutedAction, action_id)
    
    if not action or action.business_id != tenant.business_id:
        raise HTTPException(404, "Action not found")
    
    executor = ActionExecutor(db)
    result = await executor.reverse_action(
        action_id=action_id,
        user_id=tenant.user_id,
        reason=data.reason,
    )
    
    if not result.success:
        raise HTTPException(400, result.message)
    
    audit = AuditService(db)
    await audit.log(
        business_id=tenant.business_id,
        user_id=tenant.user_id,
        action_type="action_reversed",
        action_category="action",
        entity_type=action.entity_type,
        entity_id=action.entity_id,
        old_value=action.new_state,
        new_value=action.previous_state,
        metadata={"reason": data.reason, "original_action_id": str(action_id)},
    )
    
    return result


@router.get("/history", response_model=list[ActionHistoryItem])
async def get_action_history(
    entity_type: str = None,
    status: str = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    executor = ActionExecutor(db)
    actions = await executor.get_action_history(
        business_id=tenant.business_id,
        entity_type=entity_type,
        status=status,
        limit=limit,
        offset=offset,
    )
    return actions


@router.get("/{action_id}", response_model=ActionDetailResponse)
async def get_action_detail(
    action_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    action = await db.get(ExecutedAction, action_id)
    
    if not action or action.business_id != tenant.business_id:
        raise HTTPException(404, "Action not found")
    
    return action


@router.post("/decisions/{decision_id}/apply", response_model=DecisionApplyResponse)
async def apply_decision(
    decision_id: UUID,
    data: DecisionApplyRequest,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    if not data.confirm:
        raise HTTPException(400, "Must confirm to apply decision")
    
    decision = await db.get(DecisionLog, decision_id)
    
    if not decision or decision.business_id != tenant.business_id:
        raise HTTPException(404, "Decision not found")
    
    if decision.was_applied:
        raise HTTPException(400, "Decision already applied")
    
    executor = ActionExecutor(db)
    
    new_state = {}
    if decision.action_type == "RESTOCK":
        new_state = {
            "current_stock": float(decision.quantity) if decision.quantity else 0,
            "item_name": decision.item_name,
        }
    
    result = await executor.execute_action(
        business_id=tenant.business_id,
        action_type=decision.action_type,
        entity_type="item",
        entity_id=decision.item_id,
        previous_state={},
        new_state=new_state,
        decision_id=decision_id,
        user_id=tenant.user_id,
        source="ai_approved",
    )
    
    return DecisionApplyResponse(
        success=result.success,
        action_id=result.action_id,
        message=result.message,
        estimated_impact={"estimated_value": float(decision.estimated_value)} if decision.estimated_value else None,
    )
