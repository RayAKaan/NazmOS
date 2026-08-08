"""Pydantic schemas for the Knowledge Graph Engine (Phase 2).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GraphEntityCreate(BaseModel):
    entity_type: str = Field(..., min_length=1, max_length=50)
    external_id: str | None = Field(default=None, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    attributes: dict[str, Any] = Field(default_factory=dict)
    vector: list[float] | None = None


class GraphEntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    entity_type: str
    external_id: str | None
    name: str
    attributes: dict[str, Any]
    vector: list[float] | None
    created_at: datetime
    updated_at: datetime


class GraphRelationshipCreate(BaseModel):
    source_id: UUID
    target_id: UUID
    relation_type: str = Field(..., min_length=1, max_length=50)
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_event_ids: list[str] = Field(default_factory=list)
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class GraphRelationshipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    source_id: UUID
    target_id: UUID
    relation_type: str
    strength: float
    evidence_event_ids: list[str]
    valid_from: datetime
    valid_until: datetime | None
    created_at: datetime
    updated_at: datetime


class GraphEdge(BaseModel):
    """Edge in an expanded graph traversal."""
    source: GraphEntityOut
    target: GraphEntityOut
    relationship: GraphRelationshipOut


class GraphExpandOut(BaseModel):
    root: GraphEntityOut | None
    depth: int
    entities: list[GraphEntityOut]
    edges: list[GraphRelationshipOut]


class GraphShortestPathOut(BaseModel):
    found: bool
    path: list[GraphEntityOut]
    edges: list[GraphRelationshipOut]
    distance: int
