"""Generate the role x endpoint authorization matrix from the live app.

The matrix in `docs/roles.md` is GENERATED, not hand-written, for the same
reason ARCHITECTURE.md section 6.5 is: a hand-maintained table of who can reach
what goes stale the first time a route is added, and a stale authorization table
is worse than none — it gets believed.

The guard on each route is read by walking the FastAPI dependency tree and
inspecting the closure of `require_roles(...)`, so this reports what the code
ACTUALLY enforces, not what a docstring claims.

    python -m scripts.authz_matrix            # rewrite the block in docs/roles.md
    python -m scripts.authz_matrix --check    # exit 1 if the block is stale
    python -m scripts.authz_matrix --print    # emit to stdout
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.main import app
from app.models.user import UserRole

DOC = Path(__file__).resolve().parents[2] / "docs" / "roles.md"
BEGIN = "<!-- BEGIN GENERATED AUTHZ MATRIX -->"
END = "<!-- END GENERATED AUTHZ MATRIX -->"

# R7 retired `regulator` (migration 0019). The enum LABEL survives in Postgres
# because a value cannot be dropped transactionally, but no account holds it
# (`test_no_regulator_accounts_remain`) and no guard admits it
# (`test_regulator_is_not_a_staff_role`). Generating a column for it published a
# reachability figure — "regulator 12/102" — for a role that cannot sign in,
# which is the most persuasive possible argument for bringing it back.
# R12 restored `regulator`, so the matrix needs a column for it — without one
# the generated table showed `approve`/`reject` as admin-only, which is exactly
# the stale-documentation failure this file exists to prevent.
ROLE_ORDER = [UserRole.admin, UserRole.regulator, UserRole.analyst,
              UserRole.field_officer, UserRole.citizen]

# Not part of the product's role model.
_SKIP_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _walk(dep, seen=None):
    """Yield every dependency callable in the tree, once."""
    seen = seen if seen is not None else set()
    for d in dep.dependencies:
        if id(d) in seen:
            continue
        seen.add(id(d))
        yield d.call
        yield from _walk(d, seen)


def guard_for(route) -> tuple[str, frozenset[UserRole] | None]:
    """Return (kind, allowed_roles).

    kind is 'public' (no authentication at all), 'authenticated' (a token is
    required but no role is checked), or 'roles' (a role set is enforced).
    """
    dep = getattr(route, "dependant", None)
    if dep is None:
        return ("public", None)

    needs_auth = False
    role_sets: list[frozenset] = []
    for fn in _walk(dep):
        if getattr(fn, "__name__", "") == "get_current_user":
            needs_auth = True
        for cell in (getattr(fn, "__closure__", None) or ()):
            try:
                v = cell.cell_contents
            except ValueError:
                continue
            if (isinstance(v, (set, frozenset, tuple)) and v
                    and all(isinstance(x, UserRole) for x in v)):
                role_sets.append(frozenset(v))
                needs_auth = True

    if role_sets:
        # Nested guards intersect: every one of them must pass.
        allowed = frozenset.intersection(*role_sets)
        return ("roles", allowed)
    return ("authenticated" if needs_auth else "public", None)


def rows():
    out = []
    for route in app.routes:
        if not hasattr(route, "methods"):
            continue
        path = route.path
        if path in _SKIP_PATHS:
            continue
        kind, allowed = guard_for(route)
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            out.append((path, method, kind, allowed))
    out.sort(key=lambda r: (not r[0].startswith("/api/v1"), r[0], r[1]))
    return out


def render() -> str:
    lines = [BEGIN, ""]
    header = "| Endpoint | " + " | ".join(r.value for r in ROLE_ORDER) + " |"
    lines.append(header)
    lines.append("|---" * (len(ROLE_ORDER) + 1) + "|")

    n_by_role = {r: 0 for r in ROLE_ORDER}
    for path, method, kind, allowed in rows():
        cells = []
        for role in ROLE_ORDER:
            if kind == "public":
                mark = "○"
            elif kind == "authenticated":
                mark = "●"
            else:
                mark = "●" if role in allowed else "·"
            if mark == "●":
                n_by_role[role] += 1
            cells.append(mark)
        lines.append(f"| `{method} {path}` | " + " | ".join(cells) + " |")

    lines.append("")
    lines.append("**● = permitted · `·` = 403 · ○ = no authentication required**")
    lines.append("")
    total = len(rows())
    tally = " · ".join(f"**{r.value}** {n_by_role[r]}/{total}" for r in ROLE_ORDER)
    lines.append(f"Reachable endpoints per role — {tally}")
    lines.append("")
    lines.append(END)
    return "\n".join(lines)


def sync(check: bool = False) -> bool:
    text = DOC.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        raise SystemExit(f"{DOC} is missing the generated-block markers.")
    head = text.split(BEGIN)[0]
    tail = text.split(END, 1)[1]
    new = head + render() + tail
    if check:
        return new == text
    if new != text:
        DOC.write_text(new, encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--print", dest="do_print", action="store_true")
    args = ap.parse_args()
    if args.do_print:
        print(render())
        return 0
    if args.check:
        if not sync(check=True):
            print("docs/roles.md authorization matrix is STALE — run "
                  "`python -m scripts.authz_matrix`", file=sys.stderr)
            return 1
        print("authorization matrix is in sync")
        return 0
    sync()
    print(f"wrote {DOC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
