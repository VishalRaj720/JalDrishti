"""The regulator role is retired, and nothing can mint one.

WHY THIS EXISTS. PostgreSQL cannot drop a value from an enum type in a
transactional migration, so `'regulator'` still exists as a LABEL in the
`userrole` type and always will. What makes it retired is that the application
vocabulary no longer contains it — `STAFF_ROLES`, every guard, and every RLS
policy.

That is a weaker guarantee than a dropped type, so it is tested rather than
assumed: a label nobody removed is a label somebody can accidentally start
honouring again.

The separation of duties that actually mattered was never the label. It is that
the person who PROPOSES a public screening is not the person who PUBLISHES it,
and that survives the merge intact.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.dependencies import STAFF_ROLES, require_reviewer
from app.models.user import User, UserRole
from app.services.auth import create_access_token, hash_password
from tests.test_p2_site_is_the_operation import FULL_SITE, _tok


@pytest_asyncio.fixture()
async def analyst_token(db_session):
    u = User(username=f"r7an{uuid.uuid4().hex[:5]}",
             email=f"r7an{uuid.uuid4().hex[:5]}@example.com",
             hashed_password=hash_password("pass1234"), role=UserRole.analyst)
    db_session.add(u)
    await db_session.commit()
    return create_access_token(str(u.id), u.role)


def test_regulator_is_not_a_staff_role():
    assert UserRole.regulator not in STAFF_ROLES
    assert set(STAFF_ROLES) == {UserRole.admin, UserRole.analyst,
                                UserRole.field_officer}


def test_reviewing_is_admin_only():
    """`require_reviewer` is named for what it protects, not who holds it.

    That naming is why retiring the role was a one-line change in
    `dependencies.py` rather than an edit at every call site.
    """
    assert require_reviewer.allowed_roles == frozenset({UserRole.admin})


@pytest.mark.asyncio
async def test_no_regulator_accounts_remain(db_session):
    """Migration 0019 merged them into admin rather than deleting them: a
    regulator account belonged to a real person who still needs to sign in."""
    n = (await db_session.execute(
        text("SELECT count(*) FROM users WHERE role = 'regulator'"))).scalar_one()
    assert n == 0


@pytest.mark.asyncio
async def test_no_rls_policy_still_admits_a_regulator(db_session):
    """A policy naming a role nobody can hold is dead code in the one place
    dead code is most dangerous to reason about."""
    rows = (await db_session.execute(text("""
        SELECT tablename, policyname FROM pg_policies
        WHERE qual LIKE '%regulator%' OR with_check LIKE '%regulator%'
    """))).all()
    assert rows == [], f"policies still admit the retired role: {rows}"


@pytest.mark.asyncio
async def test_an_analyst_still_cannot_publish(client, admin_token, analyst_token):
    """The separation the merge had to preserve.

    Retiring the regulator must not have quietly handed publication to whoever
    proposes. Asserted end to end rather than by reading the guard, because the
    guard is exactly what a refactor would get wrong.
    """
    site = (await client.post(
        "/api/v1/isr-points", headers=_tok(admin_token),
        json={"name": f"R7 {uuid.uuid4().hex[:5]}", **FULL_SITE})).json()
    q = (await client.post(f"/api/v1/simulations/{site['id']}", headers=_tok(admin_token),
                           json={"species": "uranium_ppb", "time_years": 10})).json()
    run = (await client.get(f"/api/v1/simulations/runs/{q['id']}",
                            headers=_tok(admin_token))).json()

    adv = await client.post("/api/v1/advisories", headers=_tok(analyst_token), json={
        "run_id": run["id"], "headline": "Screening published for this area",
        "what_it_means": "A model of what would happen if an ISR operation ran here."})
    assert adv.status_code == 201, adv.text

    denied = await client.post(f"/api/v1/advisories/{adv.json()['id']}/decision",
                               headers=_tok(analyst_token), json={"decision": "publish"})
    assert denied.status_code == 403, (
        "an analyst published their own screening; retiring the regulator must "
        "not collapse the proposer and the decider into one person")


@pytest.mark.asyncio
async def test_citizen_copy_no_longer_credits_a_regulator(client, admin_token):
    """With no regulator in the system, saying one published it would be false."""
    from app.api.v1.citizen import _WHAT_THIS_IS
    assert "regulator" not in _WHAT_THIS_IS.lower()
    assert "authority" in _WHAT_THIS_IS.lower()
