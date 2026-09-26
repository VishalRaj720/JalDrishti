"""Grounding pass 2026-09-26 (LIMITATIONS.md 1k).

Pins four things the pass changed, each to the data it rests on:
  * uranium / radium BACKGROUNDS come from the BARC mining-area surveys on disk,
    blended continuously, with provenance -- and the generator uses the same rule;
  * the shear-zone BASELINE T is the measured maximum of the belt's host-rock
    pumping tests (Kudada EW), and the mine discharge bounds it;
  * the ISR-FEASIBILITY answer is a labelled hypothetical that changes only the
    ore-zone K and never the baseline;
  * every deposit's ore-depth SEED lies inside its documented range.
"""
from __future__ import annotations

import csv
import json
import math

import numpy as np
import pytest

from ml_pipeline.config import parameters as P
from ml_pipeline.data_prep import groundwater_baselines as GB
from ml_pipeline.data_prep.ore_loader import (
    DEPOSIT_ORE_DEPTH_M, DEPOSIT_ORE_DEPTH_RANGE_M, ORE_CSV, deposit_ore_depth_range,
)
from ml_pipeline.dashboard.resolve import (
    resolve_inputs, pin_info, shear_zone_reference,
)

JADUGUDA = (86.347, 22.652)
TURAMDIH = (86.18645, 22.72867)
NARWAPAHAR = (86.2609, 22.6985)
RANCHI = (85.33, 23.35)


# ── the dataset ─────────────────────────────────────────────────────────

def test_exactly_one_served_row_per_area_and_species():
    served = {}
    for r in GB.load_rows():
        if r["served"] == "yes":
            key = (r["area"], r["species"])
            assert key not in served, f"two served rows for {key}"
            served[key] = r
    areas = {r["area"] for r in GB.load_rows() if r["area"] != GB.REGIONAL_AREA}
    for area in areas:
        for sp in GB.SURVEYED_SPECIES:
            assert (area, sp) in served, f"{area} has no served {sp} row"
    # the regional anchor serves radium only (uranium's anchor is CGWB)
    assert (GB.REGIONAL_AREA, "radium_226_mbq_l") in served
    assert (GB.REGIONAL_AREA, "uranium_ppb") not in served


def test_every_row_is_cited():
    for r in GB.load_rows():
        assert r["citation"].strip(), r
        assert r["statistic"].strip(), r


def test_radium_anchor_constant_is_the_csv_row():
    """P.RADIUM_BACKGROUND_MBQ_L and the CSV's regional row must not drift."""
    reg = GB.regional_survey()["radium_226_mbq_l"]
    assert reg["value"] == pytest.approx(P.RADIUM_BACKGROUND_MBQ_L)
    assert reg["n_samples"] == 108


def test_uranium_default_is_the_cgwb_statewide_median():
    from ml_pipeline.data_prep.jharkhand_loader import load_jharkhand_water_quality
    u = load_jharkhand_water_quality()["uranium_ppb"].dropna()
    assert len(u) == 342
    assert P.BACKGROUND_DEFAULTS["uranium_ppb"] == pytest.approx(float(u.median()), abs=1e-3)


def test_the_cgwb_well_nearest_each_deposit_has_no_uranium():
    """The reason the surveys matter: without them every deposit pin served the
    config default. If CGWB ever measures uranium there, revisit the blend."""
    from ml_pipeline.data_prep.jharkhand_loader import (
        load_jharkhand_water_quality, baseline_at_point)
    wq = load_jharkhand_water_quality()
    for name, (lon, lat) in GB._deposit_centres().items():
        b = baseline_at_point(lon, lat, wq)
        assert b.get("uranium_ppb") != b.get("uranium_ppb"), name     # NaN


# ── the blend ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("species", GB.SURVEYED_SPECIES)
def test_each_area_centre_serves_its_own_survey(species):
    for a in GB.served_surveys()[species]:
        v, prov = GB.background_for(species, a["lon"], a["lat"], nearest_value=None,
                                    nearest_km=None, district="E. Singhbhum")
        assert v == pytest.approx(a["value"], rel=0.01), a["area"]
        assert prov["dominant"]["area"] == a["area"]


def test_far_from_every_mine_the_anchor_is_served_and_flagged():
    inp, h = resolve_inputs(dict(lon=RANCHI[0], lat=RANCHI[1],
                                 species="radium_226_mbq_l"))
    assert inp["background_conc_Cb"] == pytest.approx(P.RADIUM_BACKGROUND_MBQ_L, rel=0.02)
    assert h["background_provenance"]["anchor"]["borrowed_outside_survey_districts"]


def test_the_blend_is_continuous_between_mining_areas():
    """No seam anywhere along a Turamdih -> Narwapahar -> Jaduguda walk."""
    pts = np.vstack([np.linspace(TURAMDIH, NARWAPAHAR, 400),
                     np.linspace(NARWAPAHAR, JADUGUDA, 400)])
    for sp in GB.SURVEYED_SPECIES:
        vals = [GB.background_for(sp, lon, lat, nearest_value=None, nearest_km=None,
                                  district="E. Singhbhum")[0] for lon, lat in pts]
        steps = np.abs(np.diff(np.log(vals)))
        assert float(steps.max()) < math.log(1.03), (sp, float(np.exp(steps.max())))


def test_deposit_pins_serve_measured_uranium_not_the_old_default():
    for lon, lat in (JADUGUDA, TURAMDIH, NARWAPAHAR):
        inp, h = resolve_inputs(dict(lon=lon, lat=lat, species="uranium_ppb"))
        assert inp["background_conc_Cb"] != pytest.approx(1.0, abs=1e-6)
        assert h["background_provenance"]["dominant"]["area"] != "anchor"


def test_the_generator_uses_the_same_background_rule():
    """train == serve: a sampled scenario's uranium background is exactly what
    background_for returns at its pin (radium is drawn over its served range)."""
    from ml_pipeline.data_prep.jharkhand_loader import (
        load_jharkhand_aquifers, load_jharkhand_water_quality)
    from ml_pipeline.data_prep.texas_loader import (
        texas_source_signature, texas_restoration_residual)
    from ml_pipeline.synthetic.generate import sample_scenario
    aq, wq = load_jharkhand_aquifers(), load_jharkhand_water_quality()
    sig, rest = texas_source_signature(), texas_restoration_residual()
    rng = np.random.default_rng(7)
    ra_hi = max(a["value"] for a in GB.served_surveys()["radium_226_mbq_l"])
    for _ in range(4):
        scn = sample_scenario(rng, aq, wq, sig, rest)
        d2 = (wq["longitude"] - scn["lon"]) ** 2 + (wq["latitude"] - scn["lat"]) ** 2
        base = wq.loc[d2.idxmin()]
        u = base["uranium_ppb"]
        expect, _ = GB.background_for(
            "uranium_ppb", scn["lon"], scn["lat"],
            nearest_value=(None if u != u else float(u)),
            nearest_km=math.sqrt(float(d2.min())) * 111.0, district=base["district"])
        assert scn["Cb"]["uranium_ppb"] == pytest.approx(expect)
        assert P.RADIUM_BACKGROUND_MBQ_L <= scn["Cb"]["radium_226_mbq_l"] <= ra_hi


# ── the shear-zone baseline ─────────────────────────────────────────────

def _belt_tests():
    from ml_pipeline.data_prep.cgwb_boreholes import load_boreholes
    from ml_pipeline.data_prep.ore_loader import ore_zone_at
    out = []
    for w in load_boreholes():
        if w["transmissivity_m2day"] is None or w["lon"] is None:
            continue
        if (w.get("formation") or "") != "metasediments":
            continue
        if ore_zone_at(w["lon"], w["lat"])["zone"] == "none":
            continue
        out.append(w)
    return out


def test_baseline_T_is_the_measured_maximum_of_placed_host_rock_tests():
    tests = _belt_tests()
    assert tests, "no placed metasediment pumping test inside the belt"
    best = max(tests, key=lambda w: w["transmissivity_m2day"])
    assert best["well_id"] == P.SHEAR_ZONE_T_SOURCE["well_id"]
    assert P.SHEAR_ZONE_T_M2DAY == pytest.approx(best["transmissivity_m2day"])
    assert P.SHEAR_ZONE_T_M2DAY <= P.SHEAR_ZONE_T_SOURCE["cap_m2day"]
    # the thickness is the interval that test measured
    assert P.SHEAR_ZONE_THICKNESS_M == pytest.approx(
        best["depth_m"] - best["casing_m"], abs=0.5)


def test_the_disclosed_unplaced_well_is_really_unplaced():
    """AMD Jamshedpur (T = 101) is excluded only because it has no position; if
    one is ever published this must be revisited, and this test says so."""
    from ml_pipeline.data_prep.cgwb_boreholes import load_boreholes
    amd = next(w for w in load_boreholes() if w["well_id"] == "amd_jamshedpur_ew")
    assert amd["transmissivity_m2day"] == pytest.approx(101.0)
    assert amd["lon"] is None and amd["lat"] is None


def test_mine_discharge_record_rederives_and_bounds_the_baseline():
    from ml_pipeline.validation import mine_inflow_transmissivity as M
    live = M.run()
    rec = json.loads(M.OUT_JSON.read_text())
    assert live == rec, "rerun: python -m ml_pipeline.validation.mine_inflow_transmissivity"
    for name, m in live["mines"].items():
        # the baseline sits on the conservative side of what the mines allow
        assert P.SHEAR_ZONE_T_M2DAY > m["bulk_T_m2day"][2], name
        assert m["engine_column"]["column_T_m2day"] > m["bulk_T_m2day"][2], name
    assert live["forced_discharge_turamdih"]["370"]["times_reported"] > 15.0


# ── the ISR-feasibility hypothetical ────────────────────────────────────

def test_baseline_ore_zone_is_below_the_iaea_floor_at_the_deposits():
    for lon, lat in (JADUGUDA, TURAMDIH):
        _, h = resolve_inputs(dict(lon=lon, lat=lat, species="tds_mg_l",
                                   ore_depth_m=150.0))
        isr = h["isr_feasibility"]
        assert isr["below_unfeasible_floor"] is True
        assert isr["applied"] is False and isr["scenario"] == "baseline"


def test_the_hypothetical_moves_only_the_ore_zone_K():
    pay = dict(lon=JADUGUDA[0], lat=JADUGUDA[1], species="tds_mg_l", ore_depth_m=150.0)
    b_inp, b_h = resolve_inputs(pay)
    s_inp, s_h = resolve_inputs({**pay, "hydro_scenario": "isr_feasibility"})
    assert s_inp["K_m_day"] == pytest.approx(P.ISR_FEASIBILITY["K_scenario_m_day"])
    assert s_h["isr_feasibility"]["applied"] is True
    for k in b_inp:
        if k != "K_m_day":
            assert s_inp[k] == b_inp[k], k
    # the confining column's reference K is untouched
    assert s_h["k_depth"] == b_h["k_depth"]


def test_the_hypothetical_never_lowers_K_and_yields_to_an_explicit_K():
    pay = dict(lon=JADUGUDA[0], lat=JADUGUDA[1], species="tds_mg_l",
               K_m_day=3.0, hydro_scenario="isr_feasibility")
    inp, h = resolve_inputs(pay)
    assert inp["K_m_day"] == pytest.approx(3.0)
    assert h["isr_feasibility"]["applied"] is False


def test_predict_returns_both_answers_labelled():
    from ml_pipeline.dashboard.server import PredictRequest, api_predict
    r = api_predict(PredictRequest(lon=JADUGUDA[0], lat=JADUGUDA[1],
                                   species="tds_mg_l", time_years=20,
                                   ore_depth_m=180.0))
    assert r["hydro_scenario"] == "baseline"
    sc = r["hypotheticals"]["isr_feasibility"]
    assert sc["hypothetical"] is True and sc["applies"] is True
    assert "Not a prediction" in sc["note"]
    base = r["metrics"]["analytical"]
    assert sc["baseline_metrics"]["migration_m"] == pytest.approx(base["migration_m"])
    assert sc["metrics"]["migration_m"] > base["migration_m"]
    # the vertical pathway is unchanged by construction, and computed to show it
    v = sc["vertical"]
    assert v["years_to_vertical_breakthrough"] == v["baseline_years_to_vertical_breakthrough"]


def test_metrics_only_calls_skip_the_hypothetical():
    from ml_pipeline.dashboard.server import PredictRequest, api_predict
    r = api_predict(PredictRequest(lon=JADUGUDA[0], lat=JADUGUDA[1],
                                   species="tds_mg_l", display_extras=False))
    assert r["hypotheticals"] is None


# ── ore depth ───────────────────────────────────────────────────────────

def test_every_deposit_has_a_documented_range_and_a_seed_inside_it():
    lo, hi = P.VERTICAL["ore_depth_range_m"]
    with ORE_CSV.open(encoding="utf-8-sig") as fh:
        names = {r["name"].strip() for r in csv.DictReader(fh)
                 if r["name"].strip() != P.ORE_BELT_NAME
                 and (r.get("record_source") or "original").strip() != "added"}
    assert names == set(DEPOSIT_ORE_DEPTH_RANGE_M) == set(DEPOSIT_ORE_DEPTH_M)
    for name, rec in DEPOSIT_ORE_DEPTH_RANGE_M.items():
        seed = DEPOSIT_ORE_DEPTH_M[name]
        assert rec["top_m"] <= seed <= rec["bottom_m"], name
        assert lo <= seed <= hi, name
        assert rec["source"] and rec["basis"], name
        assert rec["confidence"] in ("primary", "secondary"), name


def test_pin_info_carries_the_range_backgrounds_and_ore_flag():
    p = pin_info(*TURAMDIH)
    assert p["ore_depth_range"]["deposit"] == "Turamdih"
    assert p["ore_depth_range"]["top_m"] == 50.0 and p["ore_depth_range"]["bottom_m"] == 200.0
    assert p["in_ore"] is True and p["ore_name"] == "Turamdih"
    assert p["shear_zone"]["T_m2day"] == P.SHEAR_ZONE_T_M2DAY
    for sp in GB.SURVEYED_SPECIES:
        assert p["backgrounds"][sp]["dominant"]["area"] == "turamdih_complex"
    far = pin_info(*RANCHI)
    assert far["ore_depth_range"] is None and far["shear_zone"] is None
    assert far["in_ore"] is False
    assert deposit_ore_depth_range("Not A Deposit") is None
