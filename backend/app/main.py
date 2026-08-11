"""
JalDrishti FastAPI Application
Groundwater contamination impact assessment platform.
"""
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from loguru import logger

from app.config import settings
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

# ── Rate limiter ──────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"])


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
    if n_policies and (is_super or bypasses):
        logger.warning(
            f"ROW-LEVEL SECURITY IS INERT: connected as '{user}' "
            f"(superuser={is_super}, bypassrls={bypasses}), so the "
            f"{n_policies} policies in this database DO NOT APPLY. Run "
            f"`python -m scripts.create_app_role` and point DATABASE_URL at "
            f"jaldrishti_app. Until then, access control is application-layer only."
        )
    elif n_policies:
        logger.info(f"Row-level security active: {n_policies} policies, "
                    f"connected as '{user}' (no bypass).")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.APP_ENV}]")
    await _warn_if_rls_is_inert()
    yield
    logger.info("Shutting down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "JalDrishti – Groundwater Contamination ISR Impact Assessment Platform. "
            "Supports spatial queries, async simulations, ML predictions, and RBAC."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── Rate limiting ─────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── CORS ──────────────────────────────────────────────────────
    # Frontend uses JWT in Authorization headers (not cookies), so
    # allow_credentials=False is correct and permits allow_origins=["*"].
    # In production, restrict to the specific deployed origins.
    origins = settings.cors_origins_list if settings.APP_ENV == "production" else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

        user = getattr(request.state, "current_user", None)
        entity_type, entity_id = audit.entity_from_path(request.url.path)
        detail = {"method": request.method, "status": response.status_code}
        if denied:
            detail["denied"] = denied

        await audit.record(
            action=("access_denied" if denied
                    else f"{request.method.lower()}:{entity_type}"),
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=(user.id if user else None),
            actor_label=(user.email if user else None),
            detail=detail,
            # X-Forwarded-For only when a trusted proxy sets it; behind none,
            # request.client is the truthful source.
            ip_address=(request.client.host if request.client else None),
        )
        return response

    # ── Prometheus metrics (optional) ─────────────────────────────
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator().instrument(app).expose(app, endpoint="/metrics")
        logger.info("Prometheus metrics exposed at /metrics")
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
        logger.exception(f"Unhandled error on {request.method} {request.url}: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error."},
        )

    # ── Health & root ─────────────────────────────────────────────
    @app.get("/health", tags=["Health"])
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