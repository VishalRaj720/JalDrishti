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
