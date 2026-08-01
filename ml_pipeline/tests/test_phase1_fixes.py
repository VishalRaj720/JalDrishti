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
