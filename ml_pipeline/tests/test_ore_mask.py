"""Module 2 -- 3-tier ore masking + ML-bypass for non-ore uranium."""
from __future__ import annotations

from fastapi.testclient import TestClient

from ml_pipeline.data_prep.ore_loader import ore_zone_at
from ml_pipeline.dashboard.server import app

client = TestClient(app)

JADUGUDA = (86.347, 22.652)     # inside a surveyed deposit
MID_BELT = (86.25, 22.63)       # inside the Singhbhum envelope, outside deposits
RANCHI = (85.33, 23.36)         # clean, ~113 km from nearest deposit


def test_zone_classification():
    assert ore_zone_at(*JADUGUDA)["zone"] == "deposit"
    assert ore_zone_at(*MID_BELT)["zone"] == "belt"
    assert ore_zone_at(*RANCHI)["zone"] == "none"


def _predict(lon, lat, species="uranium_ppb"):
    return client.post("/api/predict",
                       json={"lon": lon, "lat": lat, "species": species}).json()


def test_deposit_uranium_full_source_and_ml():
    b = _predict(*JADUGUDA)
    assert b["ore_zone"]["zone"] == "deposit"
    assert b["notice"] is None
    assert b["hydro"]["source_conc_C0"] > 1000    # full Texas-derived source


def test_belt_uranium_reduced_source():
    b = _predict(*MID_BELT)
    dep = _predict(*JADUGUDA)
    assert b["ore_zone"]["zone"] == "belt"
    assert "Prospective Belt" in b["notice"]
    # belt source is a fraction of the deposit's full source term
    assert b["hydro"]["source_conc_C0"] < dep["hydro"]["source_conc_C0"]


def test_non_ore_uranium_suppressed_zero_plume():
    b = _predict(*RANCHI)
    assert b["ore_zone"]["zone"] == "none"
    assert b["hydro"]["u_suppressed"] is True
    assert b["ml_status"].startswith("suppressed")
    assert b["metrics"]["ml"] is None
    assert b["hydro"]["source_conc_C0"] <= 20      # trace only
    assert b["metrics"]["analytical"]["area_ha"] == 0.0   # no uranium plume


def test_non_ore_sulfate_still_simulated():
    b = _predict(*RANCHI, species="sulfate_mg_l")
    # lixiviant reagents perturb non-radiological chemistry anywhere fluid is injected
    assert b["notice"] is None
    assert b["hydro"]["u_suppressed"] is False
    assert b["hydro"]["source_conc_C0"] > 100


# --------------------------------------------------------------------------- #
# Belt registration fix (2026-08-04)
#
# The hand-drawn CSV arc claimed to be an "envelope enclosing the known deposit
# cluster ... that hosts all deposits above" but contained only Jaduguda -- the
# other six sat 1.0-13.7 km outside it, because the arc was drawn ~6 km south of
# the actual deposit chain. Symptoms: pins between real deposits resolved to
# "none", zeroing the uranium source AND (Ra-226 being ore-gated) making radium
# show no plume off a deposit at all.
# --------------------------------------------------------------------------- #
def test_belt_actually_contains_every_documented_deposit():
    """The belt's stated purpose. It previously satisfied it for 1 of 7."""
    from ml_pipeline.data_prep.ore_loader import _ore
    deposits, belt = _ore()
    assert belt is not None
    geom, prepared = belt
    outside = [name for name, poly, _ in deposits
               if not prepared.covers(poly.centroid)]
    assert not outside, f"deposits outside their own belt envelope: {outside}"


def test_no_cliff_inside_the_taper_radius():
    """3.6b ramps C0 over ORE_TAPER_KM, but `_belt_c0` only runs for zone ==
    'belt'. If the belt does not reach that far the ramp has nowhere to act and
    C0 falls straight to background -- the exact hard step 3.6b removed."""
    import numpy as np
    from ml_pipeline.config import parameters as P
    from ml_pipeline.data_prep.ore_loader import _ore
    deposits, _ = _ore()
    rng = np.random.default_rng(0)
    bad = []
    for name, poly, _p in deposits:
        c = poly.centroid
        for _ in range(120):
            ang = rng.uniform(0, 2 * np.pi)
            r = rng.uniform(0, P.ORE_TAPER_KM / 111.0)
            lon, lat = c.x + r * np.cos(ang), c.y + r * np.sin(ang)
            if ore_zone_at(lon, lat)["zone"] == "none":
                bad.append((name, round(lon, 4), round(lat, 4)))
    assert not bad, f"{len(bad)} pins inside the taper radius classified none: {bad[:3]}"


def test_near_miss_is_not_displayed_as_zero_distance():
    """A pin 12 m outside Jaduguda reported 'nearest_deposit_km: 0.0' while the
    zone read 'none' -- i.e. 'you are on the deposit, there is no deposit'."""
    z = ore_zone_at(86.3564, 22.6547)
    assert z["nearest_deposit_m"] is not None
    assert 0 < z["nearest_deposit_m"] < 200      # a real near-miss, not zero
    # the explicit flag is what callers must key off, never the rounded distance
    assert z["inside_deposit"] is (z["zone"] == "deposit")


def test_far_pins_still_have_no_source_the_guard_is_intact():
    """Widening the belt must not let the tool invent contamination statewide."""
    for lon, lat in [RANCHI, (86.43, 23.80), (84.5, 23.9)]:
        z = ore_zone_at(lon, lat)
        assert z["zone"] == "none"
        assert z["nearest_deposit_m"] > 20_000


def test_radium_spreads_in_the_belt_but_not_outside_the_ore_system():
    """The user-visible symptom: Ra-226 showed a bare square and no plume."""
    dep = _predict(*JADUGUDA, species="radium_226_mbq_l")
    assert dep["ore_zone"]["zone"] == "deposit"
    assert dep["metrics"]["analytical"]["area_ha"] > 0
    assert dep["metrics"]["analytical"]["migration_m"] > 0
    far = _predict(*RANCHI, species="radium_226_mbq_l")
    assert far["ore_zone"]["zone"] == "none"
    assert far["metrics"]["analytical"]["area_ha"] == 0.0
