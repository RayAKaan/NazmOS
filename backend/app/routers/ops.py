from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import User, get_db
from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_platform_operator
from app.services.money_audit_service import get_latest_money_audit
from app.services.llm_rate_limiter import llm_rate_limiter

router = APIRouter(prefix="/api/v1/ops", tags=["Pilot Ops"])


@router.get("/pilot-console")
async def pilot_console(
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Founder/operator console for controlled pilots.

    This is intentionally operational, not merchant-facing: uploads, audit queue,
    failed imports, and Recovery Match issues in one place. The business_id here
    is the *target* of a pilot, not the caller's own tenant, so the gate is the
    platform-operator identity — a merchant owner alone must never reach it.
    Denials are recorded to the AuditLog and surfaced as 403.
    """
    await assert_platform_operator(db, current_user, business_id=business_id)

    llm_usage = await llm_rate_limiter.usage()

    upload_counts_res = await db.execute(text("""
        SELECT status, COUNT(*) AS count
        FROM uploaded_files
        WHERE business_id = :business_id
        GROUP BY status
    """), {"business_id": str(business_id)})
    upload_counts = {row.status: int(row.count or 0) for row in upload_counts_res.fetchall()}

    recent_uploads_res = await db.execute(text("""
        SELECT id, original_filename, status, row_count_raw, row_count_imported, row_count_failed, error_summary, created_at
        FROM uploaded_files
        WHERE business_id = :business_id
        ORDER BY created_at DESC
        LIMIT 10
    """), {"business_id": str(business_id)})
    recent_uploads = [
        {
            "upload_id": str(row.id),
            "filename": row.original_filename,
            "status": row.status,
            "row_count_raw": int(row.row_count_raw or 0),
            "row_count_imported": int(row.row_count_imported or 0),
            "row_count_failed": int(row.row_count_failed or 0),
            "error_summary": row.error_summary,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in recent_uploads_res.fetchall()
    ]

    latest_audit = await get_latest_money_audit(db, business_id)

    action_queue_res = await db.execute(text("""
        SELECT id, audit_id, title, action_type, status, expected_recovery_sar, priority, created_at
        FROM money_audit_actions
        WHERE business_id = :business_id AND status IN ('suggested', 'approved')
        ORDER BY priority ASC, expected_recovery_sar DESC, created_at ASC
        LIMIT 15
    """), {"business_id": str(business_id)})
    action_queue = [
        {
            "id": str(row.id),
            "audit_id": str(row.audit_id),
            "title": row.title,
            "action_type": row.action_type,
            "status": row.status,
            "expected_recovery_sar": float(row.expected_recovery_sar or 0),
            "priority": row.priority,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in action_queue_res.fetchall()
    ]

    issues_res = await db.execute(text("""
        SELECT e.id, e.match_id, e.listing_id, e.event_type, e.notes, e.payload, e.created_at
        FROM stock_recovery_events e
        WHERE e.actor_business_id = :business_id AND e.event_type = 'issue_reported'
        ORDER BY e.created_at DESC
        LIMIT 15
    """), {"business_id": str(business_id)})
    recovery_issues = [
        {
            "id": str(row.id),
            "match_id": str(row.match_id) if row.match_id else None,
            "listing_id": str(row.listing_id) if row.listing_id else None,
            "event_type": row.event_type,
            "notes": row.notes,
            "payload": row.payload,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in issues_res.fetchall()
    ]

    return {
        "business_id": str(business_id),
        "upload_counts": upload_counts,
        "recent_uploads": recent_uploads,
        "latest_audit": latest_audit,
        "action_queue": action_queue,
        "recovery_issues": recovery_issues,
        "llm_usage": llm_usage,
        "operator_next_steps": [
            "Review failed uploads before merchant call.",
            "Regenerate Money Audit after corrected files are imported.",
            "Send WhatsApp summary manually during pilot.",
            "Do not reveal Recovery Match contact without mutual approval and founder review.",
        ],
    }
