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
    # Also stash the identity as PLAIN VALUES. The audit middleware runs after
    # the request's session has closed, and on the 403 path `get_db` rolls back
    # — which expires every ORM instance regardless of `expire_on_commit`.
    # Touching `user.email` there raised DetachedInstanceError and took out the
    # whole response. The test suite cannot see this: its `get_db` override
    # holds one session open for the entire test, so nothing is ever detached.
    request.state.audit_actor = {
        "id": user.id, "email": user.email, "role": user.role.value,
    }

    # Hand the verified identity to the RLS policies for this transaction.
    # Done here rather than in `get_db` because only now is the caller known,
    # and it is bound to the same session the route will query through.
    await set_rls_context(
        db,
        role=user.role.value,
        org_id=(str(user.org_id) if user.org_id else None),
        # field_observations policies scope a field officer to their OWN
        # submissions, so the identity has to reach the database too.
        user_id=str(user.id),
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

    # Expose what this guard admits. A dependency factory returns an opaque
    # closure, so without this the only way to learn which roles an endpoint
    # accepts is to call it and observe a 403 — which is how a role set drifts
    # from the documentation describing it.
    _check.allowed_roles = frozenset(roles)  # type: ignore[attr-defined]
    return _check


# ── Role sets ────────────────────────────────────────────────────────
# Named for what they protect, not for who happens to be in them today.

#: `regulator` was retired in R7 and RESTORED in R12 with a narrower, real job:
#: reviewing what a field officer submits and deciding whether it is accepted.
#: That is a genuinely different authority from `admin`, which is why merging
#: them was wrong — the person who accepts evidence into the record should not
#: also be the person who operates the pipeline that consumes it.
#:
#: A regulator is staff: they must see the submission queue, and the queue lives
#: behind `require_staff`. They are deliberately NOT given any dataset, model or
#: account power — those all sit behind `require_admin`, and a regulator hits
#: exactly the same 403 a citizen would.
STAFF_ROLES = (UserRole.admin, UserRole.analyst, UserRole.field_officer,
               UserRole.regulator)
PUBLIC_ROLES = (UserRole.citizen, UserRole.viewer)
ALL_ROLES = STAFF_ROLES + PUBLIC_ROLES

require_admin = require_roles(UserRole.admin)
require_analyst_or_admin = require_roles(UserRole.admin, UserRole.analyst)

#: Deciding whether a SCREENING reaches residents. Admin only, unchanged.
#: Publication is the act that speaks to the public in the institution's name,
#: and R12 deliberately did NOT hand it to `regulator`: a regulator accepts
#: evidence into the record, which is a different decision from announcing a
#: modelled result to a village.
require_reviewer = require_roles(UserRole.admin)

#: Deciding on a FIELD OFFICER'S SUBMISSION — approve or reject. This is the
#: regulator's whole purpose, and admin retains it because admin retains
#: everything it had before R12.
#:
#: Note what this guard does NOT imply: approving an observation records a
#: decision and nothing else. Writing that observation into `Datasets/` is a
#: separate, admin-only operation (`/dataset-sync/*`), and keeping the two apart
#: is the point of the split — see `services/field_observation.py`.
require_field_reviewer = require_roles(UserRole.admin, UserRole.regulator)

#: Reading the audit trail. Admin only — a regulator's decisions are WRITTEN to
#: it (automatically, by the service) but reading everyone's history is an
#: operator power, not a reviewer's.
require_audit_reader = require_roles(UserRole.admin)

#: Deprecated name from the R7 merge, when it meant "admin". Kept so nothing
#: breaks on import, but it is ambiguous now that `regulator` is real again:
#: prefer `require_field_reviewer` or `require_audit_reader`.
require_regulator_or_admin = require_audit_reader

#: Who may run the contaminant model and place the sites it runs at.
#: Excludes `field_officer` (collects evidence, does not model) and `citizen`.
#:
#: `regulator` was added 2026-08-25 at the product owner's request. R12 had
#: excluded it on the reasoning that a reviewer of field evidence should not
#: also operate the pipeline that consumes it — but running a screening is not
#: operating the pipeline. A CGWB or SPCB officer asking "what would happen if"
#: is the primary real-world user of a screening tool, and refusing them the
#: model while showing them everything it produced was the wrong side of that
#: line. What stays admin-only is unchanged and is the part that matters:
#: publishing to citizens, dataset writes, model operations and accounts.
require_simulation_roles = require_roles(UserRole.admin, UserRole.regulator,
                                         UserRole.analyst)

#: Any staff role. Excludes `citizen`: use this wherever a response can expose
#: a precise ISR site location (design section 2). Includes `regulator` since
#: R12, which is what lets a regulator see the queue it decides on.
require_staff = require_roles(*STAFF_ROLES)

#: KEPT, UNUSED. Left here as a record of a decision that was reversed.
#:
#: R12 first excluded `regulator` from the read side of the dataset tooling —
#: the Dataset Manager listing, the sync status, the model-ops status — on the
#: reasoning that a reviewer has no workflow needing them. The product owner
#: overruled it, and was right: the rule that matters is **only admin WRITES**.
#: Reading is how a reviewer understands what they are deciding about, and a
#: role that can see nothing but a queue cannot judge whether a finding is
#: plausible.
#:
#: Every sync, seed, reset and model operation is a POST behind `require_admin`
#: and always was. Blocking reads never protected the data; it only made the
#: role harder to use.
require_pipeline_staff = require_roles(UserRole.admin, UserRole.analyst,
                                       UserRole.field_officer)

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
