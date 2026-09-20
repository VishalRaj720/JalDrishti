"""Hydrochemical quality assurance of the measured record (R17).

WHAT THIS IS. Every major ion in the CGWB chemistry file is measured -- Ca,
Mg, Na, K on the cation side; HCO3, CO3, Cl, SO4, NO3, F on the anion side --
and until R17 nothing read them together. Read together they carry the one
piece of information about a laboratory analysis that the analysis itself
provides: whether it is internally consistent. Water is electrically neutral,
so the sum of cation equivalents must balance the sum of anion equivalents;
the charge-balance error

    CBE (%) = 100 * (sum cations - sum anions) / (sum cations + sum anions)

in milliequivalents per litre is the standard check on a complete analysis
(Hem 1985, "Study and interpretation of the chemical characteristics of
natural water", USGS WSP 2254, ch. 3; Freeze & Cherry 1979, Groundwater,
section 3.4; APHA Standard Methods 1030 E). Analyses within +/-5 % are
conventionally accepted; between 5 and 10 % they are questionable; beyond
10 % the analysis is suspect -- an ion was mis-measured, mis-reported, or an
unmeasured ion carries significant charge.

A second, weaker check: the sum of the measured ions in mg/L against the
measured electrical conductivity. For most fresh groundwaters the dissolved
solids are 0.55-0.75 times the conductivity in uS/cm (Hem 1985, p. 67), so a
ratio far outside that band points at a unit or transcription error.

WHAT IT IS NOT. A failed balance does NOT delete the sample and does NOT
remove its exceedance from the citizen band or the alert scan. A nitrate of
121 mg/L in an analysis whose cations and anions disagree by 12 % is still
the laboratory's reported nitrate; the imbalance means the analysis deserves
a re-run, not that the number is wrong in a known direction. So the result
is a FLAG carried with the sample -- on the water-quality surface, on the
Data & Gaps screen, and in the `confidence` block of any alert the sample
raises -- and the counts by class are a finding for the data-gap analysis.
`incomplete` (an ion missing, so the balance cannot be formed) is reported
separately from every failure class: absence of a test is never a result.

pH is not in the balance: H+ and OH- contribute negligibly between pH 6.5 and
8.5, the range every sample here falls in.

THE FINDING THIS PRODUCED, first run 2026-09-20 on the 397-sample CGWB 2023
file: 393 of 393 computable analyses balance within +/-3.2 % (median |CBE|
0.56 %). Routine laboratory data does not do that -- a few per cent of any
real batch fails at 10 %. Tested and consistent with one cause: SODIUM WAS
COMPUTED BY CHARGE DIFFERENCE. Re-deriving Na from the other ions reproduces
the reported value to a median 1.6 mg/L on integer-rounded data (65 % within
2 mg/L); total hardness likewise equals 2.497 Ca + 4.118 Mg within 5 % for
99 % of samples. So on this file the charge balance is a consistency of
construction, NOT an independent check on the analysis, and a count of zero
suspect analyses must not be read as evidence of laboratory quality.
`independence_check` in the summary reports the test so the surface says so.
The EC check (ion sum / EC, median 0.70) remains independent and passes.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: mg/L -> meq/L factors: |charge| / molar mass (g/mol). Molar masses from
#: IUPAC 2013 atomic weights, rounded to the precision the data carries.
CATIONS: dict[str, tuple[str, float]] = {
    # column                 (ion,   meq per mg)
    "calcium_mg_l":         ("Ca2+", 2 / 40.078),
    "magnesium_mg_l":       ("Mg2+", 2 / 24.305),
    "sodium_mg_l":          ("Na+",  1 / 22.990),
    "potassium_mg_l":       ("K+",   1 / 39.098),
}
ANIONS: dict[str, tuple[str, float]] = {
    "bicarbonate_mg_l":     ("HCO3-", 1 / 61.017),
    "carbonate_mg_l":       ("CO3 2-", 2 / 60.009),
    "chloride_mg_l":        ("Cl-",   1 / 35.453),
    "sulphate_mg_l":        ("SO4 2-", 2 / 96.06),
    "nitrate_mg_l":         ("NO3-",  1 / 62.004),   # reported as NO3
    "fluoride_mg_l":        ("F-",    1 / 18.998),
}
#: Ions that MUST be present to form a balance. Carbonate is all-zero in the
#: file (reported, not missing) and fluoride/nitrate are minor; the balance
#: is still formed if only those are absent, and the response says which
#: were treated as zero.
REQUIRED = ("calcium_mg_l", "magnesium_mg_l", "sodium_mg_l", "potassium_mg_l",
            "bicarbonate_mg_l", "chloride_mg_l", "sulphate_mg_l")

#: Conventional thresholds (Hem 1985; Freeze & Cherry 1979; APHA 1030 E).
CBE_ACCEPT_PCT = 5.0
CBE_FLAG_PCT = 10.0
#: TDS/EC ratio band for fresh groundwater (Hem 1985, p. 67); widened by a
#: margin because the ion sum omits silica and minor species.
EC_RATIO_LO, EC_RATIO_HI = 0.45, 0.90

CLASSES = ("balanced", "questionable", "suspect", "incomplete")


def charge_balance(sample: Mapping[str, Any]) -> dict[str, Any]:
    """The charge-balance error of one analysis, its class, and the ion sums.

    Returns `qa_class` in CLASSES. `incomplete` when a REQUIRED ion is
    missing; missing minor ions (NO3, F, CO3) are treated as zero and named
    in `assumed_zero`.
    """
    missing = [c for c in REQUIRED if sample.get(c) is None]
    if missing:
        return {"qa_class": "incomplete", "cbe_pct": None,
                "cations_meq_l": None, "anions_meq_l": None,
                "missing": missing, "assumed_zero": [],
                "note": "a required major ion is not reported, so no balance "
                        "can be formed -- this is absence of a test, not a failure"}
    assumed_zero = []
    cat = 0.0
    for col, (_, f) in CATIONS.items():
        v = sample.get(col)
        cat += float(v) * f if v is not None else 0.0
    an = 0.0
    for col, (_, f) in ANIONS.items():
        v = sample.get(col)
        if v is None:
            assumed_zero.append(col)
            continue
        an += float(v) * f
    total = cat + an
    if total <= 0:
        return {"qa_class": "incomplete", "cbe_pct": None,
                "cations_meq_l": round(cat, 4), "anions_meq_l": round(an, 4),
                "missing": [], "assumed_zero": assumed_zero,
                "note": "all reported ions are zero"}
    cbe = 100.0 * (cat - an) / total
    a = abs(cbe)
    cls = ("balanced" if a <= CBE_ACCEPT_PCT
           else "questionable" if a <= CBE_FLAG_PCT else "suspect")
    return {"qa_class": cls, "cbe_pct": round(cbe, 2),
            "cations_meq_l": round(cat, 4), "anions_meq_l": round(an, 4),
            "missing": [], "assumed_zero": assumed_zero,
            "thresholds": {"accept_pct": CBE_ACCEPT_PCT, "flag_pct": CBE_FLAG_PCT}}


def ec_consistency(sample: Mapping[str, Any]) -> dict[str, Any]:
    """Sum of measured ions (mg/L) against EC (uS/cm)."""
    ec = sample.get("ec_us_cm")
    if ec is None or float(ec) <= 0:
        return {"ec_ratio": None, "ec_class": "incomplete"}
    cols = list(CATIONS) + list(ANIONS)
    vals = [sample.get(c) for c in cols]
    if all(v is None for v in vals):
        return {"ec_ratio": None, "ec_class": "incomplete"}
    ions = sum(float(v) for v in vals if v is not None)
    ratio = ions / float(ec)
    ok = EC_RATIO_LO <= ratio <= EC_RATIO_HI
    return {"ec_ratio": round(ratio, 3), "ion_sum_mg_l": round(ions, 1),
            "ec_us_cm": float(ec),
            "ec_class": "consistent" if ok else "inconsistent",
            "band": [EC_RATIO_LO, EC_RATIO_HI]}


def assess(sample: Mapping[str, Any]) -> dict[str, Any]:
    """Both checks, one dict, for one sample row."""
    out = charge_balance(sample)
    out.update(ec_consistency(sample))
    return out


SAMPLE_SQL = """
    SELECT ws.id::text AS sample_id, ws.well_id::text AS well_id, ws.sampled_at,
           mw.name AS well_name, b.name AS block_name, d.name AS district_name,
           ws.ph, ws.ec_us_cm, ws.calcium_mg_l, ws.magnesium_mg_l, ws.sodium_mg_l,
           ws.potassium_mg_l, ws.bicarbonate_mg_l, ws.carbonate_mg_l,
           ws.chloride_mg_l, ws.sulphate_mg_l, ws.nitrate_mg_l, ws.fluoride_mg_l,
           ws.uranium_ppb
    FROM water_samples ws
    JOIN monitoring_wells mw ON mw.id = ws.well_id
    LEFT JOIN blocks b ON b.id = mw.block_id
    LEFT JOIN districts d ON d.id = b.district_id
    WHERE NOT ws.synthetic
"""


async def qa_for_sample_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        q = assess(r)
        out.append({"sample_id": r.get("sample_id"), "well_id": r.get("well_id"),
                    "well_name": r.get("well_name"), "block": r.get("block_name"),
                    "district": r.get("district_name"),
                    "sampled_at": r.get("sampled_at"), **q})
    return out


async def summary(db: AsyncSession, *, worst: int = 25) -> dict[str, Any]:
    """Counts by class over the whole measured record, the distribution of
    the error, and the worst analyses named -- for the Data & Gaps screen and
    the report's data-quality section."""
    rows = (await db.execute(text(SAMPLE_SQL))).mappings().all()
    per = await qa_for_sample_rows([dict(r) for r in rows])
    counts = {c: 0 for c in CLASSES}
    for p in per:
        counts[p["qa_class"]] += 1
    ec_counts = {"consistent": 0, "inconsistent": 0, "incomplete": 0}
    for p in per:
        ec_counts[p["ec_class"]] += 1
    cbes = sorted(p["cbe_pct"] for p in per if p["cbe_pct"] is not None)
    n = len(cbes)

    def pct(q: float) -> Optional[float]:
        if not n:
            return None
        i = min(max(int(round(q * (n - 1))), 0), n - 1)
        return cbes[i]

    per_district: dict[str, dict[str, int]] = {}
    for p in per:
        d = per_district.setdefault(p["district"] or "?", {c: 0 for c in CLASSES})
        d[p["qa_class"]] += 1
    named = sorted((p for p in per if p["cbe_pct"] is not None),
                   key=lambda p: -abs(p["cbe_pct"]))[:worst]
    indep = independence_check([dict(r) for r in rows])
    return {
        "independence_check": indep,
        "samples": len(per),
        "by_class": counts,
        "ec_by_class": ec_counts,
        "cbe_distribution": {"n": n, "p05": pct(0.05), "p25": pct(0.25),
                             "median": pct(0.5), "p75": pct(0.75), "p95": pct(0.95),
                             "mean_abs": (round(sum(abs(c) for c in cbes) / n, 2) if n else None),
                             "sign_bias": (round(sum(1 for c in cbes if c > 0) / n, 3) if n else None)},
        "by_district": per_district,
        "worst": [{k: p[k] for k in ("well_name", "block", "district", "cbe_pct",
                                     "qa_class", "ec_ratio", "ec_class",
                                     "cations_meq_l", "anions_meq_l")} for p in named],
        "thresholds": {"cbe_accept_pct": CBE_ACCEPT_PCT, "cbe_flag_pct": CBE_FLAG_PCT,
                       "ec_ratio_band": [EC_RATIO_LO, EC_RATIO_HI]},
        "method": {
            "charge_balance": "CBE % = 100 (sum cations - sum anions) / (sum cations + "
                              "sum anions), meq/L, cations Ca Mg Na K, anions HCO3 CO3 "
                              "Cl SO4 NO3 F",
            "classes": {"balanced": f"|CBE| <= {CBE_ACCEPT_PCT:g} %",
                        "questionable": f"{CBE_ACCEPT_PCT:g} < |CBE| <= {CBE_FLAG_PCT:g} %",
                        "suspect": f"|CBE| > {CBE_FLAG_PCT:g} %",
                        "incomplete": "a required major ion is not reported"},
            "references": ["Hem (1985) USGS Water-Supply Paper 2254, ch. 3",
                           "Freeze & Cherry (1979) Groundwater, section 3.4",
                           "APHA Standard Methods, 1030 E"],
            "policy": ("A flagged analysis is NOT excluded from the citizen band or "
                       "the alert scan: the imbalance says the analysis deserves a "
                       "re-run, not that a reported exceedance is wrong. The flag "
                       "travels with the sample instead."),
        },
    }


def independence_check(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Is the balance an independent check, or a consistency of construction?

    Re-derives sodium from the other ions (Na_meq = anions - Ca - Mg - K) and
    compares with the reported sodium; likewise total hardness from Ca and Mg.
    If sodium was measured, the residual scatters like an analytical error
    (several mg/L, both signs, a tail); if it was computed by difference, it
    sits within rounding of zero. The verdict is stated, with its numbers."""
    diffs: list[float] = []
    for r in rows:
        need = ("calcium_mg_l", "magnesium_mg_l", "potassium_mg_l", "sodium_mg_l",
                "bicarbonate_mg_l", "chloride_mg_l", "sulphate_mg_l")
        if any(r.get(c) is None for c in need):
            continue
        an = 0.0
        for col, (_, f) in ANIONS.items():
            v = r.get(col)
            an += float(v) * f if v is not None else 0.0
        cat_other = sum(float(r[c]) * CATIONS[c][1] for c in
                        ("calcium_mg_l", "magnesium_mg_l", "potassium_mg_l"))
        na_pred = (an - cat_other) / CATIONS["sodium_mg_l"][1]
        diffs.append(abs(float(r["sodium_mg_l"]) - na_pred))
    n = len(diffs)
    if not n:
        return {"tested": False}
    diffs.sort()
    within2 = sum(1 for d in diffs if d <= 2.0) / n
    median = diffs[n // 2]
    derived = within2 >= 0.5 and median <= 3.0
    return {
        "tested": True, "n": n,
        "sodium_vs_balance_median_abs_mg_l": round(median, 2),
        "sodium_within_2_mg_l_fraction": round(within2, 3),
        "sodium_likely_computed_by_difference": derived,
        "verdict": (
            "The reported sodium reproduces the value implied by charge balance "
            "to within rounding for most samples, so the balance is a consistency "
            "of construction and NOT an independent check on these analyses. A "
            "count of zero suspect analyses is not evidence of laboratory quality."
            if derived else
            "Sodium does not reproduce the balance-implied value, so the charge "
            "balance is an independent check on these analyses."),
    }
