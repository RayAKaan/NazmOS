from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone
import structlog

from app.database.models import AuditLog

logger = structlog.get_logger(__name__)


class AuditService:
    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    def create_recovery_checkpoint(self) -> dict:
        import hashlib, json
        payload = {"service": "NazmOS", "timestamp": datetime.now(timezone.utc).isoformat()}
        checksum = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return {**payload, "checksum": checksum}

    async def log(
        self,
        business_id: UUID,
        action_type: str,
        action_category: str,
        user_id: Optional[UUID] = None,
        user_email: Optional[str] = None,
        user_role: Optional[str] = None,
        organization_id: Optional[UUID] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[UUID] = None,
        entity_name: Optional[str] = None,
        old_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[UUID] = None,
        metadata: Optional[dict] = None,
    ) -> AuditLog:
        audit_entry = AuditLog(
            business_id=business_id,
            organization_id=organization_id,
            user_id=user_id,
            user_email=user_email,
            user_role=user_role,
            action_type=action_type,
            action_category=action_category,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            metadata=metadata or {},
        )
        self.db.add(audit_entry)
        await self.db.commit()
        await self.db.refresh(audit_entry)
        
        logger.info(
            "audit_logged",
            action_type=action_type,
            action_category=action_category,
            business_id=str(business_id),
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
        )
        
        return audit_entry

    async def log_auth(
        self,
        business_id: UUID,
        user_id: UUID,
        user_email: str,
        action: str,
        success: bool,
        ip_address: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> AuditLog:
        return await self.log(
            business_id=business_id,
            user_id=user_id,
            user_email=user_email,
            action_type=action,
            action_category="auth",
            new_value={"success": success, **(metadata or {})},
            ip_address=ip_address,
        )

    async def log_decision(
        self,
        business_id: UUID,
        user_id: Optional[UUID],
        decision_id: UUID,
        decision_type: str,
        item_id: Optional[UUID],
        item_name: str,
        action_taken: str,
        old_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
    ) -> AuditLog:
        return await self.log(
            business_id=business_id,
            user_id=user_id,
            action_type=f"decision_{action_taken}",
            action_category="decision",
            entity_type="decision",
            entity_id=decision_id,
            entity_name=f"{decision_type}: {item_name}",
            old_value=old_value,
            new_value=new_value,
            metadata={"decision_type": decision_type},
        )

    async def log_billing(
        self,
        business_id: UUID,
        event_type: str,
        amount_cents: Optional[int] = None,
        old_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
    ) -> AuditLog:
        return await self.log(
            business_id=business_id,
            action_type=f"billing_{event_type}",
            action_category="billing",
            old_value=old_value,
            new_value=new_value,
            metadata={"amount_cents": amount_cents} if amount_cents else None,
        )

    async def log_team(
        self,
        business_id: UUID,
        user_id: UUID,
        action: str,
        target_user_id: Optional[UUID] = None,
        target_email: Optional[str] = None,
        role: Optional[str] = None,
    ) -> AuditLog:
        return await self.log(
            business_id=business_id,
            user_id=user_id,
            action_type=f"team_{action}",
            action_category="team",
            entity_type="team_member",
            entity_id=target_user_id,
            entity_name=target_email,
            new_value={"role": role} if role else None,
        )

    async def log_integration(
        self,
        business_id: UUID,
        action: str,
        integration_type: str,
        integration_id: UUID,
        integration_name: str,
        metadata: Optional[dict] = None,
    ) -> AuditLog:
        return await self.log(
            business_id=business_id,
            action_type=f"integration_{action}",
            action_category="integration",
            entity_type=integration_type,
            entity_id=integration_id,
            entity_name=integration_name,
            metadata=metadata,
        )

    async def get_logs(
        self,
        business_id: UUID,
        action_category: Optional[str] = None,
        entity_type: Optional[str] = None,
        user_id: Optional[UUID] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        query = select(AuditLog).where(AuditLog.business_id == business_id)
        count_query = select(func.count(AuditLog.id)).where(AuditLog.business_id == business_id)

        if action_category:
            query = query.where(AuditLog.action_category == action_category)
            count_query = count_query.where(AuditLog.action_category == action_category)

        if entity_type:
            query = query.where(AuditLog.entity_type == entity_type)
            count_query = count_query.where(AuditLog.entity_type == entity_type)

        if user_id:
            query = query.where(AuditLog.user_id == user_id)
            count_query = count_query.where(AuditLog.user_id == user_id)

        query = query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)

        result = await self.db.execute(query)
        count_result = await self.db.execute(count_query)

        return result.scalars().all(), count_result.scalar() or 0
