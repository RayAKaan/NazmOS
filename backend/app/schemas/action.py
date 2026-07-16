from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional


class ActionExecuteRequest(BaseModel):
    action_type: str = Field(..., pattern=r'^(RESTOCK|PRICE_CHANGE|DISCOUNT|ALERT_DISMISS)$')
    entity_type: str = Field(..., pattern=r'^(item|inventory|pricing_rule)$')
    entity_id: UUID
    new_state: dict


class ActionResponse(BaseModel):
    success: bool
    action_id: Optional[UUID]
    message: str
    external_reference: Optional[str] = None


class ActionReverseRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class ActionHistoryItem(BaseModel):
    id: UUID
    decision_id: Optional[UUID]
    source: str
    action_type: str
    entity_type: str
    entity_id: UUID
    status: str
    executed_at: Optional[datetime]
    executed_by: Optional[UUID]
    is_reversed: bool
    is_reversible: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ActionDetailResponse(BaseModel):
    id: UUID
    decision_id: Optional[UUID]
    source: str
    action_type: str
    entity_type: str
    entity_id: UUID
    previous_state: dict
    new_state: dict
    status: str
    executed_at: Optional[datetime]
    executed_by: Optional[UUID]
    external_actions: list[dict]
    is_reversible: bool
    is_reversed: bool
    reversed_at: Optional[datetime]
    reversed_by: Optional[UUID]
    reversal_reason: Optional[str]
    outcome: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


class DecisionApplyRequest(BaseModel):
    decision_id: UUID
    confirm: bool = Field(..., description="Must be true to confirm action")


class DecisionApplyResponse(BaseModel):
    success: bool
    action_id: Optional[UUID]
    message: str
    estimated_impact: Optional[dict] = None
