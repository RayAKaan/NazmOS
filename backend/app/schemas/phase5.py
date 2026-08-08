"""Pydantic schemas for Phase 5: Agents, Planning, Simulation, Execution.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ═══════════════════════════════════════════════════════════════════════════
# Agents
# ═══════════════════════════════════════════════════════════════════════════

class AgentProposalRequest(BaseModel):
    agent_type: str = Field(..., min_length=1, max_length=50)
    context: dict[str, Any] = Field(default_factory=dict)


class AgentProposalOut(BaseModel):
    agent_type: str
    proposal_event_type: str
    payload: dict[str, Any]
    confidence: float
    reasons: list[str]


# ═══════════════════════════════════════════════════════════════════════════
# Planning
# ═══════════════════════════════════════════════════════════════════════════

class PlanStep(BaseModel):
    step_number: int = Field(..., ge=1)
    action_type: str
    description: str
    payload: dict[str, Any] = Field(default_factory=dict)
    depends_on_step: int | None = None


class PlanCreate(BaseModel):
    goal: str = Field(..., min_length=1, max_length=500)
    context: dict[str, Any] = Field(default_factory=dict)


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    goal: str
    steps: list[dict[str, Any]]
    estimated_roi: float | None
    estimated_cost: float | None
    estimated_duration_hours: float | None
    simulation_id: UUID | None
    status: str
    approved_by: UUID | None
    approved_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ═══════════════════════════════════════════════════════════════════════════
# Simulation
# ═══════════════════════════════════════════════════════════════════════════

class SimulationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    scenario: dict[str, Any] = Field(default_factory=dict)
    assumptions: dict[str, Any] = Field(default_factory=dict)


class SimulationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    name: str
    scenario: dict[str, Any]
    assumptions: dict[str, Any]
    results: dict[str, Any] | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ═══════════════════════════════════════════════════════════════════════════
# Execution
# ═══════════════════════════════════════════════════════════════════════════

class ExecutionRequest(BaseModel):
    decision_id: UUID | None = None
    plan_id: UUID | None = None
    action_type: str = Field(..., min_length=1, max_length=50)
    entity_type: str = Field(..., min_length=1, max_length=50)
    entity_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)


class ExecutionJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    decision_id: UUID | None
    plan_id: UUID | None
    action_type: str
    entity_type: str
    entity_id: UUID
    payload: dict[str, Any]
    external_reference: str | None
    status: str
    result: dict[str, Any] | None
    error: str | None
    executed_at: datetime | None
    created_at: datetime
    updated_at: datetime
