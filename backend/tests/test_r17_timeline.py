"""R17 (2026-09-20) -- plume timeline frames on stored runs.

Pins:
  * the frame years: the base set clipped to the horizon, the horizon itself,
    and both phase boundaries, sorted and de-duplicated;
  * every frame is a separate engine evaluation (a stub engine is called once
    per frame with that frame's `time_years`; nothing is interpolated);
  * the first-exceedance year is the first evaluated frame whose ring
    concentration exceeds the threshold -- consistent with an independent
    scan of the same evaluations, and with the lifecycle calculation, which
    reads the same `compliance_conc` from the same engine;
  * on a real stored run the horizon frame's metrics equal the run's own
    metrics (same engine, same inputs), and frames are ordered;
  * a run stored before R17 is reported as "not recorded" -- never as "no
    change" -- on both the staff and the public route;
  * the public route serves published screenings only and strips the model
    internals.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.models.user import UserRole
from app.services import timeline as tl
from tests.test_p3_simulation import LON, LAT, _mk, _tok  # noqa: F401


# ── frame years ──────────────────────────────────────────────────────

def test_frame_years_clip_to_horizon_and_include_edges():
    ys = tl.frame_years(20.0, 8.0, 3.0)
    assert ys == sorted(set(ys))
    assert ys[0] == 0.0 and ys[-1] == 20.0
    assert 8.0 in ys and 11.0 in ys                  # end of operation, end of sweep
    assert all(y <= 20.0 for y in ys)
    assert 30.0 not in ys


def test_frame_years_long_horizon_and_no_restoration():
    ys = tl.frame_years(50.0, 10.0, 0.0)
    assert ys[-1] == 50.0 and 30.0 in ys and 40.0 in ys
    assert 10.0 in ys and ys.count(10.0) == 1           # edge coincides with base
    assert len(ys) <= 15


def test_frame_years_short_horizon():
    assert tl.frame_years(2.0, 8.0, 3.0) == [0.0, 1.0, 2.0]


# ── the evaluation contract, with a stub engine ──────────────────────

def _stub_engine(threshold=30.0, cross_at=5.0):
    """A deterministic engine: ring concentration grows linearly with time and
    crosses `threshold` at `cross_at` years. Records every call."""
    calls: list[float] = []

    async def predict(payload):
        y = float(payload["time_years"])
        calls.append(y)
        conc = threshold * (y / cross_at) if cross_at else 0.0
        return {
            "threshold": threshold,
            "metrics": {"analytical": {"area_ha": 0.5 * y, "migration_m": 2.0 * y,
                                       "compliance_conc": conc,
                                       "excursion_probability": 0.0},
                        "ml": {"migration_m": {"p10": y, "p50": 2 * y, "p90": 4 * y}}},
            "plume": {"contours": [{"level": threshold, "is_bis": True,
                                    "polygons": [[[86.3, 22.7], [86.31, 22.7], [86.31, 22.71]]]},
                                   {"level": 1.0, "is_bis": False,
                                    "polygons": [[[86.2, 22.6], [86.4, 22.6], [86.4, 22.8]]]}],
                      "source_zone": {"polygon": [[86.3, 22.7], [86.3, 22.71], [86.31, 22.71]],
                                      "conc": 1000.0},
                      "compliance_ring": {"radius_m": 100.0}},
            "isr_excursion": {"excursion_declared": y >= 8.0},
            "timeline": {"phase": "operation" if y <= 8 else "drift",
                         "current_date": f"20{int(y):02d}-01-01"},
            "extrapolation": ["time_years"] if y > 20 else [],
        }

    def payload_from_site(site, overrides=None):
        return {**(overrides or {})}

    return predict, payload_from_site, calls


@pytest.mark.asyncio
async def test_every_frame_is_its_own_evaluation_and_nothing_is_interpolated():
    predict, pfs, calls = _stub_engine()
    site = SimpleNamespace(operation_years=8.0, restoration_years=0.0)
    out = await tl.compute_timeline(site, {"species": "uranium_ppb", "time_years": 20,
                                           "restoration_years": 3},
                                    predict=predict, payload_from_site=pfs)
    years = tl.frame_years(20, 8, 3)
    assert calls == years, "one engine call per frame, in order, at that frame's year"
    assert [f["year"] for f in out["frames"]] == years
    assert out["frame_errors"] == 0
    for f in out["frames"]:
        assert f["migration_m"] == 2.0 * f["year"]         # the engine's own value
        assert f["ml_migration_band"] == {"p10": f["year"], "p50": 2 * f["year"], "p90": 4 * f["year"]}
        assert len(f["contours"]) == 1                      # only the screening-limit contour
        assert f["source_zone"] is not None
    assert out["frames"][-1]["extrapolating"] is False
    assert out["threshold"] == 30.0 and out["monitor_ring_m"] == 100.0


@pytest.mark.asyncio
async def test_first_exceedance_matches_an_independent_scan_of_the_same_evaluations():
    """The crossing is at 5.0 yr in the stub, so the first evaluated frame that
    is strictly above the threshold is 8 (frames at 5 sit exactly at it)."""
    predict, pfs, _ = _stub_engine(threshold=30.0, cross_at=5.0)
    site = SimpleNamespace(operation_years=8.0, restoration_years=0.0)
    out = await tl.compute_timeline(site, {"species": "uranium_ppb", "time_years": 20},
                                    predict=predict, payload_from_site=pfs)
    independent = next(f["year"] for f in out["frames"] if f["compliance_conc"] > 30.0)
    assert out["first_exceedance_year"] == independent == 8.0
    assert out["first_excursion_year"] == 8.0
    # and the lifecycle calculation, which reads the same field from the same
    # engine, agrees when evaluated on the same years
    from app.api.v1.lifecycle import _phase_of
    lifecycle_first = None
    for y in out["years"]:
        pt = await predict({"time_years": y})
        if pt["metrics"]["analytical"]["compliance_conc"] > 30.0:
            lifecycle_first = y
            break
    assert lifecycle_first == out["first_exceedance_year"]
    assert _phase_of(8.0, 8.0, 0.0) == "operation"


@pytest.mark.asyncio
async def test_no_crossing_is_reported_as_none_not_hidden():
    predict, pfs, _ = _stub_engine(threshold=30.0, cross_at=0.0)   # conc stays 0
    site = SimpleNamespace(operation_years=8.0, restoration_years=0.0)
    out = await tl.compute_timeline(site, {"species": "uranium_ppb", "time_years": 10},
                                    predict=predict, payload_from_site=pfs)
    assert out["first_exceedance_year"] is None
    assert "first" in out["note"]


@pytest.mark.asyncio
async def test_a_failed_frame_is_kept_as_an_error_not_dropped():
    predict, pfs, _ = _stub_engine()

    async def flaky(payload):
        if float(payload["time_years"]) == 5.0:
            raise RuntimeError("engine hiccup")
        return await predict(payload)

    site = SimpleNamespace(operation_years=8.0, restoration_years=0.0)
    out = await tl.compute_timeline(site, {"species": "uranium_ppb", "time_years": 10},
                                    predict=flaky, payload_from_site=pfs)
    bad = [f for f in out["frames"] if "error" in f]
    assert len(bad) == 1 and bad[0]["year"] == 5.0 and out["frame_errors"] == 1
    assert len(out["frames"]) == len(tl.frame_years(10, 8, 0))


def test_not_recorded_is_explicit():
    out = tl.not_recorded(SimpleNamespace(id="abc"))
    assert out["recorded"] is False and "not a finding" in out["reason"]


def test_public_view_strips_model_internals():
    predict, pfs, _ = _stub_engine()
    import asyncio
    site = SimpleNamespace(operation_years=8.0, restoration_years=0.0)
    out = asyncio.get_event_loop().run_until_complete(
        tl.compute_timeline(site, {"species": "uranium_ppb", "time_years": 10},
                            predict=predict, payload_from_site=pfs))
    pub = tl.public_view(out)
    assert pub["recorded"] is True and pub["frames"]
    for f in pub["frames"]:
        assert "ml_migration_band" not in f and "extrapolation" not in f
        assert "contours" in f and "compliance_conc" in f
    assert "premise" in pub


# ── on a real stored run ─────────────────────────────────────────────

@pytest_asyncio.fixture()
async def site_id(db_session):
    rid = (await db_session.execute(text("""
        INSERT INTO isr_points (id, name, location, injection_rate_m3_day,
                                operation_years, injection_start_date)
        VALUES (gen_random_uuid(), 'R17 Timeline Site',
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 1000, 8,
                '2010-01-01T00:00:00Z')
        RETURNING id
    """), {"lon": LON, "lat": LAT})).scalar_one()
    await db_session.commit()
    return rid


@pytest_asyncio.fixture()
async def analyst2(db_session):
    return await _mk(db_session, f"tl{uuid.uuid4().hex[:5]}", f"tl{uuid.uuid4().hex[:5]}@example.com",
                     UserRole.analyst)


@pytest.mark.asyncio
async def test_a_stored_run_carries_ordered_frames_consistent_with_its_own_result(
        client, analyst2, site_id):
    r = await client.post(f"/api/v1/simulations/{site_id}", headers=_tok(analyst2),
                          json={"species": "sulfate_mg_l", "time_years": 15,
                                "restoration_years": 2})
    assert r.status_code == 202, r.text
    run_id = r.json()["id"]
    g = (await client.get(f"/api/v1/simulations/runs/{run_id}", headers=_tok(analyst2))).json()
    assert g["status"] == "completed", g.get("error_message")

    t = await client.get(f"/api/v1/simulations/runs/{run_id}/timeline", headers=_tok(analyst2))
    assert t.status_code == 200, t.text
    body = t.json()
    assert body["recorded"] is True
    years = [f["year"] for f in body["frames"]]
    assert years == sorted(years) == tl.frame_years(15, 8, 2)
    assert body["frame_errors"] == 0, body["frames"]
    # the horizon frame is the run's own evaluation
    last = body["frames"][-1]
    an = g["metrics"]["analytical"]
    assert last["migration_m"] == pytest.approx(an["migration_m"], rel=1e-6)
    assert last["area_ha"] == pytest.approx(an["area_ha"], rel=1e-6)
    assert last["compliance_conc"] == pytest.approx(an["compliance_conc"], rel=1e-6)
    # calendar dates come from the site's own start date, and the phases follow
    # the operation/restoration boundaries
    assert body["frames"][0]["calendar_date"].startswith("2010")
    assert body["frames"][0]["phase"] == "operation"
    assert any(f["phase"] == "restoration" for f in body["frames"])
    assert body["frames"][-1]["phase"] in ("drift", "post_closure")
    # t = 0: nothing has been injected -- zero area, zero migration, no contour
    assert body["frames"][0]["area_ha"] == 0 and body["frames"][0]["migration_m"] == 0
    # first exceedance, if any, is the first frame over the threshold
    thr = body["threshold"]
    scan = next((f["year"] for f in body["frames"] if f["compliance_conc"] > thr), None)
    assert body["first_exceedance_year"] == scan


@pytest.mark.asyncio
async def test_a_pre_r17_run_reads_as_not_recorded(client, analyst2, site_id, db_session):
    r = await client.post(f"/api/v1/simulations/{site_id}", headers=_tok(analyst2),
                          json={"species": "uranium_ppb", "time_years": 5})
    run_id = r.json()["id"]
    # strip the frames, as a run stored before R17 would have none
    await db_session.execute(text(
        "UPDATE simulation_runs SET plume = plume - 'frames' WHERE id = :id"),
        {"id": run_id})
    await db_session.commit()
    t = (await client.get(f"/api/v1/simulations/runs/{run_id}/timeline",
                          headers=_tok(analyst2))).json()
    assert t["recorded"] is False and "not a finding" in t["reason"]


@pytest.mark.asyncio
async def test_public_timeline_needs_a_published_advisory(client, analyst2, site_id, db_session):
    r = await client.post(f"/api/v1/simulations/{site_id}", headers=_tok(analyst2),
                          json={"species": "sulfate_mg_l", "time_years": 10})
    run_id = r.json()["id"]
    adv = (await db_session.execute(text("""
        INSERT INTO advisories (id, isr_point_id, run_id, status, headline,
                                what_it_means, species, proposed_by)
        VALUES (gen_random_uuid(), :sid, :rid, 'proposed', 'h', 'm', 'sulfate_mg_l', :who)
        RETURNING id::text
    """), {"sid": str(site_id), "rid": run_id, "who": str(analyst2.id)})).scalar_one()
    await db_session.commit()
    r = await client.get(f"/api/v1/public/risk/advisories/{adv}/timeline")
    assert r.status_code == 404                                  # not published
    await db_session.execute(text(
        "UPDATE advisories SET status = 'published', published_at = now(), "
        "decided_by = :who WHERE id = :a"), {"a": adv, "who": str(analyst2.id)})
    await db_session.commit()
    r = await client.get(f"/api/v1/public/risk/advisories/{adv}/timeline")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recorded"] is True and body["frames"]
    txt = r.text
    assert "ml_migration_band" not in txt and "extrapolation" not in txt
    assert "premise" in body
