"""One writer at a time for `Datasets/`.

DEPLOYMENT AUDIT F-3. Every routine that writes a dataset file — the three
syncs, `sync_all`, the factory reset, and the row-level edit and delete paths —
reads a CSV or xlsx fully, mutates it in memory and rewrites the whole file.
There was no lock of any kind, and all of them execute **inline in the request
handler** rather than through a queue. Two overlapping writers therefore
interleave at whole-file granularity: one sync's appended rows silently vanish
under the other's rewrite, or a factory reset lays a pristine snapshot over a
sync that is still in flight.

Two admins, or one admin with two browser tabs, is all it takes — and both
requests return success, because neither one can see what the other did.

WHY A POSTGRES ADVISORY LOCK, and not a `threading.Lock`:

* It is held in the **database**, so it serialises across processes and across
  uvicorn workers. An in-process mutex protects one worker from itself and
  nothing else, which is the wrong shape for a deployment that will run more
  than one.
* Postgres releases a session-level advisory lock automatically when the
  connection goes away, so a crash mid-write cannot wedge the system. A lock
  file on disk would need a stale-lock reaper; this does not.
* It costs one round trip and no schema.

WHY `try` RATHER THAN A BLOCKING ACQUIRE. These operations rewrite the evidence
base and take seconds. Queueing a second one behind the first means a request
that appears to hang and a user who presses the button again. Refusing with a
409 that names what is already running is the honest answer, and it is the same
shape as the 409 the row-level API already returns for an `original` row.

NOT held across the whole request: acquired immediately before the file work and
released in a `finally`. It deliberately does NOT use `pg_advisory_xact_lock`,
because these routines commit part-way through and a transaction-scoped lock
would be released early — at exactly the moment the file rewrite is still going.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppException

#: Arbitrary but fixed. Any 64-bit int works; this one is derived from the
#: string "jaldrishti.datasets" so it will not collide with another product
#: sharing the database.
DATASET_LOCK_KEY = 7_314_882_099_311_004_001


class DatasetBusyError(AppException):
    """Another dataset write is already running."""

    def __init__(self, message: str):
        super().__init__(message, status_code=409)


@asynccontextmanager
async def dataset_write_lock(db: AsyncSession, *, what: str):
    """Serialise everything that rewrites a file in `Datasets/`.

    `what` names the operation in the 409, so a user who is refused learns which
    other operation holds the lock rather than being told "busy".
    """
    got = (await db.execute(
        text("SELECT pg_try_advisory_lock(:k)"),
        {"k": DATASET_LOCK_KEY})).scalar()

    if not got:
        raise DatasetBusyError(
            f"Another dataset operation is already running, so '{what}' was "
            f"refused rather than run alongside it. These routines rewrite "
            f"whole files; two at once would silently lose one of them. Wait "
            f"for the running operation to finish and try again.")

    logger.info(f"dataset write lock acquired for '{what}'")
    try:
        yield
    finally:
        # A commit inside the body does not release this (it is session-scoped,
        # not transaction-scoped), which is the whole point — but it does mean
        # the unlock has to be explicit.
        try:
            await db.execute(text("SELECT pg_advisory_unlock(:k)"),
                             {"k": DATASET_LOCK_KEY})
            logger.info(f"dataset write lock released after '{what}'")
        except Exception as exc:  # noqa: BLE001
            # Not fatal: Postgres drops session-level advisory locks when the
            # connection closes, so a failure here delays the next writer until
            # this connection is returned and recycled rather than wedging it.
            logger.error(f"could not release the dataset lock after '{what}': "
                         f"{exc}. It will clear when the connection closes.")


def with_dataset_lock(label: str):
    """Decorator form, for the service entry points that write files.

    Applied at the service layer rather than in the routers so that every
    caller is covered — including `sync_all`, which calls the three individual
    syncs, and any future script or job that imports them directly. The project
    already follows this rule for the `original`-row 409: the check lives where
    every caller must pass it, not in one route.

    NESTING IS SAFE. `sync_all` acquires the lock and then calls three functions
    that each acquire it again. Postgres advisory locks are re-entrant within a
    session and counted, so the nested acquisitions succeed and each `finally`
    decrements one. The lock is only truly released when the outermost frame
    exits.

    DRY RUNS SKIP IT. A `dry_run` reports what would change and writes nothing,
    so making it contend for a write lock would refuse a harmless preview while
    a real sync is running — the opposite of useful, since a preview is exactly
    what you want at that moment.
    """
    import functools

    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(db: AsyncSession, *args, **kwargs):
            if kwargs.get("dry_run"):
                return await fn(db, *args, **kwargs)
            async with dataset_write_lock(db, what=label):
                return await fn(db, *args, **kwargs)
        return wrapper
    return deco
