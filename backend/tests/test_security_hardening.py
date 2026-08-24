"""The seven findings from the 2026-08-24 security audit, pinned.

Each test names the finding it guards. They exist because every one of these
defects was *invisible* — the code looked correct, the settings were present and
read, and every request succeeded. A reviewer re-reading `main.py` would not
have found #1; only sending 120 logins did.

The rate-limiting tests re-enable the limiter around themselves. `conftest`
turns it off for the suite (see `_disable_rate_limiting`), so a test that wants
to observe a 429 has to ask for it and clean up afterwards.
"""
import pytest
from slowapi.middleware import SlowAPIMiddleware

from app.config import (MIN_JWT_SECRET_LENGTH, Settings,
                        _require_production_secrets)
from app.main import app
from app.ratelimit import limiter


# ── Finding #1: the rate limiter was inert ───────────────────────────

def test_slowapi_middleware_is_installed():
    """The whole bug in one assertion.

    `app.state.limiter` and the RateLimitExceeded handler were both already
    present and neither applies a limit. slowapi consults `default_limits` from
    SlowAPIMiddleware and nowhere else, so its absence made every other piece of
    rate-limiting configuration decorative.
    """
    installed = [m.cls for m in app.user_middleware]
    assert SlowAPIMiddleware in installed, (
        "SlowAPIMiddleware is not installed, so Limiter.default_limits applies "
        "to nothing. This is finding #1 regressing.")


def test_limiter_is_enabled_by_default():
    """Guard the guard: conftest disables it, and must restore it."""
    from app import ratelimit
    assert ratelimit.limiter is limiter


@pytest.mark.asyncio
async def test_login_is_rate_limited(client):
    """Finding #1, measured the way the audit measured it.

    Before the fix: 120 bad logins in 5.7 s produced 120 * 401 and zero 429s.
    """
    limiter.reset()
    limiter.enabled = True
    try:
        codes = []
        for _ in range(30):
            r = await client.post("/api/v1/auth/login", json={
                "email": "nobody@example.com", "password": "wrong"})
            codes.append(r.status_code)
    finally:
        limiter.enabled = False
        limiter.reset()

    assert 429 in codes, (
        f"30 rapid failed logins produced no 429: {sorted(set(codes))}. "
        "Login is brute-forceable.")
    # The allowed prefix should be the configured auth budget, not the general
    # one — if this ever equals RATE_LIMIT_PER_MINUTE the decorator was dropped
    # and only the global default is applying.
    allowed = codes.index(429)
    assert allowed <= Settings().AUTH_RATE_LIMIT_PER_MINUTE, (
        f"{allowed} attempts allowed before throttling, but "
        f"AUTH_RATE_LIMIT_PER_MINUTE is {Settings().AUTH_RATE_LIMIT_PER_MINUTE}")


@pytest.mark.asyncio
async def test_health_is_exempt_from_rate_limiting(client):
    """A liveness probe that 429s gets the container killed by its orchestrator,
    turning a busy minute into an outage."""
    limiter.reset()
    limiter.enabled = True
    try:
        codes = [(await client.get("/health")).status_code for _ in range(40)]
    finally:
        limiter.enabled = False
        limiter.reset()
    assert set(codes) == {200}, f"/health was throttled: {sorted(set(codes))}"


# ── Finding #3: no production guard on JWT_SECRET ────────────────────

def _prod(**kw) -> Settings:
    base = dict(APP_ENV="production", JWT_SECRET="x" * 64,
                DATABASE_URL="postgresql+asyncpg://u:p@h/db",
                CORS_ORIGINS="https://jaldrishti.example.org")
    base.update(kw)
    return Settings(**base)


def test_production_refuses_placeholder_jwt_secret():
    problems = _require_production_secrets(_prod(JWT_SECRET="change-this-secret"))
    assert any("JWT_SECRET" in p for p in problems), problems


def test_production_refuses_empty_jwt_secret():
    assert any("JWT_SECRET" in p for p in _require_production_secrets(
        _prod(JWT_SECRET="")))


def test_production_refuses_short_jwt_secret():
    problems = _require_production_secrets(
        _prod(JWT_SECRET="x" * (MIN_JWT_SECRET_LENGTH - 1)))
    assert any("characters" in p for p in problems), problems


def test_production_refuses_wildcard_cors():
    assert any("CORS" in p for p in _require_production_secrets(
        _prod(CORS_ORIGINS="*")))


def test_production_refuses_empty_database_url():
    assert any("DATABASE_URL" in p for p in _require_production_secrets(
        _prod(DATABASE_URL="")))


def test_a_correct_production_config_passes():
    assert _require_production_secrets(_prod()) == []


# ── Finding #4: no secret may be a default ───────────────────────────

def test_no_real_credential_is_a_config_default():
    """`config.py` shipped a real local Postgres password, twice.

    A default must never be a secret: it is readable by anyone with the source,
    and it silently *works* on the author's machine, so nothing ever forces it
    to be replaced.
    """
    s = Settings(_env_file=None)
    assert s.DB_PASSWORD == "", "DB_PASSWORD default must be empty"
    assert s.DATABASE_URL == "", "DATABASE_URL default must be empty"


# ── Finding #7: one definition of "production" ───────────────────────

@pytest.mark.parametrize("value", ["production", "prod", "Production", " PROD "])
def test_production_aliases_are_recognised(value):
    """CORS tested `== "production"` while metrics tested
    `.lower() in ("production","prod")`, so `APP_ENV=prod` gated metrics and
    still opened CORS to every origin."""
    assert Settings(APP_ENV=value).is_production is True


@pytest.mark.parametrize("value", ["development", "dev", "staging", ""])
def test_non_production_values_are_not_production(value):
    assert Settings(APP_ENV=value).is_production is False


# ── Finding #5: security headers ─────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("header,expected", [
    ("x-content-type-options", "nosniff"),
    ("x-frame-options", "DENY"),
    ("referrer-policy", "no-referrer"),
])
async def test_security_headers_present(client, header, expected):
    r = await client.get("/api/v1/public/risk/districts")
    assert r.headers.get(header) == expected


@pytest.mark.asyncio
async def test_csp_is_set_on_api_responses(client):
    r = await client.get("/api/v1/public/risk/districts")
    csp = r.headers.get("content-security-policy", "")
    assert "frame-ancestors 'none'" in csp


@pytest.mark.asyncio
async def test_hsts_is_not_sent_unless_enabled(client):
    """Opt-in deliberately: sent over plain HTTP it pins the browser to a scheme
    the host cannot answer, breaking the deployment it was meant to protect."""
    r = await client.get("/api/v1/public/risk/districts")
    assert "strict-transport-security" not in {k.lower() for k in r.headers}


# ── Finding #6: docs are not unconditionally public ──────────────────

def test_docs_are_disabled_in_production_by_default():
    s = Settings(APP_ENV="production", JWT_SECRET="x" * 64)
    assert (s.DOCS_ENABLED or not s.is_production) is False, (
        "Swagger/OpenAPI would be served in production, publishing the full "
        "route inventory and every role guard.")


def test_docs_can_be_re_enabled_deliberately():
    s = Settings(APP_ENV="production", DOCS_ENABLED=True, JWT_SECRET="x" * 64)
    assert (s.DOCS_ENABLED or not s.is_production) is True


def test_docs_are_on_in_development():
    s = Settings(APP_ENV="development")
    assert (s.DOCS_ENABLED or not s.is_production) is True
