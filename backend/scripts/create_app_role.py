"""Create the restricted database role the API should connect as.

WHY THIS EXISTS. The application connects as `postgres`, which is a superuser
with `rolbypassrls = true`. Row-level security does not apply to such a role —
verified empirically: a table with `FORCE ROW LEVEL SECURITY` and a
`USING (false)` deny-all policy still returned every row to this connection.

That means RLS policies written while the app connects as `postgres` are
**security theatre**: they exist in the schema, survive review, and enforce
nothing. The policies in migration 0009 are only real once the API connects as
a role that cannot bypass them.

Two roles, deliberately separated:

    postgres (or another owner)  runs migrations and `init_db`. Needs to
                                 CREATE EXTENSION and own tables.
    jaldrishti_app               what the API connects as. NOSUPERUSER,
                                 NOBYPASSRLS, no DDL, no table ownership.

Usage (as a superuser):

    python -m scripts.create_app_role --password 'choose-a-real-one'

Then point the API at it and leave migrations on the owner role:

    DATABASE_URL=postgresql+asyncpg://jaldrishti_app:<password>@localhost:5432/groundwater_db

`app/main.py` logs a loud warning at startup if the connected role can bypass
RLS while policies exist, so this cannot be forgotten silently.
"""
from __future__ import annotations

import argparse
import sys

import psycopg2
from psycopg2 import sql

from app.config import settings

APP_ROLE = "jaldrishti_app"


def create_app_role(password: str, dbname: str, role: str = APP_ROLE) -> None:
    conn = psycopg2.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=settings.DB_USER, password=settings.DB_PASSWORD, dbname=dbname,
    )
    conn.autocommit = True
    ident = sql.Identifier(role)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if cur.fetchone():
            print(f"role {role} exists — updating password and attributes")
            cur.execute(sql.SQL(
                "ALTER ROLE {} WITH LOGIN NOSUPERUSER NOBYPASSRLS "
                "NOCREATEDB NOCREATEROLE PASSWORD %s").format(ident), (password,))
        else:
            cur.execute(sql.SQL(
                "CREATE ROLE {} WITH LOGIN NOSUPERUSER NOBYPASSRLS "
                "NOCREATEDB NOCREATEROLE PASSWORD %s").format(ident), (password,))
            print(f"created role {role}")

        db_ident = sql.Identifier(dbname)
        cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(db_ident, ident))
        cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(ident))
        # DML only. No CREATE, no ownership: the app must not be able to drop a
        # policy that constrains it.
        cur.execute(sql.SQL(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
            "TO {}").format(ident))
        cur.execute(sql.SQL(
            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(ident))
        # Tables created by future migrations must be reachable too.
        cur.execute(sql.SQL(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}").format(ident))
        cur.execute(sql.SQL(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "GRANT USAGE, SELECT ON SEQUENCES TO {}").format(ident))

        cur.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s",
                    (role,))
        rolsuper, rolbypassrls = cur.fetchone()
        if rolsuper or rolbypassrls:
            raise SystemExit(
                f"REFUSING: {role} has superuser={rolsuper} bypassrls={rolbypassrls}. "
                f"RLS would not apply to it.")
        print(f"verified {role}: superuser=False bypassrls=False")
    conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--password", required=True, help="password for the app role")
    ap.add_argument("--dbname", default=settings.DB_NAME)
    ap.add_argument("--role", default=APP_ROLE)
    args = ap.parse_args()
    create_app_role(args.password, args.dbname, args.role)
    print("\nNow set, for the API only (leave migrations on the owner role):")
    print(f"  DATABASE_URL=postgresql+asyncpg://{args.role}:<password>"
          f"@{settings.DB_HOST}:{settings.DB_PORT}/{args.dbname}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
