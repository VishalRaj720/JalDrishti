"""2026-09-25 -- the vertical alerts key on the FIRST arrival, not the display
species (ml_pipeline LIMITATIONS.md 1f).

The engine's upward pathway now carries each species through the rock's matrix
storage, so a uranium run's own breakthrough is centuries while the injected
salts from the same wellfield arrive within years. An alert keyed on the display
species would go quiet for every uranium advisory -- the uranium-only failure
R14 removed from the citizen map, one layer down. These tests pin the helper
every vertical alert path now reads through, and that runs stored before the
change keep their old meaning.
"""
from app.api.v1.citizen import _shallow_summary
from app.services.alerts import arrival_words, vertical_headline

NEW_RUN = {
    "years_to_vertical_breakthrough": 447.1,
    "shallow_impact_probability": 0.09,
    "risk_band": "low",
    "first_arrival": {"species": "tds_mg_l", "years": 4.5,
                      "shallow_impact_probability": 1.0, "risk_band": "high"},
    "seasonal": {"static_deep_head": {"dry_season": {"years_to_breakthrough": 153.0}}},
}
LEGACY_RUN = {  # stored before 2026-09-25: a species-blind water-parcel time
    "years_to_vertical_breakthrough": 17.5,
    "shallow_impact_probability": 0.661,
    "risk_band": "high",
}


def test_a_uranium_run_alerts_on_the_salts_that_arrive_first():
    yrs, prob, species = vertical_headline(NEW_RUN)
    assert (yrs, prob, species) == (4.5, 1.0, "tds_mg_l")
    assert yrs < NEW_RUN["years_to_vertical_breakthrough"]


def test_a_legacy_run_keeps_its_old_meaning():
    yrs, prob, species = vertical_headline(LEGACY_RUN)
    assert (yrs, prob, species) == (17.5, 0.661, None)
    # its number never belonged to a species, so it is not named as one
    assert arrival_words(species) == "contamination"


def test_residents_are_told_what_arrives():
    assert "dissolved salts" in arrival_words("tds_mg_l")
    assert arrival_words("uranium_ppb") == "uranium"


def test_citizen_summary_carries_both_the_species_and_the_first_arrival():
    s = _shallow_summary({"hydro": {"vertical": NEW_RUN}})
    assert s["years_to_breakthrough"] == 447.1
    assert s["first_arrival"]["species"] == "tds_mg_l"
    assert s["first_arrival"]["years"] == 4.5
    # the dry-season figure used to read a key the engine never produced
    assert s["dry_season_years"] == 153.0
    legacy = _shallow_summary({"hydro": {"vertical": LEGACY_RUN}})
    assert legacy["first_arrival"] is None
