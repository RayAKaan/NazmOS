from datetime import datetime, timedelta
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import User, Business
from app.schemas.auth import RegisterRequest, UserResponse
from app.utils.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.utils.exceptions import UnauthorizedException, DuplicateResourceException


async def register_user(db: AsyncSession, data: RegisterRequest) -> tuple[User, str, str]:
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise DuplicateResourceException("Email already registered")
    
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        phone=data.phone,
        role="owner",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    
    return user, access_token, refresh_token


async def login_user(db: AsyncSession, email: str, password: str) -> tuple[User, str, str]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(password, user.password_hash):
        raise UnauthorizedException("Invalid email or password")
    
    if not user.is_active:
        raise UnauthorizedException("Account is disabled")
    
    user.last_login = datetime.utcnow()
    await db.flush()
    
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    
    return user, access_token, refresh_token


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> str:
    from app.utils.security import verify_refresh_token
    
    valid, payload = verify_refresh_token(refresh_token)
    if not valid:
        raise UnauthorizedException("Invalid refresh token")
    
    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedException("Invalid token payload")
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise UnauthorizedException("User not found or inactive")
    
    return create_access_token({"sub": str(user.id)})


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_demo_business(db: AsyncSession) -> Business | None:
    result = await db.execute(select(Business).where(Business.is_demo == True))
    return result.scalar_one_or_none()
