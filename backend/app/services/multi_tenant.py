from typing import Optional, Protocol
from uuid import UUID
from contextvars import ContextVar
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from starlette.requests import Request
import structlog

from app.database.models import Business, Organization, TeamMember

logger = structlog.get_logger(__name__)

tenant_context: ContextVar[Optional["TenantContext"]] = ContextVar("tenant_context", default=None)


@dataclass
class TenantContext:
    business_id: UUID
    organization_id: Optional[UUID]
    user_id: UUID
    user_role: str
    permissions: list[str]


class MultiTenantService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def set_context(self, context: TenantContext) -> None:
        tenant_context.set(context)
        logger.debug(
            "tenant_context_set",
            business_id=str(context.business_id),
            organization_id=str(context.organization_id) if context.organization_id else None,
            user_id=str(context.user_id),
        )

    def clear_context(self) -> None:
        tenant_context.set(None)
        logger.debug("tenant_context_cleared")

    def get_context(self) -> Optional[TenantContext]:
        return tenant_context.get()

    async def get_business_ids_for_user(self, user_id: UUID) -> list[UUID]:
        result = await self.db.execute(
            select(Business.id).where(Business.owner_id == user_id)
        )
        owned = list(result.scalars().all())
        
        team_result = await self.db.execute(
            select(TeamMember.business_id).where(
                TeamMember.user_id == user_id,
                TeamMember.is_active == True
            )
        )
        team_businesses = list(team_result.scalars().all())
        
        org_result = await self.db.execute(
            select(Organization.id).where(Organization.owner_id == user_id)
        )
        org_ids = list(org_result.scalars().all())
        
        if org_ids:
            org_business_result = await self.db.execute(
                select(Business.id).where(Business.organization_id.in_(org_ids))
            )
            org_businesses = list(org_business_result.scalars().all())
        else:
            org_businesses = []
        
        all_businesses = list(set(owned + team_businesses + org_businesses))
        logger.debug(
            "user_businesses_resolved",
            user_id=str(user_id),
            owned=len(owned),
            team=len(team_businesses),
            organization=len(org_businesses),
            total=len(all_businesses),
        )
        
        return all_businesses

    async def verify_business_access(
        self,
        user_id: UUID,
        business_id: UUID,
        require_write: bool = False,
    ) -> bool:
        business = await self.db.get(Business, business_id)
        if not business:
            return False
        
        if business.owner_id == user_id:
            return True
        
        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.user_id == user_id,
                TeamMember.business_id == business_id,
                TeamMember.is_active == True
            )
        )
        member = result.scalar_one_or_none()
        
        if not member:
            if business.organization_id:
                org_result = await self.db.execute(
                    select(Organization).where(
                        Organization.id == business.organization_id,
                        Organization.owner_id == user_id
                    )
                )
                if org_result.scalar_one_or_none():
                    return True
            return False
        
        if require_write and member.role in ("viewer", "accountant"):
            return False
        
        return True

    async def verify_organization_access(
        self,
        user_id: UUID,
        organization_id: UUID,
        require_write: bool = False,
    ) -> bool:
        org = await self.db.get(Organization, organization_id)
        if not org:
            return False
        
        if org.owner_id == user_id:
            return True
        
        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.user_id == user_id,
                TeamMember.organization_id == organization_id,
                TeamMember.is_active == True
            )
        )
        member = result.scalar_one_or_none()
        
        if not member:
            return False
        
        if require_write and member.role in ("viewer", "accountant"):
            return False
        
        return True

    async def get_role_permissions(
        self,
        db: AsyncSession,
        role: str,
        business_id: Optional[UUID] = None,
    ) -> list[str]:
        query = """
            SELECT pd.id 
            FROM permission_definitions pd
            LEFT JOIN role_default_permissions rdp ON pd.id = rdp.permission_id AND rdp.role = :role
            WHERE pd.requires_plan IN ('free', 'basic', 'pro', 'enterprise')
        """
        result = await db.execute(select(query), {"role": role})
        return [row[0] for row in result.fetchall()]

    def require_business_access(self, business_id: UUID) -> None:
        context = self.get_context()
        if not context:
            raise PermissionError("No tenant context set")
        if context.business_id != business_id:
            raise PermissionError(f"Access denied to business {business_id}")

    def require_permission(self, permission: str) -> None:
        context = self.get_context()
        if not context:
            raise PermissionError("No tenant context set")
        if permission not in context.permissions:
            raise PermissionError(f"Missing required permission: {permission}")


def get_tenant_from_request(request: Request) -> Optional[TenantContext]:
    return request.state.tenant_context if hasattr(request.state, "tenant_context") else None
