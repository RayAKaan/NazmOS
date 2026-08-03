from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime, timezone
import json

from app.database.connection import get_db
from app.database.models import POSConnection, POSSyncLog
from app.services.audit_service import AuditService
from app.services.multi_tenant import TenantContext
from app.services.credential_vault import POSCredentialManager
from app.schemas.adapter import (
    POSConnectionCreate, POSConnectionResponse, POSConnectionUpdate,
    POSSyncStatusResponse, POSSyncTriggerResponse, POSFieldMappingUpdate,
)
from app.tasks.pos_sync_tasks import run_sync_pos_connection
from app.adapters.registry import ADAPTER_REGISTRY
from app.config import get_settings

settings = get_settings()

router = APIRouter(prefix="/api/v1/pos", tags=["pos"])


def get_current_tenant(request: Request) -> TenantContext:
    if not hasattr(request.state, "tenant_context"):
        raise HTTPException(401, "Not authenticated")
    return request.state.tenant_context


@router.post("/connections", response_model=POSConnectionResponse)
async def create_connection(
    data: POSConnectionCreate,
    credentials: dict,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    vault = POSCredentialManager()
    
    if not vault.validate_credentials(data.adapter_type, credentials):
        raise HTTPException(400, "Invalid credentials for adapter type")
    
    encrypted = vault.encrypt_credentials(data.adapter_type, credentials)
    
    connection = POSConnection(
        business_id=tenant.business_id,
        adapter_type=data.adapter_type,
        connection_name=data.connection_name,
        credentials_encrypted=encrypted,
        endpoint_url=data.endpoint_url,
        sync_interval_minutes=data.sync_interval_minutes,
        sync_sales=data.sync_sales,
        sync_inventory=data.sync_inventory,
        push_orders=data.push_orders,
        sync_status="never_synced",
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)
    
    audit = AuditService(db)
    await audit.log_integration(
        business_id=tenant.business_id,
        action="created",
        integration_type="pos",
        integration_id=connection.id,
        integration_name=connection.connection_name,
        metadata={"adapter_type": data.adapter_type},
    )
    
    return connection


@router.get("/connections", response_model=list[POSConnectionResponse])
async def list_connections(
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    result = await db.execute(
        select(POSConnection)
        .where(POSConnection.business_id == tenant.business_id)
        .order_by(POSConnection.created_at.desc())
    )
    return result.scalars().all()


@router.get("/connections/{connection_id}", response_model=POSConnectionResponse)
async def get_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    connection = await db.get(POSConnection, connection_id)
    
    if not connection or connection.business_id != tenant.business_id:
        raise HTTPException(404, "Connection not found")
    
    return connection


@router.patch("/connections/{connection_id}", response_model=POSConnectionResponse)
async def update_connection(
    connection_id: UUID,
    data: POSConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    connection = await db.get(POSConnection, connection_id)
    
    if not connection or connection.business_id != tenant.business_id:
        raise HTTPException(404, "Connection not found")
    
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(connection, key, value)
    
    connection.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(connection)
    
    return connection


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    connection = await db.get(POSConnection, connection_id)
    
    if not connection or connection.business_id != tenant.business_id:
        raise HTTPException(404, "Connection not found")
    
    connection.is_active = False
    connection.sync_status = "disabled"
    connection.updated_at = datetime.now(timezone.utc)
    await db.commit()
    
    audit = AuditService(db)
    await audit.log_integration(
        business_id=tenant.business_id,
        action="disabled",
        integration_type="pos",
        integration_id=connection.id,
        integration_name=connection.connection_name,
    )
    
    return {"message": "Connection disabled"}


@router.post("/connections/{connection_id}/sync", response_model=POSSyncTriggerResponse)
async def trigger_sync(
    connection_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    connection = await db.get(POSConnection, connection_id)
    
    if not connection or connection.business_id != tenant.business_id:
        raise HTTPException(404, "Connection not found")
    
    if connection.sync_status == "syncing":
        raise HTTPException(400, "Sync already in progress")
    
    connection.sync_status = "syncing"
    connection.updated_at = datetime.now(timezone.utc)
    await db.commit()
    
    task_id = f"sync_{connection_id}"

    if settings.USE_CELERY:
        from app.tasks.pos_sync_tasks import sync_pos_connection
        sync_pos_connection.delay(str(connection_id))
    else:
        import asyncio

        async def _run_sync():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, run_sync_pos_connection, str(connection_id))

        background_tasks.add_task(_run_sync)
    
    return POSSyncTriggerResponse(
        task_id=task_id,
        status="initiated",
        message="POS sync started. Check status for progress.",
    )


@router.get("/connections/{connection_id}/status", response_model=POSSyncStatusResponse)
async def get_sync_status(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    connection = await db.get(POSConnection, connection_id)
    
    if not connection or connection.business_id != tenant.business_id:
        raise HTTPException(404, "Connection not found")
    
    result = await db.execute(
        select(POSSyncLog)
        .where(POSSyncLog.connection_id == connection_id)
        .order_by(POSSyncLog.started_at.desc())
        .limit(1)
    )
    latest_log = result.scalar_one_or_none()
    
    return POSSyncStatusResponse(
        connection_id=connection_id,
        status=connection.sync_status,
        started_at=latest_log.started_at if latest_log else None,
        completed_at=latest_log.completed_at if latest_log else None,
        records_fetched=latest_log.records_fetched if latest_log else 0,
        records_created=latest_log.records_created if latest_log else 0,
        records_updated=latest_log.records_updated if latest_log else 0,
        records_skipped=latest_log.records_skipped if latest_log else 0,
        records_failed=latest_log.records_failed if latest_log else 0,
        errors=latest_log.errors if latest_log else [],
    )


@router.patch("/connections/{connection_id}/mapping")
async def update_field_mapping(
    connection_id: UUID,
    data: POSFieldMappingUpdate,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    connection = await db.get(POSConnection, connection_id)
    
    if not connection or connection.business_id != tenant.business_id:
        raise HTTPException(404, "Connection not found")
    
    connection.field_mapping = data.mapping.model_dump(exclude_none=True)
    connection.updated_at = datetime.now(timezone.utc)
    await db.commit()
    
    return {"message": "Field mapping updated"}


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    connection = await db.get(POSConnection, connection_id)

    if not connection or connection.business_id != tenant.business_id:
        raise HTTPException(404, "Connection not found")

    vault = POSCredentialManager()
    creds = vault.decrypt_credentials(connection.credentials_encrypted)
    adapter_type = connection.adapter_type

    adapter_class = ADAPTER_REGISTRY.get(adapter_type)
    if not adapter_class:
        raise HTTPException(400, f"Unsupported adapter type: {adapter_type}")

    adapter = adapter_class(creds)
    ok = await adapter.test_connection()

    return {
        "success": ok,
        "message": (
            f"Successfully connected to {connection.connection_name}"
            if ok
            else f"Could not connect to {connection.connection_name}; check credentials and reachability"
        ),
        "adapter_type": adapter_type,
        "credentials_configured": bool(creds.get("credentials")),
    }
