"""P2: migrate `viewer` accounts to `citizen`.

PRODUCT_DESIGN.md section 2. `viewer` was a generic read-only account; `citizen`
is a designed role with a specific constraint attached — it must not reach
precise ISR site coordinates, because every site is hypothetical and publishing
one next to a named village invites it being read as a real plan.

0007 added the value to the enum. This migration moves the accounts, once the
code that distinguishes the roles exists (`app/dependencies.py`: `STAFF_ROLES`
excludes both `citizen` and `viewer`).

`viewer` is NOT removed from the enum. Postgres cannot drop an enum value
without recreating the type, and the label surviving is harmless: the
application no longer assigns it, `STAFF_ROLES` excludes it either way, and
`downgrade()` needs it to move the accounts back.
"""
from alembic import op
import sqlalchemy as sa

revision = '0008_viewer_to_citizen'
down_revision = '0007_orgs_provenance_audit'
branch_labels = None
depends_on = None


def upgrade() -> None:
    res = op.get_bind().execute(
        sa.text("UPDATE users SET role = 'citizen' WHERE role = 'viewer'"))
    print(f"  migrated {res.rowcount} viewer account(s) to citizen")


def downgrade() -> None:
    # Not exact: an account created directly as `citizen` after this migration
    # is indistinguishable from one migrated from `viewer`, so the down path
    # returns every citizen to viewer. Acceptable because the two carry the same
    # privileges in `STAFF_ROLES` terms; recorded here so it is not a surprise.
    res = op.get_bind().execute(
        sa.text("UPDATE users SET role = 'viewer' WHERE role = 'citizen'"))
    print(f"  reverted {res.rowcount} citizen account(s) to viewer")
