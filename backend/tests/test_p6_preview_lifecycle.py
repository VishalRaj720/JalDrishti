"""Ephemeral runs, and the lifecycle trace.

TWO PROPERTIES WORTH PINNING.

**A preview stores nothing.** Exploring "what does 12 years look like, and 18?"
used to leave a trail of runs nobody meant to keep, which turned the run history
from a record of decisions into a log of curiosity. A preview must therefore
write no row -- and must still return the plume geometry, or it is not a preview
of the thing it claims to preview.

**The lifecycle trace matches the physics, not the intuition.** The obvious
expectation is that concentration climbs while mining, falls during restoration,
then decays. The model says something more specific, and the chart has to show
what the model says:

  * source strength is FLAT during injection (that is what injection is)
  * it falls only under a restoration sweep
  * afterwards it is HELD at the rebound floor, while MIGRATION keeps growing
    because containment stops at closure

If a future change makes source strength rise during operation, or decay after
closure, these tests fail -- and they should, because the chart would then be
telling a story the engine does not support.
"""
import uuid

import pytest
import pytest_asyncio

from app.models.user import User, UserRole
from app.services.auth import create_access_token, hash_password
from tests.test_p2_site_is_the_operation import FULL_SITE, _tok

OP_YEARS = 10.0


@pytest_asyncio.fixture()
async def field_token(db_session):
    u = User(username=f"p6off{uuid.uuid4().hex[:5]}",
             email=f"p6off{uuid.uuid4().hex[:5]}@example.com",
             hashed_password=hash_password("pass1234"), role=UserRole.field_officer)
    db_session.add(u)
    await db_session.commit()
    return create_access_token(str(u.id), u.role)


async def _site(client, token) -> dict:
    body = {**FULL_SITE, "operation_years": OP_YEARS}
    r = await client.post("/api/v1/isr-points", headers=_tok(token),
                          json={"name": f"P6 {uuid.uuid4().hex[:6]}", **body})
    assert r.status_code == 201, r.text
    return r.json()


# -- preview ----------------------------------------------------------

@pytest.mark.asyncio
async def test_a_preview_stores_nothing(client, admin_token):
    site = await _site(client, admin_token)
    before = (await client.get(f"/api/v1/simulations/runs?isr_id={site['id']}",
                               headers=_tok(admin_token))).json()

    r = await client.post(f"/api/v1/simulations/{site['id']}/preview",
                          headers=_tok(admin_token),
                          json={"species": "uranium_ppb", "time_years": 12})
    assert r.status_code == 200, r.text
    assert r.json()["persisted"] is False

    after = (await client.get(f"/api/v1/simulations/runs?isr_id={site['id']}",
                              headers=_tok(admin_token))).json()
    assert len(after) == len(before), (
        "the preview wrote a row; exploring must not fill the run history with "
        "results nobody chose to keep")


@pytest.mark.asyncio
async def test_a_preview_returns_a_drawable_plume(client, admin_token):
    """Otherwise it is not previewing the thing it claims to preview."""
    site = await _site(client, admin_token)
    r = await client.post(f"/api/v1/simulations/{site['id']}/preview",
                          headers=_tok(admin_token),
                          json={"species": "uranium_ppb", "time_years": 12})
    body = r.json()
    assert body["plume"] is not None
    assert body["plume"]["contours"], "no contours to draw"
    assert body["plume"]["source_zone"]["polygon"], "no leach zone to draw"
    # And the panels the Console renders beside the map.
    assert body["vertical"] is not None, "no vertical screening returned"
    assert body["azimuth_deg"] is not None, "no plume direction returned"


@pytest.mark.asyncio
async def test_a_preview_cannot_change_the_sites_operation(client, admin_token):
    """The P2 rule holds on this path too."""
    site = await _site(client, admin_token)
    plain = (await client.post(f"/api/v1/simulations/{site['id']}/preview",
                               headers=_tok(admin_token),
                               json={"species": "uranium_ppb", "time_years": 12})).json()
    spiked = (await client.post(
        f"/api/v1/simulations/{site['id']}/preview", headers=_tok(admin_token),
        json={"species": "uranium_ppb", "time_years": 12,
              "injection_rate_m3_day": 8000, "operation_years": 20})).json()
    assert plain["metrics"]["analytical"] == spiked["metrics"]["analytical"], (
        "injected operating parameters changed a preview; the operation must "
        "come from the registered site")


@pytest.mark.asyncio
async def test_a_field_officer_cannot_preview(client, field_token):
    r = await client.post(f"/api/v1/simulations/{uuid.uuid4()}/preview",
                          headers=_tok(field_token), json={"species": "uranium_ppb"})
    assert r.status_code == 403


# -- lifecycle --------------------------------------------------------

@pytest.mark.asyncio
async def test_lifecycle_samples_every_phase_boundary(client, admin_token):
    """The restoration drop is the most informative feature on the chart.

    With only evenly spaced samples the curve can step straight over it and
    appear to show nothing happening, so the boundary and a point just past it
    are forced into the sample set.
    """
    site = await _site(client, admin_token)
    r = await client.post(f"/api/v1/simulations/{site['id']}/lifecycle",
                          headers=_tok(admin_token),
                          json={"species": ["uranium_ppb"], "time_years": 20,
                                "restoration_years": 2, "points": 6})
    assert r.status_code == 200, r.text
    body = r.json()
    years = [p["year"] for p in body["series"][0]["points"]]
    assert OP_YEARS in years, "no sample at the end of operation"
    assert OP_YEARS + 2 in years, "no sample at the end of restoration"

    phases = {p["phase"] for p in body["series"][0]["points"]}
    assert {"operation", "restoration", "post_closure"} <= phases


@pytest.mark.asyncio
async def test_lifecycle_matches_the_modelled_physics(client, admin_token):
    """The three shapes the chart exists to show -- asserted, not assumed."""
    site = await _site(client, admin_token)
    r = await client.post(f"/api/v1/simulations/{site['id']}/lifecycle",
                          headers=_tok(admin_token),
                          json={"species": ["uranium_ppb"], "time_years": 20,
                                "restoration_years": 2, "points": 8})
    pts = [p for p in r.json()["series"][0]["points"] if p["error"] is None]

    op = [p for p in pts if p["phase"] == "operation"]
    rest = [p for p in pts if p["phase"] == "restoration"]
    post = [p for p in pts if p["phase"] == "post_closure"]
    assert op and rest and post

    # 1. Source strength is FLAT while injecting -- not rising.
    src_op = {round(p["source_conc"], 3) for p in op}
    assert len(src_op) == 1, (
        f"source concentration varied during injection ({src_op}); the leach "
        f"solution is held at strength, so this line must be flat")

    # 2. It FALLS under the sweep.
    assert rest[-1]["source_conc"] < op[-1]["source_conc"], (
        "the restoration sweep did not reduce source strength")

    # 3. Afterwards it is HELD, not decaying -- the rebound floor.
    src_post = {round(p["source_conc"], 3) for p in post}
    assert len(src_post) == 1, (
        f"source concentration changed after closure ({src_post}); the engine "
        f"holds it at the demonstrated stable endpoint because residual "
        f"uranium can re-oxidise")

    # 4. Migration keeps growing after closure -- containment has stopped.
    assert post[-1]["migration_m"] > post[0]["migration_m"], (
        "migration did not grow post-closure; hydraulic containment ends with "
        "the operation, so the front is released")

    # 5. Area grows during injection.
    assert op[-1]["area_ha"] > op[0]["area_ha"]


@pytest.mark.asyncio
async def test_lifecycle_traces_every_species_including_outside_ore(
        client, admin_token):
    """A non-ore pin still has chemistry worth showing.

    Uranium is correctly refused outside an ore zone, but sulfate and TDS are
    not -- and a UI that only ever asks for uranium makes the whole map look
    broken away from Singhbhum.
    """
    body = {**FULL_SITE, "operation_years": OP_YEARS,
            "location": {"type": "Point", "coordinates": [85.33, 23.36]}}  # Ranchi
    site = (await client.post("/api/v1/isr-points", headers=_tok(admin_token),
                              json={"name": f"NonOre {uuid.uuid4().hex[:5]}",
                                    **body})).json()
    r = await client.post(f"/api/v1/simulations/{site['id']}/lifecycle",
                          headers=_tok(admin_token),
                          json={"species": ["uranium_ppb", "sulfate_mg_l"],
                                "time_years": 15, "points": 5})
    assert r.status_code == 200, r.text
    by_sp = {s["species"]: s for s in r.json()["series"]}

    u = by_sp["uranium_ppb"]
    assert u["suppressed"], "the engine's non-ore notice was not carried through"
    assert all((p["area_ha"] or 0) == 0 for p in u["points"] if p["error"] is None)

    so4 = by_sp["sulfate_mg_l"]
    assert any((p["area_ha"] or 0) > 0 for p in so4["points"]), (
        "sulfate produced no extent outside the ore belt; the engine does "
        "return one, so the map should show it")


@pytest.mark.asyncio
async def test_lifecycle_stores_nothing(client, admin_token):
    site = await _site(client, admin_token)
    before = (await client.get(f"/api/v1/simulations/runs?isr_id={site['id']}",
                               headers=_tok(admin_token))).json()
    r = await client.post(f"/api/v1/simulations/{site['id']}/lifecycle",
                          headers=_tok(admin_token),
                          json={"species": ["uranium_ppb"], "time_years": 15,
                                "points": 4})
    assert r.status_code == 200
    assert r.json()["persisted"] is False
    after = (await client.get(f"/api/v1/simulations/runs?isr_id={site['id']}",
                              headers=_tok(admin_token))).json()
    assert len(after) == len(before)
