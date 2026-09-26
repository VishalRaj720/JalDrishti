"""2026-09-26 -- the engine's ISR-feasibility hypothetical reaches the Console and
survives storage, and nothing that alerts reads it.

The engine returns two answers per run: the MEASURED-MAXIMUM baseline (every
metric, the vertical screening, the excursion panel) and, under
`hypotheticals`, the same run with the ore-zone K raised to the IAEA ISR level.
The second exists to show how far a plume could spread IF the rock were
permeable enough for in-situ leaching; it must never become the basis of an
alert, an advisory or a citizen-facing band.
"""
import pathlib

from app.services.simulation_run import _hydro_with_extras

HYPO = {"isr_feasibility": {"hypothetical": True, "applies": True,
                            "metrics": {"migration_m": 534.6}}}


def test_a_stored_run_keeps_the_hypothetical_and_the_vertical_screen():
    out = _hydro_with_extras({"hydro": {"K_m_day": 0.034},
                              "vertical": {"years_to_vertical_breakthrough": 139.6},
                              "hypotheticals": HYPO})
    assert out["hypotheticals"] == HYPO
    assert out["vertical"] == {"years_to_vertical_breakthrough": 139.6}
    assert out["K_m_day"] == 0.034


def test_a_run_without_them_stores_hydro_unchanged():
    hydro = {"K_m_day": 0.034}
    assert _hydro_with_extras({"hydro": hydro}) == hydro
    assert _hydro_with_extras({"hydro": None, "hypotheticals": HYPO}) is None


def test_only_the_passthrough_code_mentions_the_hypothetical():
    """Alerts, tiers, advisories and the citizen map read the baseline only. If
    a new reader appears, it must be a deliberate, reviewed decision -- this
    test makes that decision visible."""
    app = pathlib.Path(__file__).resolve().parents[1] / "app"
    readers = sorted(p.relative_to(app).as_posix() for p in app.rglob("*.py")
                     if "hypotheticals" in p.read_text(encoding="utf-8"))
    assert readers == ["api/v1/preview.py", "services/simulation_run.py"]
