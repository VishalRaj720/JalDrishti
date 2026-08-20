"""A visible record of work that takes longer than a click.

THE PROBLEM. Several admin actions do real work — a flow-field rebuild reads a
671 MB raster, a sync rewrites a 9,583-row CSV, a model backup copies 12 MB — and
the UI said nothing while they ran. A button that stays pressed for forty seconds
with no feedback is indistinguishable from a button that did nothing, so the
honest reading of the old behaviour was "I have no idea whether that worked".

WHAT THIS IS. An in-process registry: start a job, finish or fail it, list the
recent ones. Jobs run as FastAPI background tasks, the same mechanism the
simulation runner already uses. No queue is introduced — `PRODUCT_DESIGN.md`
§3.6 records why a broker is the right end state only if this ever ingests
sensor streams, and it is heavy machinery for a handful of admin actions.

WHAT THIS IS NOT: durable. The registry lives in memory and is empty after a
restart, which is stated in the API response rather than left for someone to
discover. That is acceptable *because it is not the record* — every one of these
actions already writes to the audit log, which is append-only and survives
everything. This is the progress indicator; the audit log is the history.
"""
from __future__ import annotations

import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from loguru import logger

#: Most recent first, capped — this is a progress view, not storage.
_MAX = 50
_jobs: deque[dict[str, Any]] = deque(maxlen=_MAX)
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def start(kind: str, *, label: str, actor: Optional[str] = None,
          detail: Optional[dict[str, Any]] = None) -> str:
    """Register a job as running. Returns its id."""
    job = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "label": label,
        "status": "running",
        "actor": actor,
        "started_at": _now(),
        "finished_at": None,
        "duration_s": None,
        "message": None,
        "error": None,
        "detail": detail or {},
    }
    with _lock:
        _jobs.appendleft(job)
    logger.info(f"job {job['id']} started: {label}")
    return job["id"]


def _find(job_id: str) -> Optional[dict[str, Any]]:
    with _lock:
        for j in _jobs:
            if j["id"] == job_id:
                return j
    return None


def finish(job_id: str, *, message: str = "", detail: Optional[dict] = None) -> None:
    j = _find(job_id)
    if not j:
        return
    with _lock:
        j["status"] = "succeeded"
        j["finished_at"] = _now()
        j["message"] = message
        if detail:
            j["detail"] = {**j["detail"], **detail}
        j["duration_s"] = _elapsed(j)
    logger.info(f"job {job_id} succeeded in {j['duration_s']}s: {message}")


def fail(job_id: str, error: str) -> None:
    j = _find(job_id)
    if not j:
        return
    with _lock:
        j["status"] = "failed"
        j["finished_at"] = _now()
        j["error"] = error
        j["duration_s"] = _elapsed(j)
    logger.error(f"job {job_id} failed after {j['duration_s']}s: {error}")


def _elapsed(j: dict[str, Any]) -> float:
    a = datetime.fromisoformat(j["started_at"])
    b = datetime.fromisoformat(j["finished_at"] or _now())
    return round((b - a).total_seconds(), 1)


def listing() -> dict[str, Any]:
    with _lock:
        jobs = [dict(j) for j in _jobs]
    for j in jobs:
        if j["status"] == "running":
            # Live elapsed, so a long job visibly ticks rather than looking stuck.
            j["duration_s"] = _elapsed(j)
    running = [j for j in jobs if j["status"] == "running"]
    return {
        "running": len(running),
        "jobs": jobs,
        "note": ("This list is in-process and is empty after a restart. It is the "
                 "progress view, not the record — every action here also writes to "
                 "the audit log, which is append-only and permanent."),
    }


def run(kind: str, *, label: str, actor: Optional[str], fn: Callable[[], Any],
        detail: Optional[dict] = None) -> Callable[[], None]:
    """Wrap a callable so it reports itself into the registry.

    Returns a zero-arg function suitable for `BackgroundTasks.add_task`. The job
    is registered as running *before* it is handed over, so the UI shows it the
    moment the request returns rather than after the work begins.
    """
    job_id = start(kind, label=label, actor=actor, detail=detail)

    def _wrapped() -> None:
        try:
            out = fn()
            msg = ""
            extra = None
            if isinstance(out, dict):
                msg = str(out.get("message", ""))
                extra = {k: v for k, v in out.items()
                         if isinstance(v, (str, int, float, bool, type(None)))}
            finish(job_id, message=msg, detail=extra)
        except Exception as exc:  # noqa: BLE001
            # Never re-raise: a background task that raises dies silently in the
            # worker and the UI would show "running" forever.
            fail(job_id, str(exc))

    _wrapped.job_id = job_id  # type: ignore[attr-defined]
    return _wrapped


def run_async(kind: str, *, label: str, actor: Optional[str],
              coro_factory, detail: Optional[dict] = None):
    """Async twin of `run`, for work that needs its own database session.

    The request's session is closed by the time a background task runs, so a job
    that touches the database has to open its own — which means the callable is
    a coroutine and cannot go through `run`.
    """
    job_id = start(kind, label=label, actor=actor, detail=detail)

    async def _wrapped() -> None:
        try:
            out = await coro_factory()
            msg, extra = "", None
            if isinstance(out, dict):
                msg = str(out.get("message", ""))
                extra = {k: v for k, v in out.items()
                         if isinstance(v, (str, int, float, bool, type(None)))}
            finish(job_id, message=msg, detail=extra)
        except Exception as exc:  # noqa: BLE001
            # Never re-raise: a background task that raises dies silently in the
            # worker and the UI would show "running" for ever.
            fail(job_id, str(exc))

    _wrapped.job_id = job_id  # type: ignore[attr-defined]
    return _wrapped
