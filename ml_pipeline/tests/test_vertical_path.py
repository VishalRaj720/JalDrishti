"""
2026-09-25 -- the vertical path gets the same physics as the horizontal one
(P.VERTICAL_PATH, dashboard/vertical_path.py, LIMITATIONS.md section 1f).

THE FINDING. At Jaduguda (20-yr run) the upward pathway reported 17.4 yr to
the shallow aquifer for uranium AND for TDS, and moving the matrix-storage
ratio beta from 3 to 0 did not change it -- while the same run's horizontal
front retarded uranium ~270x through that beta. The pathway moved a water
parcel, not a solute. What is pinned here:

  * retention is applied, by the SAME law and tables as the horizontal front,
    and switching it off reproduces the water parcel exactly;
  * beta now moves the vertical answer (the exact symptom);
  * the column's series K is a harmonic mean of the NAQUIM K(z) law;
  * Kv/Kh is the measured Indian hard-rock value, its range is reported;
  * a uranium run cannot hide the earlier arrival of the injected salts.
"""
from __future__ import annotations

import math

import pytest

from ml_pipeline.config import parameters as P
from ml_pipeline.physics.transport import (
    confining_path_conductivity, effective_capacity_ratio, shallow_impact_screening,
    vertical_solute_arrival_days)

JADUGUDA = (86.347, 22.652)


def _screen(**over):
    kw = dict(C0=8000.0, background=5.0, threshold=30.0, Xc_m=200.0,
              source_width_m=300.0, alpha_L=10.0, alpha_V=0.05,
              ore_depth_m=150.0, ore_thickness_m=20.0, layer1_base_m=30.0,
              K_m_day=0.4, phi_confining=0.008, Kv_Kh_ratio=0.12,
              upward_gradient=P.VERTICAL["upward_gradient"], t_days=3650.0,
              wellbore_failure_prob=0.05)
    kw.update(over)
    return shallow_impact_screening(**kw)


def _serve(**over):
    from ml_pipeline.dashboard.server import api_predict, PredictRequest
    kw = dict(lon=JADUGUDA[0], lat=JADUGUDA[1], mode="analytical", time_years=20)
    kw.update(over)
    return api_predict(PredictRequest(**kw))


# ── the kinematics ──────────────────────────────────────────────────────


def test_zero_retention_is_the_water_parcel_exactly():
    """beta_eff = 0 must reproduce what the pathway reported before, bit for bit
    -- the change adds retention and nothing else."""
    r = _screen(layer2_beta_eff=0.0)
    assert r["years_to_vertical_breakthrough"] == r["water_arrival_years"]
    assert r["layer2_retardation"] == 1.0
    # and by hand: separation / (Kv * i_duty / phi)
    duty = r["seasonal"]["duty_cycle"]
    v = 0.4 * 0.12 * duty["gradient"] / 0.008
    assert r["years_to_vertical_breakthrough"] == pytest.approx(
        r["separation_m"] / v / 365.0, abs=0.05)             # reported to 0.1 yr


@pytest.mark.parametrize("beta_eff", [0.5, 3.0, 15.0, 250.0, 3000.0])
def test_solute_arrival_is_bracketed_by_water_and_full_capacity(beta_eff):
    """I(t) lies between t/(1+beta) and t, so the solute arrives no sooner than
    the water and no later than the fully matured-capacity front."""
    v, dz = 0.05, 120.0
    t_w = dz / v
    t_s = vertical_solute_arrival_days(v, dz, beta_eff)
    assert t_w <= t_s <= (1.0 + beta_eff) * t_w * (1 + 1e-9)
    # once the clock has matured (t >> 1/omega) the front runs on the capacity
    if t_w * (1 + beta_eff) > 20 / P.DUAL_POROSITY["mass_transfer_omega"]:
        assert t_s / t_w == pytest.approx(1.0 + beta_eff, rel=0.1)


def test_a_closed_pathway_never_breaks_through():
    assert math.isinf(vertical_solute_arrival_days(0.0, 120.0, 3.0))
    r = _screen(upward_gradient=0.0, water_table_wet_m=3.0, water_table_dry_m=3.0)
    assert r["years_to_vertical_breakthrough"] is None


def test_retention_slows_the_front_and_lowers_the_index():
    fast = _screen(layer2_beta_eff=0.0)
    slow = _screen(layer2_beta_eff=250.0)
    assert slow["years_to_vertical_breakthrough"] > 100 * fast["years_to_vertical_breakthrough"]
    assert slow["pathways"]["advective_leakage"] < fast["pathways"]["advective_leakage"]
    # the wellbore shortcut has no matrix: it must NOT be retarded
    assert slow["pathways"]["wellbore"] == fast["pathways"]["wellbore"]


# ── the served answer: the exact symptom ────────────────────────────────


def test_uranium_no_longer_climbs_at_the_speed_of_water():
    """The reported symptom: identical vertical times for uranium and TDS."""
    u = _serve(species="uranium_ppb")["vertical"]
    tds = _serve(species="tds_mg_l")["vertical"]
    assert u["water_arrival_years"] == tds["water_arrival_years"]
    assert u["years_to_vertical_breakthrough"] > 50 * tds["years_to_vertical_breakthrough"]


def test_beta_now_moves_the_vertical_answer():
    """Before 2026-09-25 this pair returned the same breakthrough time."""
    lo = _serve(species="uranium_ppb", beta=0.5)["vertical"]
    hi = _serve(species="uranium_ppb", beta=10.0)["vertical"]
    assert hi["years_to_vertical_breakthrough"] > 5 * lo["years_to_vertical_breakthrough"]


def test_vertical_and_horizontal_share_one_retention_law():
    """Same rock, same law: with the ore zone's mobile porosity set to the
    confining layer's, the two directions must report the same retardation."""
    phi = P.VERTICAL["phi_confining"]
    r = _serve(species="uranium_ppb", phi_mobile=phi)
    horiz = r["hydro"]["retardation_effective"]
    vert = r["vertical"]["layer2_retardation"]
    assert vert == pytest.approx(horiz, rel=1e-3)
    ret = r["vertical"]["confining_path"]["retention"]
    beta = P.beta_from_porosities(ret["n_total"], phi)
    assert 1 + effective_capacity_ratio(beta, ret["n_total"], ret["grain_density"],
                                        ret["Kd_L_kg"]) == pytest.approx(vert, rel=1e-3)


# ── the column's conductivity ───────────────────────────────────────────


def test_path_conductivity_is_the_series_mean_of_the_profile():
    K_ref, fb = 2.467, 258.0
    # wholly above the reference depth: K(z) = K_ref everywhere
    assert confining_path_conductivity(K_ref, 5.0, P.K_DEPTH_REF_M, fb) == pytest.approx(K_ref)
    k_path = confining_path_conductivity(K_ref, 20.0, 140.0, fb)
    k_bottom = K_ref * P.depth_decay_factor(140.0, fb)
    assert k_bottom < k_path < K_ref
    # closed form for this profile: flat to z_ref, exponential below it
    lam = (fb - P.K_DEPTH_REF_M) / math.log(1 / P.K_DEPTH_RESIDUAL_AT_FRACTURE_BASE)
    integral = (P.K_DEPTH_REF_M - 20.0) + lam * (math.exp((140.0 - P.K_DEPTH_REF_M) / lam) - 1)
    assert k_path == pytest.approx(K_ref * 120.0 / integral, rel=1e-4)


def test_served_path_uses_the_same_profile_as_the_ore_zone():
    r = _serve(species="tds_mg_l")
    cp = r["vertical"]["confining_path"]
    kd = r["hydro"]["k_depth"]
    assert cp["K_reference_m_day"] == pytest.approx(kd["K_shallow_m_day"], rel=1e-3)
    assert cp["K_ore_depth_m_day"] == pytest.approx(r["hydro"]["K_m_day"], rel=1e-3)
    assert cp["K_ore_depth_m_day"] < cp["K_path_m_day"] < cp["K_reference_m_day"]


# ── the anisotropy is measured, and its range is shown ──────────────────


def test_kv_kh_is_the_geometric_mean_of_the_published_measurements():
    """Maréchal et al. (2004) J. Geol. Soc. India 63(5), Tables 2-3."""
    measured = [0.606, 0.125, 0.034, 1 / 18.7, 1 / 5.5]
    gm = math.exp(sum(math.log(x) for x in measured) / len(measured))
    assert P.VERTICAL["Kv_Kh_by_regime"]["fractured"] == pytest.approx(gm, abs=0.005)
    lo, hi = P.VERTICAL["Kv_Kh_band_by_regime"]["fractured"]
    assert lo == pytest.approx(min(measured), abs=0.001)
    assert hi == pytest.approx(max(measured), abs=0.005)


def test_the_anisotropy_band_brackets_the_headline():
    v = _serve(species="tds_mg_l")["vertical"]
    fast, slow = v["anisotropy_band"]["years_to_breakthrough_range"]
    assert fast <= v["years_to_vertical_breakthrough"] <= slow


def test_the_anisotropy_band_scales_exactly_for_water():
    """Water arrival is exactly proportional to 1/Kv. A retarded solute is NOT:
    on a fast path it outruns the matrix uptake (the first-order clock has not
    matured), so its band is WIDER than the Kv ratio -- 44x vs 18x for TDS at
    Jaduguda. That is the physics, not an error, so only water is pinned."""
    lo, hi = P.VERTICAL["Kv_Kh_band_by_regime"]["fractured"]
    r = _screen(layer2_beta_eff=0.0, Kv_Kh_band=(lo, hi))
    fast, slow = r["anisotropy_band"]["years_to_breakthrough_range"]
    assert slow / fast == pytest.approx(hi / lo, rel=0.05)
    sol = _screen(layer2_beta_eff=2.75, Kv_Kh_band=(lo, hi))["anisotropy_band"]
    f2, s2 = sol["years_to_breakthrough_range"]
    assert s2 / f2 > hi / lo


# ── the display species cannot hide the salts ───────────────────────────


def test_a_uranium_run_still_reports_when_the_injected_salts_arrive():
    u = _serve(species="uranium_ppb")["vertical"]
    tds = _serve(species="tds_mg_l")["vertical"]
    first = u["first_arrival"]
    assert first["species"] != "uranium_ppb"
    assert first["years"] < u["years_to_vertical_breakthrough"]
    # mirrored-site guard: the indicator inside the uranium run and the TDS run
    # itself must agree -- one geometry builder, not two
    ind = {i["species"]: i for i in u["indicators"]}
    assert ind["tds_mg_l"]["years_to_breakthrough"] == tds["years_to_vertical_breakthrough"]


def test_no_index_is_invented_for_a_species_without_a_limit():
    u = _serve(species="uranium_ppb")["vertical"]
    cl = {i["species"]: i for i in u["indicators"]}["chloride_mg_l"]
    assert cl["health_limit"] is None
    assert cl["shallow_impact_probability"] is None
    assert cl["source_exceeds_limit"] is None
    assert cl["years_to_breakthrough"] is not None       # arrival is still a fact
    assert u["first_detectable"]["years"] <= u["first_arrival"]["years"]


# ── reversibility ───────────────────────────────────────────────────────


def test_switching_the_corrections_off_restores_the_old_answer(monkeypatch):
    """All three changes off -> the pre-2026-09-25 served answer, identical for
    every species. Pinned against the previous code at this exact pin (main
    d2bb215, 20-yr run, default operation): 17.5 yr, seasonal band [6.4, 31.1]
    for uranium AND for TDS -- the symptom itself."""
    monkeypatch.setitem(P.VERTICAL_PATH, "matrix_retention", False)
    monkeypatch.setitem(P.VERTICAL_PATH, "depth_resolved_K", False)
    monkeypatch.setitem(P.VERTICAL["Kv_Kh_by_regime"], "fractured", 0.03)
    run = _serve(species="uranium_ppb")
    u = run["vertical"]
    tds = _serve(species="tds_mg_l")["vertical"]
    assert u["years_to_vertical_breakthrough"] == pytest.approx(17.5, abs=1e-9)
    assert u["seasonal"]["breakthrough_years_range"] == [6.4, 31.1]
    assert u["years_to_vertical_breakthrough"] == tds["years_to_vertical_breakthrough"]
    assert u["years_to_vertical_breakthrough"] == u["water_arrival_years"]
    assert u["confining_path"]["K_path_m_day"] == pytest.approx(run["hydro"]["K_m_day"],
                                                                rel=1e-3)
