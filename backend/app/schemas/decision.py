"""Pydantic schemas for the Decision & Explainability Engine (Phase 4).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CandidateAction(BaseModel):
    action_type: str
    title: str
    payload: dict[str, Any]
    expected_roi: float | None = None
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    urgency: float = Field(default=0.0, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class DecisionGenerateRequest(BaseModel):
    decision_type: str | None = Field(default=None, max_length=50)
    input_event_ids: list[UUID] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    decision_type: str
    input_event_ids: list[str]
    rules_applied: list[str]
    memory_snapshot: dict[str, Any] | None
    graph_evidence: dict[str, Any] | None
    context_evidence: dict[str, Any] | None
    candidate_actions: list[dict[str, Any]]
    ranked_action: dict[str, Any] | None
    confidence: float
    expected_roi: float | None
    risk_score: float
    urgency: float
    status: str
    approved_by: UUID | None
    approved_at: datetime | None
    explanation: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class DecisionExplainOut(BaseModel):
    decision_id: UUID
    decision_type: str
    why: str
    primary_drivers: list[str]
    evidence: dict[str, Any]
    confidence: float
    expected_roi: float | None
    risk_score: float
    urgency: float
    alternative_actions: list[dict[str, Any]]
    ranked_action: dict[str, Any] | None


class DecisionApprovalRequest(BaseModel):
    approved: bool
    note: str | None = None
