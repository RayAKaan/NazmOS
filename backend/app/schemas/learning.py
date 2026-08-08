"""Pydantic schemas for Phase 6: Learning Engine.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OutcomeFeedbackCreate(BaseModel):
    decision_id: UUID | None = None
    execution_job_id: UUID | None = None
    actual_outcome: dict[str, Any] = Field(default_factory=dict)
    feedback_source: str = Field(default="manual", pattern="^(manual|system)$")
    recorded_at: datetime | None = None


class OutcomeFeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    decision_id: UUID | None
    execution_job_id: UUID | None
    decision_type: str | None
    predicted_outcome: dict[str, Any]
    actual_outcome: dict[str, Any]
    delta: dict[str, Any]
    feedback_source: str
    recorded_at: datetime
    created_at: datetime


class OutcomeFeedbackListOut(BaseModel):
    items: list[OutcomeFeedbackOut]
    total: int
    limit: int
    offset: int


class ModelPerformanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    decision_type: str
    window_start: datetime
    window_end: datetime
    samples: int
    accuracy: float | None
    roi_error: float | None
    mean_latency_ms: float | None
    last_updated_at: datetime


class LearningRefreshOut(BaseModel):
    refreshed: list[ModelPerformanceOut]
    window_days: int


class CandidateAction(BaseModel):
    action_type: str = Field(..., min_length=1, max_length=50)
    title: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    expected_roi: float | None = None


class SuggestActionRequest(BaseModel):
    candidates: list[CandidateAction] = Field(..., min_length=1)
    decision_type: str | None = Field(default=None, max_length=50)
    seed: int | None = None


class SuggestActionOut(BaseModel):
    selected_candidate: CandidateAction
    probabilities: dict[str, float]
    note: str
