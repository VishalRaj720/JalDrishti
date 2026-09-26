"""Out-of-distribution guard for the two concentration features.

WHY THIS EXISTS. `source_conc_C0` and `background_conc_Cb` are trained features,
but they were the only two the serving-side guard never checked.
`envelope_violations` looked them up in the model card's `training_envelope`,
which has no entry for either, and `env.get(key, (-inf, inf))` turned each
lookup into a silent no-op. A baseline or source term outside trained support
extrapolated with the conformal 80 % band still printed and no longer meaning
80 %.

The tests below pin three things: that the bounds are real (not infinite), that
an out-of-support value is flagged, and that the recorded support still matches
the training set it was measured from.
"""
import pytest

from ml_pipeline.config import parameters as P
from ml_pipeline.dashboard.resolve import (
    _species_support, envelope_violations, resolve_inputs,
)

JADUGUDA = (86.36, 22.65)
FAR_NON_ORE = (85.20, 23.80)
SPECIES = ("uranium_ppb", "sulfate_mg_l", "tds_mg_l", "radium_226_mbq_l")


def _inputs(lon, lat, species):
    return resolve_inputs(dict(lon=lon, lat=lat, species=species))


# ── the bounds are real ──────────────────────────────────────────────

def test_every_species_has_finite_c0_and_cb_bounds():
    """The bug was infinite bounds via a missing key, so assert the opposite."""
    support = _species_support()
    for sp in SPECIES:
        assert sp in support, f"{sp} has no recorded concentration support"
        for key in ("source_conc_C0", "background_conc_Cb"):
            lo, hi = support[sp][key]
            assert lo == lo and hi == hi           # not NaN
            assert abs(lo) != float("inf") and abs(hi) != float("inf")
            assert lo <= hi


def test_the_model_card_now_records_the_species_support():
    """UPDATED 2026-09-26 (v6). This test used to document that the card had no
    concentration support, which is why P.TRAINED_SPECIES_SUPPORT was the source
    of truth. The v6 trainer records `species_support` in the card, so
    `_species_support` prefers it -- and the config fallback must agree with it,
    or the two would be two answers to one question."""
    from ml_pipeline.dashboard.resolve import _model_card
    card = _model_card()
    env = card.get("training_envelope", {})
    assert "source_conc_C0" not in env and "background_conc_Cb" not in env
    rec = card.get("species_support")
    assert rec, "the v6 card must record species_support"
    for sp, keys in rec.items():
        for key, (lo, hi) in keys.items():
            c_lo, c_hi = P.TRAINED_SPECIES_SUPPORT[sp][key]
            assert lo == pytest.approx(c_lo, rel=1e-3, abs=1e-9), (sp, key)
            assert hi == pytest.approx(c_hi, rel=1e-3, abs=1e-9), (sp, key)


def test_recorded_support_matches_the_training_set():
    """Drift guard: a retrain that shifts the support must fail here rather than
    quietly invalidate the constant this guard depends on."""
    import pathlib
    import pandas as pd
    csv = (pathlib.Path(__file__).resolve().parents[1] / "outputs"
           / "synthetic_training.csv")
    if not csv.exists():
        pytest.skip("training set not present (outputs/ is gitignored)")

    df = pd.read_csv(csv)
    for sp, g in df.groupby("species"):
        rec = P.TRAINED_SPECIES_SUPPORT[sp]
        for key in ("source_conc_C0", "background_conc_Cb"):
            lo, hi = rec[key]
            # 0.1 % of the bound absorbs the rounding in the recorded literals.
            assert g[key].min() == pytest.approx(lo, rel=1e-3, abs=1e-9), \
                f"{sp}.{key} min drifted"
            assert g[key].max() == pytest.approx(hi, rel=1e-3, abs=1e-9), \
                f"{sp}.{key} max drifted"


# ── an out-of-support value is flagged ───────────────────────────────

@pytest.mark.parametrize("species", SPECIES)
def test_c0_far_above_support_is_flagged(species):
    inp, hyd = _inputs(*JADUGUDA, species)
    hi = _species_support()[species]["source_conc_C0"][1]
    viol = envelope_violations({**inp, "source_conc_C0": hi * 10.0}, hyd)
    assert "conc:source_conc_C0" in viol


@pytest.mark.parametrize("species", SPECIES)
def test_c0_far_below_support_is_flagged(species):
    inp, hyd = _inputs(*JADUGUDA, species)
    lo = _species_support()[species]["source_conc_C0"][0]
    viol = envelope_violations({**inp, "source_conc_C0": lo / 100.0}, hyd)
    assert "conc:source_conc_C0" in viol


@pytest.mark.parametrize("species", SPECIES)
def test_cb_far_above_support_is_flagged(species):
    inp, hyd = _inputs(*JADUGUDA, species)
    hi = _species_support()[species]["background_conc_Cb"][1]
    viol = envelope_violations({**inp, "background_conc_Cb": hi * 10.0 + 100.0},
                               hyd)
    assert "conc:background_conc_Cb" in viol


@pytest.mark.parametrize("species", SPECIES)
def test_a_value_inside_support_is_not_flagged(species):
    """Midpoint of the trained box must be clean, or the guard is useless."""
    inp, hyd = _inputs(*JADUGUDA, species)
    sup = _species_support()[species]
    mid = {k: (sup[k][0] + sup[k][1]) / 2.0
           for k in ("source_conc_C0", "background_conc_Cb")}
    viol = envelope_violations({**inp, **mid}, hyd)
    assert "conc:source_conc_C0" not in viol
    assert "conc:background_conc_Cb" not in viol


def test_the_check_is_per_species_not_global():
    """A uranium C0 is a perfectly ordinary number for uranium and wildly out of
    support for radium. A single global range would accept both."""
    u_c0 = sum(_species_support()["uranium_ppb"]["source_conc_C0"]) / 2.0

    inp_u, hyd_u = _inputs(*JADUGUDA, "uranium_ppb")
    assert "conc:source_conc_C0" not in envelope_violations(
        {**inp_u, "source_conc_C0": u_c0}, hyd_u)

    inp_r, hyd_r = _inputs(*JADUGUDA, "radium_226_mbq_l")
    assert "conc:source_conc_C0" in envelope_violations(
        {**inp_r, "source_conc_C0": u_c0}, hyd_r)


def test_radium_baseline_support_covers_every_served_background():
    """REWRITTEN 2026-09-26 (v6). Radium's background used to be one constant
    for every training row (lo == hi == 23) and this test checked the tolerance
    accepted it. It is now the BARC survey blend (10-23 mBq/L, LIMITATIONS.md
    1k), trained over that whole range -- so every mining area's own value and
    the far-field anchor must sit inside support, unflagged."""
    lo, hi = _species_support()["radium_226_mbq_l"]["background_conc_Cb"]
    assert lo < hi
    pins = [(86.347, 22.652), (86.186, 22.729), (86.2609, 22.6985),
            (86.491, 22.470), FAR_NON_ORE]
    for lon, lat in pins:
        inp, hyd = _inputs(lon, lat, "radium_226_mbq_l")
        assert lo * 0.98 <= inp["background_conc_Cb"] <= hi * 1.02, (lon, lat)
        assert "conc:background_conc_Cb" not in envelope_violations(inp, hyd), (lon, lat)


# ── the suppression rule ─────────────────────────────────────────────

def test_non_ore_pins_are_not_flagged_because_the_surrogate_is_bypassed():
    """In a non-ore zone C0 is deliberately clamped to background and the server
    already bypasses the surrogate for that species, so the clamped value is not
    an ML extrapolation. Flagging it would turn every non-ore pin amber."""
    for species in ("uranium_ppb", "radium_226_mbq_l"):
        inp, hyd = _inputs(*FAR_NON_ORE, species)
        assert hyd.get("u_suppressed") is True, f"{species} not suppressed here"
        viol = envelope_violations(inp, hyd)
        assert "conc:source_conc_C0" not in viol, (
            f"{species} flagged at a non-ore pin where the ML is bypassed")


def test_without_hydro_the_call_still_works():
    """Backward compatible: `hydro` is optional, and older callers keep working.
    Without it the suppression cannot be known, so the check simply applies."""
    inp, _ = _inputs(*JADUGUDA, "sulfate_mg_l")
    viol = envelope_violations(inp)          # no hydro argument
    assert isinstance(viol, list)


# ── the honest consequence at a real pin ─────────────────────────────

def test_jaduguda_baseline_is_now_reported_as_out_of_support():
    """A REAL behaviour change, pinned deliberately.

    Measured groundwater at Jaduguda is more mineralised than anything the
    generator sampled: sulfate baseline 227 mg/L against a trained 2-190, TDS
    1779 against 97.9-1513.6. The conformal band there was never guaranteed;
    before this fix the run said nothing. It now reports extrapolation, which is
    the correct and more conservative answer.
    """
    for species in ("sulfate_mg_l", "tds_mg_l"):
        inp, hyd = _inputs(*JADUGUDA, species)
        assert not hyd.get("u_suppressed")
        assert "conc:background_conc_Cb" in envelope_violations(inp, hyd), (
            f"{species} baseline at Jaduguda should report out-of-support")


def test_operational_and_hydro_checks_are_unchanged():
    """The fix is additive: it must not alter the flags that already existed."""
    inp, hyd = _inputs(*JADUGUDA, "uranium_ppb")
    viol = envelope_violations(inp, hyd)
    non_conc = [v for v in viol if not v.startswith("conc:")]
    assert non_conc == [], f"pre-existing checks changed: {non_conc}"
