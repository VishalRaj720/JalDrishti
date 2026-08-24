"""
JalDrishti FastAPI Application
Groundwater contamination impact assessment platform.
"""
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from loguru import logger

from app.config import settings, _require_production_secrets
from app.ratelimit import limiter
from app.api.router import api_router
from app.exceptions import AppException
from app.services import audit

# Health checks and metrics scrapes are high-frequency and carry no security
# meaning; auditing them would bury the entries that matter.
_AUDIT_EXEMPT = frozenset({"/health", "/metrics"})

# ── Logging ───────────────────────────────────────────────────────
logger.remove()
logger.add(
    sys.stdout,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
    level="DEBUG" if settings.APP_ENV == "development" else "INFO",
    serialize=False,
)

# The rate limiter lives in `app.ratelimit`: the routers decorate individual
# endpoints with it, and `main` imports the routers, so defining it here would
# be an import cycle.


def _rls_verdict(*, user: str, is_super: bool, bypasses: bool, n_policies: int,
                 app_env: str, allow_inert: bool) -> tuple[str, str]:
    """Decide what to do about the RLS posture. Pure, so it is testable.

    Returns `(level, message)` with level in "ok" | "warn" | "critical" | "fatal".

    Split out of the query because the case that matters — a bypassing role in
    production — cannot be produced by pointing at a correctly configured
    database, and a test that first requires a deliberately broken deployment is
    a test nobody runs. This one is a function call.
    """
    if not n_policies or not (is_super or bypasses):
        return "ok", (f"Row-level security active: {n_policies} policies, "
                      f"connected as '{user}' (no bypass).")

    message = (
        f"ROW-LEVEL SECURITY IS INERT: connected as '{user}' "
        f"(superuser={is_super}, bypassrls={bypasses}), so the "
        f"{n_policies} policies in this database DO NOT APPLY. Run "
        f"`python -m scripts.create_app_role` and point DATABASE_URL at "
        f"jaldrishti_app. Until then, access control is application-layer only."
    )
    if app_env.lower() not in ("production", "prod"):
        return "warn", message
    if allow_inert:
        return "critical", (f"{message} Started anyway because ALLOW_INERT_RLS "
                            f"is set.")
    return "fatal", (
        f"{message} Refusing to start with APP_ENV=production. Set "
        f"ALLOW_INERT_RLS=true to override this deliberately.")


async def _warn_if_rls_is_inert() -> None:
    """Refuse to let RLS be security theatre without saying so.

    Postgres skips row-level security entirely for a superuser or a role with
    BYPASSRLS. If the API connects as such a role, every policy from migration
    0009 exists, reviews cleanly, and enforces nothing. That is worse than
    having no policies at all, because the schema claims protection.
    """
    from sqlalchemy import text
    from app.database import engine
    try:
        async with engine.connect() as conn:
            row = (await conn.execute(text(
                "SELECT current_user, rolsuper, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"))).first()
            n_policies = (await conn.execute(text(
                "SELECT count(*) FROM pg_policies WHERE schemaname = 'public'"
            ))).scalar_one()
    except Exception as exc:  # noqa: BLE001 — never block startup on this check
        logger.warning(f"Could not verify RLS enforcement: {exc}")
        return

    if row is None:
        return
    user, is_super, bypasses = row
    level, message = _rls_verdict(
        user=user, is_super=is_super, bypasses=bypasses, n_policies=n_policies,
        app_env=settings.APP_ENV, allow_inert=settings.ALLOW_INERT_RLS)

    # DEPLOYMENT AUDIT F-4. This used to warn and start regardless. The
    # deployment most likely to get the roles wrong is the first production one,
    # and the symptom is one startup log line in a process whose output nobody
    # reads after the first minute — a live system that believes it has
    # row-level security and does not. `DEPLOYMENT.md` §2.2 already says "get
    # this right or RLS is silently inert"; refusing to start is what makes that
    # sentence true. Development still only warns, because a laptop connecting
    # as `postgres` is the normal case and blocking it would help nobody.
    if level == "fatal":
        logger.critical(message)
        raise RuntimeError(message)
    if level == "critical":
        logger.critical(message)
    elif level == "warn":
        logger.warning(message)
    else:
        logger.info(message)


async def _reap_orphaned_runs() -> None:
    """Clear simulations abandoned by a previous restart.

    Runs execute as in-process background tasks, so a restart ends whatever was
    in flight and leaves the row at `queued` for ever — a spinner nobody can
    clear. The audit found three real ones from the previous day.

    Never blocks startup: if this fails the API still serves, it just leaves the
    corpses for the next boot or for `POST /simulations/reap`.
    """
    from app.database import AsyncSessionLocal, set_rls_context
    from app.services.simulation_run import reap_orphaned_runs
    try:
        async with AsyncSessionLocal() as db:
            await set_rls_context(db, bypass=True)
            out = await reap_orphaned_runs(db)
        if out["reaped"]:
            logger.warning(f"startup: failed {out['reaped']} simulation run(s) "
                           f"abandoned by an earlier restart")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Could not reap orphaned simulation runs: {exc}")


def _enforce_production_secrets() -> None:
    """Refuse to start production on placeholder secrets.

    AUDIT 2026-08-24, finding #3. `_warn_if_rls_is_inert` already refuses to
    start production with unenforced row-level security; this is the same idea
    applied to the control that sits IN FRONT of it. A token forged with the
    published default secret arrives as a valid administrator, and RLS serves it
    faithfully -- the database cannot tell a real admin from a minted one, so no
    policy below can compensate for a known signing key.

    Development is untouched: a laptop on the default secret is the normal case,
    and blocking it would help nobody.
    """
    if not settings.is_production:
        return
    problems = _require_production_secrets(settings)
    if not problems:
        return
    message = ("Refusing to start with APP_ENV=production:\n  - "
               + "\n  - ".join(problems))
    logger.critical(message)
    raise RuntimeError(message)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.APP_ENV}]")
    _enforce_production_secrets()
    await _warn_if_rls_is_inert()
    await _reap_orphaned_runs()
    yield
    logger.info("Shutting down.")


def create_app() -> FastAPI:
    # AUDIT 2026-08-24, finding #6. Swagger and the OpenAPI schema publish the
    # full route inventory, every request/response shape and every role guard --
    # a reconnaissance gift on a public host, and they were served
    # unconditionally. Development keeps them, because they are how you work on
    # this API; production opts back in with DOCS_ENABLED.
    _expose_docs = settings.DOCS_ENABLED or not settings.is_production
    _docs_url = "/docs" if _expose_docs else None
    _redoc_url = "/redoc" if _expose_docs else None
    # /openapi.json has to go too: on its own it reconstructs everything /docs
    # renders, so hiding only the HTML page would be theatre.
    _openapi_url = "/openapi.json" if _expose_docs else None
    if not _expose_docs:
        logger.info("API docs disabled (production; set DOCS_ENABLED=true to serve them)")

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "JalDrishti – Groundwater Contamination ISR Impact Assessment Platform. "
            "Supports spatial queries, async simulations, ML predictions, and RBAC."
        ),
        docs_url=_docs_url,
        redoc_url=_redoc_url,
        openapi_url=_openapi_url,
        lifespan=lifespan,
    )

    # ── Rate limiting ─────────────────────────────────────────────
    # AUDIT 2026-08-24, finding #1. Both of these lines were already here, and
    # neither one applies a limit: slowapi enforces `default_limits` from
    # SlowAPIMiddleware, and without it the Limiter is a configured object that
    # nothing ever consults. Measured before the fix: 120 POST /auth/login in
    # 5.7 s, zero 429s.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # ── CORS ──────────────────────────────────────────────────────
    # Frontend uses JWT in Authorization headers (not cookies), so
    # allow_credentials=False is correct and permits allow_origins=["*"].
    # In production, restrict to the specific deployed origins.
    # AUDIT finding #7: this tested `== "production"` while the metrics block
    # below tested `.lower() in ("production", "prod")`. With `APP_ENV=prod` the
    # metrics guard engaged and CORS still fell through to every origin -- two
    # controls disagreeing about which environment they were in. One definition
    # now, on Settings.
    origins = settings.cors_origins_list if settings.is_production else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Cache policy (deployment audit F-5) ───────────────────────
    #
    # `no-store` was set by hand in 4 of 21 routers, so `/audit`, `/users`,
    # `/isr-points`, `/field-observations`, `/datasets` and a dozen more sent no
    # Cache-Control at all. The project already holds this principle and tests
    # it in `test_ml_router.py`: "`private, max-age` is not per-user. Only
    # `no-store` keeps a citizen from being handed an analyst's cached response
    # by their own browser." It applies at least as strongly to the audit log.
    #
    # Default-deny is the right shape: a new router is safe on the day it is
    # written, and the handful of genuinely public, genuinely cacheable layers
    # opt out by setting their own header, which this will not overwrite.
    # -- Security headers (AUDIT 2026-08-24, finding #5) -----------
    #
    # There were none at all -- verified against a live response rather than
    # assumed. Each of these closes a specific hole rather than being decoration:
    #
    #   nosniff          stops a browser re-interpreting a JSON error body as
    #                    HTML and executing script inside it
    #   DENY             this API is never legitimately framed, and framing it
    #                    is how a clickjack gets an admin to click Publish
    #   no-referrer      request paths carry site UUIDs; a Referer header would
    #                    leak them to wherever the user navigates next
    #   CSP              applies to what THIS service serves (error bodies, and
    #                    Swagger when enabled). The SPA is served by the gateway
    #                    and carries its own policy.
    #
    # `setdefault`, not assignment: a route that has deliberately set its own
    # value knows something this middleware does not.
    #
    # HSTS is opt-in. Sent over plain HTTP it pins the browser to a scheme the
    # host cannot answer, which breaks the deployment it was meant to protect.
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        # Swagger legitimately loads its own bundled CSS/JS, so the strict
        # policy would blank the page it is trying to protect.
        if request.url.path not in ("/docs", "/redoc"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        if settings.HSTS_ENABLED:
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={settings.HSTS_MAX_AGE}; includeSubDomains")
        return response

    @app.middleware("http")
    async def cache_policy(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/")                 and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

    # ── Audit trail ───────────────────────────────────────────────
    # Records every mutating request and every authorisation denial. Registered
    # AFTER CORS so it sees the real request, and it never fails the response:
    # `audit.record` swallows and logs its own errors (see that module).
    @app.middleware("http")
    async def audit_middleware(request: Request, call_next):
        response = await call_next(request)

        denied = getattr(request.state, "authz_denied", None)
        mutating = request.method in audit.MUTATING_METHODS
        if not (mutating or denied) or request.url.path in _AUDIT_EXEMPT:
            return response

        # Plain values, not the ORM object: by the time this runs the request's
        # session is closed, and on the 403 path it was rolled back, which
        # expires every instance. See dependencies.get_current_user.
        actor = getattr(request.state, "audit_actor", None) or {}
        entity_type, entity_id = audit.entity_from_path(request.url.path)
        detail = {"method": request.method, "status": response.status_code}
        if denied:
            detail["denied"] = denied

        await audit.record(
            action=("access_denied" if denied
                    else f"{request.method.lower()}:{entity_type}"),
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor.get("id"),
            actor_label=actor.get("email"),
            detail=detail,
            # X-Forwarded-For only when a trusted proxy sets it; behind none,
            # request.client is the truthful source.
            ip_address=(request.client.host if request.client else None),
        )
        return response

    # ── Prometheus metrics (optional, and not world-readable) ─────
    #
    # DEPLOYMENT AUDIT F-2. This used to be `.expose(app, endpoint="/metrics")`
    # with no guard at all: `curl http://host/metrics` returned the full
    # Prometheus dump to anyone. Metrics leak the route inventory, request
    # volumes and latencies — reconnaissance that costs an attacker nothing.
    #
    # Three states now, and the production default is the safe one:
    #   token set        -> exposed, requires `Authorization: Bearer <token>`
    #   dev, no token    -> exposed openly (a token on a laptop protects nothing)
    #   production, none -> NOT MOUNTED, and says so at startup
    _is_prod = settings.is_production
    if not settings.METRICS_ENABLED:
        logger.info("Prometheus metrics disabled by METRICS_ENABLED=false")
    elif _is_prod and not settings.METRICS_TOKEN:
        logger.warning(
            "Prometheus metrics NOT exposed: APP_ENV is production and "
            "METRICS_TOKEN is unset. Set METRICS_TOKEN to enable an "
            "authenticated /metrics, or METRICS_ENABLED=false to silence this.")
    else:
        try:
            from prometheus_fastapi_instrumentator import Instrumentator

            if settings.METRICS_TOKEN:
                @app.middleware("http")
                async def _guard_metrics(request: Request, call_next):
                    if request.url.path == "/metrics":
                        # `Bearer <token>` is what a Prometheus scrape config
                        # sends; compared with compare_digest so the check does
                        # not leak the token's prefix through timing.
                        import hmac
                        sent = request.headers.get("authorization", "")
                        prefix = "Bearer "
                        ok = sent.startswith(prefix) and hmac.compare_digest(
                            sent[len(prefix):], settings.METRICS_TOKEN)
                        if not ok:
                            return JSONResponse(
                                status_code=401,
                                content={"detail": "Metrics require a bearer token."})
                    return await call_next(request)

            Instrumentator().instrument(app).expose(app, endpoint="/metrics")
            logger.info(
                "Prometheus metrics exposed at /metrics "
                + ("(bearer token required)" if settings.METRICS_TOKEN
                   else "(OPEN - development only)"))
        except ImportError:
            pass

    # ── Global exception handlers ─────────────────────────────────
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # A row-level security refusal is an AUTHORIZATION outcome, not a server
        # fault. Postgres raises insufficient_privilege (42501) when a row fails
        # a policy's USING or WITH CHECK clause; reporting that as 500 tells the
        # caller "we broke" when the truth is "you may not do that", and buries
        # a working security control in the error log as if it were a defect.
        if getattr(getattr(exc, "orig", None), "sqlstate", None) == "42501":
            logger.warning(
                f"RLS refused {request.method} {request.url.path}: {exc}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "The database's row-level security policy "
                                   "refused this row for your role."},
            )
        logger.exception(f"Unhandled error on {request.method} {request.url}: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error."},
        )

    # ── Health & root ─────────────────────────────────────────────
    # Exempt from the rate limiter: a liveness probe that starts answering 429
    # gets the container killed by its own orchestrator, which turns a busy
    # minute into an outage.
    @app.get("/health", tags=["Health"])
    @limiter.exempt
    async def health():
        return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}

    # The `GET /` welcome banner was deleted in P2 (PRODUCT_DESIGN.md section
    # 3.1): the SPA owns that route, and an API that answers 200 at the origin
    # makes it harder to tell a healthy deployment from a misrouted one.
    # `GET /health` is the liveness check.

    # ── API routes ────────────────────────────────────────────────
    app.include_router(api_router)

    return app


app = create_app()

# if __name__=='__main__':
#     import uvicorn
#     uvicorn.run(app, host="localhost", port=8000)