"""P3: simulations backed by the real ml_pipeline engine.

The load-bearing test here is
`test_approving_field_data_does_not_change_the_model_output`. Everything else
guards the plumbing; that one guards the requirement that a regulator approving
a field reading must not silently move a contamination model.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.models.monitoring_well import MonitoringWell
from app.models.user import User, UserRole
from app.services import ml_pipeline_adapter as mlp
from app.services.auth import hash_password, create_access_token

# Jaduguda — inside Jharkhand, in the ore belt, so the engine returns a plume.
LON, LAT = 86.36, 22.65


async def _mk(db, username, email, role):
    u = User(username=username, email=email,
             hashed_password=hash_password("pass1234"), role=role)
    db.add(u)
    await db.commit()
    return u


def _tok(u):
    return {"Authorization": f"Bearer {create_access_token(str(u.id), u.role)}"}


@pytest_asyncio.fixture()
async def isr_id(db_session):
    rid = (await db_session.execute(text("""
        INSERT INTO isr_points (id, name, location, injection_rate)
        VALUES (gen_random_uuid(), 'P3 Test Site',
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 1000)
        RETURNING id
    """), {"lon": LON, "lat": LAT})).scalar_one()
    await db_session.commit()
    return rid


@pytest_asyncio.fixture()
async def analyst(db_session):
    return await _mk(db_session, "p3ana", "p3ana@example.com", UserRole.analyst)


@pytest_asyncio.fixture()
async def officer(db_session):
    return await _mk(db_session, "p3off", "p3off@example.com",
                     UserRole.field_officer)


@pytest_asyncio.fixture()
async def regulator(db_session):
    return await _mk(db_session, "p3reg", "p3reg@example.com", UserRole.regulator)


# ── the boundary: nothing from the database may reach the engine ─────

def test_payload_allowlist_contains_no_measured_chemistry():
    """The engine resolves chemistry from its own datasets. If a key like
    `uranium_ppb` or `well_id` ever appears here, database-held field data has
    a route into a model whose conformal coverage was calibrated without it."""
    forbidden = {"uranium_ppb", "tds_mg_l", "sulfate_mg_l", "chloride_mg_l",
                 "well_id", "station_id", "baseline", "samples",
                 "water_quality", "observations"}
    assert not (mlp.ALLOWED_PAYLOAD_KEYS & forbidden)
    assert mlp.ALLOWED_PAYLOAD_KEYS == {
        "lon", "lat", "species", "operation_years", "time_years",
        "injection_rate_m3_day", "wellfield_width_m", "bleed_percent",
        "restoration_years", "gradient_i", "azimuth_deg", "monitor_ring_m",
        # Added when the interactive map gained click-to-run. Geometry and
        # presentation, not chemistry: which regime to assume, whether to
        # return ML bands, the calendar anchor, and the target-zone depth.
        "regime", "mode", "start_date", "ore_depth_m", "ore_thickness_m",
    }


def test_expert_chemistry_overrides_cannot_cross_the_boundary():
    """The pipeline's own local dashboard exposes expert overrides for Kd, beta,
    K and porosity. Those are precisely the hydrogeology this seam exists to
    keep on the engine's side, so the portal must not be able to set them —
    a hand-tuned K would produce an authoritative-looking number with no
    provenance. Listed explicitly in the adapter so the refusal is legible."""
    assert not (mlp.ALLOWED_PAYLOAD_KEYS & mlp.EXPERT_OVERRIDES_WITHHELD)
    for key in ("kd_L_kg", "beta", "K_m_day", "phi_mobile",
                "u_attenuation_k_per_yr"):
        assert key in mlp.EXPERT_OVERRIDES_WITHHELD
        assert key not in mlp.build_payload(lon=LON, lat=LAT, params={key: 1.0})


def test_build_payload_drops_anything_not_allowlisted():
    payload = mlp.build_payload(
        lon=LON, lat=LAT,
        params={"operation_years": 8, "uranium_ppb": 999.0,
                "well_id": str(uuid.uuid4()), "note": "from the field"})
    assert set(payload) == {"lon", "lat", "species", "operation_years"}
    assert "uranium_ppb" not in payload


@pytest.mark.asyncio
async def test_predict_refuses_a_payload_carrying_database_values():
    """Refuses rather than filters, so a design error surfaces instead of
    being silently cleaned up."""
    with pytest.raises(mlp.MLPipelineError) as exc:
        await mlp.predict({"lon": LON, "lat": LAT, "uranium_ppb": 120.0})
    assert "not permitted across the ml_pipeline boundary" in str(exc.value)


# ── running ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyst_can_run_and_the_result_is_pinned(client, analyst, isr_id):
    r = await client.post(f"/api/v1/simulations/{isr_id}", headers=_tok(analyst),
                          json={"species": "uranium_ppb", "operation_years": 8,
                                "time_years": 20})
    assert r.status_code == 202
    run_id = r.json()["id"]

    g = await client.get(f"/api/v1/simulations/runs/{run_id}",
                         headers=_tok(analyst))
    body = g.json()
    assert body["status"] == "completed", body.get("error_message")

    # reproducibility: the three things that can change under a result
    assert body["model_card_sha"] and len(body["model_card_sha"]) == 64
    assert body["artifacts_sha"] and len(body["artifacts_sha"]) == 64
    assert body["code_version"]
    assert body["runtime_ms"] > 0

    # real engine output, not a stub
    assert body["metrics"], "no metrics returned"
    assert body["excursion"] is not None
    assert "NOT REGULATORY-COMPLIANT" in body["excursion"]["compliance_status"]


@pytest.mark.asyncio
async def test_the_deleted_stub_constants_are_gone(client, analyst, isr_id):
    """P0's engine returned a constant 0.5733 km² for every input. If that value
    ever reappears, the stub is back."""
    r = await client.post(f"/api/v1/simulations/{isr_id}", headers=_tok(analyst),
                          json={"species": "uranium_ppb", "operation_years": 8})
    run = (await client.get(f"/api/v1/simulations/runs/{r.json()['id']}",
                            headers=_tok(analyst))).json()
    assert "0.5733" not in str(run["metrics"])


@pytest.mark.asyncio
async def test_field_officer_and_citizen_cannot_run_simulations(
        client, officer, isr_id):
    r = await client.post(f"/api/v1/simulations/{isr_id}", headers=_tok(officer),
                          json={"species": "uranium_ppb"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_unknown_isr_point_is_404(client, analyst):
    r = await client.post(f"/api/v1/simulations/{uuid.uuid4()}",
                          headers=_tok(analyst), json={"species": "uranium_ppb"})
    assert r.status_code == 404


# ── THE CONSTRAINT ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approving_field_data_does_not_change_the_model_output(
        client, db_session, analyst, officer, regulator, isr_id):
    """Approved field data must not feed the model.

    A regulator approving a water-quality reading is a data-governance act, not
    a model change. The surrogate's conformal bands were calibrated against a
    fixed input distribution; if approved field chemistry moved the prediction,
    the printed 80% would quietly stop meaning 80%. Changing what the model
    consumes requires a deliberate re-bake and retrain with the coverage gate
    re-run (PRODUCT_DESIGN.md section 4.6, rule 9).
    """
    def _run():
        return client.post(f"/api/v1/simulations/{isr_id}", headers=_tok(analyst),
                           json={"species": "uranium_ppb", "operation_years": 8,
                                 "time_years": 20})

    first = (await client.get(
        f"/api/v1/simulations/runs/{(await _run()).json()['id']}",
        headers=_tok(analyst))).json()
    assert first["status"] == "completed", first.get("error_message")

    # A field officer submits an extreme reading right at the site, and a
    # regulator approves it. It becomes authoritative in `water_samples`.
    well = MonitoringWell(name="P3 Well", location=f"SRID=4326;POINT({LON} {LAT})",
                          latitude=LAT, longitude=LON)
    db_session.add(well)
    await db_session.commit()

    obs = await client.post("/api/v1/field-observations", headers=_tok(officer),
                            json={"observation_type": "water_sample",
                                  "operation": "create",
                                  "payload": {"well_id": str(well.id),
                                              "sampled_at": "2026-08-12T00:00:00Z",
                                              "uranium_ppb": 9999.0}})
    assert obs.status_code == 201
    approved = await client.post(
        f"/api/v1/field-observations/{obs.json()['id']}/approve",
        headers=_tok(regulator), json={"review_note": "verified"})
    assert approved.status_code == 200

    in_db = (await db_session.execute(
        text("SELECT count(*) FROM water_samples WHERE uranium_ppb = 9999.0"))
    ).scalar_one()
    assert in_db == 1, "the approval did not become authoritative"

    second = (await client.get(
        f"/api/v1/simulations/runs/{(await _run()).json()['id']}",
        headers=_tok(analyst))).json()
    assert second["status"] == "completed", second.get("error_message")

    assert second["metrics"] == first["metrics"], (
        "approved field data changed the model output. The engine must resolve "
        "its inputs from ml_pipeline's own datasets, never from the database.")
    assert second["excursion"]["indicators"] == first["excursion"]["indicators"], (
        "approved field data moved the excursion indicators")
    assert second["artifacts_sha"] == first["artifacts_sha"]
