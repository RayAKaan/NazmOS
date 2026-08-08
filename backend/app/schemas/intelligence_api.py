"""Pydantic schemas for Phase 7: Unified Intelligence API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.decision import DecisionExplainOut, DecisionOut
from app.schemas.events import EventIngest
from app.schemas.phase5 import ExecutionJobOut, PlanOut, SimulationOut


class AnalyzeRequest(BaseModel):
    query: str | None = Field(default=None, max_length=500)
    decision_type: str | None = Field(default=None, max_length=50)
    context: dict[str, Any] = Field(default_factory=dict)


class AnalyzeOut(BaseModel):
    query: str | None
    summary: str
    memory_snapshot: dict[str, Any]
    graph_evidence: list[dict[str, Any]]
    context_evidence: dict[str, Any]
    recent_event_count: int
    decision: DecisionOut | None
    sources: list[str]


class PredictRequest(BaseModel):
    target: str = Field(..., pattern="^(sales|demand|stock)$")
    horizon_days: int = Field(default=7, ge=1, le=90)
    item_id: str | None = Field(default=None, max_length=255)


class PredictOut(BaseModel):
    target: str
    horizon_days: int
    item_id: str | None
    predicted_value: float
    unit: str
    confidence: float
    basis: list[str]


class ExplainRequest(BaseModel):
    decision_id: UUID


class PlanRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=500)
    context: dict[str, Any] = Field(default_factory=dict)


class SimulateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    scenario: dict[str, Any] = Field(default_factory=dict)
    assumptions: dict[str, Any] = Field(default_factory=dict)


class ExecuteRequest(BaseModel):
    action_type: str = Field(..., min_length=1, max_length=50)
    entity_type: str = Field(..., min_length=1, max_length=50)
    entity_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)
    decision_id: UUID | None = None
    plan_id: UUID | None = None


class ObserveRequest(BaseModel):
    event: EventIngest


class ObserveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: UUID
    event_type: str
    processed: bool
    correlation_id: UUID | None


class RememberRequest(BaseModel):
    memory_type: str = Field(..., min_length=1, max_length=50)
    operation: str = Field(default="set", pattern="^(set|goal)$")
    path: str | None = Field(default=None, max_length=500)
    value: Any = None
    goals: dict[str, Any] | None = None


class RememberOut(BaseModel):
    memory_type: str
    data: dict[str, Any]
    version: int


class ReasonRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    context: dict[str, Any] = Field(default_factory=dict)


class ReasonOut(BaseModel):
    answer: str
    decision: DecisionOut | None
    plan: PlanOut | None
    sources: list[str]
