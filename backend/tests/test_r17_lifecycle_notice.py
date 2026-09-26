"""R17 follow-up (2026-09-21) -- two things the lifecycle and sweep charts said
that were not true, found by the owner on the deployed Jaduguda report.

1. THE BANNER. The registered Jaduguda site sits 0.35 km from the deposit
   polygon, so the ore mask classes it "belt": a hypothetical, low-confidence
   ore zone whose uranium source term is scaled DOWN (C0 14,294 ppb) but is
   very much present. The engine returns a `notice` for that -- the same
   field it uses for the "none" zone, where the source term is refused
   outright. `lifecycle.py` copied whichever notice arrived into
   `series.suppressed`, and the chart captioned it "No source term for this
   contaminant here" above a curve holding 14,295 ppb. Both cases now travel
   in separate fields, split on `hydro.u_suppressed` -- the engine's own
   boolean for the outright case -- and the chart words each honestly.

2. THE CHIP. A uranium sweep point read "1 ppb at the ring" and "excursion"
   at once. Both are correct: the NUREG-1569 panel is judged on the
   conservative indicators (chloride, TDS, sulfate) at the ring, and NUREG
   rejects uranium as an indicator because it is retarded. But nothing on
   screen said so. Every point now carries `excursion_indicators`, the
   species over their control limit, and the chips name them.

These run the REAL engine at the real Jaduguda coordinates and at a non-ore
pin, so the belt/none split is pinned to what the ore mask actually says.
"""
from __future__ import annotations

import uuid

import pytest

from tests.test_p2_site_is_the_operation import FULL_SITE, _tok

JADUGUDA_SITE = (86.36, 22.65)     # the registered site: "belt", 0.35 km off the deposit
RANCHI = (85.33, 23.36)            # "none": no ore, source term refused
# 2026-09-26: a belt pin between Jaduguda and Narwapahar (2.2 km from the latter).
# With the MEASURED shear-zone K (Kudada, 19 m2/day; LIMITATIONS.md 1k) the
# reagents at the registered Jaduguda site no longer reach its 100 m ring inside
# 20 yr, so the two tests that need a DECLARED excursion run here, where the
# shear-zone correction tapers toward the schist polygon and chloride + TDS
# arrive. Same operation, same ore mask tier ("belt").
BELT_SITE = (86.29, 22.69)


async def _site_at(client, token, lon, lat, name):
    body = {**FULL_SITE, "operation_years": 8.0, "monitor_ring_m": 100.0,
            "location": {"type": "Point", "coordinates": [lon, lat]}}
    r = await client.post("/api/v1/isr-points", headers=_tok(token),
                          json={"name": f"{name} {uuid.uuid4().hex[:5]}", **body})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_belt_pin_is_a_notice_not_a_suppression(client, admin_token):
    site = await _site_at(client, admin_token, *JADUGUDA_SITE, "Belt")
    r = await client.post(f"/api/v1/simulations/{site['id']}/lifecycle",
                          headers=_tok(admin_token),
                          json={"species": ["uranium_ppb"], "time_years": 20, "points": 4})
    assert r.status_code == 200, r.text
    u = r.json()["series"][0]
    # the source term is real -- five figures, held while injecting
    first = next(p for p in u["points"] if p["error"] is None)
    assert (first["source_conc"] or 0) > 5_000, first
    # and therefore it is a NOTICE (reduced), never a SUPPRESSION (absent)
    assert u["suppressed"] is None
    assert u["notice"] and "reduced" in u["notice"]
    assert "No uranium source term" not in u["notice"]


@pytest.mark.asyncio
async def test_non_ore_pin_is_a_suppression_not_a_notice(client, admin_token):
    site = await _site_at(client, admin_token, *RANCHI, "NonOre")
    r = await client.post(f"/api/v1/simulations/{site['id']}/lifecycle",
                          headers=_tok(admin_token),
                          json={"species": ["uranium_ppb"], "time_years": 15, "points": 4})
    assert r.status_code == 200, r.text
    u = r.json()["series"][0]
    assert u["suppressed"] and "No uranium source term" in u["suppressed"]
    assert u["notice"] is None
    assert all((p["area_ha"] or 0) == 0 for p in u["points"] if p["error"] is None)


@pytest.mark.asyncio
async def test_excursion_names_the_indicators_not_the_species(client, admin_token):
    """At a belt site, 20 yr, no restoration: uranium never reaches the 100 m
    ring (background there), while chloride and TDS have arrived and the 2-of-3
    panel declares. The point must say which substances declared, and it must
    not be uranium. (Was the Jaduguda site until 2026-09-26 -- see BELT_SITE.)"""
    site = await _site_at(client, admin_token, *BELT_SITE, "Chip")
    r = await client.post(f"/api/v1/simulations/{site['id']}/sweep",
                          headers=_tok(admin_token),
                          json={"axis": "restoration", "species": "uranium_ppb",
                                "points": 3, "time_years": 20})
    assert r.status_code == 200, r.text
    pts = [p for p in r.json()["points"] if p["error"] is None]
    p0 = next(p for p in pts if p["value"] == 0)
    assert p0["excursion_declared"] is True
    # uranium background there is the BARC survey blend (~0.90 ug/L, Narwapahar)
    assert p0["compliance_conc"] == pytest.approx(0.90, abs=0.05), (
        "uranium should sit at background at the ring while the reagents declare")
    assert "uranium_ppb" not in p0["excursion_indicators"]
    assert {"chloride_mg_l", "tds_mg_l"} <= set(p0["excursion_indicators"])
    # a long sweep holds the front for the whole post-operation window: no arrival
    p_long = max(pts, key=lambda p: p["value"])
    assert p_long["excursion_declared"] is False
    assert p_long["excursion_indicators"] == []


@pytest.mark.asyncio
async def test_lifecycle_points_carry_the_indicators_too(client, admin_token):
    site = await _site_at(client, admin_token, *BELT_SITE, "LC")
    r = await client.post(f"/api/v1/simulations/{site['id']}/lifecycle",
                          headers=_tok(admin_token),
                          json={"species": ["uranium_ppb"], "time_years": 20, "points": 5})
    assert r.status_code == 200, r.text
    pts = [p for p in r.json()["series"][0]["points"] if p["error"] is None]
    declared = [p for p in pts if p["excursion_declared"]]
    assert declared, "the 20-yr belt-site trace should declare an excursion late on"
    # the 2-of-3 rule, point by point: declared <=> at least two indicators
    # over their control limit. One indicator over (chloride, the least
    # retarded, arrives first) is the honest in-between state and is listed
    # without a declaration.
    for p in pts:
        n = len(p["excursion_indicators"])
        assert "uranium_ppb" not in p["excursion_indicators"]
        assert p["excursion_declared"] == (n >= 2), (p["year"], p["excursion_indicators"])
