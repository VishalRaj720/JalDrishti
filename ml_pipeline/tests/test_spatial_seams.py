"""
Spatial-seam continuity (remediation 2026-08-05, review.md findings #5 and #6).
==============================================================================
Fidelity row 3.6 claimed "K is provably continuous across every boundary". It was
not, in two places the audit measured, and BOTH were second categorical maps
layered on top of the aquifer polygons that 3.6 had smoothed:

  #5  the per-district NAQUIM fracture-death depth that fix 3.3 uses to calibrate
      the K(z) decay length -- K stepped 1.74x over ~130 m at a district line,
      inside ONE aquifer polygon and ONE lithology;
  #6  the D5 shear-zone override, toggled on ore-zone membership -- K 2.2x and
      thickness 4x in a single step, at a line that is not even mapped geology
      since 61b1260 (the belt is the CSV arc unioned with the deposits' convex
      hull and a taper buffer).

Run:  python -m pytest ml_pipeline/tests/test_spatial_seams.py -q
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from ml_pipeline.config import parameters as P
from ml_pipeline.dashboard.resolve import resolve_inputs
from ml_pipeline.data_prep.naquim_vertical import fracture_base_at

# the exact pair of pins the audit measured the district step between
SEAM_A = (86.1721, 22.7738)
SEAM_B = (86.1731, 22.7731)


def _K(lon, lat, species="sulfate_mg_l"):
    return resolve_inputs({"lon": lon, "lat": lat, "species": species})[0]["K_m_day"]


def test_district_fracture_base_is_continuous_across_borders():
    """The blended fracture-death depth must not step at a district line."""
    prev = None
    worst = 0.0
    for km in np.arange(-1.0, 1.0, 0.05):          # 2 km window, 50 m samples
        fb = fracture_base_at(86.1725, 22.7738 + km / 111.0)["fracture_base_m"]
        if prev is not None:
            worst = max(worst, abs(fb - prev))
        prev = fb
    # 50 m of travel may not move a ~200 m depth by more than a couple of metres
    assert worst < 3.0, f"fracture_base steps {worst:.1f} m across 50 m"


def test_k_is_continuous_at_the_district_seam_the_audit_measured():
    """review.md finding #5, at its own coordinates: K stepped 1.74x."""
    ka, kb = _K(*SEAM_A), _K(*SEAM_B)
    ratio = max(ka, kb) / min(ka, kb)
    assert ratio < 1.10, f"district seam still steps {ratio:.2f}x ({ka} -> {kb})"


def test_k_has_no_step_along_a_fine_transect_through_that_seam():
    """Continuity is a property of the FIELD, not of two lucky sample points."""
    prev = None
    worst = 0.0
    for km in np.arange(-1.0, 1.0, 0.05):
        k = _K(86.1725, 22.7738 + km / 111.0)
        if prev is not None:
            worst = max(worst, abs(math.log(k / prev)))
        prev = k
    assert math.exp(worst) < 1.10, f"max step {math.exp(worst):.3f}x over 50 m"


def test_shear_zone_override_tapers_instead_of_toggling():
    """review.md finding #6. Walking out of Jaduguda, K and thickness must ramp
    down to the polygon values rather than flipping at the belt outline."""
    lon0, lat0 = 86.347, 22.652
    prev_k = prev_b = None
    worst_k = worst_b = 0.0
    for km in np.arange(0.0, 6.0, 0.05):
        inp, h = resolve_inputs({"lon": lon0, "lat": lat0 + km / 111.0,
                                 "species": "sulfate_mg_l"})
        k, b = inp["K_m_day"], inp["thickness_m"]
        if prev_k is not None:
            worst_k = max(worst_k, abs(math.log(k / prev_k)))
            worst_b = max(worst_b, abs(b - prev_b))
        prev_k, prev_b = k, b
    assert math.exp(worst_k) < 1.35, f"K still steps {math.exp(worst_k):.2f}x"
    assert worst_b < 20.0, f"thickness still steps {worst_b:.0f} m in 50 m"


def test_shear_zone_reaches_full_strength_on_the_deposit():
    """The taper must not weaken the correction where it is actually evidenced --
    NAQUIM measured T = 207-570 m2/day on the ore belt itself."""
    _, h = resolve_inputs({"lon": 86.347, "lat": 22.652, "species": "sulfate_mg_l"})
    sz = h["shear_zone"]
    assert sz is not None and sz["taper_weight"] == pytest.approx(1.0)
    assert sz["K_m_day"] == pytest.approx(          # reported rounded to 3 dp
        P.SHEAR_ZONE_T_M2DAY / P.SHEAR_ZONE_THICKNESS_M, abs=5e-4)
    assert sz["thickness_m"] == pytest.approx(P.SHEAR_ZONE_THICKNESS_M)


def test_belt_edge_plume_area_no_longer_jumps():
    """The user-visible consequence: nudging the pin across the belt outline used
    to move the sulfate plume 13.8 -> 19.0 ha (+37%) in 100 m. Sulfate is not
    ore-gated, so this isolates the HYDRAULIC step from the source-term step."""
    from ml_pipeline.ml.predict import predict_analytical
    lon0, lat0 = 86.347, 22.652
    prev = None
    worst = 0.0
    for km in np.arange(4.0, 5.4, 0.1):
        inp, _ = resolve_inputs({"lon": lon0, "lat": lat0 + km / 111.0,
                                 "species": "sulfate_mg_l"})
        a = predict_analytical(**inp)["area_ha"]["p50"]
        if prev is not None and prev > 0:
            worst = max(worst, abs(a - prev) / prev)
        prev = a
    assert worst < 0.10, f"belt-edge area still steps {worst * 100:.0f}%"
