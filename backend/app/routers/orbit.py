"""Orbit API Router — exposes /orbit endpoints for history, comparison, drill-down."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.services.audit_persistence import AuditPersistenceService

router = APIRouter(prefix="/orbit", tags=["Orbit"])


def get_persistence_service(db: AsyncSession = Depends(get_db)) -> AuditPersistenceService:
    return AuditPersistenceService(db)


@router.get("/audits")
async def list_audit_history(
    business_id: UUID | None = Query(None, description="Filter by business ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    svc: AuditPersistenceService = Depends(get_persistence_service),
) -> dict[str, Any]:
    """List audit history with pagination, optionally filtered by business."""
    audits = await svc.get_audit_history(business_id=business_id, limit=limit, offset=offset)
    return {
        "audits": audits,
        "limit": limit,
        "offset": offset,
        "count": len(audits),
    }


@router.get("/audits/{audit_id}")
async def get_audit_detail(
    audit_id: UUID,
    svc: AuditPersistenceService = Depends(get_persistence_service),
) -> dict[str, Any]:
    """Get full audit result by ID."""
    audit = await svc.get_audit_run(audit_id)
    if not audit:
        raise HTTPException(404, "Audit not found")
    return audit.to_api_response() if hasattr(audit, "to_api_response") else audit.__dict__


@router.get("/audits/{audit_id}/compare")
async def compare_audits(
    audit_id: UUID,
    vs_audit_id: UUID | None = Query(None, description="Specific audit to compare against (defaults to previous)"),
    svc: AuditPersistenceService = Depends(get_persistence_service),
) -> dict[str, Any]:
    """Compare current audit with previous (or specified) audit."""
    comparison = await svc.get_audit_comparison(audit_id, vs_audit_id)
    if "error" in comparison:
        raise HTTPException(404, comparison["error"])
    return comparison


@router.get("/audits/{audit_id}/findings/{finding_id}")
async def get_finding_drilldown(
    audit_id: UUID,
    finding_id: str,
    svc: AuditPersistenceService = Depends(get_persistence_service),
) -> dict[str, Any]:
    """Drill down from finding → products → evidence → source rows."""
    drilldown = await svc.get_finding_drilldown(audit_id, finding_id)
    if not drilldown:
        raise HTTPException(404, "Finding not found")
    return drilldown


@router.get("/data-quality/history")
async def get_data_quality_history(
    business_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    svc: AuditPersistenceService = Depends(get_persistence_service),
) -> dict[str, Any]:
    """Get data quality score trend over time."""
    history = await svc.get_data_quality_history(business_id=business_id, limit=limit)
    return {
        "history": history,
        "count": len(history),
    }