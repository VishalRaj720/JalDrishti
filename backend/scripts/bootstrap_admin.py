"""Create or reset THE administrator. The only supported way to get one.

R12. A deployment has exactly one admin — the account that operates the dataset
pipeline, the factory reset and the model — and its password must never be a
value that lives in this repository. `scripts/seed.py` therefore does not create
one, and `POST /api/v1/users` refuses to create a second.

    python -m scripts.bootstrap_admin --email you@example.com

THE PASSWORD IS NEVER TAKEN FROM AN ARGUMENT. Command lines end up in shell
history, in `ps` output for every user on the box, and in CI logs. It is read
from a prompt, or from `ADMIN_BOOTSTRAP_PASSWORD` for an automated deploy where
the value comes from a secret store. Only the argon2 hash is ever written, and
nothing prints it back.

WHAT THIS WILL NOT DO:

* create a second admin — if one already exists with a different address it
  says so and stops, because promoting a second operator is a decision, not a
  side effect of running a script;
* print, log or echo the password;
* accept a password from `--password`, for the reason above.

Resetting the existing admin's password is allowed and is the intended recovery
path: run it again with the same address.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import re
import sys
import uuid

from sqlalchemy import select

# Same import shape as the other scripts in this directory.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import AsyncSessionLocal, set_rls_context  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

#: Long enough that a leaked hash is not worth grinding, short of a policy
#: nobody can satisfy. Deliberately not a complexity rule: length beats classes.
MIN_LENGTH = 12

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _read_password() -> str:
    """Prompt, or take the deployment secret. Never an argument."""
    env = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")
    if env:
        if len(env) < MIN_LENGTH:
            raise SystemExit(
                f"ADMIN_BOOTSTRAP_PASSWORD is shorter than {MIN_LENGTH} "
                f"characters. This account can rewrite the evidence base.")
        return env

    if not sys.stdin.isatty():
        raise SystemExit(
            "No terminal to prompt on and ADMIN_BOOTSTRAP_PASSWORD is unset. "
            "Set it from your secret store for an automated deployment.")

    first = getpass.getpass("New administrator password: ")
    if len(first) < MIN_LENGTH:
        raise SystemExit(f"Too short — {MIN_LENGTH} characters minimum.")
    if first != getpass.getpass("Repeat it: "):
        raise SystemExit("The two entries did not match. Nothing was changed.")
    return first


async def _run(email: str, username: str) -> int:
    email = email.strip().lower()
    if not _EMAIL.match(email):
        raise SystemExit(f"'{email}' does not look like an email address.")

    password = _read_password()

    async with AsyncSessionLocal() as db:
        # Bootstrapping runs as the system: there may be no admin yet, so there
        # is nobody whose identity the RLS policies could be set to.
        await set_rls_context(db, bypass=True)

        existing_admin = (await db.execute(
            select(User).where(User.role == UserRole.admin))).scalar_one_or_none()
        by_email = (await db.execute(
            select(User).where(User.email == email))).scalar_one_or_none()

        if existing_admin is not None and existing_admin.email != email:
            print(f"This deployment already has an administrator: "
                  f"{existing_admin.email}", file=sys.stderr)
            print("There is exactly one by design. To hand the role over, "
                  "demote that account first — deliberately, so the change is "
                  "in the audit trail. To give somebody the power to review "
                  "field submissions, assign 'regulator' instead.",
                  file=sys.stderr)
            return 2

        if by_email is not None:
            was = by_email.role.value
            by_email.hashed_password = hash_password(password)
            by_email.role = UserRole.admin
            await db.commit()
            print(f"Updated {email}: role {was} -> admin, password reset.")
        else:
            db.add(User(id=uuid.uuid4(), username=username or email.split("@")[0],
                        email=email, hashed_password=hash_password(password),
                        role=UserRole.admin))
            await db.commit()
            print(f"Created administrator {email}.")

    print("The password was not written to disk, logged, or echoed.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Create or reset the single administrator account.")
    ap.add_argument("--email", required=True, help="the administrator's address")
    ap.add_argument("--username", default="", help="display name; defaults to "
                                                   "the local part of the email")
    args = ap.parse_args()
    return asyncio.run(_run(args.email, args.username))


if __name__ == "__main__":
    raise SystemExit(main())
