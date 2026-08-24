"""Application configuration using pydantic-settings."""
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_ENV: str = "development"
    APP_NAME: str = "JalDrishti API"
    APP_VERSION: str = "1.0.0"
    PORT: int = 8000

    # ── Metrics (deployment audit F-2) ────────────────────────────────
    # `/metrics` served Prometheus output to anyone, unauthenticated: route
    # inventory, request volumes and timings, free reconnaissance on which
    # endpoints exist and how busy the deployment is.
    #
    # `METRICS_TOKEN` is the intended production control — set it and the
    # endpoint requires `Authorization: Bearer <token>`, which is what a
    # Prometheus scrape config supplies. Leave it empty in development and the
    # endpoint stays open, because a token on a laptop protects nothing and
    # makes `curl /metrics` annoying.
    #
    # With APP_ENV=production and no token set, metrics are NOT exposed at all.
    # Failing closed is the right default for a surface nobody notices is open.
    METRICS_ENABLED: bool = True
    METRICS_TOKEN: str = ""

    # ── RLS enforcement (deployment audit F-4) ────────────────────────
    # With APP_ENV=production the API refuses to start if it is connected as a
    # role that bypasses row-level security, because every policy would exist,
    # review cleanly and enforce nothing. Set this only to override that
    # deliberately, and write down why.
    ALLOW_INERT_RLS: bool = False

    # Database
    # DATABASE_URL is what the RUNNING API connects as. Since the P2 cutover
    # that is `jaldrishti_app`: NOSUPERUSER, NOBYPASSRLS, DML only. Row-level
    # security does not apply to a superuser, so connecting as `postgres` here
    # silently disables every policy in migration 0009.
    # AUDIT 2026-08-24: this default previously carried a REAL local Postgres
    # password, committed to a public repo. A default must never be a secret --
    # it is read by anyone with the source, and it silently "works" on the
    # author's laptop so nothing ever forces it to be replaced. Empty now, and
    # `_require_production_secrets` refuses to start production without a real
    # value.
    DATABASE_URL: str = ""
    # The privileged connection, used ONLY by alembic and scripts/init_db.
    # Empty means "fall back to DATABASE_URL", which is right for a fresh clone
    # that has not split the roles yet.
    MIGRATION_DATABASE_URL: str = ""
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "groundwater_db"
    # DB_USER / DB_PASSWORD stay PRIVILEGED: scripts/init_db creates the PostGIS
    # extension and the enum types, and the test harness creates databases.
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""      # see DATABASE_URL -- never ship a real secret

    # JWT (single access token; refresh-token rotation removed in the slim-down)
    #: The literal that means "nobody has set this". Checked at startup so a
    #: deployment cannot inherit a signing key that is printed in the source.
    JWT_SECRET: str = "change-this-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8h — practical for a single-token prototype

    # CORS (comma-separated)
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        """One definition of "production", used everywhere.

        AUDIT 2026-08-24, finding #7: the CORS block tested
        `APP_ENV == "production"` while the metrics block tested
        `.lower() in ("production", "prod")`. With `APP_ENV=prod` the metrics
        guard engaged and CORS fell through to `allow_origins=["*"]` -- the two
        controls disagreed about which environment they were in.
        """
        return self.APP_ENV.strip().lower() in ("production", "prod")

    # ── Rate limiting (AUDIT 2026-08-24, finding #1) ──────────────────
    # This setting existed and enforced NOTHING: `main.py` built a slowapi
    # Limiter with `default_limits` but never added SlowAPIMiddleware and never
    # decorated a route, and in slowapi 0.1.9 `default_limits` alone is inert.
    # Measured before the fix: 120 POST /auth/login in 5.7 s, zero 429s.
    #
    # Two buckets, because one number cannot serve both jobs. The Console loads
    # ~14 map layers in a burst on a single navigation, so a limit tight enough
    # to slow a password-guesser would break normal use; and a limit loose
    # enough for the map is no protection on a login form.
    RATE_LIMIT_PER_MINUTE: int = 300          # general API, per user or per IP
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10      # login + citizen registration

    # ── API documentation ─────────────────────────────────────────────
    # `/docs`, `/redoc` and `/openapi.json` were served unconditionally. They
    # publish the complete route inventory, every schema and every role guard --
    # a free map of the attack surface. Off in production unless asked for.
    DOCS_ENABLED: bool = False

    # ── HSTS ──────────────────────────────────────────────────────────
    # Only meaningful once TLS terminates in front of this service, and actively
    # harmful on a plain-HTTP host, so it is opt-in rather than on by default.
    HSTS_ENABLED: bool = False
    HSTS_MAX_AGE: int = 31_536_000

    # S3
    S3_BUCKET: str = ""
    S3_ENDPOINT_URL: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""


#: Values that mean "this was never configured". Startup refuses them in
#: production rather than trusting that someone read the deployment checklist.
_PLACEHOLDER_SECRETS = frozenset({
    "", "change-this-secret", "changeme", "secret", "please-change-me",
})
MIN_JWT_SECRET_LENGTH = 32


def _require_production_secrets(s: "Settings") -> list[str]:
    """Return the reasons this configuration must not run in production.

    Pure and returning a list rather than raising, so the whole set of problems
    is reported at once and so it is testable without constructing a broken
    process. AUDIT 2026-08-24, finding #3: there was a startup guard for inert
    row-level security but none for the JWT signing key, which is the more
    direct failure -- a known signing key lets anyone mint an admin token, and
    no policy in the database can refuse a request that arrives correctly
    signed as an administrator.
    """
    problems: list[str] = []
    if s.JWT_SECRET.strip() in _PLACEHOLDER_SECRETS:
        problems.append(
            "JWT_SECRET is unset or still the placeholder from config.py. "
            "Anyone reading this repository can forge an admin token. "
            "Generate one: python -c \"import secrets;print(secrets.token_urlsafe(64))\"")
    elif len(s.JWT_SECRET) < MIN_JWT_SECRET_LENGTH:
        problems.append(
            f"JWT_SECRET is {len(s.JWT_SECRET)} characters; "
            f"{MIN_JWT_SECRET_LENGTH} is the minimum for HS256.")
    if not s.DATABASE_URL.strip():
        problems.append("DATABASE_URL is unset.")
    if "*" in s.cors_origins_list:
        problems.append(
            "CORS_ORIGINS contains '*'. Name the exact frontend origin.")
    return problems


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
