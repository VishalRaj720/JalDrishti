"""Restore `regulator` as a review-only role, and pin `admin` to exactly one.

R12, reversing part of R7. Retiring `regulator` was a reasonable call at the
time — it held four powers and `admin` already had all four, so it was a second
label on one authority. What that missed is that the powers should never have
been the same. Accepting a field officer's evidence into the record and
operating the pipeline that consumes it are different jobs, and giving both to
one account means the only person who can approve a submission is also the only
person who can rewrite the file it lands in.

So the role comes back with a deliberately smaller remit than it had:

    regulator CAN      see the submission queue, approve, reject — and that
                       decision is written to the audit trail like any other
    regulator CANNOT   sync or seed `Datasets/`, factory reset, run model
                       operations, create or promote an admin, or publish an
                       advisory to residents

There may be many regulators. There is exactly **one** admin.

WHY THE POLICIES HAVE TO CHANGE, and why this is the dangerous half of the
migration. A role that passes a FastAPI guard but is absent from the row-level
policies does not get an error — it gets an empty result. A regulator would
have loaded the review queue, seen nothing, and had `approve` report success
while updating zero rows. That exact failure (a policy silently refusing a write
the API had already allowed) is what left this product with eight published
advisories and an empty `alerts` table, so every policy naming the staff list is
rewritten here rather than assumed.

`field_obs_write` is also SPLIT. It was `FOR ALL` with one USING and one CHECK,
and on an UPDATE Postgres applies USING to the old row and WITH CHECK to the
new one — so approving would have needed `regulator` in the CHECK clause too,
which would simultaneously have let a regulator INSERT a submission. Separate
INSERT / UPDATE / DELETE policies say what is actually true: a regulator may
change the status of somebody else's submission and may not create one.

Revision ID: 0022_regulator_single_admin
Revises: 0021_aquifer_pathway
"""
import os

import sqlalchemy as sa
from alembic import op

revision = "0022_regulator_single_admin"
down_revision = "0021_aquifer_pathway"
branch_labels = None
depends_on = None

#: Must stay identical to `app.dependencies.STAFF_ROLES`.
#: `tests/test_rls.py` pins the two together, which is what will catch the next
#: person who adds a role to one and not the other.
_STAFF = "('admin','analyst','field_officer','regulator')"
_BYPASS = "coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'"
_ROLE = "coalesce(current_setting('app.current_role', true), '')"
_UID = "coalesce(current_setting('app.current_user_id', true), '')"

#: Staff-scoped read policies. A regulator that cannot read these can still sign
#: in and reach the portal, but every list is empty and nothing says why.
_STAFF_READ = [
    ("isr_points", "isr_points_read"),
    ("simulation_runs", "sim_runs_read"),
    ("scenarios", "scenarios_read"),
    ("ore_observations", "ore_obs_read"),
]


def upgrade() -> None:
    # ── 1. staff-scoped reads now include regulator ──────────────────
    for table, policy in _STAFF_READ:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(f"""
            CREATE POLICY {policy} ON {table} FOR SELECT
            USING ({_BYPASS} OR {_ROLE} IN {_STAFF})
        """)

    # Advisories keep their extra branch: anything published is world-readable.
    op.execute("DROP POLICY IF EXISTS advisories_read ON advisories")
    op.execute(f"""
        CREATE POLICY advisories_read ON advisories FOR SELECT
        USING ({_BYPASS} OR {_ROLE} IN {_STAFF} OR status = 'published')
    """)

    # ── 2. the review queue ──────────────────────────────────────────
    op.execute("DROP POLICY IF EXISTS field_obs_read ON field_observations")
    op.execute(f"""
        CREATE POLICY field_obs_read ON field_observations FOR SELECT
        USING (
            {_BYPASS}
            OR {_ROLE} IN ('admin','analyst','regulator')
            OR submitted_by::text = {_UID}
        )
    """)

    # Split from the old FOR ALL policy. See the module docstring.
    op.execute("DROP POLICY IF EXISTS field_obs_write ON field_observations")

    # Creating a submission: field officers and admin. NOT regulators — a
    # reviewer who can also submit can approve their own evidence, and
    # `ck_field_obs_no_self_review` only stops them doing it in one step.
    op.execute(f"""
        CREATE POLICY field_obs_insert ON field_observations FOR INSERT
        WITH CHECK (
            {_BYPASS}
            OR {_ROLE} IN ('admin','field_officer')
            OR submitted_by::text = {_UID}
        )
    """)

    # Deciding on one: admin and regulator. A submitter may still update their
    # own row (that is how withdraw works).
    op.execute(f"""
        CREATE POLICY field_obs_update ON field_observations FOR UPDATE
        USING (
            {_BYPASS}
            OR {_ROLE} IN ('admin','regulator')
            OR submitted_by::text = {_UID}
        )
        WITH CHECK (
            {_BYPASS}
            OR {_ROLE} IN ('admin','regulator')
            OR submitted_by::text = {_UID}
        )
    """)

    op.execute(f"""
        CREATE POLICY field_obs_delete ON field_observations FOR DELETE
        USING (
            {_BYPASS}
            OR {_ROLE} = 'admin'
            OR submitted_by::text = {_UID}
        )
    """)

    # ── 3. exactly one admin ─────────────────────────────────────────
    #
    # Resolving an existing multi-admin database is a DATA decision, so the rule
    # is explicit rather than "keep whichever row comes first":
    #
    #   1. the account named by PRODUCTION_ADMIN_EMAIL, if it is an admin
    #   2. otherwise the oldest admin whose address is NOT a seeded demo
    #      account — the real owner, not the fixture
    #   3. otherwise the oldest admin
    #
    # Everyone else is demoted to `analyst`, which keeps them able to sign in
    # and work. Nobody is deleted and no password changes.
    designated = (os.environ.get("PRODUCTION_ADMIN_EMAIL") or "").strip().lower()

    conn = op.get_bind()
    admins = conn.execute(sa.text(
        "SELECT id, email FROM users WHERE role = 'admin' ORDER BY created_at"
    )).fetchall()

    if len(admins) > 1:
        conn.execute(
            sa.text("""
                WITH ranked AS (
                    SELECT id,
                           row_number() OVER (
                               ORDER BY (lower(email) = :designated) DESC,
                                        (email NOT LIKE '%@jaldrishti.local') DESC,
                                        created_at ASC
                           ) AS rn
                    FROM users WHERE role = 'admin'
                )
                UPDATE users SET role = 'analyst'
                WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
            """),
            {"designated": designated},
        )
        kept = conn.execute(sa.text(
            "SELECT email FROM users WHERE role = 'admin'")).scalar()
        print(f"[0022] {len(admins)} admins found; kept '{kept}', demoted the "
              f"rest to analyst. Set PRODUCTION_ADMIN_EMAIL to choose "
              f"explicitly before running this.")

    # The application refuses a second admin in `UserService`, but that check is
    # a race between two concurrent requests and this is not.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_single_admin
        ON users ((role)) WHERE role = 'admin'
    """)


def downgrade() -> None:
    """Undo the admin index and the policy split. Roles are not restored.

    Which accounts this migration demoted is not recorded — the same reason
    0019's downgrade refuses. Anyone demoted stays an analyst until an admin
    promotes them back, which is a deliberate, auditable act.
    """
    op.execute("DROP INDEX IF EXISTS uq_single_admin")

    for table, policy in _STAFF_READ:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(f"""
            CREATE POLICY {policy} ON {table} FOR SELECT
            USING ({_BYPASS} OR {_ROLE} IN ('admin','analyst','field_officer'))
        """)

    op.execute("DROP POLICY IF EXISTS advisories_read ON advisories")
    op.execute(f"""
        CREATE POLICY advisories_read ON advisories FOR SELECT
        USING ({_BYPASS} OR {_ROLE} IN ('admin','analyst','field_officer')
               OR status = 'published')
    """)

    for p in ("field_obs_insert", "field_obs_update", "field_obs_delete"):
        op.execute(f"DROP POLICY IF EXISTS {p} ON field_observations")

    op.execute("DROP POLICY IF EXISTS field_obs_read ON field_observations")
    op.execute(f"""
        CREATE POLICY field_obs_read ON field_observations FOR SELECT
        USING ({_BYPASS} OR {_ROLE} IN ('admin','analyst')
               OR submitted_by::text = {_UID})
    """)
    op.execute(f"""
        CREATE POLICY field_obs_write ON field_observations FOR ALL
        USING ({_BYPASS} OR {_ROLE} = 'admin' OR submitted_by::text = {_UID})
        WITH CHECK ({_BYPASS} OR {_ROLE} IN ('admin','field_officer')
                    OR submitted_by::text = {_UID})
    """)
