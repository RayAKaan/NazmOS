from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=1, max_length=100)
    default_currency: str = Field(default="SAR", max_length=3)
    default_timezone: str = Field(default="Asia/Kolkata", max_length=50)


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    logo_url: Optional[str] = None
    primary_color: Optional[str] = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    owner_id: UUID
    default_currency: str
    default_timezone: str
    logo_url: Optional[str]
    primary_color: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BusinessLocationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., pattern=r'^(supermart|cafe|retail|hotel|restaurant)$')
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    location_code: Optional[str] = Field(None, max_length=20)
    location_name: Optional[str] = Field(None, max_length=100)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    is_headquarters: bool = False


class BusinessLocationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    location_code: Optional[str] = Field(None, max_length=20)
    location_name: Optional[str] = Field(None, max_length=100)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    is_headquarters: Optional[bool] = None


class BusinessLocationResponse(BaseModel):
    id: UUID
    name: str
    type: str
    address: Optional[str]
    city: Optional[str]
    organization_id: Optional[UUID]
    location_code: Optional[str]
    location_name: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    is_headquarters: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ChainDashboardResponse(BaseModel):
    organization_id: UUID
    organization_name: str
    total_locations: int
    total_revenue_today: float
    total_revenue_yesterday: float
    total_transactions_today: int
    locations_summary: list[dict]


class TeamMemberInvite(BaseModel):
    email: str = Field(..., format="email")
    role: str = Field(..., pattern=r'^(admin|manager|staff|accountant|viewer)$')


class TeamMemberUpdate(BaseModel):
    role: str = Field(..., pattern=r'^(admin|manager|staff|accountant|viewer)$')


class TeamMemberResponse(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    full_name: str
    role: str
    permissions: list[str]
    is_active: bool
    invited_at: Optional[datetime]
    accepted_at: Optional[datetime]

    class Config:
        from_attributes = True


class InvitationResponse(BaseModel):
    id: UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True
