"""
ml_pipeline.data_prep.ore_grades  (Phase-2 D4 -- grade-scaled uranium source C0)
================================================================================
Module 2 gives every surveyed deposit the SAME "full Texas-derived" uranium
source concentration C0. But the Singhbhum ore is markedly lower grade than the
Texas roll-fronts that C0 was calibrated on, and the deposits differ from each
other. This scales the deposit C0 by the deposit's actual ore grade (IAEA UDEPO)
so a low-grade underground mine and a higher-grade one no longer leach identical
uranium.

  C0_deposit = clip( C0_texas * (grade_deposit / GRADE_REF),  env_lo, env_hi )

  * grade_deposit -- midpoint of the deposit's UDEPO grade class (%U).
  * GRADE_REF     -- the Texas ISR reference grade the Texas-derived C0 encodes
                     (P.URANIUM_GRADE_REF_PCT, %U).
  * [env_lo,env_hi] -- the uranium source-signature range the surrogate was
                     TRAINED on. Clipping there means the scaled C0 is always
                     inside the model's support -> NO retrain, no envelope
                     violation (the whole point of doing this at serve time).

First-order linear grade->concentration scaling: at fixed leaching chemistry the
mobilized U roughly tracks ore grade. Deliberately simple; the grade classes are
coarse bins, so a fancier law would be false precision.

UDEPO grades are %U (uranium metal). Texas ISR ore ~0.05-0.10% U3O8 = 0.04-0.08%
U; GRADE_REF defaults to 0.05% U (the class the Texas midpoint sits in). Both
sides are %U -> the ratio is unit-consistent.
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

from ml_pipeline.config import parameters as P

REPO_ROOT = Path(__file__).resolve().parents[2]
UDEPO_XLSX = REPO_ROOT / "Datasets" / "udepo_uranium_deposits.xlsx"

_NUM = re.compile(r"\d+\.?\d*")
# Map each ore_loader deposit -> the UDEPO base-deposit entry to read grade from.
# (Prefer the base name over deeper/satellite extensions like "Jaduguda North" /
#  "Narwapahar Deeper", which are separate higher-grade UDEPO rows.)
_ALIASES = {"turamdih": "Turamdih West-East-South"}


def _parse_grade(text: str):
    """"≥0.01 - <0.05" -> (0.01, 0.05, 0.03). None if unparseable."""
    nums = [float(x) for x in _NUM.findall(str(text))]
    if len(nums) >= 2:
        lo, hi = nums[0], nums[1]
        return lo, hi, 0.5 * (lo + hi)
    if len(nums) == 1:
        return nums[0], nums[0], nums[0]
    return None


@functools.lru_cache(maxsize=1)
def _grades() -> dict:
    """UDEPO deposit-name(lower) -> (lo, hi, mid) grade in %U, uranium rows only."""
    import pandas as pd
    import warnings
    warnings.filterwarnings("ignore")
    df = pd.read_excel(UDEPO_XLSX, header=8).dropna(how="all")
    out = {}
    for _, row in df.iterrows():
        name = str(row.get("Deposit Name", "")).strip()
        commodity = str(row.get("Main Commodity", ""))
        if not name or "uranium" not in commodity.lower():
            continue
        g = _parse_grade(row.get("Grade Range", ""))
        if g is not None:
            out[name.lower()] = g
    return out


def deposit_grade_pct(deposit_name: str):
    """Midpoint ore grade (%U) for an ore_loader deposit name, or None if no
    UDEPO match. Exact match first, then the aliased base entry, then a unique
    prefix match (so "Jaduguda" hits "Jaduguda", never "Jaduguda North")."""
    if not deposit_name:
        return None
    grades = _grades()
    key = deposit_name.strip().lower()
    if key in grades:
        return grades[key][2]
    alias = _ALIASES.get(key)
    if alias and alias.lower() in grades:
        return grades[alias.lower()][2]
    # unique prefix match, shortest name wins (the base deposit, not extensions)
    hits = sorted((n for n in grades if n.startswith(key)), key=len)
    return grades[hits[0]][2] if hits else None


def grade_c0_factor(deposit_name: str) -> tuple[float, float | None]:
    """(multiplier, grade_pct) for a deposit's uranium C0. Multiplier is the
    grade ratio vs GRADE_REF, sanity-bounded; envelope clipping is the caller's
    job (it owns the trained C0 range). Falls back to (1.0, None) -- full Texas
    C0 -- for a deposit with no UDEPO grade."""
    grade = deposit_grade_pct(deposit_name)
    if grade is None:
        return 1.0, None
    factor = grade / P.URANIUM_GRADE_REF_PCT
    return float(min(max(factor, 0.1), 2.0)), grade


if __name__ == "__main__":
    print(f"GRADE_REF = {P.URANIUM_GRADE_REF_PCT} %U | UDEPO uranium rows: {len(_grades())}")
    for d in ["Jaduguda", "Bhatin", "Narwapahar", "Turamdih", "Banduhurang",
              "Mohuldih", "Bagjata"]:
        f, g = grade_c0_factor(d)
        print(f"  {d:12s} grade={g!s:>5} %U  ->  C0 x{f:.2f}")
