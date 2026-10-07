"""Read-only queries for the canonical Orbit Business Reality layer."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    JevCall,
    OrbitBusinessProfile,
    OrbitConflict,
    OrbitDataQuality,
    OrbitEntity,
    OrbitEvidence,
    OrbitIngestionRun,
    OrbitStateVersion,
    UniversalArtifact,
)


async def _limit(query, limit: int, offset: int = 0):
    return query.limit(limit).offset(offset)


async def list_artifacts(db: AsyncSession, business_id: UUID, limit: int = 50, offset: int = 0):
    result = await db.execute(
        select(UniversalArtifact)
        .where(UniversalArtifact.business_id == business_id)
        .order_by(desc(UniversalArtifact.received_at))
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def get_artifact(db: AsyncSession, business_id: UUID, artifact_id: UUID):
    result = await db.execute(
        select(UniversalArtifact).where(
            UniversalArtifact.business_id == business_id,
            UniversalArtifact.id == artifact_id,
        )
    )
    return result.scalar_one_or_none()


async def list_entities(db: AsyncSession, business_id: UUID, limit: int = 100, offset: int = 0):
    result = await db.execute(
        select(OrbitEntity)
        .where(OrbitEntity.business_id == business_id)
        .order_by(OrbitEntity.kind, OrbitEntity.normalized_name)
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def list_evidence(db: AsyncSession, business_id: UUID, limit: int = 100, offset: int = 0):
    result = await db.execute(
        select(OrbitEvidence)
        .where(OrbitEvidence.business_id == business_id)
        .order_by(desc(OrbitEvidence.created_at))
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def list_conflicts(db: AsyncSession, business_id: UUID, limit: int = 100, offset: int = 0):
    result = await db.execute(
        select(OrbitConflict)
        .where(OrbitConflict.business_id == business_id)
        .order_by(desc(OrbitConflict.id))
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def latest_quality(db: AsyncSession, business_id: UUID):
    result = await db.execute(
        select(OrbitDataQuality)
        .join(OrbitIngestionRun, OrbitIngestionRun.id == OrbitDataQuality.run_id)
        .where(OrbitIngestionRun.business_id == business_id)
        .order_by(desc(OrbitIngestionRun.completed_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def latest_state(db: AsyncSession, business_id: UUID):
    result = await db.execute(
        select(OrbitStateVersion)
        .where(OrbitStateVersion.business_id == business_id)
        .order_by(desc(OrbitStateVersion.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def state_history(db: AsyncSession, business_id: UUID, limit: int = 50):
    result = await db.execute(
        select(OrbitStateVersion)
        .where(OrbitStateVersion.business_id == business_id)
        .order_by(desc(OrbitStateVersion.created_at))
        .limit(limit)
    )
    return result.scalars().all()


async def business_profile(db: AsyncSession, business_id: UUID):
    result = await db.execute(
        select(OrbitBusinessProfile).where(
            OrbitBusinessProfile.business_id == business_id
        )
    )
    return result.scalar_one_or_none()


async def ingestion_runs(db: AsyncSession, business_id: UUID, limit: int = 50):
    result = await db.execute(
        select(OrbitIngestionRun)
        .where(OrbitIngestionRun.business_id == business_id)
        .order_by(desc(OrbitIngestionRun.completed_at))
        .limit(limit)
    )
    return result.scalars().all()


async def jev_calls(db: AsyncSession, business_id: UUID, limit: int = 100):
    result = await db.execute(
        select(JevCall)
        .where(JevCall.business_id == business_id)
        .order_by(desc(JevCall.created_at))
        .limit(limit)
    )
    return result.scalars().all()


def model_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if hasattr(obj, "to_dict"):
        value = obj.to_dict()
        if isinstance(value, dict):
            return value
    out: dict[str, Any] = {}
    for column in getattr(obj, "__table__", []).columns if hasattr(obj, "__table__") else []:
        value = getattr(obj, column.name, None)
        if isinstance(value, UUID):
            value = str(value)
        elif hasattr(value, "isoformat") and not isinstance(value, (str, bytes)):
            value = value.isoformat()
        out[column.name] = value
    return out
