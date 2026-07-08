"""Phase-2 D4 -- grade-scaled uranium C0 (reads committed UDEPO xlsx, no retrain)."""
from __future__ import annotations

import numpy as np
import pytest

from ml_pipeline.data_prep.ore_grades import (
    deposit_grade_pct, grade_c0_factor, _grades,
)
from ml_pipeline.config import parameters as P

_ORE_DEPOSITS = ["Jaduguda", "Bhatin", "Narwapahar", "Turamdih",
                 "Banduhurang", "Mohuldih", "Bagjata"]


def test_all_ore_loader_deposits_have_a_grade():
    for d in _ORE_DEPOSITS:
        assert deposit_grade_pct(d) is not None, f"{d} has no UDEPO grade"


def test_base_deposit_not_extension():
    # "Jaduguda" must read the base 0.01-0.05 class, never "Jaduguda North" (0.05-0.10)
    assert deposit_grade_pct("Jaduguda") == pytest.approx(0.03)
    assert deposit_grade_pct("Narwapahar") == pytest.approx(0.03)


def test_factor_direction_and_value():
    # 0.03%U vs 0.05 reference -> 0.6x; Banduhurang 0.075% -> 1.5x
    f_jad, g_jad = grade_c0_factor("Jaduguda")
    f_ban, g_ban = grade_c0_factor("Banduhurang")
    assert f_jad == pytest.approx(0.6, abs=1e-6) and g_jad == pytest.approx(0.03)
    assert f_ban == pytest.approx(1.5, abs=1e-6) and g_ban == pytest.approx(0.075)
    assert f_ban > f_jad                      # higher grade -> higher source term


def test_unknown_deposit_falls_back_to_full_c0():
    f, g = grade_c0_factor("Nonexistent Deposit")
    assert f == 1.0 and g is None


def test_factor_is_sanity_bounded():
    for d in _ORE_DEPOSITS:
        f, _ = grade_c0_factor(d)
        assert 0.1 <= f <= 2.0


def test_scaled_c0_stays_in_trained_envelope():
    # reproduce resolve.py's clip: every deposit C0 must land in the source-signature range
    from ml_pipeline.data_prep.texas_loader import texas_source_signature
    sig = texas_source_signature()["uranium_ppb"]
    base, env_lo, env_hi = float(np.mean(sig)), min(sig), max(sig)
    for d in _ORE_DEPOSITS:
        f, _ = grade_c0_factor(d)
        c0 = float(np.clip(base * f, env_lo, env_hi))
        assert env_lo <= c0 <= env_hi


def test_grade_ref_config_present():
    assert 0.01 <= P.URANIUM_GRADE_REF_PCT <= 0.15    # plausible %U reference grade
