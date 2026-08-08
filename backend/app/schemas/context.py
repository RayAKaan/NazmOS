"""Pydantic schemas for the Context Engine (Phase 3).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BusinessContextCreate(BaseModel):
    context_type: str = Field(..., min_length=1, max_length=50)
    source: str | None = Field(default=None, max_length=100)
    source_url: str | None = Field(default=None, max_length=500)
    effective_from: datetime
    effective_until: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class BusinessContextOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    context_type: str
    source: str | None
    source_url: str | None
    effective_from: datetime
    effective_until: datetime | None
    payload: dict[str, Any]
    confidence: float
    created_at: datetime
    updated_at: datetime


class EventDerivationCreate(BaseModel):
    cause_event_id: UUID
    effect_event_id: UUID
    derivation_type: str = Field(default="caused_by", min_length=1, max_length=50)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: dict[str, Any] | None = None


class EventDerivationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    cause_event_id: UUID
    effect_event_id: UUID
    derivation_type: str
    confidence: float
    evidence: dict[str, Any] | None
    created_at: datetime


class TimelineEventOut(BaseModel):
    id: UUID
    event_type: str
    source: str
    payload: dict[str, Any]
    occurred_at: datetime
    context_snapshot: dict[str, Any] | None


class TimelineOut(BaseModel):
    items: list[TimelineEventOut]
    total: int
    limit: int
    offset: int


class WhatChangedOut(BaseModel):
    since: datetime
    events: list[TimelineEventOut]
    summary: dict[str, Any]


class WhyOut(BaseModel):
    event_id: UUID
    causal_chain: list[TimelineEventOut]
    derivations: list[EventDerivationOut]
