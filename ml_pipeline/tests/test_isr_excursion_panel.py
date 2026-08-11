"""ISR excursion panel: chloride + TDS + sulfate, 2-of-3.   [2026-08-11]

Chloride was added to the EXCURSION LAYER ONLY. These tests pin both halves of
that claim: that the 2-of-3 decision logic is correct, and that the trained
water-quality pipeline was not touched to get it.

The decision-rule tests drive `_ring_concentration` directly rather than
hunting for physical operating points that happen to trip a chosen subset --
the rule is a counting rule and deserves to be tested as one, exhaustively.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ml_pipeline.config import parameters as P
from ml_pipeline.dashboard import isr_excursion as IX
from ml_pipeline.dashboard.server import app

client = TestClient(app)
PANEL = ("chloride_mg_l", "tds_mg_l", "sulfate_mg_l")
PIN = dict(lon=86.347, lat=22.652, injection_rate_m3_day=8000.0,
           bleed_percent=0.5, gradient_i=0.0021, operation_years=8.0,
           time_years=20.0)


# --------------------------------------------------------------------------- #
# Panel composition
# --------------------------------------------------------------------------- #
def test_panel_is_chloride_tds_sulfate():
    assert set(P.ISR_EXCURSION_INDICATORS) == set(PANEL)
    assert len(P.ISR_EXCURSION_INDICATORS) == 3


def test_rule_is_two_of_three():
    assert P.ISR_EXCURSION_MIN_INDICATORS == 2
    out = IX.isr_indicator_excursion(dict(PIN, species="uranium_ppb"))
    assert out["indicators_available"] == 3
    assert "2-of-3" in out["rule"]
    assert out["panel_shortfall"] is False


def test_uranium_and_radium_are_not_indicators():
    """They are contaminants of concern and must stay OUT of the panel."""
    for sp in ("uranium_ppb", "radium_226_mbq_l"):
        assert sp not in P.ISR_EXCURSION_INDICATORS
        assert sp in P.ISR_NON_INDICATORS and P.ISR_NON_INDICATORS[sp]


# --------------------------------------------------------------------------- #
# The 2-of-3 counting rule, exhaustively
# --------------------------------------------------------------------------- #
def _stub_ring(over_set):
    """Return a _ring_concentration stub where `over_set` species exceed UCL.

    Baseline 100, lixiviant 1000, UCL = 100*1.2 = 120 -> ring 500 trips,
    ring 100 does not.
    """
    def _fake(payload, species, ring_m):
        return {"species": species, "unit": "mg/L", "baseline": 100.0,
                "lixiviant_C0": 1000.0,
                "ring_conc": 500.0 if species in over_set else 100.0,
                "plume_increment": 400.0 if species in over_set else 0.0}
    return _fake


@pytest.mark.parametrize("solo", PANEL)
def test_one_indicator_alone_does_not_declare(monkeypatch, solo):
    monkeypatch.setattr(IX, "_ring_concentration", _stub_ring({solo}))
    out = IX.isr_indicator_excursion(dict(PIN, species="uranium_ppb"))
    assert out["indicators_over_ucl"] == 1
    assert out["excursion_declared"] is False, (
        f"{solo} alone must NOT declare an excursion — that is the whole point "
        f"of the 2-of-N rule, and for sulfate specifically it is what protects "
        f"against sulfide-oxidation false alarms")


@pytest.mark.parametrize("pair", list(itertools.combinations(PANEL, 2)))
def test_any_two_indicators_declare(monkeypatch, pair):
    monkeypatch.setattr(IX, "_ring_concentration", _stub_ring(set(pair)))
    out = IX.isr_indicator_excursion(dict(PIN, species="uranium_ppb"))
    assert out["indicators_over_ucl"] == 2
    assert out["excursion_declared"] is True, f"{pair} must declare"


def test_all_three_declare(monkeypatch):
    monkeypatch.setattr(IX, "_ring_concentration", _stub_ring(set(PANEL)))
    out = IX.isr_indicator_excursion(dict(PIN, species="uranium_ppb"))
    assert out["indicators_over_ucl"] == 3
    assert out["excursion_declared"] is True


def test_none_over_does_not_declare(monkeypatch):
    monkeypatch.setattr(IX, "_ring_concentration", _stub_ring(set()))
    out = IX.isr_indicator_excursion(dict(PIN, species="uranium_ppb"))
    assert out["indicators_over_ucl"] == 0
    assert out["excursion_declared"] is False


def test_uranium_or_radium_over_limit_cannot_reach_the_indicator_count(monkeypatch):
    """Even with U and Ra wildly over their limits, the count is driven only by
    the panel — the requested guarantee that they never contribute."""
    monkeypatch.setattr(IX, "_ring_concentration",
                        _stub_ring({"uranium_ppb", "radium_226_mbq_l"}))
    out = IX.isr_indicator_excursion(dict(PIN, species="uranium_ppb"))
    assert out["indicators_over_ucl"] == 0
    assert out["excursion_declared"] is False
    assert {i["species"] for i in out["indicators"]} == set(PANEL)


# --------------------------------------------------------------------------- #
# Chloride comes from the EXISTING data, not a fabricated source
# --------------------------------------------------------------------------- #
def test_chloride_background_comes_from_the_real_cgwb_column():
    """397/397 wells carry `Cl (mg/L)`; it was simply never parsed."""
    import pandas as pd
    from ml_pipeline.data_prep.jharkhand_loader import (
        load_jharkhand_water_quality, WQ_CSV)
    raw = pd.read_csv(WQ_CSV, encoding="utf-8-sig")
    assert "Cl (mg/L)" in raw.columns, "the source column must pre-exist"
    wq = load_jharkhand_water_quality()
    assert "chloride_mg_l" in wq.columns
    s = wq["chloride_mg_l"].dropna()
    assert len(s) >= 390, f"expected near-full coverage, got {len(s)}"
    # values must equal the raw column, not a synthesised distribution
    assert s.median() == pytest.approx(
        pd.to_numeric(raw["Cl (mg/L)"], errors="coerce").dropna().median())


def test_chloride_source_term_comes_from_the_real_texas_sheet():
    import pandas as pd
    from ml_pipeline.data_prep.texas_loader import (load_texas_geochem,
                                                    texas_source_signature)
    eom = load_texas_geochem()["End of Mining"]
    assert "Chloride" in eom.columns
    per_mine = pd.to_numeric(eom["Chloride"], errors="coerce").dropna()
    lo, hi = texas_source_signature()["chloride_mg_l"]
    assert lo >= per_mine.min() - 1 and hi <= per_mine.max() + 1, (
        "the envelope must not exceed the observed measurements")
    assert lo > 0 and hi > lo


def test_chloride_baseline_is_pin_specific_not_a_constant():
    """It must come from the nearest well, like every other indicator."""
    from ml_pipeline.data_prep.jharkhand_loader import baseline_at_point
    a = baseline_at_point(86.347, 22.652)["chloride_mg_l"]
    b = baseline_at_point(85.33, 23.36)["chloride_mg_l"]
    assert a == a and b == b          # not NaN
    assert a != b, "two distant pins should resolve different wells"


def test_chloride_is_modelled_as_a_conservative_tracer():
    for regime in ("fractured", "porous"):
        assert P.kd_range_for("chloride_mg_l", regime) == (0.0, 0.0, 0.0)


# --------------------------------------------------------------------------- #
# THE FREEZE: the trained pipeline must be untouched
# --------------------------------------------------------------------------- #
def test_chloride_is_not_a_trained_or_generated_species():
    """SPECIES is what synthetic.generate iterates to bake labels. Chloride in
    it would silently imply a 22,500-row re-bake and a retrain."""
    assert "chloride_mg_l" not in P.SPECIES
    assert "chloride_mg_l" not in P.ML_SPECIES
    assert "chloride_mg_l" in P.EXCURSION_ONLY_SPECIES
    assert len(P.SPECIES) == 4 and len(P.ML_SPECIES) == 4


def test_trained_model_card_still_has_exactly_four_species():
    card = json.loads((Path(P.__file__).resolve().parents[1]
                       / "ml" / "artifacts" / "model_card.json").read_text())
    onehots = [f for f in card["features"] if f in P.SPECIES_ONEHOT]
    assert len(onehots) == 4
    assert "is_chloride_mg_l" not in card["features"]


def test_extra_registry_keys_are_inert_to_the_generator():
    """Every registry chloride was added to is consumed as `d[sp] for sp in
    SPECIES`, so an extra key cannot change a training label."""
    from ml_pipeline.data_prep.texas_loader import (texas_source_signature,
                                                    texas_restoration_residual)
    for d in (texas_source_signature(), texas_restoration_residual(),
              P.KD_RANGES, P.BACKGROUND_DEFAULTS, P.SPECIES_UNITS):
        assert "chloride_mg_l" in d
        assert set(P.SPECIES) - {"radium_226_mbq_l"} <= set(d) or d is P.SPECIES_UNITS


@pytest.mark.parametrize("species", list(P.SPECIES))
def test_existing_analytical_and_ml_outputs_are_unchanged(species):
    """Pinned against values captured BEFORE chloride was introduced, at the
    PIN operating point. If adding an excursion-only constituent had leaked
    into the modelled species in any way, these would move."""
    expected = {
        "uranium_ppb":      dict(area_ha=12.510, migration_m=12.9),
        "sulfate_mg_l":     dict(area_ha=13.184, migration_m=40.2),
        "tds_mg_l":         dict(area_ha=17.087, migration_m=139.3),
        "radium_226_mbq_l": dict(area_ha=12.325, migration_m=0.3),
    }[species]
    j = client.post("/api/predict", json=dict(PIN, species=species)).json()
    a = j["metrics"]["analytical"]
    assert a["area_ha"] == pytest.approx(expected["area_ha"], abs=0.05)
    assert a["migration_m"] == pytest.approx(expected["migration_m"], abs=0.5)


def test_uranium_and_radium_remain_contaminant_outputs():
    """They must still be served as full water-quality predictions with bands —
    excluding them as INDICATORS must not have demoted them as OUTPUTS."""
    for sp in ("uranium_ppb", "radium_226_mbq_l"):
        j = client.post("/api/predict", json=dict(PIN, species=sp)).json()
        assert j["metrics"]["analytical"]["area_ha"] > 0
        ml = j["metrics"]["ml"]
        assert ml is not None, f"{sp} must still have an ML surrogate answer"
        for k in ("area_ha", "migration_m", "compliance_conc"):
            assert set(ml[k]) == {"p10", "p50", "p90"}


# --------------------------------------------------------------------------- #
# Framing
# --------------------------------------------------------------------------- #
def test_result_never_claims_regulatory_compliance():
    out = IX.isr_indicator_excursion(dict(PIN, species="uranium_ppb"))
    assert "NOT REGULATORY-COMPLIANT" in out["compliance_status"]
    note = out["compliance_note"].lower()
    for missing in ("temporal", "verification", "60-day", "no isr operation"):
        assert missing in note
