"""
2026-09-27 -- the Gemini-review build (docs/GEMINI_REVIEW_ASSESSMENT.md,
LIMITATIONS.md section 1l, P section 9).

Pinned here:
  * the preferential-pathway channel is built from the belt's own logged
    fracture zones, reduces to the single-fracture Tang solution, and reads at a
    monitoring well as a flux-weighted mix -- never above its strongest channel;
  * alerts read max(continuum, channel) and never less than the continuum;
  * the surrogate's out-of-support check now sees Kd in fractured rock, and the
    alerting envelope never uses an out-of-support ML band;
  * the high-alkalinity Kd scenario is a labelled hypothetical with its own
    Monte-Carlo range;
  * the upward gradient runs on the P50 of the measured band, with P10/P90
    beside it, and states its sign record;
  * the dip-rotated tensor has the right limits;
  * the injectivity read-out matches a hand-calculated Muskat case.
"""
from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.special import erfc

from ml_pipeline.config import parameters as P
from ml_pipeline.physics import channel as CH
from ml_pipeline.physics.injectivity import injectivity_check
from ml_pipeline.physics.transport import dip_rotated_kv_kh, dip_kv_kh_band

JADUGUDA = (86.3468, 22.6520)


def _serve(**over):
    from ml_pipeline.dashboard.server import api_predict, PredictRequest
    kw = dict(lon=JADUGUDA[0], lat=JADUGUDA[1], time_years=20, operation_years=8,
              ore_depth_m=180)
    kw.update(over)
    return api_predict(PredictRequest(**kw))


# ── the logged fracture sets ────────────────────────────────────────────


def test_fracture_sets_come_from_the_belt_logs_and_skip_the_tertiary_wells():
    sets = {s["well_id"]: s for s in CH.fracture_sets()}
    kudada = [z[2] for z in sets["kudada_ew"]["zones"]]
    # 0.41, 0.6 and 11.5 L/s -> the 137-139 m zone carries 92% of the yield
    assert kudada == pytest.approx([0.41 / 12.51, 0.6 / 12.51, 11.5 / 12.51])
    assert CH.central_set()["well_id"] == "kudada_ew"
    for s in sets.values():
        assert s["formation"] != "Tertiary"
        assert sum(z[2] for z in s["zones"]) == pytest.approx(1.0)
    assert "manusmuria_ew" not in sets and "baharagora_ew" not in sets


def test_cubic_law_aperture_by_hand():
    T = 10.0                                            # m2/day
    ap = CH.hydraulic_aperture_m(T)
    assert ap == pytest.approx((12e-3 * T / 86400.0 / 9810.0) ** (1.0 / 3.0))
    # and T scales as aperture cubed
    assert CH.hydraulic_aperture_m(8 * T) == pytest.approx(2 * ap)


def test_the_continuum_porosity_is_far_above_what_the_cubic_law_allows_at_jaduguda():
    d = CH.cubic_law_consistency(0.034, 0.0075)
    assert d["inconsistent"]
    assert 500 < d["continuum_over_cubic_law"] < 2000


# ── one channel is the Tang solution ────────────────────────────────────


def _evaluate(zones, **over):
    kw = dict(T_m2_day=4.0, gradient_i=0.002, eta=0.0, n_total=0.03,
              grain_density=2750.0, kd_L_kg=0.0, zones=zones, c_factor=1.0,
              C0=1000.0, background=0.0, threshold=100.0, ring_x=100.0,
              t_days=3650.0, op_days=3650.0, rest_days=0.0, residual_ref=1.0,
              atten_k_yr=0.0)
    kw.update(over)
    return CH.evaluate(**kw)


def test_a_single_zone_reduces_to_the_tang_single_fracture_solution():
    r = _evaluate(((100.0, 101.0, 1.0),))
    ch = r["channels"][0]
    t = 3650.0
    t_w = 100.0 / ch["v"]
    by_hand = 1000.0 * erfc(ch["sigma"] * t_w / (2.0 * math.sqrt(t - t_w)))
    assert r["ring_increment"] == pytest.approx(by_hand, rel=1e-6)


def test_the_well_reading_never_exceeds_the_strongest_channel():
    zones = ((100.0, 101.0, 0.2), (120.0, 121.0, 0.8))
    r = _evaluate(zones)
    singles = [_evaluate(((z[0], z[1], 1.0),), T_m2_day=4.0 * z[2])["ring_increment"]
               for z in zones]
    assert r["ring_increment"] <= max(singles) + 1e-9
    assert r["ring_increment"] == pytest.approx(0.2 * singles[0] + 0.8 * singles[1],
                                                rel=1e-6)


def test_full_containment_holds_the_channel_during_operations():
    r = _evaluate(((100.0, 101.0, 1.0),), eta=1.0, t_days=1000.0, op_days=3650.0)
    assert r["ring_increment"] == 0.0 and r["reach_m"] == 0.0


def test_porous_pins_have_no_channel():
    inputs = dict(regime="porous")
    out = CH.channel_answer(inputs, {}, threshold=30.0, ring_x=100.0)
    assert out["applies"] is False


# ── what alerts read ────────────────────────────────────────────────────


def test_alerting_is_the_max_and_never_below_the_continuum():
    cont = {"migration_m": 30.0, "compliance_conc": 5.0, "excursion_probability": 0.1}
    ch = {"applies": True, "reach_m": 900.0, "ring_conc": 3.0,
          "excursion_probability": 0.6}
    a = CH.alerting_metrics(cont, ch)
    assert a["migration_m"] == 900.0 and a["basis"]["migration_m"] == "channel"
    assert a["compliance_conc"] == 5.0 and a["basis"]["compliance_conc"] == "continuum"
    assert a["excursion_probability"] == 0.6
    for k in ("migration_m", "compliance_conc", "excursion_probability"):
        assert a[k] >= cont[k]


def test_switching_the_channel_off_for_alerts_returns_the_continuum(monkeypatch):
    monkeypatch.setitem(P.CHANNEL, "drives_alerts", False)
    cont = {"migration_m": 30.0, "compliance_conc": 5.0, "excursion_probability": 0.1}
    ch = {"applies": True, "reach_m": 900.0, "ring_conc": 9.0,
          "excursion_probability": 1.0}
    a = CH.alerting_metrics(cont, ch)
    assert a["rule"] == "continuum only"
    assert a["migration_m"] == 30.0 and a["excursion_probability"] == 0.1


def test_served_run_carries_both_answers_and_the_alerting_max():
    r = _serve(species="tds_mg_l")
    m = r["metrics"]
    assert m["channel"]["applies"]
    assert m["alerting"]["migration_m"] >= m["analytical"]["migration_m"]
    assert m["alerting"]["excursion_probability"] >= m["analytical"]["excursion_probability"]
    # the continuum answer itself is untouched by the channel
    assert m["analytical"]["migration_m"] == pytest.approx(30.4, abs=0.2)


# ── out of trained support ──────────────────────────────────────────────


def test_a_fractured_kd_outside_its_training_prior_is_flagged():
    from ml_pipeline.dashboard.resolve import resolve_inputs, envelope_violations
    inp, hydro = resolve_inputs(dict(lon=JADUGUDA[0], lat=JADUGUDA[1],
                                     species="uranium_ppb"))
    assert inp["regime"] == "fractured"
    assert "kd:Kd_L_kg" not in envelope_violations(inp, hydro)      # served default
    low = dict(inp, kd_L_kg=0.1)
    assert "kd:Kd_L_kg" in envelope_violations(low, hydro)


def test_the_alert_envelope_never_uses_an_out_of_support_ml_band():
    r = _serve(species="tds_mg_l")                 # Jaduguda TDS background is OOD
    assert r["extrapolation"]
    env = r["alert_envelope"]
    assert "ml" not in env["candidates_m"]
    assert env["p90_m"] == max(env["candidates_m"].values())
    assert r["band_source"] == "engine_mc"
    assert r["metrics"]["engine_mc"]["migration_m"]["p90"] > 0


# ── the high-alkalinity scenario ────────────────────────────────────────


def test_high_alkalinity_is_a_labelled_hypothetical_with_its_own_kd_range():
    r = _serve(species="uranium_ppb")
    h = r["hypotheticals"]["high_alkalinity"]
    assert h["hypothetical"] and h["applies"]
    assert h["kd_L_kg"] == P.KD_SCENARIO_HIGH_ALKALINITY["kd_range_L_kg"][1]
    assert "kd:Kd_L_kg" in h["extrapolation"]
    # weaker sorption can only move uranium further
    assert h["metrics"]["migration_m"] >= h["baseline_metrics"]["migration_m"]
    # and it does not touch the served answer or what alerts read
    assert r["metrics"]["analytical"]["migration_m"] == h["baseline_metrics"]["migration_m"]


def test_the_scenario_kd_range_reaches_the_monte_carlo():
    from ml_pipeline.dashboard.resolve import resolve_inputs
    from ml_pipeline.ml.predict import mc_param_draws
    inp, _ = resolve_inputs(dict(lon=JADUGUDA[0], lat=JADUGUDA[1],
                                 species="uranium_ppb", time_years=20))
    base = mc_param_draws(inp)
    low = mc_param_draws(inp, kd_range=(0.03, 0.1, 0.3))
    assert np.median([p.Xc for p in low]) > np.median([p.Xc for p in base])


# ── the upward-gradient band ────────────────────────────────────────────


def test_the_screening_runs_on_the_p50_of_the_measured_band_and_states_the_sign():
    from ml_pipeline.dashboard.vertical_path import upward_gradient_setting
    g = upward_gradient_setting()
    lo, hi = P.VERTICAL_GRADIENT_BAND["magnitude_range"]
    assert g["served"] == pytest.approx(math.sqrt(lo * hi))
    assert g["band"][0] < g["served"] < g["band"][1]
    assert "2 of 4" in g["sign_note"]
    v = _serve(species="tds_mg_l")["vertical"]
    assert v["upward_gradient"] == pytest.approx(g["served"], rel=1e-3)
    fast, slow = v["gradient_band"]["years_to_breakthrough_range"]
    assert fast <= v["years_to_vertical_breakthrough"] <= slow


def test_switching_the_band_off_restores_the_fixed_gradient(monkeypatch):
    from ml_pipeline.dashboard.vertical_path import upward_gradient_setting
    monkeypatch.setitem(P.VERTICAL_GRADIENT_BAND, "enabled", False)
    g = upward_gradient_setting()
    assert g["served"] == P.VERTICAL["upward_gradient"] and g["band"] is None


# ── the dip-rotated tensor ──────────────────────────────────────────────


@pytest.mark.parametrize("a", [0.01, 0.1, 0.5, 1.0])
def test_tensor_limits(a):
    assert dip_rotated_kv_kh(0.0, a)["Kzz_over_Kh"] == pytest.approx(a)
    assert dip_rotated_kv_kh(90.0, a)["Kzz_over_Kh"] == pytest.approx(1.0 / math.sqrt(a))
    for d in (10.0, 40.0, 70.0):
        r = dip_rotated_kv_kh(d, a)
        # positive definite in the dip plane: Kxx*Kzz > Kxz^2
        assert r["Kxx_over_Kpar"] * r["Kzz_over_Kpar"] - (r["Kxz_over_Kh"]
               * math.sqrt(r["Kxx_over_Kpar"])) ** 2 >= -1e-12


def test_jaduguda_dip_band_sits_above_the_served_granite_ratio():
    b = dip_kv_kh_band((40.0, 40.0), P.FOLIATION_DIP["anisotropy_range"])
    assert b["Kv_Kh_low"] > P.VERTICAL["Kv_Kh_by_regime"]["fractured"]


# ── injectivity ─────────────────────────────────────────────────────────


def test_injectivity_matches_a_hand_calculated_muskat_case():
    out = injectivity_check(K_ore_m_day=0.034, ore_thickness_m=20.0,
                            Q_in_m3_day=2500.0, wellfield_width_m=300.0,
                            ore_depth_m=180.0, water_table_m=5.0)
    n = round(math.pi * 150.0 ** 2 / (2 * 15.0 ** 2))
    q_w = 2500.0 / n
    by_hand = q_w / (math.pi * 0.034 * 20.0) * (math.log(15.0 / 0.075) - 0.619)
    assert out["patterns"][0]["head_rise_m"] == pytest.approx(by_hand, abs=0.05)
    assert out["verdict"] == "marginal"
    assert out["fracture_headroom_range_m"][0] == pytest.approx(0.5 * 2.7 * 180 - 175, abs=0.1)
    ok = injectivity_check(K_ore_m_day=1.0, ore_thickness_m=20.0, Q_in_m3_day=2500.0,
                           wellfield_width_m=300.0, ore_depth_m=180.0, water_table_m=5.0)
    assert ok["verdict"] == "feasible"
