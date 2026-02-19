"""FastAPI dependency injection: RBAC, current user."""
import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User, UserRole
from app.services.auth import decode_access_token
from app.repositories.user import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")
    repo = UserRepository(db)
    user = await repo.get(uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user


def require_roles(*roles: UserRole):
    """Dependency factory: restrict endpoint to specific roles."""
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not allowed for this action.",
            )
        return current_user
    return _check


# Convenience shortcuts
require_admin = require_roles(UserRole.admin)
require_analyst_or_admin = require_roles(UserRole.admin, UserRole.analyst)
require_any_role = require_roles(UserRole.admin, UserRole.analyst, UserRole.viewer)
