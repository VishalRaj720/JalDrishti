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

# ── Logging ───────────────────────────────────────────────────────
logger.remove()
logger.add(
    sys.stdout,
    format='{"time":"{time:YYYY-MM-DD HH:mm:ss}", "level":"{level}", "message":"{message}"}',
    level="DEBUG" if settings.APP_ENV == "development" else "INFO",
    serialize=False,
)

# ── Sentry (optional) ─────────────────────────────────────────────
if settings.SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.1)
    logger.info("Sentry initialized.")

# ── Rate limiter ──────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.APP_ENV}]")
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

    @app.get("/", tags=["Root"])
    async def root():
        return {"message": f"Welcome to {settings.APP_NAME}. Docs: /docs"}

    # ── API routes ────────────────────────────────────────────────
    app.include_router(api_router)

    return app


app = create_app()
