"""Auth router: signup, login, refresh token."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.auth import SignupRequest, LoginRequest, TokenResponse, RefreshRequest
from app.schemas.user import UserResponse
from app.schemas.common import MessageResponse
from app.services.user import UserService
from app.services.auth import (
    create_access_token, create_refresh_token, decode_refresh_token
)
from app.exceptions import AppException

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth2 compatible token login, used for Swagger UI.
    """
    try:
        svc = UserService(db)
        # OAuth2 form sends 'username', but we use it as 'email'
        user = await svc.authenticate(form_data.username, form_data.password)
        return TokenResponse(
            access_token=create_access_token(str(user.id), user.role),
            refresh_token=create_refresh_token(str(user.id), user.role),
        )
    except AppException as e:
        # OAuth2 spec suggests 400 for invalid grant, but we can propagate 401/400 from service
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Create a new user account (Admin-created in production via /users)."""
    try:
        svc = UserService(db)
        user = await svc.create_user(payload)  # type: ignore
        return user
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        svc = UserService(db)
        user = await svc.authenticate(payload.email, payload.password)
        return TokenResponse(
            access_token=create_access_token(str(user.id), user.role),
            refresh_token=create_refresh_token(str(user.id), user.role),
        )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshRequest):
    try:
        data = decode_refresh_token(payload.refresh_token)
        return TokenResponse(
            access_token=create_access_token(data["sub"], data["role"]),
            refresh_token=create_refresh_token(data["sub"], data["role"]),
        )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/logout", response_model=MessageResponse)
async def logout():
    """Client-side token invalidation (stateless JWT: just drop the token)."""
    return MessageResponse(message="Logged out successfully. Please discard your tokens.")
