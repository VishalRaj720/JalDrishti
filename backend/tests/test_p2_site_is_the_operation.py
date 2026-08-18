"""A registered site IS the operation, and a run may not override it.

WHY THIS EXISTS. Migration 0015 moved the operating parameters onto the ISR
point so that two people running "Jaduguda" run the same thing. Nothing
enforced it. Three separate paths quietly defeated it:

1. `POST /isr-points` gave every parameter a default, so a site could be
   registered without stating the operation — and the portal's own map did
   exactly that, posting a misspelled `injection_rate` that Pydantic dropped.
   Every site in the registry claimed 2500 m³/day because nobody had chosen.
2. `POST /simulations/{id}` accepted ten operational fields and passed them
   through as overrides, so the stored site parameters were never used.
3. `POST /scenarios` validated against the wide interactive-map allowlist, so a
   saved scenario could carry `operation_years` and reach the engine through
   `POST /scenarios/{id}/run`, which never goes near `RunRequest`.

Closing (2) without (3) would have moved the hole rather than shut it. These
tests are written against the PROPERTY — "only the evaluation horizon, the
restoration sweep and the species may vary per run" — so a fourth door fails
here too.
"""
import uuid

import pytest

from app.services.ml_pipeline_adapter import RUN_VARIABLE


def _tok(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


#: A complete, valid registration body.
FULL_SITE = {
    "injection_rate_m3_day": 1500.0,
    "bleed_percent": 2.0,
    "operation_years": 8.0,
    "wellfield_width_m": 300.0,
    "monitor_ring_m": 100.0,
    "ore_depth_m": 150.0,
    "ore_thickness_m": 20.0,
    "location": {"type": "Point", "coordinates": [86.36, 22.65]},
}

#: Every parameter that describes the OPERATION rather than the question asked
#: of it. None of these may be set by a run or stored on a scenario.
SITE_ONLY = [
    ("injection_rate_m3_day", 4000.0),
    ("bleed_percent", 5.0),
    ("operation_years", 15.0),
    ("wellfield_width_m", 600.0),
    ("monitor_ring_m", 150.0),
    ("ore_depth_m", 200.0),
    ("ore_thickness_m", 30.0),
    ("gradient_i", 0.01),
    ("azimuth_deg", 90.0),
]


@pytest.mark.asyncio
async def test_registration_refuses_a_site_with_no_operation(client, admin_token):
    """A name and a coordinate is not a site."""
    r = await client.post(
        "/api/v1/isr-points", headers=_tok(admin_token),
        json={"name": "Unspecified", "location": FULL_SITE["location"]})
    assert r.status_code == 422, r.text
    missing = {e["loc"][-1] for e in r.json()["detail"]}
    # Every operator choice must be stated; there is no defensible default for
    # how much lixiviant you inject.
    assert {"injection_rate_m3_day", "bleed_percent", "operation_years",
            "wellfield_width_m", "monitor_ring_m", "ore_depth_m",
            "ore_thickness_m"} <= missing


@pytest.mark.asyncio
async def test_registration_refuses_a_site_with_no_location(client, admin_token):
    """A site without a coordinate cannot be drawn, run or published."""
    body = {k: v for k, v in FULL_SITE.items() if k != "location"}
    r = await client.post("/api/v1/isr-points", headers=_tok(admin_token),
                          json={"name": "Nowhere", **body})
    assert r.status_code == 422, r.text
    assert any(e["loc"][-1] == "location" for e in r.json()["detail"])


@pytest.mark.asyncio
async def test_registration_rejects_transposed_coordinates(client, admin_token):
    """(lat, lon) instead of (lon, lat) is the exact bug migration 0011 fixed.

    Latitude 86 does not exist. Caught in the schema because the PostGIS error
    for a bad geometry names a WKB parse failure, which tells an analyst
    nothing they can act on.
    """
    r = await client.post(
        "/api/v1/isr-points", headers=_tok(admin_token),
        json={"name": "Transposed", **{**FULL_SITE,
              "location": {"type": "Point", "coordinates": [22.65, 186.0]}}})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_a_full_registration_keeps_every_value_it_was_given(
        client, admin_token):
    """The regression that motivated all of this.

    The old form posted `injection_rate`, which does not exist, so the value was
    dropped and the server default used instead. Nothing errored — the site just
    silently was not the operation the analyst had chosen.
    """
    name = f"Full {uuid.uuid4().hex[:6]}"
    created = await client.post("/api/v1/isr-points", headers=_tok(admin_token),
                                json={"name": name, **FULL_SITE})
    assert created.status_code == 201, created.text
    body = created.json()
    for field, expected in FULL_SITE.items():
        if field == "location":
            continue
        assert body[field] == pytest.approx(expected), (
            f"{field} did not round-trip: sent {expected}, got {body[field]}")


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", SITE_ONLY)
async def test_a_run_cannot_override_the_sites_operation(
        client, admin_token, field, value):
    """The property, one field at a time.

    Extra keys are ignored rather than rejected (Pydantic's default), so the
    assertion is not on the status code — it is that the value **did not reach
    the stored request**. A 202 that silently applied the override would be the
    bug.
    """
    site = (await client.post(
        "/api/v1/isr-points", headers=_tok(admin_token),
        json={"name": f"Locked {uuid.uuid4().hex[:6]}", **FULL_SITE})).json()

    r = await client.post(f"/api/v1/simulations/{site['id']}",
                          headers=_tok(admin_token),
                          json={"species": "uranium_ppb", "time_years": 10,
                                field: value})
    assert r.status_code == 202, r.text
    assert field not in r.json()["request"], (
        f"'{field}' crossed into the run request; a run must not be able to "
        f"change the operation the site describes.")


@pytest.mark.asyncio
async def test_a_run_keeps_the_three_things_it_may_vary(client, admin_token):
    """The other half: the allowed variables must actually survive."""
    site = (await client.post(
        "/api/v1/isr-points", headers=_tok(admin_token),
        json={"name": f"Varies {uuid.uuid4().hex[:6]}", **FULL_SITE})).json()

    r = await client.post(f"/api/v1/simulations/{site['id']}",
                          headers=_tok(admin_token),
                          json={"species": "sulfate_mg_l", "time_years": 12,
                                "restoration_years": 5})
    assert r.status_code == 202, r.text
    req = r.json()["request"]
    assert req["species"] == "sulfate_mg_l"
    assert req["time_years"] == 12
    assert req["restoration_years"] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", SITE_ONLY)
async def test_a_scenario_cannot_store_a_site_parameter(
        client, admin_token, field, value):
    """The third door.

    `POST /scenarios/{id}/run` never goes through `RunRequest`, so narrowing
    that schema alone left the override reachable by saving it as a scenario
    first. Refused at SAVE time, not run time: a scenario that cannot run is
    worse than one that is refused, because it looks saved.
    """
    site = (await client.post(
        "/api/v1/isr-points", headers=_tok(admin_token),
        json={"name": f"Scen {uuid.uuid4().hex[:6]}", **FULL_SITE})).json()

    r = await client.post("/api/v1/scenarios", headers=_tok(admin_token),
                          json={"name": f"S {uuid.uuid4().hex[:6]}",
                                "isr_point_id": site["id"],
                                "params": {"time_years": 10, field: value}})
    assert r.status_code == 422, r.text
    assert field in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_completed_run_carries_drawable_plume_geometry(
        client, admin_token):
    """Migration 0016 — the auditable path can now draw what it computed.

    Before this, a stored run held metrics, excursion state and hydrogeology but
    not one coordinate of the plume, so the Studio rendered a "Planned" card
    where the map belonged while the *unpersisted* map click drew the full
    result. The best evidence in the product was on its throwaway route.

    The site is placed inside the Singhbhum ore envelope on purpose: outside an
    ore zone the engine correctly refuses a uranium source term, and `plume`
    would legitimately be null — which would make this test pass for the wrong
    reason.
    """
    site = (await client.post(
        "/api/v1/isr-points", headers=_tok(admin_token),
        json={"name": f"Geom {uuid.uuid4().hex[:6]}", **FULL_SITE})).json()

    queued = await client.post(f"/api/v1/simulations/{site['id']}",
                               headers=_tok(admin_token),
                               json={"species": "uranium_ppb", "time_years": 10})
    assert queued.status_code == 202, queued.text

    run = (await client.get(f"/api/v1/simulations/runs/{queued.json()['id']}",
                            headers=_tok(admin_token))).json()
    assert run["status"] == "completed", run.get("error_message")

    plume = run["plume"]
    assert plume is not None, (
        "a completed run inside the ore envelope produced no geometry; the "
        "stored run cannot be redrawn")

    # Enough to actually render: a contour ring, the swept leach zone, and the
    # ring an excursion would be detected at.
    assert plume["contours"], "no concentration contours stored"
    first = plume["contours"][0]
    assert "level" in first and first.get("polygons"), (
        "a contour must carry its level and at least one ring, or the renderer "
        "cannot shade it by concentration")
    assert plume["compliance_ring"]["polygon"], "no monitoring ring stored"
    assert plume["source_zone"]["polygon"], "no leach zone stored"

    # The display frame has to be stored too: the geometry is projected along
    # the down-gradient azimuth, and a redraw without it is a plume pointing an
    # arbitrary direction.
    assert isinstance(plume["azimuth_deg"], (int, float))
    assert plume["azimuth_source"]


def test_the_run_variable_set_is_exactly_three_things():
    """A guard on the rule itself.

    If someone widens `RUN_VARIABLE`, they have re-opened the ability of a run
    to redefine the operation, and they should have to change this line and
    read why that was closed.
    """
    assert RUN_VARIABLE == {"species", "time_years", "restoration_years"}
