"""OAuth routes for Salla, Zid, and Foodics integrations."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, User
from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access
from app.services.oauth_manager import build_authorize_url, exchange_code, save_oauth_credentials

router = APIRouter(prefix="/api/v1/oauth", tags=["OAuth"])


class AuthorizeRequest(BaseModel):
    provider: str = Field(..., pattern=r"^(salla|zid|foodics)$")
    business_id: UUID
    redirect_uri: str = Field(..., max_length=500)


class CallbackRequest(BaseModel):
    provider: str = Field(..., pattern=r"^(salla|zid|foodics)$")
    code: str = Field(..., min_length=1)
    state: str = Field(..., min_length=1)
    redirect_uri: str = Field(..., max_length=500)


@router.post("/{provider}/authorize")
async def oauth_authorize(
    provider: str,
    req: AuthorizeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, req.business_id, current_user)
    try:
        return build_authorize_url(provider, req.business_id, req.redirect_uri)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{provider}/callback")
async def oauth_callback(
    provider: str,
    req: CallbackRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        token_data = await exchange_code(provider, req.code, req.state, req.redirect_uri)
        result = await save_oauth_credentials(
            db, provider, token_data["business_id"], token_data,
        )
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
