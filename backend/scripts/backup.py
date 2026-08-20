"""Back up and restore the two things that cannot be regenerated.

DEPLOYMENT AUDIT. Nothing in this repository backed anything up, and no restore
had ever been tested. Both halves matter and they are different in kind:

  `Datasets/`   the evidence base the physics engine reads. Partly recoverable
                from git — but only the `original` rows. Every `added` row came
                from an approved field submission and exists nowhere else once
                the file is gone.

  PostgreSQL    the audit log above all. It is append-only by policy and by
                design, which makes it the one table in the system with no
                second copy anywhere. Also every field observation, advisory,
                alert, simulation run and account.

A backup that has never been restored is a hypothesis. `--verify` restores into
a scratch database and counts rows, so the procedure is exercised rather than
assumed; `docs/DEPLOYMENT.md` §10 records the result of running it.

    python -m scripts.backup                      # both, into backups/
    python -m scripts.backup --verify             # ... then prove it restores
    python -m scripts.backup --restore <dir>      # bring one back

REQUIRES `pg_dump` / `pg_restore` on PATH. They ship with PostgreSQL; if the
server is remote you still need the client binaries locally, and their major
version must be >= the server's.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DATASETS = REPO / "Datasets"
DEFAULT_OUT = REPO / "backups"

#: Restored into, then dropped. Never the live database.
VERIFY_DB = "jaldrishti_restore_check"


def _dsn() -> dict:
    """Connection parts from the migration URL, which is the privileged one."""
    raw = (os.environ.get("MIGRATION_DATABASE_URL")
           or settings.MIGRATION_DATABASE_URL
           or str(settings.DATABASE_URL))
    u = urlparse(raw.replace("postgresql+asyncpg", "postgresql")
                    .replace("postgresql+psycopg2", "postgresql"))
    return {"host": u.hostname or "localhost", "port": str(u.port or 5432),
            "user": u.username or "postgres", "password": u.password or "",
            "dbname": (u.path or "/").lstrip("/") or "postgres"}


def _env(dsn: dict) -> dict:
    e = os.environ.copy()
    # PGPASSWORD rather than a URL: a password in argv is visible in `ps` to
    # every user on the machine and lands in shell history.
    e["PGPASSWORD"] = dsn["password"]
    return e


def _run(cmd: list[str], dsn: dict) -> None:
    proc = subprocess.run(cmd, env=_env(dsn), capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"{cmd[0]} failed:\n{proc.stderr[-2000:]}")


def backup(out_root: Path) -> Path:
    dsn = _dsn()
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = out_root / stamp
    out.mkdir(parents=True, exist_ok=True)

    # ── database ──
    dump = out / "database.dump"
    print(f"  pg_dump {dsn['dbname']} -> {dump.name}")
    _run(["pg_dump", "-h", dsn["host"], "-p", dsn["port"], "-U", dsn["user"],
          "-d", dsn["dbname"], "-Fc", "--no-owner", "--no-acl",
          "-f", str(dump)], dsn)

    # ── datasets ──
    # Plain tar.gz, not a zip: this has to be readable by whatever is at hand on
    # a server five years from now, and `tar xzf` is that.
    tar_path = out / "datasets.tar.gz"
    print(f"  archiving Datasets/ -> {tar_path.name}")
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(DATASETS, arcname="Datasets",
                filter=lambda ti: None if "/.backups/" in ti.name else ti)

    (out / "MANIFEST.txt").write_text(
        f"JalDrishti backup {stamp}\n"
        f"database : {dsn['dbname']} @ {dsn['host']}:{dsn['port']}\n"
        f"dump     : {dump.stat().st_size:,} bytes (pg_dump -Fc)\n"
        f"datasets : {tar_path.stat().st_size:,} bytes (tar.gz)\n\n"
        f"Restore:\n"
        f"  python -m scripts.backup --restore {out}\n\n"
        f"The dump excludes ownership and ACLs (--no-owner --no-acl) so it can\n"
        f"be restored as any superuser. Row-level security POLICIES are part of\n"
        f"the schema and DO come back; the `jaldrishti_app` role does not, so\n"
        f"run `python -m scripts.create_app_role` after restoring into a fresh\n"
        f"server or RLS will be inert and the API will refuse to start.\n",
        encoding="utf-8")

    print(f"  manifest written")
    return out


def verify(out: Path) -> int:
    """Restore into a scratch database and count rows. The whole point."""
    dsn = _dsn()
    dump = out / "database.dump"
    print(f"\nVerifying {out.name} by restoring into '{VERIFY_DB}' ...")

    _run(["psql", "-h", dsn["host"], "-p", dsn["port"], "-U", dsn["user"],
          "-d", "postgres", "-v", "ON_ERROR_STOP=1",
          "-c", f'DROP DATABASE IF EXISTS "{VERIFY_DB}"'], dsn)
    _run(["psql", "-h", dsn["host"], "-p", dsn["port"], "-U", dsn["user"],
          "-d", "postgres", "-v", "ON_ERROR_STOP=1",
          "-c", f'CREATE DATABASE "{VERIFY_DB}"'], dsn)

    # pg_restore reports non-zero for benign notices (extension comments), so
    # its exit code is not the test — the row counts below are.
    subprocess.run(
        ["pg_restore", "-h", dsn["host"], "-p", dsn["port"], "-U", dsn["user"],
         "-d", VERIFY_DB, "--no-owner", "--no-acl", str(dump)],
        env=_env(dsn), capture_output=True, text=True)

    tables = ["users", "audit_log", "field_observations", "advisories",
              "alerts", "simulation_runs", "water_samples", "monitoring_wells",
              "districts", "blocks"]
    sql = " UNION ALL ".join(
        f"SELECT '{t}' AS t, count(*) FROM {t}" for t in tables)
    live = subprocess.run(
        ["psql", "-h", dsn["host"], "-p", dsn["port"], "-U", dsn["user"],
         "-d", dsn["dbname"], "-t", "-A", "-F", ",", "-c", sql],
        env=_env(dsn), capture_output=True, text=True).stdout.strip()
    back = subprocess.run(
        ["psql", "-h", dsn["host"], "-p", dsn["port"], "-U", dsn["user"],
         "-d", VERIFY_DB, "-t", "-A", "-F", ",", "-c", sql],
        env=_env(dsn), capture_output=True, text=True).stdout.strip()

    def parse(s):
        return {r.split(",")[0]: int(r.split(",")[1])
                for r in s.splitlines() if "," in r}

    a, b = parse(live), parse(back)
    bad = []
    print(f"\n  {'table':22} {'live':>8} {'restored':>10}")
    for t in tables:
        la, lb = a.get(t, -1), b.get(t, -1)
        ok = la == lb and la >= 0
        if not ok:
            bad.append(t)
        print(f"  {t:22} {la:>8} {lb:>10}   {'ok' if ok else 'MISMATCH'}")

    pol = subprocess.run(
        ["psql", "-h", dsn["host"], "-p", dsn["port"], "-U", dsn["user"],
         "-d", VERIFY_DB, "-t", "-A", "-c",
         "SELECT count(*) FROM pg_policies WHERE schemaname='public'"],
        env=_env(dsn), capture_output=True, text=True).stdout.strip()
    print(f"\n  row-level security policies restored: {pol}")
    if pol in ("", "0"):
        bad.append("pg_policies")

    _run(["psql", "-h", dsn["host"], "-p", dsn["port"], "-U", dsn["user"],
          "-d", "postgres", "-c", f'DROP DATABASE IF EXISTS "{VERIFY_DB}"'], dsn)

    if bad:
        print(f"\nRESTORE VERIFICATION FAILED: {bad}")
        return 1
    print("\nRestore verified: every table matched and the policies came back.")
    return 0


def restore(src: Path) -> int:
    dsn = _dsn()
    dump, tar_path = src / "database.dump", src / "datasets.tar.gz"
    if not dump.exists():
        raise SystemExit(f"no database.dump in {src}")

    print(f"About to overwrite database '{dsn['dbname']}' and Datasets/.")
    if input("Type RESTORE to continue: ").strip() != "RESTORE":
        print("Aborted; nothing changed.")
        return 1

    subprocess.run(
        ["pg_restore", "-h", dsn["host"], "-p", dsn["port"], "-U", dsn["user"],
         "-d", dsn["dbname"], "--clean", "--if-exists", "--no-owner",
         "--no-acl", str(dump)], env=_env(dsn), capture_output=True, text=True)
    print("  database restored")

    if tar_path.exists():
        # The live tree is moved aside rather than deleted: a restore that turns
        # out to be the wrong snapshot must not also destroy the current one.
        if DATASETS.exists():
            aside = DATASETS.with_name(
                f"Datasets.before-restore-{_dt.datetime.now():%Y%m%d-%H%M%S}")
            shutil.move(str(DATASETS), str(aside))
            print(f"  existing Datasets/ moved to {aside.name}")
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(REPO)
        print("  Datasets/ restored")

    print("\nIf this was a fresh server, run `python -m scripts.create_app_role` "
          "now — the app role is not part of the dump and RLS is inert without it.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Back up / restore JalDrishti.")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--verify", action="store_true",
                    help="restore into a scratch database and compare row counts")
    ap.add_argument("--restore", metavar="DIR",
                    help="restore FROM this backup directory")
    args = ap.parse_args()

    if args.restore:
        return restore(Path(args.restore))

    print("Backing up ...")
    out = backup(Path(args.out))
    print(f"\nBackup complete: {out}")
    return verify(out) if args.verify else 0


if __name__ == "__main__":
    raise SystemExit(main())
