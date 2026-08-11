"""Regression tests for the three rendering/reporting bugs found 2026-08-11.

All three were reported from the live dashboard:
  A  the plume outline showed a hard-edged "rectangular front" welded to a circle
  B  the ML envelope rings appeared and disappeared unpredictably
  C  radium's affected area collapsed 13.78 ha -> 0.00 ha in one month

None of them touched the frozen physics; all three were display/reporting
defects, and these tests pin the fixes.
"""
from __future__ import annotations

import math
import pytest
from fastapi.testclient import TestClient

from ml_pipeline.config import parameters as P
from ml_pipeline.dashboard.server import app
from ml_pipeline.dashboard.plume_geometry import (ml_envelope_ellipses,
                                                  source_zone_polygon,
                                                  MIN_RENDERABLE_EXTENT_M)

client = TestClient(app)

# the exact operating point the bugs were reported at
BASE = dict(lon=86.347, lat=22.652, injection_rate_m3_day=8000.0,
            bleed_percent=2.0, gradient_i=0.0021, time_years=20.0)


def _predict(**over):
    r = client.post("/api/predict", json={**BASE, **over})
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# A — the source zone is its own object, not welded into the plume contour
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("op", [1.0, 10.0, 20.0])
def test_a_source_zone_is_returned_as_its_own_polygon(op):
    j = _predict(species="tds_mg_l", operation_years=op)
    sz = j["plume"]["source_zone"]
    assert sz["polygon"], "the leach disc must be drawable independently"
    assert len(sz["polygon"]) > 8
    assert sz["area_ha"] > 0


def test_a_contours_exclude_the_disc_so_no_welded_polygon():
    """With the disc unioned in, the BIS contour enclosed the whole disc. The
    plume-only contour must NOT: at op=20 the front travels 0.2 m, so there is
    nothing above threshold and the contour list is empty — the disc alone
    carries the footprint."""
    j = _predict(species="tds_mg_l", operation_years=20.0)
    assert j["plume"]["contours"] == [], (
        "at op=t the plume has not moved; any contour here is the disc being "
        "contoured again")
    assert j["plume"]["source_zone"]["polygon"], "…but the disc must still render"
    # and the reported area is unchanged by the display change
    assert j["metrics"]["analytical"]["area_ha"] > 0


def test_a_metrics_are_untouched_by_the_display_change():
    """The contour swap must not move a single reported number."""
    j = _predict(species="tds_mg_l", operation_years=1.0)
    m = j["metrics"]["analytical"]
    assert m["area_ha"] == pytest.approx(13.33, abs=0.5)
    assert m["migration_m"] == pytest.approx(170.1, abs=2.0)


# --------------------------------------------------------------------------- #
# B — the ML envelope is a DOWN-GRADIENT lobe, never an up-gradient ring
# --------------------------------------------------------------------------- #
def test_b_envelope_never_extends_upgradient():
    """The old ellipse was CENTRED on the source plane, so a P90 of ~1 km put
    the ring ~870 m upstream — contamination drawn in the one direction the
    model says has none."""
    out = ml_envelope_ellipses(86.347, 22.652, azimuth_deg=0.0,
                               migration_bands={"p90": 1000.0},
                               aspect_ratio=1.0, x_offset_m=150.0,
                               halfwidth_m=160.0)
    ring = out["rings"]["p90"]
    lats = [pt[1] for pt in ring]
    # azimuth 0 => +x is due north, so up-gradient is SOUTH of the pin
    assert min(lats) >= 22.652 - 1e-6, (
        "no part of the envelope may sit up-gradient of the pin")


def test_b_envelope_spans_source_plane_to_migration_distance():
    out = ml_envelope_ellipses(86.347, 22.652, azimuth_deg=0.0,
                               migration_bands={"p50": 400.0},
                               aspect_ratio=1.0, x_offset_m=100.0,
                               halfwidth_m=50.0)
    lats = [pt[1] for pt in out["rings"]["p50"]]
    m_per_deg = 111_320.0
    near = (min(lats) - 22.652) * m_per_deg
    far = (max(lats) - 22.652) * m_per_deg
    assert near == pytest.approx(100.0, abs=2.0), "lobe starts at the source plane"
    assert far == pytest.approx(500.0, abs=2.0), "…and reaches x_offset + migration"


def test_b_undrawable_bands_are_reported_not_silently_dropped():
    out = ml_envelope_ellipses(86.347, 22.652, azimuth_deg=0.0,
                               migration_bands={"p10": 0.0, "p50": 0.5,
                                                "p90": 50.0},
                               aspect_ratio=1.0, x_offset_m=150.0,
                               halfwidth_m=20.0)
    assert set(out["rings"]) == {"p90"}
    assert set(out["skipped"]) == {"p10", "p50"}
    for reason in out["skipped"].values():
        assert "minimum drawable extent" in reason


def test_b_aspect_below_one_is_not_clamped_to_a_circle():
    """max(aspect, 1.0) turned every wide-and-short plume into a circle — which
    is the normal radial-dominated case (aspect 0.21 at op=20)."""
    out = ml_envelope_ellipses(86.347, 22.652, azimuth_deg=0.0,
                               migration_bands={"p50": 100.0},
                               aspect_ratio=0.2, x_offset_m=0.0,
                               halfwidth_m=250.0)
    ring = out["rings"]["p50"]
    m_per_deg = 111_320.0
    half_len = (max(p[1] for p in ring) - min(p[1] for p in ring)) / 2 * m_per_deg
    half_wid = (max(p[0] for p in ring) - min(p[0] for p in ring)) / 2 * \
        m_per_deg * math.cos(math.radians(22.652))
    assert half_wid > half_len, (
        "a plume wider than it is long must render wider than it is long")


def test_b_server_reports_skipped_envelope_bands():
    j = _predict(species="tds_mg_l", operation_years=20.0)
    assert "ml_envelope_skipped" in j
    if j.get("metrics", {}).get("ml"):
        assert set(j["ml_envelope_skipped"]) >= {"p10"}


# --------------------------------------------------------------------------- #
# C — the uniform-disc threshold step is REPORTED, with its date
# --------------------------------------------------------------------------- #
def test_c_radium_area_step_is_reproduced_and_dated():
    """13.78 ha -> 0.00 ha between 44 y 1 mo and 44 y 2 mo, exactly as reported."""
    before = _predict(species="radium_226_mbq_l", operation_years=20.0,
                      time_years=44.0 + 1 / 12)
    after = _predict(species="radium_226_mbq_l", operation_years=20.0,
                     time_years=44.0 + 2 / 12)
    assert before["metrics"]["analytical"]["area_ha"] > 13.0
    assert after["metrics"]["analytical"]["area_ha"] == 0.0
    assert before["plume"]["source_zone"]["above_threshold"] is True
    assert after["plume"]["source_zone"]["above_threshold"] is False


def test_c_crossing_time_is_reported_before_and_after_the_step():
    """The step must be explained on BOTH sides — a user approaching it needs the
    warning, and a user past it needs the reason the area is zero."""
    for t in (30.0, 44.0 + 1 / 12, 44.0 + 2 / 12):
        j = _predict(species="radium_226_mbq_l", operation_years=20.0,
                     time_years=t, start_date="2026-01-01")
        cr = j["plume"]["source_zone"]["crossing"]
        assert cr["crosses"] is True
        assert cr["crossing_years"] == pytest.approx(44.126, abs=0.02)
        assert cr["crossing_date"].startswith("2070-02")


def test_c_crossing_matches_the_closed_form():
    """disc = C0 * 0.5^((t-op)/H) = thr_inc  =>  t = op + H*log2(C0/thr_inc)."""
    j = _predict(species="radium_226_mbq_l", operation_years=20.0, time_years=30.0)
    sz = j["plume"]["source_zone"]
    C0 = P.RADIUM_SOURCE_MBQ_L["max"]
    thr_inc = sz["threshold"]
    expected = 20.0 + P.DISC_FLUSH_HALFLIFE_YEARS * math.log2(C0 / thr_inc)
    assert sz["crossing"]["crossing_years"] == pytest.approx(expected, abs=0.05)


def test_c_rebound_floor_prevents_any_crossing_after_a_sweep():
    """With a restoration sweep the source is held at the measured stable
    endpoint, so the flush can never carry it under the threshold."""
    j = _predict(species="radium_226_mbq_l", operation_years=20.0,
                 restoration_years=5.0, time_years=44.0 + 2 / 12)
    cr = j["plume"]["source_zone"]["crossing"]
    assert cr["crosses"] is False
    assert "stable endpoint" in (cr["reason"] or "")
    assert j["metrics"]["analytical"]["area_ha"] > 0


def test_c_species_with_a_travelling_plume_survive_the_disc_dropout():
    """Radium collapses to exactly zero only because it does not migrate; a
    species with a plume keeps area after the disc leaves."""
    j = _predict(species="tds_mg_l", operation_years=1.0, time_years=20.0)
    assert j["metrics"]["analytical"]["migration_m"] > 1.0
    assert j["metrics"]["analytical"]["area_ha"] > 0


# --------------------------------------------------------------------------- #
# Contour colour scale — the frontend ramp depends on these server invariants
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("species", list(P.SPECIES))
def test_contour_levels_are_strictly_ascending(species):
    """The colour ramp maps level -> darkness by position in this list, so the
    ordering IS the scale. If levels ever came back unsorted the map would show
    a darker band at a lower concentration."""
    j = _predict(species=species)
    levels = [c["level"] for c in j["plume"]["contours"]]
    assert levels == sorted(levels), f"{species} contour levels must ascend"
    assert len(set(levels)) == len(levels), "duplicate levels collapse the ramp"


def test_bis_contour_is_the_lowest_level_when_present():
    """This is why the old code was inverted: it painted the BIS contour the most
    saturated red, and the BIS contour is always the LOWEST level."""
    for species in ("uranium_ppb", "sulfate_mg_l", "tds_mg_l"):
        cs = _predict(species=species)["plume"]["contours"]
        bis = [i for i, c in enumerate(cs) if c["is_bis"]]
        if bis:
            assert bis == [0], (
                f"{species}: BIS is not the lowest level — the ramp's assumption "
                f"that index 0 is the lightest no longer holds")


def test_every_species_gets_at_least_one_level_to_colour():
    for species in P.SPECIES:
        cs = _predict(species=species)["plume"]["contours"]
        assert all(c["level"] > 0 for c in cs), "log-scaled ramp needs level > 0"


def test_c_source_zone_reports_its_margin_over_the_threshold():
    j = _predict(species="radium_226_mbq_l", operation_years=20.0, time_years=30.0)
    sz = j["plume"]["source_zone"]
    # both sides are rounded for transport (conc to 2dp, ratio to 4dp), so the
    # comparison tolerance has to admit that rounding rather than fight it
    assert sz["conc_over_threshold"] == pytest.approx(sz["conc"] / sz["threshold"],
                                                      abs=1e-3)
    assert sz["conc_over_threshold"] > 1.0, "above threshold at t=30"
