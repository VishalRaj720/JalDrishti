"""Auth router: login, logout, me.

P2 (2026-08-11): `POST /auth/signup` WAS DELETED. IT WAS A PRIVILEGE-ESCALATION
HOLE, verified exploitable before removal.

The endpoint took an unauthenticated body whose `role` field flowed straight
into `UserRole(data.role)` with no server-side check. Anyone who could reach the
API could:

    POST /api/v1/auth/signup {"username": "...", "email": "...",
                              "password": "...", "role": "admin"}   -> 201
    POST /api/v1/auth/login  -> a token
    GET  /api/v1/users       -> 200, the admin-only user list

`POST /auth/token` was deleted at the same time as a duplicate of
`POST /auth/login` (design section 3.1); Swagger's OAuth2 flow is not worth a
second credential-accepting path on a government portal.

Account creation is now admin-only via `POST /users`, pending the invitation
flow in design section 3.3. `tests/test_auth_hardening.py` fails if any
unauthenticated route that can mint a user or a role ever reappears.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserResponse
from app.schemas.common import MessageResponse
from app.services.user import UserService
from app.services.auth import create_access_token
from app.services import audit
from app.exceptions import AppException
from app.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host if request.client else None
    try:
        svc = UserService(db)
        user = await svc.authenticate(payload.email, payload.password)
    except AppException as e:
        # Audited explicitly: the middleware cannot attribute this one, because
        # a failed login never resolves a current_user. Repeated failures
        # against one account are the signal worth keeping.
        await audit.record(
            action="login_failed", entity_type="auth",
            actor_label=payload.email, ip_address=ip,
            detail={"reason": e.message},
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)

    await audit.record(
        action="login", entity_type="auth", entity_id=str(user.id),
        actor_id=user.id, actor_label=user.email, ip_address=ip,
        detail={"role": user.role.value},
    )
    return TokenResponse(access_token=create_access_token(str(user.id), user.role))


@router.post("/logout", response_model=MessageResponse)
async def logout():
    """Client-side token invalidation (stateless JWT: just drop the token)."""
    return MessageResponse(message="Logged out successfully. Please discard your tokens.")


@router.post("/refresh", response_model=TokenResponse)
async def refresh(current_user: User = Depends(get_current_user)):
    """Exchange a still-valid token for a fresh one.

    R11 finding O-9: `.env` sets ACCESS_TOKEN_EXPIRE_MINUTES=15 while the code
    default is 480, and there was no way to extend a session. A 401 clears the
    token, so anyone reading a long report — or filling in a submission form —
    was silently signed out mid-task and lost what they were typing.

    This is a **sliding session**, not a refresh-token scheme. It requires a
    token that is still valid, so it extends an active session and cannot
    resurrect an expired one; an attacker holding a stolen token gains nothing
    they did not already have for its remaining lifetime. A real refresh-token
    flow (separate long-lived credential, rotation, server-side revocation) is
    the right end state and needs a token store this prototype does not have —
    recorded in LIMITATIONS.md rather than half-built here.
    """
    return TokenResponse(
        access_token=create_access_token(str(current_user.id), current_user.role))


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return current_user

