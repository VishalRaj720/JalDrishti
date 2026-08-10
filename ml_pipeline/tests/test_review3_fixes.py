"""Regression tests for the review3.md remediation (2026-08-10).

One test per finding, each asserting the PROPERTY rather than a pinned literal
wherever the property is what actually matters -- the fidelity register has gone
stale twice by pinning numbers instead of relationships.
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from ml_pipeline.config import parameters as P
from ml_pipeline.physics import transport as T


# --------------------------------------------------------------------------- #
# D-1  radium restoration residual must follow its own stated derivation
# --------------------------------------------------------------------------- #
def test_d1_radium_restoration_residual_matches_its_own_derivation():
    """The constant is derived as exp(-N/Rd_Ra) with N anchored on uranium's
    measured Texas endpoint. It went stale once already (0.99, computed from Kd
    values the config no longer holds), and it is a TRAINING LABEL. Recompute
    from the live constants rather than trusting the number."""
    from ml_pipeline.data_prep.texas_loader import texas_restoration_residual
    r_u = texas_restoration_residual()["uranium_ppb"]
    N_over_RdU = math.log(1.0 / r_u)
    implied = {}
    for regime, n_tot, rho_s in (("fractured", 0.03, 2750.0),
                                 ("porous", 0.30, 2650.0)):
        kd_u = P.KD_RANGES["uranium_ppb"][regime][1]
        kd_ra = P.RADIUM_KD_RANGES[regime][1]
        Ru = T.matrix_retardation(n_tot, rho_s, kd_u)
        Rra = T.matrix_retardation(n_tot, rho_s, kd_ra)
        implied[regime] = math.exp(-N_over_RdU * Ru / Rra)
    served = P.RADIUM_RESTORATION_RESIDUAL
    assert min(implied.values()) - 0.02 <= served <= max(implied.values()) + 0.02, (
        f"RADIUM_RESTORATION_RESIDUAL={served} is outside the range its own "
        f"derivation implies from the CURRENT Kd values {implied}. If the Kd "
        f"band changed, re-derive the constant -- do not leave it stale.")
    # and it must be the conservative (higher-residual) end, which is fractured
    assert served == pytest.approx(implied["fractured"], abs=0.02)


def test_d1_radium_restoration_is_weak_but_not_inert():
    """0.99 made the restoration slider a no-op for radium. The corrected value
    must leave radium HARDER to clean than uranium but not immovable."""
    u = P.restoration_endpoint_for("uranium_ppb", {"uranium_ppb": 0.06})
    ra = P.restoration_endpoint_for("radium_226_mbq_l", {"uranium_ppb": 0.06})
    assert u < ra < 0.95, "radium must be harder to sweep than uranium, yet sweepable"


# --------------------------------------------------------------------------- #
# D-3  Ra-226 ingrowth arithmetic (documentation-level, but must stay right)
# --------------------------------------------------------------------------- #
def test_d3_ra226_ingrowth_is_a_two_step_chain_and_negligible():
    """Freshly deposited U carries no Th-230, so Ra-226 ingrowth is rate-limited
    by TWO sequential decays. The old one-step figure overstated 50 yr by 93x."""
    lam_th = math.log(2) / P.TH230_HALFLIFE_YEARS
    lam_ra = math.log(2) / P.RADIUM_HALFLIFE_YEARS
    t = 50.0
    two_step = 1.0 - (lam_ra * math.exp(-lam_th * t)
                      - lam_th * math.exp(-lam_ra * t)) / (lam_ra - lam_th)
    one_step = 1.0 - math.exp(-lam_th * t)
    assert two_step < 1e-5, "50 yr ingrowth must be negligible"
    assert one_step / two_step > 50.0, "the one-step form overstates materially"
    assert P.RADIUM_INGROWTH_MODELLED is False


# --------------------------------------------------------------------------- #
# D-4  omega convention must stay documented while the geometry path is off
# --------------------------------------------------------------------------- #
def test_d4_geometry_omega_stays_disabled_and_documented():
    assert P.OMEGA_FROM_GEOMETRY is False, (
        "matrix_transfer_omega returns an IMMOBILE-side rate while the retarded "
        "clock expects a MOBILE-side one (a = omega*(1+beta)/beta). Enabling "
        "this without converting introduces a factor-beta error -- see the "
        "warning in transport.apparent_retardation.")
    assert "MOBILE-side" in T.apparent_retardation.__doc__
    assert "IMMOBILE-side" in T.matrix_transfer_omega.__doc__


# --------------------------------------------------------------------------- #
# D-5  the displayed retardation must not contradict the physics
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kd,expect_gap", [(0.0, False), (1.0, True), (13.2, True)])
def test_d5_effective_retardation_tracks_sorption(kd, expect_gap):
    from ml_pipeline.data_prep.feature_engineering import retardation_factor
    tracer = retardation_factor(kd, 0.03, 2750.0, "fractured", 8.0)
    eff = 1.0 + T.effective_capacity_ratio(8.0, 0.03, 2750.0, kd)
    assert tracer == pytest.approx(9.0), "tracer Rd is species-blind by design"
    if expect_gap:
        assert eff > 5.0 * tracer, "a sorbing species must retard far more"
    else:
        assert eff == pytest.approx(tracer), "Kd=0 must be bit-identical"


def test_d5_serve_path_reports_both_retardations():
    from ml_pipeline.dashboard.resolve import resolve_inputs
    _inp, hydro = resolve_inputs(dict(lon=86.347, lat=22.652,
                                      species="radium_226_mbq_l"))
    assert "retardation_effective" in hydro and "retardation_basis" in hydro
    assert hydro["retardation_effective"] > hydro["retardation_Rd"]


# --------------------------------------------------------------------------- #
# D-6  the scenario-assumption register must stay in sync with the config
# --------------------------------------------------------------------------- #
def test_d6_assumption_register_values_match_the_live_constants():
    reg = P.UNGROUNDED_PARAMETERS
    live = {"SOURCE_BV_GAIN": P.SOURCE_BV_GAIN,
            "SOURCE_BV_REF": P.SOURCE_BV_REF,
            "INCREMENTAL_FLOOR": P.INCREMENTAL_FLOOR,
            "ISR_UCL_BASELINE_INCREASE": P.ISR_UCL_BASELINE_INCREASE}
    for name, value in live.items():
        assert name in reg, f"{name} is ungrounded but missing from the register"
        assert reg[name]["value"] == value, (
            f"{name} changed to {value} but the register still says "
            f"{reg[name]['value']} -- update the register deliberately.")
    for name, entry in reg.items():
        assert entry.get("leverage") and entry.get("grounding"), name
        assert entry["kind"] in {"scenario_assumption", "modelling_policy",
                                 "foreign_analogue_literature"}, name


# --------------------------------------------------------------------------- #
# D-7  the alkalinity helper is no longer dead code
# --------------------------------------------------------------------------- #
def test_d7_ambient_alkalinity_kd_is_surfaced_not_dead():
    from ml_pipeline.dashboard.resolve import resolve_inputs
    _inp, hydro = resolve_inputs(dict(lon=86.347, lat=22.652, species="uranium_ppb"))
    assert "kd_ambient_alkalinity_adjusted" in hydro
    # it is CONTEXT: it must never be the Kd the transport engine received
    assert hydro["kd_ambient_alkalinity_adjusted"] <= hydro["Kd_L_kg"] + 1e-9


# --------------------------------------------------------------------------- #
# V-8  t = 0 must be identically zero, in BOTH engines
# --------------------------------------------------------------------------- #
def test_v8_nothing_injected_at_t_zero():
    p = T.TransportParams(C0=10000.0, aL=5.0, aT=0.5, source_width_m=300.0,
                          Xc=0.0, Xw=0.0, sigma=0.0, t_days=0.0)
    assert T.concentration_point(0.5, 0.0, p) == 0.0
    assert T.centreline_reach(p, thr_inc=30.0) == 0.0
    res = T.solve_plume(p, threshold=30.0, background=1.0, grid_n=80)
    assert res.metrics["affected_area_ha"] == 0.0
    assert res.metrics["max_migration_distance_m"] == 0.0, (
        "area and migration must agree at the origin -- they read 0.00 ha and "
        "0.336 m before this fix (review2.md V-8)")


def test_v8_mc_engine_agrees_with_the_scalar_engine_at_t_zero():
    p = T.TransportParams(C0=10000.0, aL=5.0, aT=0.5, source_width_m=300.0,
                          Xc=0.0, Xw=0.0, sigma=0.0, t_days=0.0)
    m = T.mc_field_metrics([p], threshold=30.0, background=1.0, grid_n=60)
    assert float(m["area_ha"][0]) == 0.0 and float(m["max_dist_m"][0]) == 0.0


# --------------------------------------------------------------------------- #
# Post-restoration rebound floor
# --------------------------------------------------------------------------- #
def test_rebound_floor_stops_decay_below_the_measured_stable_endpoint():
    """The Texas endpoint is measured on post-restoration STABILITY samples, so
    the passive flush must not carry the source below it."""
    op, rest = 8 * 365.0, 5 * 365.0
    endpoint = 0.06
    late = T.source_strength_fraction(endpoint, 50 * 365.0, op, rest)
    credit = T.restoration_source_fraction(endpoint, 50 * 365.0, op, rest)
    assert late == pytest.approx(credit, rel=1e-9)
    assert late > credit * T.disc_flush_factor(50 * 365.0, op), (
        "without the floor the compounding product would sit below the endpoint")


def test_rebound_floor_leaves_unrestored_scenarios_untouched():
    t, op = 50 * 365.0, 8 * 365.0
    assert T.source_strength_fraction(1.0, t, op, 0.0) == pytest.approx(
        T.disc_flush_factor(t, op)), "no sweep -> full natural flush, unchanged"


def test_restoration_still_monotone_in_sweep_length():
    op, t = 8 * 365.0, 30 * 365.0
    vals = [T.source_strength_fraction(0.06, t, op, r * 365.0)
            for r in (0.0, 1.0, 3.0, 5.0, 10.0)]
    assert all(a >= b - 1e-12 for a, b in zip(vals, vals[1:])), (
        f"a longer sweep must never leave a dirtier source: {vals}")


# --------------------------------------------------------------------------- #
# Depth-decay: no extrapolation past the NAQUIM evidence
# --------------------------------------------------------------------------- #
def test_depth_decay_is_not_extrapolated_past_the_fracture_base():
    base = 121.0                                    # Ranchi NAQUIM fracture death
    at_base = P.depth_decay_factor(base, base)
    assert P.depth_decay_factor(300.0, base) == pytest.approx(at_base)
    assert P.depth_decay_factor(600.0, base) == pytest.approx(at_base)
    assert at_base == pytest.approx(P.K_DEPTH_RESIDUAL_AT_FRACTURE_BASE, rel=1e-6)


def test_depth_decay_stays_inside_the_global_crustal_trend():
    """Manning & Ingebritsen (1999): log k = -14 - 3.2 log z (z km) gives ~440x
    between 45 m and 300 m. The old unbounded exponential claimed up to 23,000x."""
    mi = 10.0 ** (3.2 * (math.log10(0.300) - math.log10(0.045)))   # ~440
    for base in (121.0, 180.0, 258.0):
        model = 1.0 / P.depth_decay_factor(300.0, base)
        assert model <= mi, (f"district base {base} m implies a {model:.0f}x drop "
                             f"at 300 m, exceeding the global crustal trend {mi:.0f}x")


def test_depth_decay_still_decays_within_the_evidenced_interval():
    base = 258.0
    f = [P.depth_decay_factor(z, base) for z in (45.0, 100.0, 180.0, 258.0)]
    assert all(a > b for a, b in zip(f, f[1:])), "must still fall with depth"


# --------------------------------------------------------------------------- #
# Regime-contact K seam (fidelity 3.6, third seam) + the OOD guard that hid it
# --------------------------------------------------------------------------- #
def test_regime_contact_k_is_continuous():
    """Two adjacent pins with the same physical K(z) were served 2.16x apart
    because the depth-decay result was clamped into per-regime trained-K boxes."""
    from ml_pipeline.dashboard.resolve import resolve_inputs
    lon0, lat0 = 85.399, 23.312
    ks, regimes = [], []
    for d in (-0.005, 0.0, 0.005):
        inp, h = resolve_inputs(dict(lon=lon0 + d, lat=lat0,
                                     species="sulfate_mg_l", ore_depth_m=300.0))
        ks.append(inp["K_m_day"])
        regimes.append(h["regime"])
    assert len(set(regimes)) > 1, "this coordinate must straddle a regime contact"
    ratio = max(ks) / max(min(ks), 1e-12)
    assert ratio < 1.35, f"K steps {ratio:.2f}x across the regime contact"


def test_ood_guard_is_scale_aware_at_the_low_end_of_K():
    """The guard used a 2%-of-LINEAR-span tolerance, which for fractured K
    (0.044-10.6) is 5x the trained minimum itself -- so a K 500x below support
    raised no flag."""
    from ml_pipeline.dashboard.resolve import envelope_violations, _hydro_support
    sup = _hydro_support().get("fractured")
    if not sup:
        pytest.skip("no hydro_support in the deployed model card")
    k_lo = sup["K_m_day"][0]
    base = dict(regime="fractured", Q_in_m3_day=2500.0, bleed_fraction=0.02,
                operation_years=8.0, gradient_i=0.005, wellfield_width_m=300.0,
                time_years=10.0, phi_mobile=0.008, n_total=0.03,
                grain_density=2700.0, kd_L_kg=1.0, beta=8.0)
    assert "hydro:K_m_day" in envelope_violations({**base, "K_m_day": k_lo / 500.0})
    assert "hydro:K_m_day" not in envelope_violations({**base, "K_m_day": k_lo * 2.0})


# --------------------------------------------------------------------------- #
# V-2 / V-4  Texas provenance and parser hardening
# --------------------------------------------------------------------------- #
def test_v4_parser_drops_the_trailer_and_pins_row_counts():
    from ml_pipeline.data_prep.texas_loader import (load_texas_geochem,
                                                    EXPECTED_GEOCHEM_ROWS,
                                                    _MAX_MINE_LABEL_CHARS)
    geo = load_texas_geochem()                       # raises if counts moved
    for sheet, df in geo.items():
        assert len(df) == EXPECTED_GEOCHEM_ROWS[sheet]
        label = "Mine" if "Mine" in df.columns else df.columns[1]
        for v in df[label].astype(str):
            assert len(v) <= _MAX_MINE_LABEL_CHARS, f"trailer survived: {v[:60]}"
            assert not v.strip().startswith(("1 ", "2 ", "3 ")), v[:60]


def test_v2_source_envelope_is_the_full_observed_mine_level_range():
    from ml_pipeline.data_prep.texas_loader import (texas_source_signature,
                                                    texas_source_provenance,
                                                    _eom_per_mine)
    env = texas_source_signature()
    per_mine = _eom_per_mine()
    for key, (lo, hi) in env.items():
        s = per_mine[key]
        assert lo == pytest.approx(float(s.min()))
        assert hi == pytest.approx(float(s.max())), (
            "the envelope must not truncate a real observed site value")
    prov = texas_source_provenance()
    assert prov["n_rows"] == 9 and prov["n_mines"] == 7, (
        "sample size must be reported, not implied by four significant figures")


# --------------------------------------------------------------------------- #
# R-1  the NUREG regulatory excursion test
# --------------------------------------------------------------------------- #
def test_r1_uranium_and_radium_are_never_excursion_indicators():
    """NUREG-1569 p.137 rejects uranium because it may be retarded by reducing
    conditions -- exactly what this model computes independently."""
    assert "uranium_ppb" not in P.ISR_EXCURSION_INDICATORS
    assert "radium_226_mbq_l" not in P.ISR_EXCURSION_INDICATORS
    for sp in ("uranium_ppb", "radium_226_mbq_l"):
        assert sp in P.ISR_NON_INDICATORS and P.ISR_NON_INDICATORS[sp]
    for sp in P.ISR_EXCURSION_INDICATORS:
        assert P.kd_range_for(sp, "fractured")[1] < 0.5, (
            f"{sp} must be near-conservative to be a valid indicator")


def test_r1_ucl_respects_the_nureg_bracket():
    """p.138: UCL must be ABOVE baseline and BELOW the lixiviant concentration."""
    for baseline, c0 in ((300.0, 5000.0), (20.0, 900.0), (1778.0, 2000.0)):
        ucl = P.isr_upper_control_limit(baseline, c0)
        assert baseline < ucl < c0
    # source at or below baseline -> no UCL can exist -> indicator cannot signal
    assert P.isr_upper_control_limit(500.0, 400.0) == float("inf")


def test_r1_two_of_n_rule_and_panel_shortfall_are_reported():
    from ml_pipeline.dashboard.isr_excursion import isr_indicator_excursion
    out = isr_indicator_excursion(dict(lon=86.347, lat=22.652,
                                       species="uranium_ppb", time_years=20,
                                       operation_years=8, gradient_i=0.02))
    assert out["indicators_required"] == 2
    assert out["excursion_declared"] == (out["indicators_over_ucl"] >= 2)
    assert out["panel_shortfall"] is True and out["panel_note"]
    assert "NUREG-1569" in out["citation"]


def test_r1_indicators_detect_before_the_health_limit_does():
    """The whole point of the NUREG indicator system: conservative tracers warn
    before a health limit is breached. If this inverts, the module is wrong."""
    from fastapi.testclient import TestClient
    from ml_pipeline.dashboard.server import app
    c = TestClient(app)
    r = c.post("/api/predict", json=dict(lon=86.347, lat=22.652,
                                         species="uranium_ppb", time_years=20,
                                         operation_years=8, gradient_i=0.005,
                                         bleed_percent=0.0))
    j = r.json()
    assert j["isr_excursion"]["excursion_declared"] is True
    assert j["metrics"]["analytical"]["breach"] == 0, (
        "at this operating point the indicators must fire while the uranium "
        "health limit is still clear -- that ordering IS the finding")


# --------------------------------------------------------------------------- #
# R-2  monitor ring grounding + R-4 vertical monitoring density
# --------------------------------------------------------------------------- #
def test_r2_compliance_buffer_sits_inside_licensed_practice():
    lo, hi = P.MONITOR_RING_RANGE_M
    assert lo <= P.COMPLIANCE_BUFFER_M <= hi
    assert P.COMPLIANCE_BUFFER_M <= P.MONITOR_RING_JUSTIFY_BEYOND_M
    assert "NUREG-1569" in P.MONITOR_RING_CITATION


def test_r2_moving_the_ring_flags_extrapolation_and_moves_compliance():
    from fastapi.testclient import TestClient
    from ml_pipeline.dashboard.server import app
    c = TestClient(app)
    base = dict(lon=86.347, lat=22.652, species="tds_mg_l", time_years=20,
                operation_years=8, gradient_i=0.02)
    at100 = c.post("/api/predict", json={**base, "monitor_ring_m": 100.0}).json()
    at180 = c.post("/api/predict", json={**base, "monitor_ring_m": 180.0}).json()
    assert "monitor_ring_m" not in at100["extrapolation"]
    assert "monitor_ring_m" in at180["extrapolation"], (
        "the compliance head was trained at 100 m; a moved ring is extrapolation")
    assert at180["wellfield_geometry"]["monitor_ring_needs_justification"] is True
    assert (at180["wellfield_geometry"]["monitor_ring_from_pin_m"]
            > at100["wellfield_geometry"]["monitor_ring_from_pin_m"])


def test_r4_vertical_monitoring_density_is_reported():
    from fastapi.testclient import TestClient
    from ml_pipeline.dashboard.server import app
    c = TestClient(app)
    j = c.post("/api/predict", json=dict(lon=86.347, lat=22.652,
                                         species="uranium_ppb")).json()
    mon = j["vertical"]["monitoring"]
    assert mon["overlying_wells_required"] >= 1
    assert mon["ha_per_well_overlying"] == 1.6
    assert "NUREG" in mon["citation"]


# --------------------------------------------------------------------------- #
# Rn-222 scope decision
# --------------------------------------------------------------------------- #
def test_rn222_omission_is_scope_not_a_physics_claim():
    """Radon survives to the ring across part of this model's velocity envelope,
    so the omission must NOT be justified as 'decay makes it zero'."""
    assert P.RADON_222_MODELLED is False
    lam = math.log(2) / P.RADON_222_HALFLIFE_DAYS
    fast_v = 15.0                                   # m/day, near the p99 of training
    surviving = math.exp(-lam * (100.0 / fast_v))
    assert surviving > 0.05, (
        "radon is NOT universally immobile here; the recorded reason for "
        "omitting it must stay 'no source term + atmospheric pathway'")
    assert "RADON_222_MODELLED" in open(P.__file__, encoding="utf-8").read()


# --------------------------------------------------------------------------- #
# V-6  availability controls
# --------------------------------------------------------------------------- #
def test_v6_static_overlays_are_cacheable():
    from fastapi.testclient import TestClient
    from ml_pipeline.dashboard.server import app
    c = TestClient(app)
    for path in ("/api/boundary", "/api/ore", "/api/assumptions"):
        r = c.get(path)
        assert r.status_code == 200
        assert r.headers.get("ETag") and "max-age" in r.headers.get("Cache-Control", "")


def test_v6_rate_limiter_is_configured_and_bounded():
    from ml_pipeline.dashboard import server as S
    assert S.RATE_LIMIT_PER_MIN > 0 and S.RATE_LIMIT_BURST > 0
    # the timeline animation issues one request per simulated month, so the
    # limit must sit well above a legitimate burst
    assert S.RATE_LIMIT_PER_MIN >= 120


# --------------------------------------------------------------------------- #
# V-7  beta override must show what it cost
# --------------------------------------------------------------------------- #
def test_v7_beta_override_returns_the_default_answer_too():
    from fastapi.testclient import TestClient
    from ml_pipeline.dashboard.server import app
    c = TestClient(app)
    j = c.post("/api/predict", json=dict(lon=86.347, lat=22.652,
                                         species="uranium_ppb", beta=0.0)).json()
    bo = j["beta_override"]
    assert bo and bo["user_beta"] == 0.0
    assert bo["with_user_beta"]["migration_m"] > bo["with_default_beta"]["migration_m"]
    # and no comparison block when the user did not override
    j2 = c.post("/api/predict", json=dict(lon=86.347, lat=22.652,
                                          species="uranium_ppb")).json()
    assert j2["beta_override"] is None


# --------------------------------------------------------------------------- #
# Cross-cutting: the served source fraction must equal what the diagnostic says
# --------------------------------------------------------------------------- #
def test_restoration_diagnostic_matches_the_served_source():
    from ml_pipeline.dashboard.resolve import resolve_inputs
    from ml_pipeline.ml.predict import predict_analytical
    inputs, _h = resolve_inputs(dict(lon=86.347, lat=22.652, species="uranium_ppb",
                                     time_years=30, operation_years=8,
                                     restoration_years=5))
    out = predict_analytical(**inputs)
    out.pop("_field", None)
    d = out["restoration"]
    expected = T.source_strength_fraction(
        d["residual_endpoint_fraction"], 30 * 365.0, 8 * 365.0, 5 * 365.0)
    assert d["served_source_fraction"] == pytest.approx(expected, rel=1e-6), (
        "the diagnostic must report the fraction the physics actually used")
