"""Admin backup and restore-drill endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, User
from app.middleware.auth_middleware import get_current_user
from app.services.backup_service import (
    create_backup,
    list_backups,
    get_backup,
    restore_dry_run,
    apply_retention_policy,
)

router = APIRouter(prefix="/api/v1/admin/backups", tags=["admin"])


class CreateBackupRequest(BaseModel):
    name: str | None = Field(None, max_length=100)


def _require_admin(user: User) -> None:
    if getattr(user, "role", None) != "admin":
        raise HTTPException(403, "Admin access required")


@router.post("")
async def backup_create(
    req: CreateBackupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    return await create_backup(db, name=req.name)


@router.get("")
async def backup_list(
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    return {"backups": list_backups()}


@router.get("/{filename}")
async def backup_get(
    filename: str,
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    snapshot = get_backup(filename)
    if not snapshot:
        raise HTTPException(404, "Backup not found")
    return snapshot


@router.post("/{filename}/restore-dry-run")
async def backup_restore_dry_run(
    filename: str,
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    snapshot = get_backup(filename)
    if not snapshot:
        raise HTTPException(404, "Backup not found")
    return restore_dry_run(snapshot)


@router.post("/retention")
async def backup_retention(
    max_backups: int = 30,
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    return apply_retention_policy(max_backups=max_backups)
