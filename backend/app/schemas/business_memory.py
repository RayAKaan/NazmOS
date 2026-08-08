"""Pydantic schemas for the Business Memory Engine (Phase 1).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MemoryType(str):
    """String alias used by schemas to avoid importing SQLAlchemy enums."""
    pass


class BusinessMemoryOut(BaseModel):
    """Response schema for a business memory document."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    memory_type: str
    data: dict[str, Any]
    version: int
    updated_by_event_id: UUID | None
    updated_at: datetime | None


class GoalSetRequest(BaseModel):
    """Request schema for setting merchant goals."""
    model_config = ConfigDict(extra="allow")

    goals: dict[str, Any] = Field(..., description="Arbitrary goal payload, e.g. profit or stockout targets")


class MemoryUpdateOut(BaseModel):
    """Response schema for a memory mutation audit record."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    memory_type: str
    event_id: UUID | None
    path: str
    old_value: Any | None
    new_value: Any | None
    occurred_at: datetime


class MemoryChangesOut(BaseModel):
    """Paginated list of memory updates."""
    items: list[MemoryUpdateOut]
    total: int
    limit: int
    offset: int
