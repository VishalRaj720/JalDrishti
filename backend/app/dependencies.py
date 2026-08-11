"""FastAPI dependency injection: authentication and RBAC.

THE FIVE ROLES (PRODUCT_DESIGN.md section 2), and what each is actually for:

    admin          BIT Sindri / TEXMiN system owner. Everything.
    regulator      CGWB / SPCB / district officer -- the primary government
                   user. Reads every site, publishes, exports, resolves alerts.
    analyst        Technical staff. Runs and saves scenarios. No publish, no ingest.
    field_officer  Station/well data collectors. Uploads readings and samples.
    citizen        Common user. Aggregate risk views only.

`citizen` is deliberately NOT a weaker staff account. Design section 2 forbids
it precise ISR coordinates, because every site is hypothetical and publishing a
precise point for a speculative mine next to a named village invites it being
read as a real plan. `require_staff` is the guard that expresses this: it admits
the four working roles and excludes `citizen`. Use it on anything that exposes a
site location, and `require_authenticated` only where aggregate data is safe.

Note `viewer` is still accepted, mapped alongside `citizen`, until migration
0008 has run everywhere. It is not part of the designed model.
"""
import uuid
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db, set_rls_context
from app.models.user import User, UserRole
from app.services.auth import decode_access_token
from app.repositories.user import UserRepository

# HTTPBearer, not OAuth2PasswordBearer: `POST /auth/token` was deleted in P2 as
# a duplicate credential path, so there is no OAuth2 password endpoint for
# Swagger to post a form to. A plain bearer field is what this API actually
# speaks, and pointing tokenUrl at the JSON /auth/login would be a lie.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(creds.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid token payload.")
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid token payload.")
    user = await UserRepository(db).get(uid)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="User not found.")
    # The role is re-read from the database on every request rather than trusted
    # from the token claim, so a demotion takes effect immediately instead of at
    # token expiry.
    #
    # Stash the resolved user for the audit middleware. It runs outside the
    # request's dependency scope, and reading a VERIFIED user off request.state
    # is both cheaper and safer than re-decoding the token there — a token claim
    # would let a forged `sub` name someone else in the audit trail.
    request.state.current_user = user

    # Hand the verified identity to the RLS policies for this transaction.
    # Done here rather than in `get_db` because only now is the caller known,
    # and it is bound to the same session the route will query through.
    await set_rls_context(
        db,
        role=user.role.value,
        org_id=(str(user.org_id) if user.org_id else None),
    )
    return user


def require_roles(*roles: UserRole):
    """Dependency factory: restrict an endpoint to specific roles."""
    allowed = set(roles)

    async def _check(
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in allowed:
            # Mark the denial so the audit middleware records it even though the
            # request never reached a handler. A refused access attempt is the
            # most interesting line in an access log.
            request.state.authz_denied = {
                "role": current_user.role.value,
                "required": sorted(r.value for r in allowed),
            }
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role.value}' is not allowed for "
                       f"this action.",
            )
        return current_user

    return _check


# ── Role sets ────────────────────────────────────────────────────────
# Named for what they protect, not for who happens to be in them today.

STAFF_ROLES = (UserRole.admin, UserRole.regulator, UserRole.analyst,
               UserRole.field_officer)
PUBLIC_ROLES = (UserRole.citizen, UserRole.viewer)
ALL_ROLES = STAFF_ROLES + PUBLIC_ROLES

require_admin = require_roles(UserRole.admin)
require_regulator_or_admin = require_roles(UserRole.admin, UserRole.regulator)
require_analyst_or_admin = require_roles(UserRole.admin, UserRole.analyst)

#: Any of the four working roles. Excludes `citizen`: use this wherever a
#: response can expose a precise ISR site location (design section 2).
require_staff = require_roles(*STAFF_ROLES)

#: Any authenticated account, citizens included. Only for aggregate or
#: reference data that is safe to show a member of the public.
require_authenticated = require_roles(*ALL_ROLES)

#: Deprecated alias kept so existing routers keep importing successfully.
#: Points at `require_staff`, which is STRICTER than the old three-role tuple --
#: the previous version admitted `viewer` to endpoints that return site
#: coordinates. Retire the alias as each router is reviewed.
require_any_role = require_staff

# Field officers upload monitoring data; admins can too.
require_field_upload = require_roles(UserRole.admin, UserRole.field_officer)
