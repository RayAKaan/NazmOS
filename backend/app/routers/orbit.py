"""Orbit API Router — exposes /orbit endpoints for history, comparison, drill-down."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.services.audit_persistence import AuditPersistenceService
from app.database.models import User
from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access
from app.services.orbit.ingestion.service import ingest_and_project
from app.services.orbit.queries import list_artifacts, get_artifact, list_entities, list_evidence, list_conflicts, latest_quality, latest_state, state_history, business_profile, ingestion_runs, jev_calls, model_dict

router = APIRouter(prefix="/orbit", tags=["Orbit"])


def get_persistence_service(db: AsyncSession = Depends(get_db)) -> AuditPersistenceService:
    return AuditPersistenceService(db)




async def _orbit_business_gate(
    business_id: UUID,
    db: AsyncSession,
    current_user: User,
) -> None:
    await assert_business_access(db, business_id, current_user)


@router.post("/ingest")
async def ingest_business_artifact(
    business_id: UUID = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _orbit_business_gate(business_id, db, current_user)
    content = await file.read()
    if not content:
        raise HTTPException(422, "Artifact is empty")
    try:
        result, projection = await ingest_and_project(
            db,
            content,
            business_id=business_id,
            source_name=file.filename or "artifact",
            mime_type=file.content_type,
        )
    except Exception as exc:
        await db.rollback()
        raise HTTPException(422, str(exc))
    return {"ingestion": result.to_dict(), "projection": projection.to_dict()}


@router.get("/business-context")
async def get_business_context(
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _orbit_business_gate(business_id, db, current_user)
    state = await latest_state(db, business_id)
    if state is None:
        return {"business_id": str(business_id), "state_version": None, "context": None}
    return {"business_id": str(business_id), "state_version": state.state_version,
            "freshness": state.freshness, "limitations": state.limitations,
            "context": state.state.get("business_context")}


@router.get("/artifacts")
async def get_orbit_artifacts(
    business_id: UUID = Query(...), limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0), db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _orbit_business_gate(business_id, db, current_user)
    rows = await list_artifacts(db, business_id, limit, offset)
    return {"items": [model_dict(r) for r in rows], "limit": limit, "offset": offset}


@router.get("/artifacts/{artifact_id}")
async def get_orbit_artifact(
    artifact_id: UUID, business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _orbit_business_gate(business_id, db, current_user)
    row = await get_artifact(db, business_id, artifact_id)
    if row is None:
        raise HTTPException(404, "Artifact not found")
    payload = model_dict(row)
    payload.pop("source_location", None)
    return payload


@router.get("/entities")
async def get_orbit_entities(
    business_id: UUID = Query(...), limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0), db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _orbit_business_gate(business_id, db, current_user)
    rows = await list_entities(db, business_id, limit, offset)
    return {"items": [model_dict(r) for r in rows], "limit": limit, "offset": offset}


@router.get("/events")
async def get_orbit_events(
    business_id: UUID = Query(...), limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _orbit_business_gate(business_id, db, current_user)
    state = await latest_state(db, business_id)
    events = state.state.get("events", []) if state else []
    return {"items": events[:limit], "count": len(events),
            "state_version": state.state_version if state else None}


@router.get("/evidence")
async def get_orbit_evidence(
    business_id: UUID = Query(...), limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0), db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _orbit_business_gate(business_id, db, current_user)
    rows = await list_evidence(db, business_id, limit, offset)
    return {"items": [model_dict(r) for r in rows], "limit": limit, "offset": offset}


@router.get("/conflicts")
async def get_orbit_conflicts(
    business_id: UUID = Query(...), limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0), db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _orbit_business_gate(business_id, db, current_user)
    rows = await list_conflicts(db, business_id, limit, offset)
    return {"items": [model_dict(r) for r in rows], "limit": limit, "offset": offset}


@router.get("/data-quality")
async def get_orbit_data_quality(
    business_id: UUID = Query(...), db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _orbit_business_gate(business_id, db, current_user)
    quality = await latest_quality(db, business_id)
    return model_dict(quality) if quality else {"business_id": str(business_id), "overall_score": None}


@router.get("/profile")
async def get_orbit_profile(
    business_id: UUID = Query(...), db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _orbit_business_gate(business_id, db, current_user)
    profile = await business_profile(db, business_id)
    return model_dict(profile) if profile else {"business_id": str(business_id), "business_type": "unknown"}


@router.get("/state/history")
async def get_orbit_state_history(
    business_id: UUID = Query(...), limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _orbit_business_gate(business_id, db, current_user)
    rows = await state_history(db, business_id, limit)
    return {"items": [model_dict(r) for r in rows], "count": len(rows)}


@router.get("/ingestion-runs")
async def get_orbit_ingestion_runs(
    business_id: UUID = Query(...), limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _orbit_business_gate(business_id, db, current_user)
    rows = await ingestion_runs(db, business_id, limit)
    return {"items": [model_dict(r) for r in rows], "count": len(rows)}


@router.get("/jev-calls")
async def get_orbit_jev_calls(
    business_id: UUID = Query(...), limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _orbit_business_gate(business_id, db, current_user)
    rows = await jev_calls(db, business_id, limit)
    return {"items": [model_dict(r) for r in rows], "count": len(rows)}

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