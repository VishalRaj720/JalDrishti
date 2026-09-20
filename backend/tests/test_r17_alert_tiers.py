"""R17 (2026-09-20) -- alerts as auditable decision records.

What these pin:

  * the tier ladder is IS 10500's own two limits plus one PROJECT-DEFINED rung,
    and the rule text travels with every record;
  * observed tiers: warning (above acceptable, within permissible), alert
    (above permissible / no-relaxation), critical (>= 2x, or >= 2 determinands);
  * a modelled alert can never be critical -- in code AND in the schema;
  * every alert carries the seven fields (what_happened, driver, where, tier,
    basis, confidence, next_action) and `basis` is cross-checked against `kind`;
  * the measured scan reaches the `warning` rung (it used to select on the
    permissible limit only), upserts the structured fields onto pre-R17 rows,
    and never duplicates a row;
  * `possible_reach` alerts come from the run's stored P90 envelope, go only to
    blocks the footprint did not, and are worded as uncertainty;
  * the inbox and the email render the fields;
  * the rebuild endpoint is admin-only.

RLS: the test database has no policies (conftest), so the new write paths are
guarded at the source level like the ones before them -- the upsert runs inside
the same system-context sessions `raise_for_advisory` and the scan already use.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.user import UserRole
from app.services import alert_tiers as tiers
from app.services import notify
from app.services.alerts import AlertService
from app.services.water_quality import STATUS_ABOVE_ACCEPTABLE, STATUS_ABOVE_PERMISSIBLE
from tests.test_p5_citizen import _user, a_block  # noqa: F401  (fixture re-export)


# ── the ladder, without a database ───────────────────────────────────

def test_health_set_comes_from_the_registry():
    keys = [d.key for d in tiers.health_determinands()]
    assert keys == ["uranium", "fluoride", "nitrate", "arsenic", "iron"]


def test_breaches_carry_both_limits_and_the_is10500_class():
    b = tiers.breaches_for_sample({"fluoride_mg_l": 1.2})
    assert len(b) == 1
    assert b[0]["status"] == STATUS_ABOVE_ACCEPTABLE
    assert b[0]["acceptable"] == 1.0 and b[0]["permissible"] == 1.5
    assert b[0]["limit"] == 1.5 and b[0]["limit_kind"] == "permissible"
    b = tiers.breaches_for_sample({"nitrate_mg_l": 50.0})
    assert b[0]["status"] == STATUS_ABOVE_PERMISSIBLE
    assert b[0]["limit"] == 45.0 and "no relaxation" in b[0]["limit_kind"]


def test_breaches_below_acceptable_are_not_breaches():
    assert tiers.breaches_for_sample({"fluoride_mg_l": 0.9, "nitrate_mg_l": 44.0,
                                      "uranium_ppb": 29.9}) == []


@pytest.mark.parametrize("sample, expect", [
    ({"fluoride_mg_l": 1.2}, "warning"),                      # acceptable < v <= permissible
    ({"fluoride_mg_l": 1.6}, "alert"),                        # above permissible
    ({"nitrate_mg_l": 50.0}, "alert"),                        # no relaxation
    ({"uranium_ppb": 31.0}, "alert"),
    ({"nitrate_mg_l": 90.0}, "critical"),                     # 2x the limit
    ({"nitrate_mg_l": 89.9}, "alert"),                        # just under 2x
    ({"fluoride_mg_l": 3.0}, "critical"),                     # 2x permissible
    ({"nitrate_mg_l": 50.0, "fluoride_mg_l": 1.6}, "critical"),  # two over their limit
    ({"nitrate_mg_l": 50.0, "fluoride_mg_l": 1.2}, "alert"),  # one over, one warning
    ({"fluoride_mg_l": 1.2, "arsenic_ppb": 20.0}, "warning"),  # two warnings stay warning
])
def test_observed_ladder(sample, expect):
    tier, rule = tiers.observed_tier(tiers.breaches_for_sample(sample))
    assert tier == expect, rule
    assert rule


def test_critical_rules_are_labelled_project_defined():
    _, rule = tiers.observed_tier(tiers.breaches_for_sample({"nitrate_mg_l": 121.0}))
    assert "project-defined" in rule
    legend = tiers.tiers_legend()
    assert "PROJECT-DEFINED" in legend["observed"]["critical"]
    assert legend["modelled"]["critical"].startswith("never")


def test_modelled_tiers_and_never_critical():
    assert tiers.modelled_tier("published_screening", excursion_probability=0.1)[0] == "notice"
    assert tiers.modelled_tier("published_screening", excursion_probability=0.5)[0] == "alert"
    assert tiers.modelled_tier("published_screening", excursion_probability=None)[0] == "notice"
    assert tiers.modelled_tier("possible_reach")[0] == "warning"
    assert tiers.modelled_tier("aquifer_pathway")[0] == "warning"
    assert tiers.modelled_tier("aquifer_breach_due")[0] == "warning"
    for kind in ("published_screening", "possible_reach", "aquifer_pathway",
                 "aquifer_breach_due"):
        assert tiers.modelled_tier(kind, excursion_probability=1.0)[0] != "critical"


SEVEN = {"what_happened", "driver", "where", "tier", "basis", "confidence", "next_action"}


def test_observed_explanation_has_the_seven_fields():
    b = tiers.breaches_for_sample({"nitrate_mg_l": 121.0, "fluoride_mg_l": 1.9})
    t, r = tiers.observed_tier(b)
    x = tiers.explain_observed(breaches=b, tier=t, rule=r, block="Musabani",
                               district="East Singhbum", well_name="W1",
                               sampled_at="2023-05-01", n_samples_at_well=1)
    assert SEVEN <= set(x)
    assert x["basis"] == "observed"
    assert x["driver"]["determinand"] == "nitrate" and x["driver"]["times_limit"] > 2
    assert len(x["driver"]["all_breaches"]) == 2
    assert x["confidence"]["kind"] == "measurement" and x["confidence"]["single_sample"]
    assert any("boiling concentrates" in a.lower() for a in x["next_action"])
    assert any("re-sampled" in a for a in x["next_action"])
    assert "arsenic and iron" in " ".join(x["next_action"]).lower()


def test_modelled_explanation_carries_band_flags_and_premise():
    metrics = {"analytical": {"migration_m": {"p10": 6.5, "p50": 6.5, "p90": 6.5},
                              "excursion_probability": 0.12},
               "ml": {"migration_m": {"p10": 3.1, "p50": 6.8, "p90": 23.0},
                      "area_ha": {"p10": 8, "p50": 9, "p90": 11}}}
    x = tiers.explain_modelled(
        kind="published_screening", tier="notice", rule="r", block="Musabani",
        district="East Singhbum", species="uranium_ppb", overlap_ha=8.18,
        footprint_ha=8.18, horizon_years=10, engine="both", metrics=metrics,
        extrapolation=["K_m_day"], data_confidence={"level": "low"},
        beta_band=[0.75, 12.0], wells_in_reach=[])
    assert SEVEN <= set(x)
    assert x["basis"] == "modelled"
    assert x["confidence"]["band_source"] == "ml"
    assert x["confidence"]["migration_m"] == {"p10": 3.1, "p50": 6.8, "p90": 23.0}
    assert x["confidence"]["extrapolation"] == ["K_m_day"]
    assert x["confidence"]["in_trained_support"] is False
    assert x["confidence"]["beta_band"] == [0.75, 12.0]
    assert "No ISR uranium mine" in x["confidence"]["premise"]
    assert any("monitoring gap" in a for a in x["next_action"])   # empty well list
    assert "modelled" in x["tier"]["ladder"]


# ── the schema refuses what the code must never write ────────────────

@pytest.mark.asyncio
async def test_schema_refuses_a_critical_modelled_alert(db_session, a_block):
    with pytest.raises(IntegrityError):
        await db_session.execute(text("""
            INSERT INTO alerts (kind, block_id, advisory_id, headline, body,
                                severity, tier, basis)
            VALUES ('aquifer_pathway', :bid, gen_random_uuid(), 'h', 'b',
                    'high', 'critical', 'modelled')
        """), {"bid": a_block["id"]})
    await db_session.rollback()


@pytest.mark.asyncio
async def test_schema_refuses_a_basis_that_contradicts_the_kind(db_session, a_block):
    with pytest.raises(IntegrityError):
        await db_session.execute(text("""
            INSERT INTO alerts (kind, block_id, headline, body, severity, tier,
                                basis, well_name, measured_value, measured_unit,
                                sampled_at)
            VALUES ('measured_exceedance', :bid, 'h', 'b', 'high', 'alert',
                    'modelled', 'W', 1, 'x', now())
        """), {"bid": a_block["id"]})
    await db_session.rollback()


# ── the measured scan ────────────────────────────────────────────────

_WELL_SEQ = iter(range(1, 10_000))


async def _well_with_sample(db, block_id: str, name: str, **vals) -> str:
    """A well (distinct coordinates -- `uq_monitoring_wells_lat_lon`) inside
    the fixture block, with one sample carrying `vals`."""
    n = next(_WELL_SEQ)
    lon, lat = 86.30 + n * 1e-4, 22.70 + n * 1e-4
    cols = ", ".join(vals)
    binds = ", ".join(f":{k}" for k in vals)
    row = (await db.execute(text(f"""
        WITH w AS (
            INSERT INTO monitoring_wells (id, name, block_id, location, latitude, longitude)
            VALUES (gen_random_uuid(), :name, :bid,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :lat, :lon)
            RETURNING id
        )
        INSERT INTO water_samples (id, well_id, sampled_at, {cols})
        SELECT gen_random_uuid(), w.id, now(), {binds} FROM w
        RETURNING well_id::text
    """), {"name": name, "bid": block_id, "lon": lon, "lat": lat, **vals})).first()
    await db.commit()
    return row[0]


@pytest.mark.asyncio
async def test_scan_reaches_every_rung_and_carries_the_fields(db_session, a_block):
    await _well_with_sample(db_session, a_block["id"], "W-warn", fluoride_mg_l=1.2)
    await _well_with_sample(db_session, a_block["id"], "W-alert", nitrate_mg_l=50.0)
    await _well_with_sample(db_session, a_block["id"], "W-crit", nitrate_mg_l=121.0,
                            fluoride_mg_l=1.9)
    await _well_with_sample(db_session, a_block["id"], "W-clean", nitrate_mg_l=10.0)
    out = await AlertService(db_session).scan_measured_exceedances()
    assert out["alerts_created"] == 3 and out["alerts_upgraded"] == 0
    assert out["by_tier"] == {"warning": 1, "alert": 1, "critical": 1}
    assert "tiers" in out and "project_defined" in out["tiers"]
    rows = (await db_session.execute(text("""
        SELECT well_name, tier, basis, severity, explanation FROM alerts
        WHERE kind = 'measured_exceedance' AND block_id = :bid ORDER BY well_name
    """), {"bid": a_block["id"]})).mappings().all()
    by = {r["well_name"]: r for r in rows}
    assert by["W-warn"]["tier"] == "warning" and by["W-warn"]["severity"] == "warning"
    assert by["W-alert"]["tier"] == "alert" and by["W-alert"]["severity"] == "high"
    assert by["W-crit"]["tier"] == "critical"
    assert "W-clean" not in by
    for r in rows:
        assert r["basis"] == "observed"
        x = r["explanation"]
        assert SEVEN <= set(x), r["well_name"]
        assert x["where"]["block"] == a_block["name"]
    assert by["W-crit"]["explanation"]["driver"]["determinand"] == "nitrate"
    assert len(by["W-crit"]["explanation"]["driver"]["all_breaches"]) == 2


@pytest.mark.asyncio
async def test_scan_upgrades_a_pre_r17_row_without_duplicating_it(db_session, a_block):
    """A row written before migration 0026 (no explanation) is upgraded in
    place by the next scan; a row that already has one is left alone; and
    neither path creates a second row for the same (block, well, sample)."""
    await _well_with_sample(db_session, a_block["id"], "W-old", nitrate_mg_l=121.0)
    svc = AlertService(db_session)
    first = await svc.scan_measured_exceedances()
    assert first["alerts_created"] == 1
    # simulate the pre-R17 state: strip the structured fields
    await db_session.execute(text("""
        UPDATE alerts SET explanation = NULL, tier = 'alert', severity = 'high'
        WHERE well_name = 'W-old'"""))
    await db_session.commit()
    second = await svc.scan_measured_exceedances()
    assert second["alerts_created"] == 0 and second["alerts_upgraded"] == 1
    rows = (await db_session.execute(text(
        "SELECT tier, explanation FROM alerts WHERE well_name = 'W-old'"))).all()
    assert len(rows) == 1
    assert rows[0][0] == "critical" and rows[0][1] is not None
    third = await svc.scan_measured_exceedances()
    assert third["alerts_created"] == 0 and third["alerts_upgraded"] == 0


# ── modelled alerts from a stored run ────────────────────────────────

async def _published(db, block_id: str, actor: str, *, plume: dict, metrics: dict,
                     extrapolation: list[str] | None = None,
                     hydro: dict | None = None) -> tuple[str, str]:
    """A site, a completed run carrying `plume`/`metrics`, a published
    advisory whose footprint block is `block_id`. Returns (advisory_id, run_id)."""
    row = (await db.execute(text("""
        WITH p AS (
            INSERT INTO isr_points (id, name, location, injection_rate_m3_day,
                                    bleed_percent, operation_years, restoration_years,
                                    wellfield_width_m, monitor_ring_m, ore_depth_m,
                                    ore_thickness_m)
            VALUES (gen_random_uuid(), 'R17 Site',
                    ST_SetSRID(ST_MakePoint(86.30, 22.70), 4326),
                    1000, 2, 8, 0, 300, 100, 150, 20)
            RETURNING id
        ), r AS (
            INSERT INTO simulation_runs (id, isr_point_id, species, status, engine,
                                         request, plume, metrics, extrapolation,
                                         hydro, created_by, model_card_sha,
                                         artifacts_sha, code_version)
            SELECT gen_random_uuid(), p.id, 'uranium_ppb', 'completed', 'both',
                   '{"time_years": 10}'::jsonb, CAST(:plume AS jsonb),
                   CAST(:metrics AS jsonb), string_to_array(CAST(:extrap AS text), ','),
                   CAST(:hydro AS jsonb), CAST(:actor AS uuid),
                   'test-card', 'test-artifacts', 'test-code'
            FROM p RETURNING id, isr_point_id
        )
        INSERT INTO advisories (id, isr_point_id, run_id, status, headline,
                                what_it_means, species, footprint_ha, affected_blocks,
                                decided_by, published_at, proposed_by, time_years)
        SELECT gen_random_uuid(), r.isr_point_id, r.id, 'published', 'R17 SCREENING',
               'means', 'uranium_ppb', 8.2,
               jsonb_build_array(jsonb_build_object('id', CAST(:bid AS text),
                                                    'name', CAST(:bname AS text),
                                                    'district', 'Test District',
                                                    'overlap_ha', 8.2)),
               CAST(:actor AS uuid), now(), CAST(:actor AS uuid), 10
        FROM r RETURNING id::text, run_id::text
    """), {"plume": json.dumps(plume), "metrics": json.dumps(metrics),
           "extrap": ",".join(extrapolation or []),
           "hydro": json.dumps(hydro or {}), "actor": actor,
           "bid": block_id, "bname": "Test Block"})).first()
    await db.commit()
    return row[0], row[1]


def _square(lon0, lat0, half_deg):
    return [[lon0 - half_deg, lat0 - half_deg], [lon0 + half_deg, lat0 - half_deg],
            [lon0 + half_deg, lat0 + half_deg], [lon0 - half_deg, lat0 + half_deg],
            [lon0 - half_deg, lat0 - half_deg]]


@pytest.mark.asyncio
async def test_footprint_alert_is_notice_or_alert_by_the_runs_own_pex(db_session, a_block):
    from sqlalchemy import select
    from app.models.advisory import Advisory
    from app.models.simulation_run import SimulationRun
    aid, _ = await _user(db_session, f"an{uuid.uuid4().hex[:5]}", UserRole.analyst)
    for pex, expect in ((0.12, "notice"), (0.6, "alert")):
        adv_id, run_id = await _published(
            db_session, a_block["id"], str(aid), plume={},
            metrics={"analytical": {"excursion_probability": pex,
                                    "migration_m": {"p10": 6.5, "p50": 6.5, "p90": 6.5}},
                     "ml": {"migration_m": {"p10": 3, "p50": 7, "p90": 23}}},
            extrapolation=["K_m_day"], hydro={"data_confidence": {"level": "low"},
                                              "beta_band": [0.75, 12.0]})
        adv = (await db_session.execute(select(Advisory).where(Advisory.id == uuid.UUID(adv_id)))).scalar_one()
        run = (await db_session.execute(select(SimulationRun).where(SimulationRun.id == uuid.UUID(run_id)))).scalar_one()
        made = await AlertService(db_session).announce_advisory(adv, run)
        assert made == 1
        row = (await db_session.execute(text("""
            SELECT tier, basis, severity, explanation FROM alerts
            WHERE advisory_id = :a AND kind = 'published_screening'"""),
            {"a": adv_id})).mappings().one()
        assert row["tier"] == expect and row["basis"] == "modelled"
        x = row["explanation"]
        assert SEVEN <= set(x)
        assert x["confidence"]["migration_m"]["p90"] == 23
        assert x["confidence"]["extrapolation"] == ["K_m_day"]
        assert x["confidence"]["beta_band"] == [0.75, 12.0]
        assert x["confidence"]["excursion_probability"] == pytest.approx(pex)


@pytest.mark.asyncio
async def test_possible_reach_goes_only_beyond_the_footprint(db_session, a_block):
    """The P90 ring covers the footprint block AND a second block; only the
    second gets `possible_reach`, tiered warning, worded as uncertainty."""
    from sqlalchemy import select
    from app.models.advisory import Advisory
    from app.models.simulation_run import SimulationRun
    aid, _ = await _user(db_session, f"an{uuid.uuid4().hex[:5]}", UserRole.analyst)
    # a second block, adjacent to the fixture block (fixture is 86.2-86.6, 22.4-22.9)
    other = (await db_session.execute(text("""
        INSERT INTO blocks (id, name, district_id, geometry)
        SELECT gen_random_uuid(), 'Next Block', district_id,
               ST_Multi(ST_MakeEnvelope(86.60, 22.40, 86.80, 22.90, 4326))
        FROM blocks WHERE id = :bid RETURNING id::text
    """), {"bid": a_block["id"]})).first()[0]
    await db_session.commit()
    p90 = _square(86.60, 22.70, 0.05)        # straddles the shared edge at 86.6
    adv_id, run_id = await _published(
        db_session, a_block["id"], str(aid),
        plume={"ml_envelope": {"p10": _square(86.30, 22.70, 0.001),
                               "p50": _square(86.30, 22.70, 0.002), "p90": p90}},
        metrics={"analytical": {"excursion_probability": 0.1}})
    adv = (await db_session.execute(select(Advisory).where(Advisory.id == uuid.UUID(adv_id)))).scalar_one()
    run = (await db_session.execute(select(SimulationRun).where(SimulationRun.id == uuid.UUID(run_id)))).scalar_one()
    svc = AlertService(db_session)
    await svc.announce_advisory(adv, run)
    out = await svc.announce_possible_reach(adv, run)
    assert out["reason"] == "raised" and out["alerts"] == 1
    assert [b["id"] for b in out["blocks"]] == [other]
    rows = (await db_session.execute(text("""
        SELECT kind, block_id::text AS b, tier, basis, body, explanation FROM alerts
        WHERE advisory_id = :a ORDER BY kind"""), {"a": adv_id})).mappings().all()
    kinds = {(r["kind"], r["b"]) for r in rows}
    assert ("possible_reach", other) in kinds
    assert ("possible_reach", a_block["id"]) not in kinds      # footprint block excluded
    pr = next(r for r in rows if r["kind"] == "possible_reach")
    assert pr["tier"] == "warning" and pr["basis"] == "modelled"
    assert "not a finding" in pr["body"]
    assert pr["explanation"]["driver"]["quantity"].startswith("upper (P90)")
    # idempotent
    again = await svc.announce_possible_reach(adv, run)
    assert again["alerts"] == 0


@pytest.mark.asyncio
async def test_no_envelope_means_no_possible_reach_and_says_why(db_session, a_block):
    from sqlalchemy import select
    from app.models.advisory import Advisory
    from app.models.simulation_run import SimulationRun
    aid, _ = await _user(db_session, f"an{uuid.uuid4().hex[:5]}", UserRole.analyst)
    adv_id, run_id = await _published(db_session, a_block["id"], str(aid),
                                      plume={"ml_envelope_skipped": {"p90": "below drawable"}},
                                      metrics={})
    adv = (await db_session.execute(select(Advisory).where(Advisory.id == uuid.UUID(adv_id)))).scalar_one()
    run = (await db_session.execute(select(SimulationRun).where(SimulationRun.id == uuid.UUID(run_id)))).scalar_one()
    out = await AlertService(db_session).announce_possible_reach(adv, run)
    assert out["alerts"] == 0 and out["reason"] == "no_p90_envelope"
    assert "below drawable" in out["note"]


# ── the inbox, the email, the route ──────────────────────────────────

@pytest.mark.asyncio
async def test_inbox_returns_tier_basis_explanation_and_the_legend(client, db_session, a_block):
    await _well_with_sample(db_session, a_block["id"], "W-inbox", nitrate_mg_l=121.0)
    await AlertService(db_session).scan_measured_exceedances()
    uid, tok = await _user(db_session, f"c{uuid.uuid4().hex[:5]}", UserRole.citizen)
    await db_session.execute(text(
        "INSERT INTO block_subscriptions (user_id, block_id) VALUES (:u, :b)"),
        {"u": str(uid), "b": a_block["id"]})
    await db_session.commit()
    r = await client.get("/api/v1/citizen/alerts", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tiers"]["order"] == ["notice", "warning", "alert", "critical"]
    a = next(x for x in body["alerts"] if x["well_name"] == "W-inbox")
    assert a["tier"] == "critical" and a["basis"] == "observed"
    assert SEVEN <= set(a["explanation"])
    r = await client.get("/api/v1/citizen/alerts?kind=possible_reach",
                         headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200


def test_email_renders_the_seven_fields():
    b = tiers.breaches_for_sample({"nitrate_mg_l": 121.0})
    t, rule = tiers.observed_tier(b)
    x = tiers.explain_observed(breaches=b, tier=t, rule=rule, block="Musabani",
                               district="East Singhbum", well_name="W1",
                               sampled_at="2023-05-01", n_samples_at_well=1)
    subject, body = notify.render_alert_email({
        "kind": "measured_exceedance", "headline": "Nitrate above the safe limit",
        "body": "prose", "block_name": "Musabani", "district_name": "East Singhbum",
        "username": "asha", "tier": t, "basis": "observed",
        "explanation": json.dumps(x), "sampled_at": None,
    })
    assert "Level: CRITICAL (measured)" in body
    for label in ("What happened:", "Driven by:", "Where:", "Level:", "Basis:",
                  "Confidence:", "What next:"):
        assert label in body, label
    assert "nitrate 121.0 mg/L" in body and "OBSERVED" in body
    # a modelled one says so, and shows the band
    xm = tiers.explain_modelled(
        kind="possible_reach", tier="warning", rule="r", block="Next", district=None,
        species="uranium_ppb", overlap_ha=1.0, footprint_ha=8.0, horizon_years=10,
        engine="both", metrics={"ml": {"migration_m": {"p10": 3, "p50": 7, "p90": 23}}},
        extrapolation=[], data_confidence=None, wells_in_reach=None)
    _, body = notify.render_alert_email({
        "kind": "possible_reach", "headline": "h", "body": "b", "block_name": "Next",
        "tier": "warning", "basis": "modelled", "explanation": xm})
    assert "MODELLED" in body and "P10/P50/P90 = 3.0/7.0/23.0 m" in body
    assert "inside the model's trained support" in body


@pytest.mark.asyncio
async def test_rebuild_endpoint_is_admin_only(client, db_session):
    _, tok = await _user(db_session, f"an{uuid.uuid4().hex[:5]}", UserRole.analyst)
    r = await client.post("/api/v1/citizen/alerts/rebuild-explanations",
                          headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
    r = await client.post("/api/v1/citizen/alerts/rebuild-explanations")
    assert r.status_code == 401


def test_publish_path_raises_possible_reach_with_the_context_reset():
    """Source-level guard for the RLS-after-COMMIT hazard on the new write
    path (the test DB has no policies, so it cannot be caught at runtime)."""
    import inspect
    from app.services import alerts
    src = inspect.getsource(alerts.raise_for_advisory)
    i = src.index("announce_aquifer_reach")
    j = src.index("announce_possible_reach")
    assert i < j
    assert "set_rls_context(db, bypass=True)" in src[i:j], (
        "the context must be set again after announce_aquifer_reach commits")
    src2 = inspect.getsource(alerts.rebuild_explanations)
    assert src2.count("set_rls_context(db, bypass=True)") >= 3
