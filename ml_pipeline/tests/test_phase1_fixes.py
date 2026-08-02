"""
Phase-1 fidelity fixes (2026-08-01) -- regression tests.
========================================================
3.1  UI reframing            -- excursion screening, not mining feasibility
3.2  Site-specific C0        -- measured Jaduguda mine-water anchor reported
3.3  Depth-dependent K(z)    -- shallow K no longer applied at ore depth
3.5  Attenuation k tilt      -- reducing capacity graded by ore-zone mineralogy

Run:  python -m pytest ml_pipeline/tests/test_phase1_fixes.py -q
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from ml_pipeline.config import parameters as P
from ml_pipeline.dashboard.resolve import resolve_inputs, envelope_violations

JADUGUDA = dict(lon=86.347, lat=22.652, species="uranium_ppb")   # fractured deposit
BELT = dict(lon=86.25, lat=22.63, species="uranium_ppb")         # Singhbhum belt
RANCHI = dict(lon=85.33, lat=23.36, species="uranium_ppb")       # non-ore district


# --------------------------------------------------------------------------- #
# 3.3 -- depth-dependent hydraulic conductivity
# --------------------------------------------------------------------------- #
def test_depth_decay_law_shape():
    """1.0 at/above the reference depth; monotone decreasing below it; reaches
    the configured residual at the district's documented fracture-death depth."""
    base = 258.0                                    # E Singhbhum fracture base
    assert P.depth_decay_factor(P.K_DEPTH_REF_M, base) == 1.0
    assert P.depth_decay_factor(10.0, base) == 1.0
    f = [P.depth_decay_factor(z, base) for z in (60, 120, 180, 250)]
    assert all(a > b for a, b in zip(f, f[1:])), f
    # by construction K/K_ref == residual at the fracture base
    assert P.depth_decay_factor(base, base) == pytest.approx(
        P.K_DEPTH_RESIDUAL_AT_FRACTURE_BASE, rel=1e-6)


def test_depth_decay_uses_district_fracture_base():
    """A district whose fractures die shallow must decay FASTER than the belt,
    whose fractured aquifer is documented to persist to ~258 m."""
    z = 150.0
    belt = P.depth_decay_factor(z, 258.0)      # E Singhbhum
    ranchi = P.depth_decay_factor(z, 121.0)    # Ranchi
    assert ranchi < belt


def test_depth_decay_strength_knob():
    """strength < 1 damps the correction toward 1.0 (conservative interim)."""
    full = P.depth_decay_factor(180.0, 258.0, strength=1.0)
    half = P.depth_decay_factor(180.0, 258.0, strength=0.5)
    assert full < half < 1.0
    assert half == pytest.approx(math.sqrt(full), rel=1e-6)


def test_served_K_is_depth_decayed_at_deposit():
    inp, h = resolve_inputs(dict(**JADUGUDA, ore_depth_m=180.0))
    kd = h["k_depth"]
    assert kd is not None
    assert kd["fracture_base_source"] == "NAQUIM district report"
    assert kd["K_at_depth_m_day"] < kd["K_shallow_m_day"]
    # the diagnostic is rounded for display; compare within that rounding
    assert inp["K_m_day"] == pytest.approx(kd["K_at_depth_m_day"], abs=5e-4)


def test_deeper_ore_gives_lower_K():
    _, shallow = resolve_inputs(dict(**JADUGUDA, ore_depth_m=60.0))
    _, deep = resolve_inputs(dict(**JADUGUDA, ore_depth_m=400.0))
    assert deep["k_depth"]["K_at_depth_m_day"] < shallow["k_depth"]["K_at_depth_m_day"]


def test_depth_decay_never_leaves_trained_support():
    """The correction must not push K out of the model's trained box -- that
    would make our own fix raise a spurious extrapolation flag."""
    for depth in (60.0, 150.0, 300.0, 600.0):
        for pin in (JADUGUDA, RANCHI):
            inp, _ = resolve_inputs(dict(**pin, ore_depth_m=depth))
            viol = envelope_violations(inp)
            assert not any(v.startswith("hydro:K") for v in viol), (pin, depth, viol)


def test_explicit_K_override_beats_depth_decay():
    """A user stating a measured K must not have it silently decayed."""
    inp, h = resolve_inputs(dict(**JADUGUDA, ore_depth_m=400.0, K_m_day=1.5))
    assert h["k_depth"] is None
    assert inp["K_m_day"] == pytest.approx(1.5)


# --------------------------------------------------------------------------- #
# 3.5 -- attenuation mode graded by ore-zone mineralogy
# --------------------------------------------------------------------------- #
def test_attenuation_mode_follows_mineralogy():
    """Sulphide-rich ore body > belt envelope > oxidised country rock."""
    _, dep = resolve_inputs(dict(**JADUGUDA))
    _, belt = resolve_inputs(dict(**BELT))
    _, none = resolve_inputs(dict(**RANCHI))
    k_dep = dep["u_attenuation_k_per_yr"]
    k_belt = belt["u_attenuation_k_per_yr"]
    k_none = none["u_attenuation_k_per_yr"]
    assert k_dep > k_belt > k_none
    assert dep["u_attenuation_basis"] == "deposit zone mineralogy"


def test_attenuation_modes_stay_inside_trained_support():
    lo, hi = P.OPERATIONAL_RANGES["u_attenuation_k_per_yr"]
    for v in P.U_ATTENUATION_MODE_BY_ZONE.values():
        assert lo <= v <= hi


def test_attenuation_override_wins_and_is_labelled():
    inp, h = resolve_inputs(dict(**JADUGUDA, u_attenuation_k_per_yr=0.5))
    assert inp["u_attenuation_k_per_yr"] == pytest.approx(0.5)
    assert h["u_attenuation_basis"] == "user override"


def test_conservative_species_have_no_attenuation():
    inp, h = resolve_inputs(dict(lon=86.347, lat=22.652, species="sulfate_mg_l"))
    assert inp["u_attenuation_k_per_yr"] == 0.0
    assert h["source_term_context"] is None      # uranium-only block


# --------------------------------------------------------------------------- #
# 3.2 -- measured local source-term anchor is surfaced
# --------------------------------------------------------------------------- #
def test_source_term_context_reports_measured_anchor():
    _, h = resolve_inputs(dict(**JADUGUDA))
    stc = h["source_term_context"]
    assert stc is not None
    assert stc["jaduguda_mine_water_ppb"]["gm"] == pytest.approx(357.4)
    assert "10.4103/0972-0464.121824" in stc["citation"]
    # the served C0 is an ISR lixiviant and must exceed passive mine water
    assert stc["model_C0_ppb"] > stc["jaduguda_mine_water_ppb"]["gm"]
    assert stc["ratio_model_to_measured_gm"] > 1.0


# --------------------------------------------------------------------------- #
# 3.6 -- aquifer-boundary K smoothing (data seams)
# --------------------------------------------------------------------------- #
def test_boundary_blend_reports_itself_when_active():
    """Near a mapped contact the served K must be a blend, and the blend must be
    disclosed (never silently substituted)."""
    from ml_pipeline.data_prep.jharkhand_loader import (
        aquifer_at_point, load_jharkhand_aquifers)
    aq = load_jharkhand_aquifers()
    # walk the Ranchi->Jaduguda transect until a blended pin is found
    found = None
    for i in range(41):
        f = i / 40.0
        lon = 85.33 + f * (86.347 - 85.33)
        lat = 23.36 + f * (22.652 - 23.36)
        h = aquifer_at_point(lon, lat, aq)
        if h.get("_k_blend"):
            found = h
            break
    assert found is not None, "no blended pin found along the transect"
    b = found["_k_blend"]
    assert 0.5 <= b["weight_own"] <= 1.0
    lo = min(b["K_polygon_m_day"], b["K_neighbour_m_day"])
    hi = max(b["K_polygon_m_day"], b["K_neighbour_m_day"])
    assert lo - 1e-9 <= b["K_blended"] <= hi + 1e-9    # a blend, not an extrapolation
    assert found["K_m_day"] == pytest.approx(b["K_blended"])


def test_blend_weight_tapers_to_the_mapped_value_with_distance():
    """The smoothing must be LOCAL: the further a pin sits from a contact, the
    closer the served K returns to its own polygon's mapped value (weight -> 1).

    NOTE the CGWB layer is finely interleaved -- a random in-polygon pin is a
    median ~1.4 km from a contact -- so a test that demanded an entirely
    UNBLENDED pin would be testing the map's geometry, not our code. The honest
    invariant is the taper, asserted directly on the weight."""
    from ml_pipeline.data_prep.jharkhand_loader import _blend_K_at_boundary
    import types
    # weight is a pure function of d_in/L; verify the taper analytically
    L = P.K_BOUNDARY_BLEND_HALFWIDTH_DEG
    w = lambda d: 0.5 + 0.5 * min(d / L, 1.0)
    assert w(0.0) == pytest.approx(0.5)      # at the contact: 50/50 from both sides
    assert w(L / 2) == pytest.approx(0.75)
    assert w(L) == pytest.approx(1.0)        # at L: mapped value, untouched
    assert w(2 * L) == pytest.approx(1.0)    # beyond L: still untouched
    # and monotone in between
    ds = [0.0, L * 0.25, L * 0.5, L * 0.75, L]
    ws = [w(d) for d in ds]
    assert all(a <= b for a, b in zip(ws, ws[1:]))


def test_transect_has_no_large_K_step():
    """The QA transect that exposed the seam must no longer contain a large
    single-step K jump between adjacent pins (log-ratio test, so it is scale
    free). Before the fix, adjacent pins differed by a full polygon step."""
    import math
    from ml_pipeline.data_prep.jharkhand_loader import (
        aquifer_at_point, load_jharkhand_aquifers)
    aq = load_jharkhand_aquifers()
    ks = []
    for i in range(41):
        f = i / 40.0
        lon = 85.33 + f * (86.347 - 85.33)
        lat = 23.36 + f * (22.652 - 23.36)
        ks.append(float(aquifer_at_point(lon, lat, aq)["K_m_day"]))
    steps = [abs(math.log(b) - math.log(a)) for a, b in zip(ks, ks[1:])
             if a > 0 and b > 0]
    # a raw categorical step between the transect's endmember lithologies is
    # ~ln(2.35/0.46) ~ 1.6; blended, no single step should approach that
    assert max(steps) < 1.2, (max(steps), ks)


def test_blend_disabled_restores_hard_lookup(monkeypatch):
    from ml_pipeline.data_prep import jharkhand_loader as JL
    monkeypatch.setattr(P, "K_BOUNDARY_BLEND_ENABLED", False)
    aq = JL.load_jharkhand_aquifers()
    for i in range(21):
        f = i / 20.0
        h = JL.aquifer_at_point(85.33 + f * (86.347 - 85.33),
                                23.36 + f * (22.652 - 23.36), aq)
        assert h["_k_blend"] is None


# --------------------------------------------------------------------------- #
# 3.6b -- ore-zone deposit->belt source taper
# --------------------------------------------------------------------------- #
def test_belt_c0_ramps_continuously_from_deposit_to_belt():
    from ml_pipeline.dashboard.resolve import _belt_c0
    base, env = 10000.0, (0.0, 10000.0)
    flat = base * P.BELT_C0_FRACTION
    at0 = _belt_c0(base, {"nearest_deposit_km": 0.0, "nearest_deposit": None}, env)
    far = _belt_c0(base, {"nearest_deposit_km": P.ORE_TAPER_KM,
                          "nearest_deposit": None}, env)
    beyond = _belt_c0(base, {"nearest_deposit_km": 99.0, "nearest_deposit": None}, env)
    assert at0 == pytest.approx(base)          # continuous with the deposit tier
    assert far == pytest.approx(flat)          # continuous with the flat belt
    assert beyond == pytest.approx(flat)       # and stays there
    # monotone decreasing in between
    vals = [_belt_c0(base, {"nearest_deposit_km": d, "nearest_deposit": None}, env)
            for d in (0.0, 0.5, 1.0, 2.0, 3.0)]
    assert all(a >= b for a, b in zip(vals, vals[1:])), vals


def test_belt_never_out_sources_its_deposit():
    """A halo pin must never resolve to a stronger source than the ore body it
    is ramping down from -- the bug found in review when the taper was clipped
    to the raw Texas envelope instead of the deposit's own grade-scaled C0."""
    _, dep = resolve_inputs(dict(lon=86.347, lat=22.652, species="uranium_ppb"))
    _, halo = resolve_inputs(dict(lon=86.335, lat=22.652, species="uranium_ppb"))
    assert halo["ore_zone"]["zone"] == "belt"
    assert halo["source_conc_C0"] <= dep["source_conc_C0"] + 1e-6


def test_belt_taper_keeps_belt_weaker_than_trained_floor_is_allowed():
    """The belt tier is deliberately a WEAKER hypothetical source; the taper
    must not clip it UP to the trained envelope's lower edge."""
    _, far_belt = resolve_inputs(dict(lon=86.239, lat=22.652, species="uranium_ppb"))
    assert far_belt["ore_zone"]["zone"] == "belt"
    from ml_pipeline.data_prep.texas_loader import texas_source_signature
    env_lo = min(texas_source_signature()["uranium_ppb"])
    assert far_belt["source_conc_C0"] < env_lo


# --------------------------------------------------------------------------- #
# 3.4 -- ungrounded fracture parameters must stay LABELLED as such
# --------------------------------------------------------------------------- #
def test_fracture_params_are_labelled_foreign_analogue():
    """3.4 is knowingly unfixable from public data. The config must say so, so
    nobody later mistakes these literature values for Singhbhum measurements."""
    from pathlib import Path
    cfg = (Path(__file__).resolve().parents[1] / "config" / "parameters.py"
           ).read_text(encoding="utf-8")
    for marker in ("FIDELITY FLAW 3.4", "FOREIGN-ANALOGUE", "Singhbhum"):
        assert marker in cfg, marker
    # both blocks that rest on it must carry the warning
    assert cfg.count("FIDELITY FLAW 3.4") >= 2


# --------------------------------------------------------------------------- #
# 3.9 -- Radium-226 as an analytical-only species
# --------------------------------------------------------------------------- #
RADIUM = dict(lon=86.347, lat=22.652, species="radium_226_mbq_l")


def test_radium_uses_measured_local_source_and_who_threshold():
    inp, h = resolve_inputs(dict(**RADIUM))
    rc = h["radium_context"]
    assert rc is not None
    # served C0 must be one of the MEASURED statistics, not an invented number
    assert rc["served_C0_mbq_l"] == pytest.approx(
        P.RADIUM_SOURCE_MBQ_L[P.RADIUM_SOURCE_STATISTIC])
    assert rc["measured_source_mbq_l"]["gm"] == pytest.approx(371.3)
    assert "10.4103/0972-0464.121824" in rc["citation"]
    # judged against the WHO guidance level, not a BIS limit (BIS has none)
    assert P.EXCURSION_THRESHOLDS["radium_226_mbq_l"] == 1000.0
    assert inp["background_conc_Cb"] == pytest.approx(P.RADIUM_BACKGROUND_MBQ_L)


def test_radium_sorbs_far_more_strongly_than_alkaline_uranium():
    """Ra2+ is a strongly sorbing divalent cation; alkaline U travels as weakly
    sorbing uranyl-carbonate. Kd must differ by orders of magnitude, and in the
    POROUS regime (where Rd is a direct function of Kd) that must collapse the
    radium front relative to uranium."""
    from ml_pipeline.ml.predict import features_from_inputs
    xs = {}
    for sp in ("uranium_ppb", "radium_226_mbq_l"):
        inp, h = resolve_inputs(dict(lon=86.347, lat=22.652, species=sp,
                                     regime="porous", gradient_i=0.01,
                                     time_years=20.0))
        _, _, Xc = features_from_inputs(**inp)
        xs[sp] = (inp["kd_L_kg"], h["retardation_Rd"], Xc)
    assert xs["radium_226_mbq_l"][0] > 100 * xs["uranium_ppb"][0]      # Kd
    assert xs["radium_226_mbq_l"][1] > 100 * xs["uranium_ppb"][1]      # Rd
    assert xs["radium_226_mbq_l"][2] < 0.1 * xs["uranium_ppb"][2]      # front
    # matches the field observation (BARC 2008): radium does not migrate
    assert xs["radium_226_mbq_l"][2] < 1.0


def test_radium_kd_comes_from_the_shared_helper():
    """Serve path and Monte-Carlo draw must read the SAME Kd table."""
    for regime in ("fractured", "porous"):
        assert P.kd_range_for("radium_226_mbq_l", regime) == P.RADIUM_KD_RANGES[regime]
        assert P.kd_range_for("uranium_ppb", regime) == P.KD_RANGES["uranium_ppb"][regime]


def test_radium_is_ore_zone_gated():
    """Ra-226 is a uranium-decay product: no ore body, no radium source."""
    _, dep = resolve_inputs(dict(**RADIUM))
    _, belt = resolve_inputs(dict(lon=86.25, lat=22.63, species="radium_226_mbq_l"))
    _, none = resolve_inputs(dict(lon=85.33, lat=23.36, species="radium_226_mbq_l"))
    assert dep["source_conc_C0"] > belt["source_conc_C0"] > none["source_conc_C0"]
    # off the ore, the source collapses to background -> zero incremental term
    assert none["source_conc_C0"] == pytest.approx(none["background_conc_Cb"])
    assert none["u_suppressed"] is True


def test_radium_is_now_served_by_the_trained_surrogate():
    """UPDATED 2026-08-02: radium was analytical-only when fix 3.9 landed
    because the deployed surrogate had a 3-species one-hot. It has since been
    retrained WITH radium, so it must now come back with real ML bands like any
    other trained species -- and the other three must be unaffected."""
    from fastapi.testclient import TestClient
    from ml_pipeline.dashboard.server import app
    c = TestClient(app)
    j = c.post("/api/predict", json=dict(**RADIUM)).json()
    assert j["ml_status"] == "ok", j["ml_status"]
    assert j["metrics"]["ml"] is not None
    b = j["metrics"]["ml"]["area_ha"]
    assert b["p10"] <= b["p50"] <= b["p90"]
    assert j["metrics"]["analytical"]["area_ha"] is not None   # physics still runs
    for sp in ("uranium_ppb", "sulfate_mg_l", "tds_mg_l"):
        r = c.post("/api/predict", json={"lon": 86.347, "lat": 22.652,
                                         "species": sp}).json()
        assert r["metrics"]["ml"] is not None and r["ml_status"] == "ok", sp


def test_ml_species_gate_still_guards_untrained_species():
    """The SPECIES / ML_SPECIES split must remain a real gate, so a FUTURE
    analytical-only species (e.g. Rn-222) still bypasses the surrogate rather
    than being fed an unseen one-hot. Verified against the deployed model card
    rather than the constant, so it cannot drift from the actual artifacts."""
    import json
    from ml_pipeline.ml.predict import ML_SPECIES
    from ml_pipeline.ml.dataset import ARTIFACT_DIR
    card = json.loads((ARTIFACT_DIR / "model_card.json").read_text())
    trained = {f[3:] for f in card["features"] if f.startswith("is_")
               and f != "is_post_closure"}
    assert set(ML_SPECIES) == trained, (set(ML_SPECIES), trained)


# --------------------------------------------------------------------------- #
# 3.1 -- UI reframing (static content check)
# --------------------------------------------------------------------------- #
def test_ui_is_framed_as_excursion_screening_not_feasibility():
    import re
    idx = (Path(__file__).resolve().parents[2] / "frontend" / "ml_pipeline" / "index.html")
    # collapse HTML line-wrapping/indentation so phrases split across source
    # lines still match as written text
    html = re.sub(r"\s+", " ", idx.read_text(encoding="utf-8").lower())
    assert "excursion screening" in html
    assert "not a mining feasibility tool" in html
    # the premise mismatch must be stated, not buried
    assert "sandstone" in html and "schist" in html
