from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from datetime import datetime, timezone
import re
from slugify import slugify

from app.database.connection import get_db
from app.database.models import Organization, Business, User
from app.services.audit_service import AuditService
from app.services.multi_tenant import MultiTenantService, TenantContext
from app.schemas.organization import (
    OrganizationCreate, OrganizationUpdate, OrganizationResponse,
    BusinessLocationCreate, BusinessLocationUpdate, BusinessLocationResponse,
    ChainDashboardResponse, TeamMemberInvite, TeamMemberUpdate, TeamMemberResponse,
    InvitationResponse,
)
from app.services.team_service import TeamService

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


def get_current_tenant(request: Request) -> TenantContext:
    if not hasattr(request.state, "tenant_context"):
        raise HTTPException(401, "Not authenticated")
    return request.state.tenant_context


@router.post("/", response_model=OrganizationResponse)
async def create_organization(
    data: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    if data.slug:
        slug = data.slug.lower().replace(" ", "-")
    else:
        slug = slugify(data.name)
    
    existing = await db.execute(
        select(Organization).where(Organization.slug == slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Organization slug already exists")
    
    org = Organization(
        name=data.name,
        slug=slug,
        owner_id=tenant.user_id,
        default_currency=data.default_currency,
        default_timezone=data.default_timezone,
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)
    
    audit = AuditService(db)
    await audit.log(
        business_id=tenant.business_id,
        user_id=tenant.user_id,
        action_type="organization_created",
        action_category="organization",
        entity_type="organization",
        entity_id=org.id,
        entity_name=org.name,
        new_value={"name": org.name, "slug": org.slug},
    )
    
    return org


@router.get("/", response_model=list[OrganizationResponse])
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    result = await db.execute(
        select(Organization).where(Organization.owner_id == tenant.user_id)
    )
    return result.scalars().all()


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organization not found")
    
    if org.owner_id != tenant.user_id:
        raise HTTPException(403, "Access denied")
    
    return org


@router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: UUID,
    data: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organization not found")
    
    if org.owner_id != tenant.user_id:
        raise HTTPException(403, "Access denied")
    
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(org, key, value)
    
    org.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(org)
    
    return org


@router.post("/locations", response_model=BusinessLocationResponse)
async def create_location(
    data: BusinessLocationCreate,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    user = await db.get(User, tenant.user_id)
    if not user:
        raise HTTPException(401, "User not found")
    
    business = Business(
        name=data.name,
        type=data.type,
        address=data.address,
        city=data.city,
        owner_id=tenant.user_id,
        organization_id=tenant.organization_id,
        location_code=data.location_code,
        location_name=data.location_name,
        latitude=data.latitude,
        longitude=data.longitude,
        is_headquarters=data.is_headquarters,
    )
    db.add(business)
    await db.commit()
    await db.refresh(business)
    
    return business


@router.get("/locations", response_model=list[BusinessLocationResponse])
async def list_locations(
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    if tenant.organization_id:
        result = await db.execute(
            select(Business).where(Business.organization_id == tenant.organization_id)
        )
    else:
        result = await db.execute(
            select(Business).where(Business.owner_id == tenant.user_id)
        )
    return result.scalars().all()


@router.get("/chain/dashboard", response_model=ChainDashboardResponse)
async def get_chain_dashboard(
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    org = await db.get(Organization, tenant.organization_id) if tenant.organization_id else None
    
    if org:
        result = await db.execute(
            select(Business).where(Business.organization_id == org.id)
        )
    else:
        result = await db.execute(
            select(Business).where(Business.owner_id == tenant.user_id)
        )
    
    businesses = result.scalars().all()
    business_ids = [b.id for b in businesses]
    
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start.replace(day=today_start.day - 1) if today_start.day > 1 else today_start.replace(month=today_start.month - 1, day=28)
    
    locations_summary = []
    for biz in businesses:
        sales_result = await db.execute(
            select(func.sum(func.coalesce(func.jsonb_extract_path_text(
                func.cast(func.max(func.jsonb_build_object(
                    'total', 'total_sales',
                    'transactions', 'total_transactions'
                )), 'x'), 'total'), 0)).cast(func.Numeric))
            .where(func.extract('year', func.cast(today_start, func.Date)) == func.extract('year', Business.created_at))
        )
        
        locations_summary.append({
            "id": str(biz.id),
            "name": biz.name,
            "city": biz.city,
            "type": biz.type,
            "status": "active",
            "revenue_today": 0,
            "transactions_today": 0,
        })
    
    return ChainDashboardResponse(
        organization_id=tenant.organization_id or UUID("00000000-0000-0000-0000-000000000000"),
        organization_name=org.name if org else "My Business",
        total_locations=len(businesses),
        total_revenue_today=0,
        total_revenue_yesterday=0,
        total_transactions_today=0,
        locations_summary=locations_summary,
    )


@router.post("/team/invite")
async def invite_team_member(
    data: TeamMemberInvite,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    team_service = TeamService(db)
    result = await team_service.invite_team_member(
        email=data.email,
        business_id=tenant.business_id,
        role=data.role,
        invited_by=tenant.user_id,
        organization_id=tenant.organization_id,
    )
    
    if not result.success:
        raise HTTPException(400, result.message)
    
    return {"invitation_id": str(result.invitation_id), "token": result.token}


@router.get("/team", response_model=list[TeamMemberResponse])
async def get_team_members(
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    team_service = TeamService(db)
    members = await team_service.get_team_members(tenant.business_id)
    return members


@router.get("/team/invitations")
async def get_team_invitations(
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    team_service = TeamService(db)
    invitations = await team_service.get_pending_invitations(tenant.business_id)
    now = datetime.now(timezone.utc)
    return [
        {
            "id": str(inv.id),
            "email": inv.email,
            "role": inv.role,
            "status": "expired" if inv.expires_at and inv.expires_at < now else "pending",
            "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        }
        for inv in invitations
    ]


@router.post("/team/invitations/{invitation_id}/resend")
async def resend_team_invitation(
    invitation_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    team_service = TeamService(db)
    result = await team_service.resend_invitation(invitation_id)
    if not result.success:
        raise HTTPException(404, result.message)
    return {"invitation_id": str(result.invitation_id), "token": result.token, "message": result.message}


@router.patch("/team/{member_id}")
async def update_team_member(
    member_id: UUID,
    data: TeamMemberUpdate,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    team_service = TeamService(db)
    success = await team_service.update_member_role(
        member_id=member_id,
        new_role=data.role,
        updated_by=tenant.user_id,
    )
    
    if not success:
        raise HTTPException(404, "Team member not found")
    
    return {"message": "Role updated"}


@router.delete("/team/{member_id}")
async def remove_team_member(
    member_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    team_service = TeamService(db)
    success = await team_service.remove_team_member(
        member_id=member_id,
        removed_by=tenant.user_id,
    )
    
    if not success:
        raise HTTPException(404, "Team member not found")
    
    return {"message": "Team member removed"}
