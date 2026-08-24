"""The rate limiter, and the key it counts against.

Its own module rather than living in `main.py`, because the routers need to
decorate individual endpoints with a stricter limit and `main` imports the
routers -- importing it back would be a cycle.

AUDIT 2026-08-24, finding #1. Before this, `main.py` constructed a slowapi
`Limiter` with `default_limits` and never installed `SlowAPIMiddleware`. In
slowapi 0.1.9 `default_limits` is consulted BY that middleware and by nothing
else, so the limiter was a fully configured object that no request ever touched.
`RATE_LIMIT_PER_MINUTE=60` sat in `.env`, was read into settings, appeared in
the deployment checklist, and enforced nothing.

It was measured rather than reasoned about: 120 `POST /auth/login` with bad
credentials completed in 5.7 seconds with 120 `401`s and zero `429`s -- roughly
21 password guesses per second against a government portal, with no lockout.
"""
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings


def rate_limit_key(request: Request) -> str:
    """Per USER when we know who they are, per IP when we do not.

    DEPLOYMENT AUDIT. `get_remote_address` reads `request.client.host`, which
    behind a reverse proxy is the PROXY -- so every authenticated user would
    share one bucket and the first busy user would lock out everybody else.
    That is not a tuning problem; it is the limiter measuring the wrong thing.

    The subject claim is taken from the bearer token WITHOUT verifying it: this
    is a bucket key, not an authorisation decision, and a forged token still has
    to pass `get_current_user` before it reaches anything. The worst a bad token
    can do here is give itself its own bucket -- which is what an
    unauthenticated caller gets anyway.

    Anonymous traffic still keys on the address, so for the public surface
    `--proxy-headers --forwarded-allow-ips=<gateway>` on uvicorn remains
    necessary or all of it shares one bucket. `docs/DEPLOYMENT.md` says so.
    """
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        parts = token.split(".")
        if len(parts) == 3:
            import base64
            import json as _json
            try:
                pad = parts[1] + "=" * (-len(parts[1]) % 4)
                sub = _json.loads(base64.urlsafe_b64decode(pad)).get("sub")
                if sub:
                    return f"user:{sub}"
            except Exception:  # noqa: BLE001 - malformed token, fall through to IP
                pass
    return f"ip:{get_remote_address(request)}"


#: Two buckets, because one number cannot serve both jobs.
#:
#: The Console loads ~14 map layers in a burst on a single navigation, so a
#: limit tight enough to slow a password-guesser would break ordinary use. A
#: limit loose enough for the map is no protection at all on a login form. So
#: the general default is generous and the credential endpoints are decorated
#: individually with `AUTH_RATE_LIMIT`, which stacks on top of it.
limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
)

#: For the two unauthenticated endpoints that mint or exchange credentials:
#: `POST /auth/login` and `POST /citizen/register`.
AUTH_RATE_LIMIT = f"{settings.AUTH_RATE_LIMIT_PER_MINUTE}/minute"
