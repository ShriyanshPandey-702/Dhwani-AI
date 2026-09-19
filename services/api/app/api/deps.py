from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import decode_token
from app.models.models import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials:
        token = credentials.credentials
        try:
            payload = decode_token(token)
            if payload.get("type") == "access" and "sub" in payload:
                user_id: str = payload["sub"]
                result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
                user = result.scalar_one_or_none()
                if user:
                    return user
        except (JWTError, KeyError):
            pass

    # Standalone mode / unauthenticated prototype access: return default active user
    result = await db.execute(select(User).where(User.is_active == True).order_by(User.created_at.asc()).limit(1))
    user = result.scalar_one_or_none()
    if not user:
        # Auto-provision default user if DB is fresh
        user = User(
            id="00000000-0000-0000-0000-000000000001",
            email="analyst@voiceshield.in",
            password_hash="!standalone",
            full_name="VoiceShield Analyst",
            role="admin",
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user
