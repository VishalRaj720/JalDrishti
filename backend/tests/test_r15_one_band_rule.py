"""R15 — one banding rule, and the health set that was missing a member.

Two defects, both found while rebuilding the portal's citizen screens on
2026-08-26, both of the same shape: a rule stated in more than one place had
come to be stated more than one way.

1. `/citizen/my-area` banded a block on URANIUM ALONE while `/public/risk/*`
   banded on uranium, nitrate and fluoride. Uranium exceeds its limit at zero of
   Jharkhand's uranium-tested wells; nitrate exceeds at 22 and fluoride at 32.
   So a resident of a block over the fluoride limit was shown "High concern" on
   the public map and "Low concern" on the page they open to check their own
   drinking water. Neither endpoint was buggy against its own rule, which is why
   it survived.

2. `iron` was the only member of the stated health-significant set without
   `health=True`, though the interpretation sentence the same module returns
   names it, `public_risk.py` calls it a health determinand twice, and the alert
   scanner queries it alongside the other four.

These tests pin the properties rather than the wording, so the prose can be
improved without them going stale — but they will fail loudly if either rule
splits in two again.
"""
import inspect

import pytest

import app.api.v1.citizen as cz
import app.api.v1.public_risk as pr
import app.services.alerts as alerts
import app.services.water_quality as wq
from app.services import health_bands as hb


# ── the health set ───────────────────────────────────────────────────

def test_iron_is_flagged_health_significant():
    """Iron is a health determinand. It was the only one not marked as such.

    It is 0 of 397 measured, so nothing was miscounted — but the flag decides
    which group it renders in, and it would have started deciding an exceedance
    count the moment anyone ingested an iron result.
    """
    assert wq.BY_KEY["iron"].health is True


def test_health_set_matches_the_sentence_the_api_returns():
    """The registry and the prose must name the same five determinands.

    `_rollup`'s `interpretation` tells a reader which determinands were counted
    as health-significant. If the flags and that sentence disagree, one of them
    is lying to whoever reads the aggregate.
    """
    flagged = {d.key for d in wq.STANDARD if d.health}
    assert flagged == {"uranium", "fluoride", "nitrate", "arsenic", "iron"}


# ── one rule, one place ──────────────────────────────────────────────

def test_public_risk_reexports_the_shared_rule_rather_than_copying_it():
    """Identity, not equality: a copy that starts equal can stop being equal."""
    assert pr._BANDS is hb.BANDS
    assert pr._DRIVER is hb.DRIVER
    assert pr._UNTESTED is hb.UNTESTED
    assert pr._explain_multi is hb.explain_multi
    assert pr._join_and is hb.join_and
    assert pr.URANIUM_LIMIT_PPB == hb.URANIUM_LIMIT_PPB


def test_the_alert_scanner_shares_the_same_uranium_limit():
    """`citizen.py` imports the limit from `alerts`, which is a third copy no
    longer. A limit change that missed one of them would have moved the map and
    left the citizen page judging against the old number."""
    assert alerts.URANIUM_LIMIT_PPB == hb.URANIUM_LIMIT_PPB


def test_my_area_bands_with_the_shared_sql_not_its_own_ladder():
    """The citizen page must not carry a second implementation of the band.

    Checked against the source because that is where the defect lived: the
    handler had its own `elif mx >= URANIUM_LIMIT_PPB / 2` ladder and its own
    prose, and no assertion about outputs would have caught it — the ladder was
    internally consistent and produced perfectly reasonable sentences.
    """
    src = inspect.getsource(cz.my_area)
    assert "health_bands.BANDS" in src, "my-area must use the shared band SQL"
    assert "health_bands.describe" in src, "my-area must use the shared reading"

    # Comment lines are excluded, or this fails on the comment that explains why
    # the ladder was removed — which is the one place those words should still
    # appear in this handler.
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    for gone in ("Moderate concern", "High concern", "Low concern"):
        assert gone not in code, (
            f"my-area is deciding {gone!r} itself again instead of taking the "
            f"band from the shared rule")


def test_the_uranium_only_explainer_is_gone():
    """`_explain` produced "Uranium in the 2 wells sampled here was well below
    the 30 ppb safe limit" for blocks banded High concern on fluoride, and three
    handlers called it. There is no version of it worth keeping."""
    assert not hasattr(pr, "_explain")


# ── the two gaps stay apart, and neither reads as a pass ─────────────

def test_the_band_ladder_separates_the_two_gaps_on_samples():
    """`health_tests = 0` already implies `max_u IS NULL`, so the old ladder's
    'Not tested' branch was unreachable. `samples` is the only term that tells
    "sampled, never analysed" apart from "nobody has been here"."""
    assert "health_tests = 0 AND samples = 0" in hb.BANDS
    assert "'No data'" in hb.BANDS and "'Not tested'" in hb.BANDS


def test_describe_promotes_a_sampled_but_unanalysed_block_to_not_tested():
    band, means, _ = hb.describe(
        {"band": "No data", "n_u": 0, "n_no3": 0, "n_f": 0,
         "untested_health": ["uranium", "nitrate", "fluoride", "arsenic", "iron"]},
        wells=2, samples=2)
    assert band == "Not tested"
    assert "not a clean result" in means.lower()
    # It must not tell a resident nothing was collected while reporting samples.
    assert "no groundwater samples have been collected" not in means.lower()


def test_describe_reports_no_data_only_when_nothing_was_sampled():
    band, means, _ = hb.describe(
        {"band": "No data", "n_u": 0, "n_no3": 0, "n_f": 0}, wells=0, samples=0)
    assert band == "No data"
    assert "gap in monitoring" in means.lower()
    assert "not a clean result" in means.lower()


@pytest.mark.parametrize("band", ["No data", "Not tested"])
def test_neither_gap_band_ever_reads_as_a_pass(band):
    _, means, _ = hb.describe(
        {"band": band, "n_u": 0, "n_no3": 0, "n_f": 0},
        wells=2, samples=2 if band == "Not tested" else 0)
    lowered = means.lower()
    assert "not a clean result" in lowered
    assert "within the drinking-water limits" not in lowered
    assert "well below" not in lowered


# ── the band names what set it ───────────────────────────────────────

def test_a_fluoride_block_is_banded_and_explained_on_fluoride():
    """The case that made the two surfaces disagree in the first place."""
    band, means, _ = hb.describe(
        {"band": "High concern", "band_driver": "fluoride",
         "max_fluoride_mg_l": 1.8, "max_uranium_ppb": 2.5,
         "n_u": 4, "n_no3": 4, "n_f": 4},
        wells=4, samples=4)
    assert band == "High concern"
    assert "fluoride" in means.lower()
    assert "1.8" in means
    # And it must not reassure about the determinand that did not set the band.
    assert "well below" not in means.lower()


def test_a_low_concern_block_still_states_what_nobody_analysed():
    """"Low concern" must never quietly mean "clean for the ones we looked at"."""
    _, means, untested = hb.describe(
        {"band": "Low concern", "band_driver": None,
         "n_u": 3, "n_no3": 3, "n_f": 3,
         "untested_health": ["arsenic", "iron"]},
        wells=3, samples=3)
    assert untested == ["arsenic", "iron"]
    assert "arsenic and iron" in means
    assert "has not been shown to be safe" in means
