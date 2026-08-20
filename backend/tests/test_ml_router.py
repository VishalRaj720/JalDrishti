"""The `/api/v1/ml` router: role boundary, cacheability, and the payload seam.

WHY THE CACHE TEST EXISTS. The router originally sent
`Cache-Control: private, max-age=3600` on its reference-geography endpoints,
reasoning that ore polygons and aquifer outlines change only when `Datasets/`
does. That is true and irrelevant. `private` excludes shared *proxy* caches; it
says nothing about the browser's own cache, which is keyed on the URL and not on
the Authorization header. In verification a citizen signing in after an analyst
in the same browser was served the analyst's cached `/ml/ore` response and saw a
200 for an endpoint the server refuses them — the deposit map that design §2
exists to keep away from the public, delivered from disk without a request.

So: role-restricted engine endpoints must be `no-store`. The responsiveness is
recovered client-side, where the portal holds these layers in memory for an hour
and that memory dies with the session.
"""

# R7 retired the `regulator` role; migration 0019 merged those accounts
# into `admin`, which now holds the reviewer powers this exercises.
import uuid

import pytest
import pytest_asyncio

from app.models.user import User, UserRole
from app.services.auth import create_access_token, hash_password
from app.services import ml_pipeline_adapter as mlp

#: Reference geography — readable by any staff role, refused to citizens.
GEO = ["/api/v1/ml/boundary", "/api/v1/ml/ore", "/api/v1/ml/aquifers",
       "/api/v1/ml/rivers", "/api/v1/ml/flow-field", "/api/v1/ml/strike-field"]

#: Running the model. Restricted further, to the three roles that may model.
ENGINE = ["/api/v1/ml/pin?lon=86.35&lat=22.65"]


async def _user(db_session, role: UserRole) -> User:
    u = User(id=uuid.uuid4(), username=f"ml{role.value}{uuid.uuid4().hex[:4]}",
             email=f"ml{role.value}{uuid.uuid4().hex[:4]}@test.com",
             hashed_password=hash_password("pw123456"), role=role)
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture()
async def tokens(db_session):
    out = {}
    for role in (UserRole.admin, UserRole.admin, UserRole.analyst,
                 UserRole.field_officer, UserRole.citizen):
        u = await _user(db_session, role)
        out[role.value] = create_access_token(str(u.id), u.role)
    return out


def _h(t):
    return {"Authorization": f"Bearer {t}"}


# ── the role boundary ────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("path", GEO)
async def test_reference_geography_is_staff_only(client, tokens, path):
    """Every staff role may read the map's context; a citizen may not.

    `/ml/ore` is the strongest case: it is the map of where a hypothetical
    uranium site could be sited at all.
    """
    for role in ("admin", "admin", "analyst", "field_officer"):
        r = await client.get(path, headers=_h(tokens[role]))
        assert r.status_code != 403, f"{role} was refused {path}"
    assert (await client.get(path, headers=_h(tokens["citizen"]))).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ENGINE)
async def test_running_the_model_is_restricted_to_the_modelling_roles(
        client, tokens, path):
    """A field officer collects evidence and a citizen reads measurements.
    Neither runs a contaminant simulation."""
    for role in ("admin", "admin", "analyst"):
        assert (await client.get(path, headers=_h(tokens[role]))).status_code != 403
    for role in ("field_officer", "citizen"):
        assert (await client.get(path, headers=_h(tokens[role]))).status_code == 403


@pytest.mark.asyncio
async def test_predict_is_restricted_and_never_claims_to_be_persisted(client, tokens):
    body = {"lon": 86.35, "lat": 22.65, "species": "uranium_ppb",
            "mode": "analytical", "time_years": 5}
    for role in ("field_officer", "citizen"):
        r = await client.post("/api/v1/ml/predict", headers=_h(tokens[role]), json=body)
        assert r.status_code == 403

    r = await client.post("/api/v1/ml/predict", headers=_h(tokens["analyst"]), json=body)
    assert r.status_code == 200, r.text
    payload = r.json()
    # A screenshot of an interactive run must not be mistakable for a filed one.
    assert payload["persisted"] is False
    assert "not stored" in payload["persistence_note"].lower()


# ── the cache leak this router shipped with, and must not again ──────

@pytest.mark.asyncio
@pytest.mark.parametrize("path", GEO)
async def test_role_restricted_geography_is_never_browser_cacheable(
        client, tokens, path):
    """`private, max-age` is not per-user. Only `no-store` keeps a citizen from
    being handed an analyst's cached response by their own browser."""
    r = await client.get(path, headers=_h(tokens["analyst"]))
    assert r.status_code == 200
    cc = r.headers.get("cache-control", "")
    assert "no-store" in cc, (
        f"{path} sent Cache-Control: {cc!r}. A role-restricted response that the "
        f"browser may reuse across sign-ins leaks it to the next user.")
    assert "max-age" not in cc


# ── the payload seam still holds through the new route ───────────────

@pytest.mark.asyncio
async def test_predict_refuses_expert_chemistry_overrides(client, tokens):
    """The pipeline's own dashboard exposes these; the portal must not. A
    hand-tuned K produces an authoritative-looking number with no provenance."""
    r = await client.post(
        "/api/v1/ml/predict", headers=_h(tokens["admin"]),
        json={"lon": 86.35, "lat": 22.65, "K_m_day": 99.0, "kd_L_kg": 0.1})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "K_m_day" in detail and "kd_L_kg" in detail


@pytest.mark.asyncio
async def test_predict_refuses_measured_chemistry_from_the_database(client, tokens):
    """The seam's whole purpose: an approved field reading must not be able to
    move a model whose conformal coverage was calibrated without it."""
    r = await client.post(
        "/api/v1/ml/predict", headers=_h(tokens["admin"]),
        json={"lon": 86.35, "lat": 22.65, "uranium_ppb": 900.0})
    # Dropped by the allowlist rather than reaching the engine.
    assert r.status_code in (200, 422)
    if r.status_code == 200:
        assert "uranium_ppb" not in r.json().get("pin", {})


@pytest.mark.asyncio
async def test_a_point_outside_jharkhand_is_a_422_not_a_503(client, tokens):
    """Clicking the sea is a user-correctable mistake, not an engine outage."""
    r = await client.get("/api/v1/ml/pin?lon=119.5&lat=-9.8",
                         headers=_h(tokens["analyst"]))
    assert r.status_code == 422
    assert "outside jharkhand" in r.json()["detail"].lower()


def test_withheld_overrides_and_allowlist_cannot_overlap():
    """Pinned here as well as in test_p3_simulation so the two lists cannot
    drift into agreeing that something is both allowed and withheld."""
    assert not (mlp.ALLOWED_PAYLOAD_KEYS & mlp.EXPERT_OVERRIDES_WITHHELD)
