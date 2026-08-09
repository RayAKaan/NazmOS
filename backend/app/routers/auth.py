from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    RefreshTokenRequest,
    UserResponse,
    AuthResponse,
    MeResponse,
    CapabilitiesOut,
    TokenResponse,
)
from app.services.auth_service import (
    register_user,
    login_user,
    refresh_access_token,
)
from app.services.capabilities_service import build_capabilities
from app.utils.security import create_access_token, create_refresh_token
from app.middleware.auth_middleware import get_current_user
from app.database import User
from app.config import get_settings

settings = get_settings()

router = APIRouter(prefix="/auth", tags=["Authentication"])


async def _capabilities_out(db: AsyncSession, user: User) -> CapabilitiesOut:
    caps = await build_capabilities(db, user)
    return CapabilitiesOut(
        **caps.to_dict(),
        role=caps.role,
        business_id=caps.business_id,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user, access_token, refresh_token = await register_user(db, data)
    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        refresh_token=refresh_token,
        capabilities=await _capabilities_out(db, user),
    )


@router.post("/login", response_model=AuthResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    user, access_token, refresh_token = await login_user(db, data.email, data.password)
    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        refresh_token=refresh_token,
        capabilities=await _capabilities_out(db, user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    access_token = await refresh_access_token(db, data.refresh_token)
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=MeResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    caps = await build_capabilities(db, current_user)
    return MeResponse(
        user=UserResponse.model_validate(current_user),
        capabilities=CapabilitiesOut(
            **caps.to_dict(),
            role=caps.role,
            business_id=caps.business_id,
        ),
        business_id=caps.business_id,
        role=caps.role,
    )


@router.post("/demo-login", response_model=AuthResponse)
async def demo_login(db: AsyncSession = Depends(get_db)):
    """One-click demo: seeds realistic Saudi retail data, returns JWT.

    Only available when ALLOW_DEMO_SEED=true and ENVIRONMENT=development.
    """
    from app.database.seed import seed_demo_data

    if not settings.ALLOW_DEMO_SEED:
        raise HTTPException(403, detail="Demo seeding is not enabled on this server")

    result = await seed_demo_data(db)
    if not result:
        raise HTTPException(500, detail="Demo seeding failed")

    # Login as the demo user
    user_result = await db.execute(
        text("SELECT * FROM users WHERE id = :id"),
        {"id": result["user_id"]},
    )
    user = user_result.fetchone()

    access_token = create_access_token(data={"sub": str(user.id), "role": user.role})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        refresh_token=refresh_token,
        capabilities=await _capabilities_out(db, user),
    )
