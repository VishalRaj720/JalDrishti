"""Polish pass: plume-river intersection (#1), per-deposit ore-depth (#2),
disc post-closure decay (#4). (#3 is a frontend-only SVG change.)"""
from __future__ import annotations

import pytest

from ml_pipeline.config import parameters as P


# --------------------------------------------------------------------------- #
# #1 -- precise plume x river crossing
# --------------------------------------------------------------------------- #
from ml_pipeline.data_prep.rivers import plume_river_discharge, RIVER_NPZ

pytestmark_rivers = pytest.mark.skipif(not RIVER_NPZ.exists(), reason="river field not built")


@pytest.mark.skipif(not RIVER_NPZ.exists(), reason="river field not built")
def test_plume_crossing_river_is_detected():
    # a polygon spanning the Subarnarekha reach at Jamshedpur must register a crossing
    ring = [[86.15, 22.75], [86.30, 22.75], [86.30, 22.85], [86.15, 22.85], [86.15, 22.75]]
    d = plume_river_discharge([ring])
    assert d is not None and d["intersects"] and d["max_discharge_cms"] > 10.0


def test_plume_river_guards_are_safe():
    assert plume_river_discharge([]) is None                 # no rings
    assert plume_river_discharge([[[86.2, 22.8]]]) is None   # degenerate ring (<4 pts)


@pytest.mark.skipif(not RIVER_NPZ.exists(), reason="river field not built")
def test_plume_river_heals_invalid_ring():
    # a self-intersecting bow-tie ring must not crash (buffer(0) heals it)
    bowtie = [[86.15, 22.75], [86.30, 22.85], [86.30, 22.75], [86.15, 22.85], [86.15, 22.75]]
    plume_river_discharge([bowtie])   # just: no exception


# --------------------------------------------------------------------------- #
# #2 -- per-deposit ore-depth defaults
# --------------------------------------------------------------------------- #
from ml_pipeline.data_prep.ore_loader import deposit_ore_depth


def test_deposit_ore_depth_by_mining_type():
    assert deposit_ore_depth("Banduhurang") == 60.0     # open-pit -> shallow
    assert deposit_ore_depth("Mohuldih") == 250.0       # documented ~250 m
    assert deposit_ore_depth("Jaduguda") == 180.0
    assert deposit_ore_depth("Not A Deposit") is None
    assert deposit_ore_depth(None) is None


def test_pin_info_suggests_ore_depth_on_deposit_only():
    from ml_pipeline.dashboard.resolve import pin_info
    assert pin_info(86.347, 22.652)["ore_depth_suggestion_m"] == 180.0     # Jaduguda
    assert pin_info(85.33, 23.36)["ore_depth_suggestion_m"] is None        # Ranchi (none)


# --------------------------------------------------------------------------- #
# #4 -- leach-zone disc post-closure decay
# --------------------------------------------------------------------------- #
from ml_pipeline.physics.transport import disc_flush_factor


def test_disc_flush_full_during_operations():
    assert disc_flush_factor(5 * 365, 8 * 365) == pytest.approx(1.0)   # t < t_op
    assert disc_flush_factor(8 * 365, 8 * 365) == pytest.approx(1.0)   # t == t_op


def test_disc_flush_halves_at_one_halflife_post_closure():
    H = P.DISC_FLUSH_HALFLIFE_YEARS
    assert disc_flush_factor((8 + H) * 365, 8 * 365) == pytest.approx(0.5, abs=1e-6)
    assert disc_flush_factor((8 + 2 * H) * 365, 8 * 365) == pytest.approx(0.25, abs=1e-6)


def test_disc_flush_monotone_and_disableable():
    f10 = disc_flush_factor(18 * 365, 8 * 365)
    f20 = disc_flush_factor(28 * 365, 8 * 365)
    assert 0.0 < f20 < f10 < 1.0                                    # later -> more decayed
    assert disc_flush_factor(48 * 365, 8 * 365, halflife_years=0.0) == 1.0   # disabled
