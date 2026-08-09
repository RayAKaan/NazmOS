from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from uuid import UUID


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    phone: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    phone: str | None
    role: str
    is_active: bool
    last_login: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class CapabilitiesOut(BaseModel):
    """What the current user can do, computed server-side.

    Mirrors app/services/capabilities_service.py. The frontend renders from
    this object; it never independently decides permissions.
    """
    is_platform_operator: bool = False
    can_view_ops_console: bool = False
    can_run_admin_tools: bool = False
    can_manage_team: bool = False
    can_run_orchestrator: bool = False
    can_approve_actions: bool = False
    role: str | None = None
    business_id: UUID | None = None


class MeResponse(BaseModel):
    """Session/session-identity response for GET /auth/me."""
    user: UserResponse
    capabilities: CapabilitiesOut
    business_id: UUID | None
    role: str | None


class AuthResponse(BaseModel):
    user: UserResponse
    access_token: str
    refresh_token: str
    capabilities: CapabilitiesOut | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
