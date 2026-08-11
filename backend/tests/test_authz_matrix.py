"""Guards on the authorization surface and on the two production-only bugs.

TWO OF THESE EXIST BECAUSE THE NORMAL SUITE CANNOT SEE THE FAILURES THEY COVER.
Both were found by running the API against the real database as the restricted
`jaldrishti_app` role, and both are invisible here for structural reasons:

  * `conftest.get_db` holds ONE session open for a whole test, so an ORM
    instance is never detached — the real `get_db` closes (and on the 403 path
    rolls back) before the audit middleware runs.
  * tests connect as `postgres`, which bypasses RLS, so a policy that rejects an
    audit INSERT in production silently passes here.

So these assert the INVARIANT that makes each bug impossible, rather than trying
to reproduce a lifecycle the fixtures do not have.
"""
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_authorization_matrix_is_in_sync():
    """docs/roles.md is generated. A stale authorization table gets believed."""
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.authz_matrix", "--check"],
        cwd=BACKEND_DIR, capture_output=True, text=True, timeout=120,
        env={"PYTHONIOENCODING": "utf-8", **_clean_env()},
    )
    assert proc.returncode == 0, (
        f"{proc.stdout}\n{proc.stderr}\n"
        "Run `python -m scripts.authz_matrix` from backend/."
    )


def _clean_env():
    import os
    return {k: v for k, v in os.environ.items()}


def test_audit_actor_is_captured_as_plain_values():
    """Regression: DetachedInstanceError in the audit middleware.

    The middleware must never read attributes off the ORM `User`. By the time it
    runs the session is closed, and on a 403 `get_db` has rolled back — which
    expires every instance regardless of `expire_on_commit`, so touching
    `user.email` raised DetachedInstanceError and destroyed the response.
    """
    src = (BACKEND_DIR / "app" / "main.py").read_text(encoding="utf-8")
    block = src.split("async def audit_middleware")[1].split("await audit.record(")[1]
    for forbidden in ("user.email", "user.id", "current_user.email", "current_user.id"):
        assert forbidden not in block, (
            f"audit middleware reads `{forbidden}` off an ORM instance that is "
            f"detached by then; use request.state.audit_actor primitives."
        )
    assert "audit_actor" in src


def test_audit_writer_bypasses_rls():
    """Regression: the audit trail died silently under RLS.

    `audit_log` has RLS enabled and SQLAlchemy emits INSERT ... RETURNING, which
    requires the new row to be visible under the SELECT policy — admin and
    regulator only. Without the system bypass, every audit write by an analyst,
    field officer or citizen failed, and `record()` swallows its own errors, so
    the trail stopped without a single failed request.
    """
    src = (BACKEND_DIR / "app" / "services" / "audit.py").read_text(encoding="utf-8")
    assert src.count("set_rls_context(db, bypass=True)") >= 2, (
        "audit.record must set the system bypass on its own session, and again "
        "after the IntegrityError rollback (ROLLBACK discards SET LOCAL)."
    )


def test_get_db_opens_unauthenticated():
    """A route that forgets its auth dependency must fail closed, not open."""
    src = (BACKEND_DIR / "app" / "database.py").read_text(encoding="utf-8")
    body = src.split("async def get_db")[1]
    assert "set_rls_context(session)" in body, (
        "get_db must establish an unauthenticated RLS context before yielding."
    )
    assert "SET LOCAL" in src or "set_config" in src


@pytest.mark.parametrize("path", ["/api/v1/audit"])
def test_audit_endpoint_is_read_only(path):
    from app.main import app
    methods = set()
    for r in app.routes:
        if getattr(r, "path", "") == path:
            methods |= (r.methods - {"HEAD", "OPTIONS"})
    assert methods == {"GET"}, f"{path} exposes {methods}; it must be read-only"


def test_citizen_reaches_no_site_endpoint():
    """The coordinate line, checked at the guard level rather than by request."""
    from app.main import app
    from app.models.user import UserRole
    from scripts.authz_matrix import guard_for

    for route in app.routes:
        if not hasattr(route, "methods"):
            continue
        if "isr-points" not in route.path and "simulations" not in route.path:
            continue
        kind, allowed = guard_for(route)
        assert kind == "roles", f"{route.path} has no role guard"
        assert UserRole.citizen not in allowed, (
            f"{route.path} admits `citizen`; design section 2 forbids "
            f"non-staff precise ISR coordinates."
        )
        assert UserRole.viewer not in allowed, (
            f"{route.path} admits legacy `viewer`, which maps to citizen."
        )
