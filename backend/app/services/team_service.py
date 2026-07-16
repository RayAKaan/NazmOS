from typing import Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta
import secrets
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import structlog

from app.database.models import (
    TeamMember, TeamInvitation, User, Business, Organization, PermissionDefinition
)
from app.services.multi_tenant import MultiTenantService

logger = structlog.get_logger(__name__)


@dataclass
class InviteResult:
    success: bool
    invitation_id: Optional[UUID] = None
    token: Optional[str] = None
    message: str = ""


@dataclass
class TeamMemberInfo:
    id: UUID
    user_id: UUID
    email: str
    full_name: str
    role: str
    permissions: list[str]
    is_active: bool
    invited_at: Optional[datetime]
    accepted_at: Optional[datetime]


ROLE_DEFAULT_PERMISSIONS = {
    "owner": [
        "view_dashboard", "view_inventory", "edit_inventory",
        "view_decisions", "apply_decisions", "reverse_decisions",
        "view_reports", "export_reports", "manage_team",
        "manage_billing", "manage_integrations", "view_chat_history",
        "configure_notifications",
    ],
    "admin": [
        "view_dashboard", "view_inventory", "edit_inventory",
        "view_decisions", "apply_decisions", "reverse_decisions",
        "view_reports", "export_reports", "manage_team",
        "manage_integrations", "view_chat_history", "configure_notifications",
    ],
    "manager": [
        "view_dashboard", "view_inventory", "edit_inventory",
        "view_decisions", "apply_decisions", "view_reports",
        "view_chat_history",
    ],
    "staff": [
        "view_dashboard", "view_inventory", "view_decisions",
    ],
    "accountant": [
        "view_dashboard", "view_reports", "export_reports",
    ],
    "viewer": [
        "view_dashboard",
    ],
}


class TeamService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.tenant_service = MultiTenantService(db)

    async def invite_team_member(
        self,
        email: str,
        business_id: UUID,
        role: str,
        invited_by: UUID,
        organization_id: Optional[UUID] = None,
    ) -> InviteResult:
        existing_user = await self.db.execute(
            select(User).where(User.email == email.lower())
        )
        existing_user = existing_user.scalar_one_or_none()

        if existing_user:
            existing_member = await self.db.execute(
                select(TeamMember).where(
                    and_(
                        TeamMember.user_id == existing_user.id,
                        TeamMember.business_id == business_id,
                        TeamMember.is_active == True,
                    )
                )
            )
            if existing_member.scalar_one_or_none():
                return InviteResult(
                    success=False,
                    message="User is already a team member",
                )

        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        invitation = TeamInvitation(
            email=email.lower(),
            business_id=business_id,
            organization_id=organization_id,
            role=role,
            token=token,
            invited_by=invited_by,
            expires_at=expires_at,
        )
        
        self.db.add(invitation)
        await self.db.commit()
        await self.db.refresh(invitation)

        logger.info(
            "team_invitation_sent",
            email=email,
            business_id=str(business_id),
            role=role,
            invited_by=str(invited_by),
        )

        return InviteResult(
            success=True,
            invitation_id=invitation.id,
            token=token,
            message="Invitation sent successfully",
        )

    async def accept_invitation(
        self,
        token: str,
        user_id: UUID,
    ) -> tuple[bool, str]:
        invitation = await self.db.execute(
            select(TeamInvitation).where(
                and_(
                    TeamInvitation.token == token,
                    TeamInvitation.accepted_at == None,
                )
            )
        )
        invitation = invitation.scalar_one_or_none()

        if not invitation:
            return False, "Invalid or expired invitation"

        if invitation.expires_at < datetime.now(timezone.utc):
            return False, "Invitation has expired"

        user = await self.db.get(User, user_id)
        if not user or user.email.lower() != invitation.email.lower():
            return False, "Invitation was sent to a different email address"

        member = TeamMember(
            user_id=user_id,
            business_id=invitation.business_id,
            organization_id=invitation.organization_id,
            role=invitation.role,
            permissions=ROLE_DEFAULT_PERMISSIONS.get(invitation.role, []),
            invited_by=invitation.invited_by,
            invited_at=invitation.invited_at,
            accepted_at=datetime.now(timezone.utc),
            is_active=True,
        )
        
        self.db.add(member)
        
        invitation.accepted_at = datetime.now(timezone.utc)
        
        await self.db.commit()

        logger.info(
            "team_invitation_accepted",
            user_id=str(user_id),
            business_id=str(invitation.business_id),
            role=invitation.role,
        )

        return True, "Invitation accepted successfully"

    async def get_team_members(
        self,
        business_id: UUID,
    ) -> list[TeamMemberInfo]:
        result = await self.db.execute(
            select(TeamMember, User).join(
                User, TeamMember.user_id == User.id
            ).where(
                and_(
                    TeamMember.business_id == business_id,
                    TeamMember.is_active == True,
                )
            )
        )
        
        members = []
        for member, user in result.all():
            members.append(TeamMemberInfo(
                id=member.id,
                user_id=member.user_id,
                email=user.email,
                full_name=user.full_name,
                role=member.role,
                permissions=member.permissions or ROLE_DEFAULT_PERMISSIONS.get(member.role, []),
                is_active=member.is_active,
                invited_at=member.invited_at,
                accepted_at=member.accepted_at,
            ))
        
        return members

    async def update_member_role(
        self,
        member_id: UUID,
        new_role: str,
        updated_by: UUID,
    ) -> bool:
        member = await self.db.get(TeamMember, member_id)
        
        if not member:
            return False

        if new_role not in ROLE_DEFAULT_PERMISSIONS:
            return False

        member.role = new_role
        member.permissions = ROLE_DEFAULT_PERMISSIONS[new_role]
        member.updated_at = datetime.now(timezone.utc)
        
        await self.db.commit()

        logger.info(
            "team_member_role_updated",
            member_id=str(member_id),
            new_role=new_role,
            updated_by=str(updated_by),
        )

        return True

    async def remove_team_member(
        self,
        member_id: UUID,
        removed_by: UUID,
    ) -> bool:
        member = await self.db.get(TeamMember, member_id)
        
        if not member:
            return False

        member.is_active = False
        member.updated_at = datetime.now(timezone.utc)
        
        await self.db.commit()

        logger.info(
            "team_member_removed",
            member_id=str(member_id),
            removed_by=str(removed_by),
        )

        return True

    async def resend_invitation(
        self,
        invitation_id: UUID,
    ) -> InviteResult:
        invitation = await self.db.get(TeamInvitation, invitation_id)
        
        if not invitation:
            return InviteResult(success=False, message="Invitation not found")
        
        if invitation.accepted_at:
            return InviteResult(success=False, message="Invitation already accepted")

        invitation.token = secrets.token_urlsafe(32)
        invitation.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        
        await self.db.commit()

        return InviteResult(
            success=True,
            invitation_id=invitation.id,
            token=invitation.token,
            message="Invitation resent successfully",
        )

    async def cancel_invitation(
        self,
        invitation_id: UUID,
    ) -> bool:
        invitation = await self.db.get(TeamInvitation, invitation_id)
        
        if not invitation:
            return False

        await self.db.delete(invitation)
        await self.db.commit()
        
        return True

    async def get_pending_invitations(
        self,
        business_id: UUID,
    ) -> list[TeamInvitation]:
        result = await self.db.execute(
            select(TeamInvitation).where(
                and_(
                    TeamInvitation.business_id == business_id,
                    TeamInvitation.accepted_at == None,
                )
            ).order_by(TeamInvitation.created_at.desc())
        )
        return list(result.scalars().all())

    async def has_permission(
        self,
        user_id: UUID,
        business_id: UUID,
        permission: str,
    ) -> bool:
        business = await self.db.get(Business, business_id)
        if not business:
            return False

        if business.owner_id == user_id:
            return True

        result = await self.db.execute(
            select(TeamMember).where(
                and_(
                    TeamMember.user_id == user_id,
                    TeamMember.business_id == business_id,
                    TeamMember.is_active == True,
                )
            )
        )
        member = result.scalar_one_or_none()
        
        if not member:
            return False

        permissions = member.permissions or ROLE_DEFAULT_PERMISSIONS.get(member.role, [])
        return permission in permissions
