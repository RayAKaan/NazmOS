"""GDPR / PDPL compliance endpoints.

Provides data portability (export) and erasure (delete) for merchant accounts.
Deletion is a soft-delete grace period followed by hard purge for audit safety.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.database.models import (
    AgentAction,
    AuditLog,
    Business,
    ChatMessage,
    ChatSession,
    DecisionLog,
    DeletionRequest,
    ExecutedAction,
    Inventory,
    Item,
    MoneyAudit,
    MoneyAuditAction,
    Notification,
    POSConnection,
    POSSyncLog,
    PurchaseOrder,
    Report,
    StockRecoveryListing,
    StockRecoveryMatch,
    Transaction,
    UploadedFile,
    User,
)
from app.middleware.auth_middleware import get_current_user
from app.services.audit_log_service import record as record_audit
from app.utils.logger import setup_logger
from app.utils.problem_details import problem_response

router = APIRouter(prefix="/api/v1/compliance", tags=["Compliance"])
logger = setup_logger("compliance")
settings = get_settings()


GRACE_PERIOD_DAYS = 30


class DataExportResponse(BaseModel):
    exported_at: datetime
    business_id: UUID
    data: dict[str, Any]


class DeletionRequestResponse(BaseModel):
    request_id: UUID
    status: str = Field(..., pattern="^(scheduled|completed|not_found)$")
    scheduled_purge_at: datetime | None = None
    message: str


async def _get_owned_business(
    session: AsyncSession, business_id: UUID, user_id: UUID
) -> Business:
    result = await session.execute(
        select(Business).where(Business.id == business_id, Business.owner_id == user_id)
    )
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found or not owned by user")
    return business


async def _export_business_data(
    session: AsyncSession, business_id: UUID
) -> dict[str, Any]:
    """Gather all business-scoped data into a portable JSON structure."""
    data: dict[str, Any] = {"business_id": str(business_id)}

    # Helper to fetch scalar lists.
    async def fetch(model, filters):
        result = await session.execute(select(model).where(*filters))
        rows = result.scalars().all()
        return [row.__dict__ for row in rows]

    data["items"] = await fetch(Item, [Item.business_id == business_id])
    data["inventory"] = await fetch(Inventory, [Inventory.business_id == business_id])
    data["transactions"] = await fetch(Transaction, [Transaction.business_id == business_id])
    data["uploaded_files"] = await fetch(UploadedFile, [UploadedFile.business_id == business_id])
    data["money_audits"] = await fetch(MoneyAudit, [MoneyAudit.business_id == business_id])
    data["money_audit_actions"] = await fetch(MoneyAuditAction, [MoneyAuditAction.business_id == business_id])
    data["agent_actions"] = await fetch(AgentAction, [AgentAction.business_id == business_id])
    data["chat_sessions"] = await fetch(ChatSession, [ChatSession.business_id == business_id])
    data["chat_messages"] = await fetch(ChatMessage, [ChatMessage.session_id.in_(
        select(ChatSession.id).where(ChatSession.business_id == business_id)
    )])
    data["decision_log"] = await fetch(DecisionLog, [DecisionLog.business_id == business_id])
    data["executed_actions"] = await fetch(ExecutedAction, [ExecutedAction.business_id == business_id])
    data["notifications"] = await fetch(Notification, [Notification.business_id == business_id])
    data["reports"] = await fetch(Report, [Report.business_id == business_id])
    data["pos_connections"] = await fetch(POSConnection, [POSConnection.business_id == business_id])
    data["pos_sync_logs"] = await fetch(POSSyncLog, [POSSyncLog.connection_id.in_(
        select(POSConnection.id).where(POSConnection.business_id == business_id)
    )])
    data["recovery_match_listings"] = await fetch(StockRecoveryListing, [StockRecoveryListing.seller_business_id == business_id])
    data["recovery_match_matches"] = await fetch(StockRecoveryMatch, [
        (StockRecoveryMatch.buyer_business_id == business_id) | (StockRecoveryMatch.listing_id.in_(
            select(StockRecoveryListing.id).where(StockRecoveryListing.seller_business_id == business_id)
        ))
    ])
    data["purchase_orders"] = await fetch(PurchaseOrder, [PurchaseOrder.business_id == business_id])
    data["audit_log"] = await fetch(AuditLog, [AuditLog.business_id == business_id])

    # Strip internal SQLAlchemy state keys.
    for key, rows in data.items():
        if isinstance(rows, list):
            for row in rows:
                row.pop("_sa_instance_state", None)

    return data


async def _hard_delete_business_data(
    session: AsyncSession, business_id: UUID
) -> None:
    """Purge all business-scoped records. Called after the grace period."""
    # Delete child records first.
    await session.execute(
        update(Business).where(Business.id == business_id).values(is_active=False)
    )

    await session.execute(
        MoneyAuditAction.__table__.delete().where(MoneyAuditAction.business_id == business_id)
    )
    await session.execute(
        MoneyAudit.__table__.delete().where(MoneyAudit.business_id == business_id)
    )
    await session.execute(
        AgentAction.__table__.delete().where(AgentAction.business_id == business_id)
    )
    await session.execute(
        ExecutedAction.__table__.delete().where(ExecutedAction.business_id == business_id)
    )
    await session.execute(
        DecisionLog.__table__.delete().where(DecisionLog.business_id == business_id)
    )
    await session.execute(
        Notification.__table__.delete().where(Notification.business_id == business_id)
    )
    await session.execute(
        Report.__table__.delete().where(Report.business_id == business_id)
    )
    await session.execute(
        PurchaseOrder.__table__.delete().where(PurchaseOrder.business_id == business_id)
    )
    await session.execute(
        StockRecoveryMatch.__table__.delete().where(
            (StockRecoveryMatch.buyer_business_id == business_id) |
            (StockRecoveryMatch.listing_id.in_(
                select(StockRecoveryListing.id).where(StockRecoveryListing.seller_business_id == business_id)
            ))
        )
    )
    await session.execute(
        StockRecoveryListing.__table__.delete().where(StockRecoveryListing.seller_business_id == business_id)
    )
    await session.execute(
        POSSyncLog.__table__.delete().where(POSSyncLog.connection_id.in_(
            select(POSConnection.id).where(POSConnection.business_id == business_id)
        ))
    )
    await session.execute(
        POSConnection.__table__.delete().where(POSConnection.business_id == business_id)
    )
    await session.execute(
        UploadedFile.__table__.delete().where(UploadedFile.business_id == business_id)
    )
    await session.execute(
        Transaction.__table__.delete().where(Transaction.business_id == business_id)
    )
    await session.execute(
        Inventory.__table__.delete().where(Inventory.business_id == business_id)
    )
    await session.execute(
        Item.__table__.delete().where(Item.business_id == business_id)
    )

    chat_session_ids = select(ChatSession.id).where(ChatSession.business_id == business_id)
    await session.execute(
        ChatMessage.__table__.delete().where(ChatMessage.session_id.in_(chat_session_ids))
    )
    await session.execute(
        ChatSession.__table__.delete().where(ChatSession.business_id == business_id)
    )

    await session.execute(
        AuditLog.__table__.delete().where(AuditLog.business_id == business_id)
    )

    await session.execute(
        Business.__table__.delete().where(Business.id == business_id)
    )

    await session.commit()


@router.get("/export/{business_id}", response_model=DataExportResponse)
async def export_data(
    request: Request,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business = await _get_owned_business(db, business_id, current_user.id)
    data = await _export_business_data(db, business_id)

    await record_audit(
        session=db,
        action_type="DATA_EXPORT",
        action_category="compliance",
        business_id=business_id,
        user_id=current_user.id,
        user_email=current_user.email,
        entity_type="business",
        entity_id=business_id,
        entity_name=business.name,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return DataExportResponse(
        exported_at=datetime.now(timezone.utc),
        business_id=business_id,
        data=data,
    )


@router.post("/delete/{business_id}", response_model=DeletionRequestResponse)
async def request_deletion(
    request: Request,
    business_id: UUID,
    immediate: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business = await _get_owned_business(db, business_id, current_user.id)

    if immediate:
        await _hard_delete_business_data(db, business_id)
        await record_audit(
            session=db,
            action_type="DATA_DELETION_IMMEDIATE",
            action_category="compliance",
            business_id=business_id,
            user_id=current_user.id,
            user_email=current_user.email,
            entity_type="business",
            entity_id=business_id,
            entity_name=business.name,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        return DeletionRequestResponse(
            request_id=business_id,
            status="completed",
            message="Business data has been permanently deleted.",
        )

    scheduled_purge_at = datetime.now(timezone.utc) + timedelta(days=GRACE_PERIOD_DAYS)

    await db.execute(
        update(Business)
        .where(Business.id == business_id)
        .values(
            is_active=False,
            name=f"[PENDING_DELETION] {business.name}",
        )
    )

    deletion_request = DeletionRequest(
        business_id=business_id,
        requested_by=current_user.id,
        scheduled_purge_at=scheduled_purge_at,
        status="pending",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(deletion_request)
    await db.commit()
    await db.refresh(deletion_request)

    await record_audit(
        session=db,
        action_type="DATA_DELETION_SCHEDULED",
        action_category="compliance",
        business_id=business_id,
        user_id=current_user.id,
        user_email=current_user.email,
        entity_type="business",
        entity_id=business_id,
        entity_name=business.name,
        new_value={"scheduled_purge_at": scheduled_purge_at.isoformat(), "deletion_request_id": str(deletion_request.id)},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return DeletionRequestResponse(
        request_id=deletion_request.id,
        status="scheduled",
        scheduled_purge_at=scheduled_purge_at,
        message=f"Deletion scheduled. Data will be permanently purged after {GRACE_PERIOD_DAYS} days.",
    )


@router.delete("/delete/{business_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_deletion(
    request: Request,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a pending deletion and reactivate the business."""
    business = await _get_owned_business(db, business_id, current_user.id)
    if business.is_active:
        return problem_response(
            status=400,
            title="Deletion Not Scheduled",
            detail="Business is already active.",
            request=request,
        )

    await db.execute(
        update(Business)
        .where(Business.id == business_id)
        .values(is_active=True, name=business.name.replace("[PENDING_DELETION] ", ""))
    )
    await db.execute(
        update(DeletionRequest)
        .where(DeletionRequest.business_id == business_id, DeletionRequest.status == "pending")
        .values(status="cancelled")
    )
    await db.commit()

    await record_audit(
        session=db,
        action_type="DATA_DELETION_CANCELLED",
        action_category="compliance",
        business_id=business_id,
        user_id=current_user.id,
        user_email=current_user.email,
        entity_type="business",
        entity_id=business_id,
        entity_name=business.name,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
