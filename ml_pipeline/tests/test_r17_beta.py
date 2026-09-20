"""R17 (2026-09-20) -- the dual-porosity capacity ratio is derived, not served.

LIMITATIONS.md section 1d: the engine served beta at the mean of a foreign
literature range (10) while its own porosities implied ~3, and the P10-P90 band
sampled inside that assumption. These tests pin the correction:

  * served beta = (n_total - phi_mobile)/phi_mobile from the run's own porosities
  * the training prior is log-uniform on [0.3, 20]
  * the Monte-Carlo band spans a factor of 4 either side of the central value
  * a user override still wins, porous rock still gets 0
  * the served value sits inside the retrained support (Rd = 1 + beta)
  * the branch diagnostic that decided against the diffusive clock is
    reproducible: the continuum branch governs at Jaduguda for uranium

They deliberately do NOT assert any migration distance -- those are labels the
v4 retrain regenerates, and pinning them here would turn a physics change into
a test edit.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from ml_pipeline.config import parameters as P
from ml_pipeline.dashboard.resolve import resolve_inputs
from ml_pipeline.synthetic.generate import (beta_mc_sample, beta_prior_sample,
                                            mc_draws, _draw_params)

JADUGUDA = dict(lon=86.3468, lat=22.6520)
RANCHI = dict(lon=85.33, lat=23.36)


# --------------------------------------------------------------------------- #
# the definition
# --------------------------------------------------------------------------- #
def test_beta_from_porosities_is_the_capacity_ratio_definition():
    # theta_immobile / theta_mobile with the tool's own lithology values
    assert P.beta_from_porosities(0.03, 0.0075) == pytest.approx(3.0)
    assert P.beta_from_porosities(0.03, 0.010) == pytest.approx(2.0)     # Schist
    assert P.beta_from_porosities(0.02, 0.008) == pytest.approx(1.5)     # Gneiss
    assert P.beta_from_porosities(0.01, 0.005) == pytest.approx(1.0)     # Granite


@pytest.mark.parametrize("litho", sorted(P.TOTAL_POROSITY))
def test_every_lithology_gives_a_beta_inside_the_prior(litho):
    n_total = P.TOTAL_POROSITY[litho]
    phi_m = P.DEFAULT_EFFECTIVE_POROSITY.get(litho, 0.05)
    lo, hi = P.DUAL_POROSITY["beta_prior"]
    b = P.beta_from_porosities(n_total, phi_m)
    assert lo <= b <= hi


def test_beta_from_porosities_clips_to_the_prior():
    lo, hi = P.DUAL_POROSITY["beta_prior"]
    assert P.beta_from_porosities(0.30, 0.001) == hi          # 299 -> capped
    assert P.beta_from_porosities(0.011, 0.010) == lo         # 0.1 -> floored
    assert P.beta_from_porosities(0.005, 0.010) == lo         # negative -> floored


# --------------------------------------------------------------------------- #
# the serve path
# --------------------------------------------------------------------------- #
def test_served_beta_is_porosity_derived_at_a_fractured_pin():
    inputs, hydro = resolve_inputs(dict(species="uranium_ppb", **JADUGUDA))
    assert inputs["regime"] == "fractured"
    expect = P.beta_from_porosities(inputs["n_total"], inputs["phi_mobile"])
    assert inputs["beta"] == pytest.approx(expect)
    assert hydro["beta_basis"] == "porosity_derived"
    assert hydro["dual_porosity_beta"] == pytest.approx(expect, abs=0.01)
    # and it is NOT the v3 literature mean any more
    legacy = sum(P.DUAL_POROSITY["beta_legacy_range"]) / 3.0
    assert abs(inputs["beta"] - legacy) > 1.0


def test_served_beta_band_is_a_factor_of_four_inside_the_prior():
    inputs, hydro = resolve_inputs(dict(species="uranium_ppb", **JADUGUDA))
    lo, hi = hydro["beta_band"]
    F = P.DUAL_POROSITY["beta_mc_factor"]
    plo, phi = P.DUAL_POROSITY["beta_prior"]
    assert lo == pytest.approx(max(inputs["beta"] / F, plo), abs=1e-3)
    assert hi == pytest.approx(min(inputs["beta"] * F, phi), abs=1e-3)


def test_beta_follows_a_phi_mobile_override():
    """beta and phi_mobile describe the same rock: overriding the mobile
    porosity must move the derived beta with it, or the two disagree again."""
    a, _ = resolve_inputs(dict(species="uranium_ppb", **JADUGUDA))
    b, _ = resolve_inputs(dict(species="uranium_ppb", phi_mobile=0.015, **JADUGUDA))
    assert b["beta"] == pytest.approx(P.beta_from_porosities(b["n_total"], 0.015))
    assert b["beta"] < a["beta"]


def test_user_override_still_wins():
    inputs, hydro = resolve_inputs(dict(species="uranium_ppb", beta=7.5, **JADUGUDA))
    assert inputs["beta"] == 7.5
    assert hydro["beta_basis"] == "user_override"


def test_porous_rock_gets_no_capacity_ratio():
    inputs, hydro = resolve_inputs(dict(species="uranium_ppb", regime="porous",
                                        **JADUGUDA))
    assert inputs["beta"] == 0.0
    assert hydro["beta_basis"] == "not_applicable_porous"
    assert hydro["beta_band"] is None


def test_served_beta_is_inside_the_trained_support():
    """Rd = 1 + beta is a model feature with a recorded support box. The whole
    point of the v4 retrain is that the porosity-derived value lands inside it;
    if this fails after a retrain, the prior and the serve path have drifted."""
    from ml_pipeline.dashboard.resolve import _hydro_support
    box = _hydro_support().get("fractured", {}).get("retardation_Rd")
    if not box:
        pytest.skip("model card carries no hydro_support (pre-v2 artifacts)")
    lo, hi = box
    for pin in (JADUGUDA, dict(lon=86.29, lat=22.69)):
        inputs, _ = resolve_inputs(dict(species="uranium_ppb", **pin))
        assert lo <= 1.0 + inputs["beta"] <= hi, (
            f"served Rd {1 + inputs['beta']:.2f} outside trained [{lo:.2f}, {hi:.2f}]")


# --------------------------------------------------------------------------- #
# the training prior and the Monte-Carlo band
# --------------------------------------------------------------------------- #
def test_prior_sample_is_log_uniform_over_the_prior():
    lo, hi = P.DUAL_POROSITY["beta_prior"]
    assert beta_prior_sample(0.0) == pytest.approx(lo)
    assert beta_prior_sample(1.0) == pytest.approx(hi)
    assert beta_prior_sample(0.5) == pytest.approx(math.sqrt(lo * hi))
    u = np.random.default_rng(0).uniform(size=20000)
    b = np.array([beta_prior_sample(x) for x in u])
    # log-uniform: the log has a flat histogram -> median of log = midpoint
    assert np.median(np.log(b)) == pytest.approx(0.5 * (math.log(lo) + math.log(hi)), abs=0.05)
    # and at most ~ log(4/0.3)/log(20/0.3) of the mass sits below 4 (was 11% under U(2,20))
    frac_below_4 = float((b < 4.0).mean())
    assert 0.55 < frac_below_4 < 0.68


def test_mc_sample_spans_a_factor_of_four_each_way():
    F = P.DUAL_POROSITY["beta_mc_factor"]
    assert beta_mc_sample(3.0, 0.0) == pytest.approx(3.0 / F)
    assert beta_mc_sample(3.0, 1.0) == pytest.approx(3.0 * F)
    assert beta_mc_sample(3.0, 0.5) == pytest.approx(3.0)
    assert beta_mc_sample(0.0, 0.7) == 0.0                     # porous


def test_mc_sample_is_clipped_to_the_prior():
    lo, hi = P.DUAL_POROSITY["beta_prior"]
    assert beta_mc_sample(0.4, 0.0) == pytest.approx(lo)
    assert beta_mc_sample(18.0, 1.0) == pytest.approx(hi)


def test_draw_params_uses_the_mc_band():
    """The label MC and the served excursion MC share `_draw_params`; check the
    beta it feeds the kinematics is the band sample, not the v3 0.6-1.4 jitter."""
    scn = dict(width=300.0, regime="fractured", K=0.5, phi_mobile=0.0075,
               n_total=0.03, grain_density=2750.0, beta=3.0, gradient=0.003,
               Q_in=500.0, Q_net=40.0, bleed=0.08, thickness=150.0, downtime=0.0,
               seasonal_amp=0.0, aniso_ratio=None, atten_k=0.0,
               C0={"sulfate_mg_l": 3000.0}, Cb={"sulfate_mg_l": 20.0})
    draws = mc_draws(48, 1)
    fronts = []
    for i in range(48):
        prm = _draw_params(scn, "sulfate_mg_l", 20 * 365.0, 8 * 365.0, draws, i,
                           w_eff=300.0, rest_days=0.0, residual_fraction=1.0)
        fronts.append(prm.Xc)
    fronts = np.array(fronts)
    # a factor-4 band on beta (R_eff ~ 1 + beta*R_m) must spread the front by
    # far more than the old +-40% jitter could: > 3x between the extremes
    assert fronts.max() / max(fronts.min(), 1e-9) > 3.0


# --------------------------------------------------------------------------- #
# the diagnostic that decided against the diffusive clock
# --------------------------------------------------------------------------- #
def test_continuum_branch_governs_at_jaduguda_uranium():
    """Recorded decision (LIMITATIONS.md 1d): at 20 yr the retarded-continuum
    front, not the Tang early-arrival envelope, sets the uranium extent at the
    deposit. That is why beta (capacity) is the lever and the matrix-transfer
    clock is not. If this flips, the clock decision must be revisited."""
    from ml_pipeline.ml.predict import features_from_inputs
    from ml_pipeline.physics import transport as T
    inputs, _ = resolve_inputs(dict(species="uranium_ppb", time_years=20.0,
                                    operation_years=8.0, restoration_years=3.0,
                                    **JADUGUDA))
    _, feat, _ = features_from_inputs(**inputs)
    prm = T.params_from_features(feat, species_C0=inputs["source_conc_C0"],
                                 t_days=20 * 365.0, operation_days=8 * 365.0,
                                 restoration_days=3 * 365.0,
                                 residual_fraction=feat.get("_residual_endpoint", 1.0))
    thr = P.EXCURSION_THRESHOLDS["uranium_ppb"]
    thr_inc = max(thr - inputs["background_conc_Cb"], P.INCREMENTAL_FLOOR * thr)
    xs = np.linspace(0.5, 200.0, 4000)
    tran0 = T._tran_factor(xs, np.zeros_like(xs), prm.aT, prm.source_width_m)
    c_cont = prm.C0 * T._long_factor(xs, prm.Xc, prm.aL) * tran0
    c_tang = prm.C0 * T.tang_attenuation(xs, prm.t_days, prm.Xw, prm.sigma) * tran0
    reach = lambda c: float(xs[np.where(c >= thr_inc)[0][-1]]) if (c >= thr_inc).any() else 0.0  # noqa: E731
    assert reach(c_cont) >= reach(c_tang)
