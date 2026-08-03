"""
Fidelity fix 3.7 -- seasonal (monsoon) modulation of the VERTICAL pathway.

What is being locked down here:
  * the monsoon raises the shallow head that presses on the confining zone, so
    the WET season must SUPPRESS the upward gradient and the DRY season must
    ENHANCE it (this is the whole physical claim of 3.7);
  * the result is a TWO-END-MEMBER BAND, never a single number, because the deep
    head's seasonal response is unmeasured in Singhbhum;
  * the IN-PHASE end member must reproduce today's behaviour exactly -- it is
    the "no seasonal effect" bound, so if it ever drifts the band is lying;
  * none of this touches the trained surrogate (requirement: no ML retrain).
"""
import json
from pathlib import Path

import pytest

from ml_pipeline.config import parameters as P
from ml_pipeline.physics.transport import shallow_impact_screening

ART = Path(__file__).resolve().parents[1] / "ml" / "artifacts"


def _screen(**over):
    kw = dict(C0=8000.0, background=5.0, threshold=30.0, Xc_m=200.0,
              source_width_m=300.0, alpha_L=10.0, alpha_V=0.05,
              ore_depth_m=150.0, ore_thickness_m=20.0, layer1_base_m=30.0,
              K_m_day=0.4, phi_confining=0.02, Kv_Kh_ratio=0.1,
              upward_gradient=P.VERTICAL["upward_gradient"], t_days=3650.0,
              wellbore_failure_prob=0.05)
    kw.update(over)
    return shallow_impact_screening(**kw)


def test_seasonal_band_is_present_and_complete():
    s = _screen()["seasonal"]
    assert s is not None
    for k in ("water_table_wet_m", "water_table_dry_m", "seasonal_swing_m",
              "gradient_swing", "static_deep_head", "in_phase_deep_head",
              "breakthrough_years_range", "risk_band_range", "deep_head_caveat"):
        assert k in s, f"seasonal band missing {k}"
    # the dry-season table is the DEEPER one, by definition
    assert s["water_table_dry_m"] > s["water_table_wet_m"]
    assert s["seasonal_swing_m"] == pytest.approx(
        s["water_table_dry_m"] - s["water_table_wet_m"], abs=1e-6)


def test_wet_suppresses_and_dry_enhances_the_upward_gradient():
    """The core physical claim of 3.7. A high (wet) table presses DOWN and closes
    the upward pathway; a low (dry) table lets it open."""
    s = _screen()["seasonal"]
    wet = s["static_deep_head"]["wet_season"]
    dry = s["static_deep_head"]["dry_season"]
    base = s["baseline_gradient"]
    assert wet["gradient"] < base < dry["gradient"], (
        f"expected wet < {base} < dry, got {wet['gradient']} / {dry['gradient']}")
    # a suppressed pathway can never move faster than an enhanced one
    assert wet["v_up_m_day"] <= dry["v_up_m_day"]
    assert wet["p_advective"] <= dry["p_advective"]


def test_negative_gradient_closes_the_pathway_and_never_inverts_it():
    """A net DOWNWARD gradient means no upward leakage -- not negative risk."""
    s = _screen(water_table_wet_m=0.5, water_table_dry_m=40.0)["seasonal"]
    wet = s["static_deep_head"]["wet_season"]
    assert wet["gradient"] < 0.0                 # the raw gradient may go negative
    assert wet["v_up_m_day"] == 0.0              # but velocity is floored at zero
    assert wet["p_advective"] == 0.0
    assert wet["years_to_breakthrough"] is None  # never breaks through


def test_in_phase_end_member_reproduces_todays_behaviour_exactly():
    """The lower bound MUST equal the un-seasonal result, or the band is lying
    about what 'no seasonal effect' means."""
    r = _screen()
    base = r["seasonal"]["in_phase_deep_head"]
    for season in ("wet_season", "dry_season"):
        d = base[season]
        assert d["gradient"] == pytest.approx(r["seasonal"]["baseline_gradient"])
        assert d["shallow_impact_probability"] == pytest.approx(
            r["shallow_impact_probability"], abs=1e-9)
        assert d["risk_band"] == r["risk_band"]
        assert d["years_to_breakthrough"] == pytest.approx(
            r["years_to_vertical_breakthrough"])


def test_breakthrough_range_is_ordered_and_brackets_the_baseline():
    s = _screen()["seasonal"]
    lo, hi = s["breakthrough_years_range"]
    assert lo <= hi
    # the baseline (in-phase) case must lie inside the reported interval
    base_yr = s["in_phase_deep_head"]["wet_season"]["years_to_breakthrough"]
    assert lo <= base_yr <= hi


def test_sensitivity_is_not_judged_on_the_band_label_alone():
    """Jaduguda stays 'contained' in both seasons while breakthrough moves ~5x
    (11.5 -> 56.8 yr). A band-only test would call that insensitive and hide the
    single most decision-relevant fact about the pin."""
    s = _screen(water_table_wet_m=1.62, water_table_dry_m=6.34)["seasonal"]
    lo, hi = s["breakthrough_years_range"]
    assert hi > 1.5 * lo                       # arrival time materially different
    assert s["seasonally_sensitive"] is True   # ...so it must be flagged
    # and a genuinely flat pin must NOT be flagged
    flat = _screen(water_table_wet_m=4.0, water_table_dry_m=4.02)["seasonal"]
    assert flat["seasonally_sensitive"] is False


def test_per_pin_tables_override_the_state_median():
    default = _screen()["seasonal"]
    pin = _screen(water_table_wet_m=1.62, water_table_dry_m=6.34)["seasonal"]
    assert default["water_table_source"] == "state_median"
    assert pin["water_table_source"] == "pin"
    assert pin["water_table_wet_m"] == 1.62 and pin["water_table_dry_m"] == 6.34
    # a bigger swing must produce a bigger gradient excursion
    assert pin["gradient_swing"] > default["gradient_swing"]


def test_swapped_wet_dry_inputs_are_corrected_not_trusted():
    """Callers must not be able to invert the physics by passing the pair
    backwards -- the deeper table is the dry season by definition."""
    a = _screen(water_table_wet_m=3.0, water_table_dry_m=8.0)["seasonal"]
    b = _screen(water_table_wet_m=8.0, water_table_dry_m=3.0)["seasonal"]
    assert a["water_table_wet_m"] == b["water_table_wet_m"] == 3.0
    assert a["water_table_dry_m"] == b["water_table_dry_m"] == 8.0


def test_baseline_metrics_are_untouched_by_the_seasonal_addition():
    """3.7 is additive: every pre-existing vertical key keeps its old meaning."""
    r = _screen()
    for k in ("separation_m", "layer1_base_m", "shallow_impact_probability",
              "risk_band", "pathways", "dominant_pathway",
              "advective_breakthrough_fraction", "years_to_vertical_breakthrough"):
        assert k in r
    assert r["pathways"]["advective_leakage"] == pytest.approx(
        r["seasonal"]["in_phase_deep_head"]["wet_season"]["p_advective"])


def test_flow_field_surfaces_the_seasonal_pair():
    from ml_pipeline.data_prep.flow_field import flow_at
    f = flow_at(86.3564, 22.6547)                      # Jaduguda
    for k in ("depth_to_water_shallow_m", "depth_to_water_deep_m",
              "water_table_seasonal_swing_m"):
        assert k in f
    if f["depth_to_water_deep_m"] is not None:
        assert f["depth_to_water_deep_m"] >= f["depth_to_water_shallow_m"]
        assert f["water_table_seasonal_swing_m"] == pytest.approx(
            f["depth_to_water_deep_m"] - f["depth_to_water_shallow_m"], abs=0.02)


@pytest.mark.skipif(not (ART / "model_card.json").exists(),
                    reason="model card not built")
def test_3_7_did_not_touch_the_trained_surrogate():
    """Requirement: no ML retrain. The seasonal work lives entirely in the
    downstream analytical vertical module, so the deployed feature set must be
    byte-identical to the 4-species / 40-feature card trained before 3.7."""
    from ml_pipeline.ml.dataset import MODEL_FEATURES
    card = json.loads((ART / "model_card.json").read_text())
    feats = card.get("features") or card.get("model_features")
    assert len(feats) == len(MODEL_FEATURES) == 40
    assert list(feats) == list(MODEL_FEATURES)
    seasonal_leak = [f for f in feats if "water_table" in f or "seasonal_vert" in f]
    assert not seasonal_leak, f"3.7 leaked into the trained features: {seasonal_leak}"
