"""
Timeline animation (3.7b) -- calendar anchoring of the ISR lifecycle.

The timeline is a PRESENTATION layer over physics that already existed: it maps
`time_years` onto a calendar, names the lifecycle phase, and picks the month
whose water table drives the seasonal vertical state. What is locked down here:

  * phase labels can never disagree with the physics phase boundaries
    (front_position uses exactly op / op+rest);
  * the monthly water-table curve reproduces the four CGWB campaign anchors
    exactly and peaks/troughs in the right months -- it interpolates measured
    data, it does not invent a shape;
  * the timeline never widens the seasonal band: "now" must sit INSIDE the
    wet/dry bracket the band already reports;
  * a bad or absent start date degrades to un-dated behaviour instead of 500ing.
"""
import datetime as dt

import pytest

from ml_pipeline.config import parameters as P
from ml_pipeline.dashboard.server import _timeline
from ml_pipeline.physics.transport import shallow_impact_screening


# --------------------------------------------------------------------------- #
# monthly water-table shape
# --------------------------------------------------------------------------- #
def test_shape_reproduces_the_cgwb_campaign_anchors_exactly():
    """The four campaigns are the only direct evidence; interpolation must pass
    through them, not near them."""
    lo = min(P.WATER_TABLE_CAMPAIGNS_M.values())
    hi = max(P.WATER_TABLE_CAMPAIGNS_M.values())
    for month, depth in P.WATER_TABLE_CAMPAIGNS_M.items():
        assert P.water_table_at_month(month, lo, hi) == pytest.approx(depth, abs=1e-9)


def test_table_is_shallowest_in_august_and_deepest_in_may():
    depths = {m: P.water_table_shape(m) for m in range(1, 13)}
    assert min(depths, key=depths.get) == 8      # monsoon peak
    assert max(depths, key=depths.get) == 5      # pre-monsoon trough
    assert P.water_table_shape(8) == 0.0
    assert P.water_table_shape(5) == 1.0


def test_recovery_is_faster_than_recession():
    """Real monsoon asymmetry: the table recovers May->Aug in 3 months but takes
    9 to fall back. A symmetric curve would be wrong in both directions."""
    rise = (P.water_table_shape(5) - P.water_table_shape(8)) / 3.0     # per month
    fall = (P.water_table_shape(5) - P.water_table_shape(8)) / 9.0
    assert rise > fall * 2.5


def test_shape_is_cyclic_and_bounded():
    for m in range(1, 13):
        assert 0.0 <= P.water_table_shape(m) <= 1.0
        assert P.water_table_shape(m) == pytest.approx(P.water_table_shape(m + 12))
    # December must interpolate across the Nov -> Jan wrap, not clamp to an end
    assert P.water_table_shape(11) < P.water_table_shape(12) < P.water_table_shape(1)


def test_amplitude_comes_from_the_pin_not_the_state():
    """State supplies TIMING, the pin supplies AMPLITUDE (see P.water_table_shape)."""
    for m in (1, 3, 6, 8, 11):
        v = P.water_table_at_month(m, 1.62, 6.34)          # Jaduguda pair
        assert 1.62 - 1e-9 <= v <= 6.34 + 1e-9
    assert P.water_table_at_month(8, 1.62, 6.34) == pytest.approx(1.62)
    assert P.water_table_at_month(5, 1.62, 6.34) == pytest.approx(6.34)


# --------------------------------------------------------------------------- #
# lifecycle phases
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("t,expected", [
    (0.0, "operation"), (4.0, "operation"), (8.0, "operation"),
    (8.5, "restoration"), (13.0, "restoration"),
    (13.5, "drift"), (40.0, "drift"),
])
def test_phase_boundaries_match_the_physics(t, expected):
    """front_position switches at op and op+rest; the label must switch there too
    or the animation would narrate a phase the solver is not in."""
    tl = _timeline("2026-01-01", t, 8.0, 5.0)
    assert tl["phase"] == expected


def test_zero_restoration_goes_straight_to_drift():
    assert _timeline("2026-01-01", 8.0, 8.0, 0.0)["phase"] == "operation"
    assert _timeline("2026-01-01", 8.5, 8.0, 0.0)["phase"] == "drift"


def test_dates_advance_and_carry_the_season():
    # mid-month on purpose: 0.42 yr lands on 1 Aug and flips month on rounding
    tl = _timeline("2026-03-01", 0.375, 8.0, 5.0)
    assert tl["current_date"].startswith("2026-07")       # ~4.5 months on
    assert tl["season"] == P.SEASON_LABELS[7] == "monsoon"
    assert tl["month"] == 7
    late = _timeline("2026-03-01", 9.0, 8.0, 5.0)
    assert late["current_date"].startswith("2035-0")
    assert dt.date.fromisoformat(late["current_date"]) > dt.date.fromisoformat(
        tl["current_date"])


def test_monthly_steps_visit_every_month_exactly_once():
    """Regression: date + timedelta DROPS the sub-day remainder, so a monthly
    animation step kept landing one day short of the 1st. The animation repeated
    Jan/Aug/Oct and never showed Feb/Sep/Nov until the day count was rounded."""
    months = [_timeline("2026-01-01", 2 + m / 12, 8.0, 5.0)["month"]
              for m in range(12)]
    assert sorted(months) == list(range(1, 13)), f"skipped/repeated months: {months}"


def test_phase_end_dates_are_ordered():
    tl = _timeline("2026-01-01", 1.0, 8.0, 5.0)
    d = dt.date.fromisoformat
    assert d(tl["start_date"]) < d(tl["operation_ends"]) < d(tl["restoration_ends"])


def test_the_run_is_always_labelled_hypothetical():
    """No ISR has ever operated in Jharkhand. A dated map must never read as a
    historical record -- this flag is what the UI banner keys off."""
    tl = _timeline("2026-01-01", 5.0, 8.0, 5.0)
    assert tl["hypothetical"] is True
    assert "has ever existed" in tl["disclaimer"]
    assert "not a historical record" in tl["disclaimer"]
    assert "climatology" in tl["disclaimer"]


@pytest.mark.parametrize("bad", [None, "", "not-a-date", "2026-13-01", "01/01/2026"])
def test_bad_or_missing_start_date_degrades_quietly(bad):
    assert _timeline(bad, 5.0, 8.0, 5.0) is None


# --------------------------------------------------------------------------- #
# the timeline must not widen the seasonal band it rides on
# --------------------------------------------------------------------------- #
def _screen(**over):
    kw = dict(C0=8000.0, background=5.0, threshold=30.0, Xc_m=200.0,
              source_width_m=300.0, alpha_L=10.0, alpha_V=0.05,
              ore_depth_m=150.0, ore_thickness_m=20.0, layer1_base_m=30.0,
              K_m_day=0.4, phi_confining=0.02, Kv_Kh_ratio=0.1,
              upward_gradient=P.VERTICAL["upward_gradient"], t_days=3650.0,
              wellbore_failure_prob=0.05,
              water_table_wet_m=1.62, water_table_dry_m=6.34)
    kw.update(over)
    return shallow_impact_screening(**kw)


@pytest.mark.parametrize("month", list(range(1, 13)))
def test_current_month_state_stays_inside_the_seasonal_band(month):
    """'now' is a point ON the band, never outside it -- otherwise the animation
    would show a risk the band claims is impossible."""
    now = P.water_table_at_month(month, 1.62, 6.34)
    s = _screen(water_table_now_m=now)["seasonal"]
    g_wet = s["static_deep_head"]["wet_season"]["gradient"]
    g_dry = s["static_deep_head"]["dry_season"]["gradient"]
    g_now = s["now"]["static_deep_head"]["gradient"]
    assert g_wet - 1e-9 <= g_now <= g_dry + 1e-9
    assert s["water_table_now_m"] == pytest.approx(round(now, 2))


def test_august_and_may_reproduce_the_band_endpoints():
    aug = _screen(water_table_now_m=P.water_table_at_month(8, 1.62, 6.34))["seasonal"]
    may = _screen(water_table_now_m=P.water_table_at_month(5, 1.62, 6.34))["seasonal"]
    assert (aug["now"]["static_deep_head"]["gradient"]
            == pytest.approx(aug["static_deep_head"]["wet_season"]["gradient"]))
    assert (may["now"]["static_deep_head"]["gradient"]
            == pytest.approx(may["static_deep_head"]["dry_season"]["gradient"]))


def test_no_now_block_without_a_timeline():
    """Un-dated runs keep exactly their old shape."""
    s = _screen()["seasonal"]
    assert "now" not in s and "water_table_now_m" not in s
