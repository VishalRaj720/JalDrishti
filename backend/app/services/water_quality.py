"""Multi-parameter drinking-water assessment against IS 10500:2012.

WHY THIS EXISTS
---------------
The 2026-08-24 audit found that `water_samples` carries twenty determinands at
99-100 % coverage and that exactly one of them — `uranium_ppb` — drove any logic
in the product. pH, EC, TDS, hardness, nitrate, fluoride, chloride, sulphate,
calcium, magnesium, sodium, potassium, phosphate, bicarbonate and carbonate were
ingested, stored, spatially joined to blocks, and then read by nothing.

That is a real shortfall against the project's first objective, which is to
assess *water-quality degradation* and aquifer vulnerability — not uranium
alone. A resident whose well is fine for uranium and carries 3.1 mg/L fluoride
was being told "Low concern".

Nothing here is modelled, predicted or fitted. Every number is a laboratory
measurement compared with a published limit, which is why this module sits
beside the physics rather than inside it: it needs no retrain, no calibration
and no uncertainty band, and it must never be described as a prediction.

THE STANDARD
------------
IS 10500:2012 *Drinking Water — Specification* (Bureau of Indian Standards),
second revision, with Amendment No. 2 (2015) which introduced the uranium
limit. Two columns, and the distinction matters when reporting:

  * **Acceptable limit** — what water should meet.
  * **Permissible limit in the absence of an alternate source** — tolerated only
    where no better source exists. Several determinands carry "No relaxation",
    meaning the acceptable limit is absolute.

Uranium's 0.03 mg/L (30 ppb) is the same threshold the rest of this platform
already uses in `public_risk.URANIUM_LIMIT_PPB`, and it agrees with the WHO
provisional guideline value. The constant is imported rather than re-typed so
the two surfaces cannot drift apart.

WHAT IS DELIBERATELY NOT DONE
-----------------------------
**No composite Water Quality Index is the headline.** The weighted-arithmetic
WQI is common in the Indian groundwater literature, and it is offered here — but
as a clearly-labelled secondary figure with its weights returned in the same
response, never as the primary answer. The reason is that a single 0-100 score
silently trades a fluoride exceedance against good calcium, and the resulting
number implies a precision that the underlying weights do not have. The primary
answer is factual: which determinands exceed which limit, by how much.

**"Not tested" is never "safe".** A determinand with no measurement returns
`not_tested` and is counted separately everywhere. This is the same rule the
uranium surface already follows, and it is the single most misleading thing this
module could get wrong.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

# The uranium threshold is owned by the public-risk surface. Imported, not
# repeated: two copies of a safety limit is one copy waiting to go stale.
from app.api.v1.public_risk import URANIUM_LIMIT_PPB

#: Status vocabulary. Ordered worst-first for `worst_status`.
STATUS_ABOVE_PERMISSIBLE = "above_permissible"
STATUS_ABOVE_ACCEPTABLE = "above_acceptable"
STATUS_ACCEPTABLE = "acceptable"
STATUS_NO_LIMIT = "no_limit"
STATUS_NOT_TESTED = "not_tested"

#: Worst first. `not_tested` sorts last but is NOT "best" — it is absence of
#: evidence, and callers must report it separately rather than folding it in.
_SEVERITY = [
    STATUS_ABOVE_PERMISSIBLE,
    STATUS_ABOVE_ACCEPTABLE,
    STATUS_ACCEPTABLE,
    STATUS_NO_LIMIT,
    STATUS_NOT_TESTED,
]

_BIS = "IS 10500:2012"
_BIS_A2 = "IS 10500:2012 Amendment No. 2 (2015)"


@dataclass(frozen=True)
class Determinand:
    """One measured quantity and the limit it is judged against.

    `permissible is None` with an `acceptable` value set means the standard says
    **"No relaxation"** — there is no tolerated band above the acceptable limit.
    That is materially different from "we do not know the permissible limit",
    so it is spelled out in `relaxation` rather than inferred from a null.
    """
    key: str
    column: Optional[str]          # None => derived, see `derive`
    label: str
    unit: str
    acceptable: Optional[float]
    permissible: Optional[float]
    source: str
    #: "max"   -> exceedance above a ceiling
    #: "range" -> outside [lo, hi], used for pH, which fails in both directions
    kind: str = "max"
    lo: Optional[float] = None
    hi: Optional[float] = None
    relaxation: str = ""
    note: str = ""
    #: Health-significant determinands. Aesthetic ones (hardness, chloride,
    #: TDS) matter for acceptability and corrosion, not toxicity, and the
    #: citizen wording must not treat the two the same.
    health: bool = False

    def classify(self, value: Optional[float]) -> str:
        if value is None:
            return STATUS_NOT_TESTED
        if self.kind == "range":
            if self.lo is not None and value < self.lo:
                return STATUS_ABOVE_ACCEPTABLE
            if self.hi is not None and value > self.hi:
                return STATUS_ABOVE_ACCEPTABLE
            return STATUS_ACCEPTABLE
        if self.acceptable is None:
            return STATUS_NO_LIMIT
        if self.permissible is not None and value > self.permissible:
            return STATUS_ABOVE_PERMISSIBLE
        if value > self.acceptable:
            # "No relaxation" determinands have no permissible band, so any
            # exceedance of the acceptable limit is the worst class there is.
            return (STATUS_ABOVE_ACCEPTABLE if self.permissible is not None
                    else STATUS_ABOVE_PERMISSIBLE)
        return STATUS_ACCEPTABLE

    def times_limit(self, value: Optional[float]) -> Optional[float]:
        """How many times the acceptable limit. `None` where meaningless.

        Not defined for pH: a two-sided range has no ratio that means anything,
        and returning one would invite it being charted alongside the others.
        """
        if value is None or self.kind == "range" or not self.acceptable:
            return None
        return round(value / self.acceptable, 2)


#: The registry. Ordered for display: health-significant first, then the
#: general/aesthetic set, then the measured-but-unregulated tail.
STANDARD: tuple[Determinand, ...] = (
    Determinand(
        key="uranium", column="uranium_ppb", label="Uranium", unit="ppb",
        acceptable=URANIUM_LIMIT_PPB, permissible=None, source=_BIS_A2,
        relaxation="No relaxation", health=True,
        note="0.03 mg/L. Agrees with the WHO provisional guideline value. "
             "This is the same limit the rest of the platform uses."),
    Determinand(
        key="fluoride", column="fluoride_mg_l", label="Fluoride", unit="mg/L",
        acceptable=1.0, permissible=1.5, source=_BIS, health=True,
        note="Above 1.5 mg/L over years causes dental and skeletal fluorosis. "
             "Endemic in parts of Jharkhand and unrelated to mining."),
    Determinand(
        key="nitrate", column="nitrate_mg_l", label="Nitrate (as NO3)",
        unit="mg/L", acceptable=45.0, permissible=None, source=_BIS,
        relaxation="No relaxation", health=True,
        note="Chiefly an infant health risk (methaemoglobinaemia). Usually "
             "indicates agricultural or sanitation contamination, not geology."),
    Determinand(
        key="arsenic", column="arsenic_ppb", label="Arsenic", unit="ppb",
        acceptable=10.0, permissible=50.0, source=_BIS, health=True,
        note="0.01 / 0.05 mg/L. NOT MEASURED in the CGWB dataset this platform "
             "carries — the column exists and is empty for all 397 samples, so "
             "every well reports `not_tested`. That is a monitoring gap, and "
             "the proposal names arsenic explicitly."),
    Determinand(
        key="iron", column="iron_ppm", label="Iron", unit="mg/L",
        acceptable=0.3, permissible=None, source=_BIS,
        relaxation="No relaxation",
        note="Also unmeasured in this dataset — 0 of 397 samples carry a value."),
    Determinand(
        key="ph", column="ph", label="pH", unit="pH units",
        acceptable=None, permissible=None, source=_BIS,
        kind="range", lo=6.5, hi=8.5, relaxation="No relaxation",
        note="Fails in both directions, so it is judged as a range. Acidic "
             "groundwater mobilises metals; that is why it is reported first "
             "among the general parameters."),
    Determinand(
        key="tds", column="tds_mg_l", label="Total dissolved solids",
        unit="mg/L", acceptable=500.0, permissible=2000.0, source=_BIS,
        note="Also one of the three NUREG-1569-inspired excursion indicators "
             "the engine screens on, though there it is compared against a "
             "site baseline rather than this drinking-water limit."),
    Determinand(
        key="hardness", column="total_hardness", label="Total hardness",
        unit="mg/L as CaCO3", acceptable=200.0, permissible=600.0, source=_BIS),
    Determinand(
        key="chloride", column="chloride_mg_l", label="Chloride", unit="mg/L",
        acceptable=250.0, permissible=1000.0, source=_BIS,
        note="The third excursion indicator. Same caveat as TDS."),
    Determinand(
        key="sulphate", column="sulphate_mg_l", label="Sulphate", unit="mg/L",
        acceptable=200.0, permissible=400.0, source=_BIS,
        note="The second excursion indicator, and the co-contaminant an "
             "alkaline ISR lixiviant would mobilise."),
    Determinand(
        key="calcium", column="calcium_mg_l", label="Calcium", unit="mg/L",
        acceptable=75.0, permissible=200.0, source=_BIS),
    Determinand(
        key="magnesium", column="magnesium_mg_l", label="Magnesium",
        unit="mg/L", acceptable=30.0, permissible=100.0, source=_BIS),
    Determinand(
        key="alkalinity", column=None, label="Total alkalinity",
        unit="mg/L as CaCO3", acceptable=200.0, permissible=600.0, source=_BIS,
        note="DERIVED, not measured: HCO3 x 50/61 + CO3 x 50/30, the standard "
             "conversion to CaCO3 equivalent. Flagged as derived wherever it is "
             "shown, on the same principle as the existing `tds_derived` column."),
    Determinand(
        key="turbidity", column="turbidity_ntu", label="Turbidity", unit="NTU",
        acceptable=1.0, permissible=5.0, source=_BIS,
        note="Unmeasured in this dataset — 0 of 397 samples."),
    # Measured, and the standard sets no drinking-water limit for them. Kept
    # visible rather than dropped: a determinand that was analysed and has no
    # limit is a different fact from one nobody measured, and hiding it would
    # make the panel look like the standard covers everything it reports.
    Determinand(
        key="ec", column="ec_us_cm", label="Electrical conductivity",
        unit="uS/cm", acceptable=None, permissible=None, source=_BIS,
        note="IS 10500 regulates TDS rather than conductivity. Reported "
             "because it is measured and is the field proxy for TDS."),
    Determinand(
        key="sodium", column="sodium_mg_l", label="Sodium", unit="mg/L",
        acceptable=None, permissible=None, source=_BIS,
        note="No IS 10500 drinking-water limit."),
    Determinand(
        key="potassium", column="potassium_mg_l", label="Potassium",
        unit="mg/L", acceptable=None, permissible=None, source=_BIS,
        note="No IS 10500 drinking-water limit."),
    Determinand(
        key="phosphate", column="phosphate_mg_l", label="Phosphate",
        unit="mg/L", acceptable=None, permissible=None, source=_BIS,
        note="No IS 10500 drinking-water limit."),
)

BY_KEY: dict[str, Determinand] = {d.key: d for d in STANDARD}

#: Columns this module reads. Used to build the SELECT, so adding a determinand
#: above is the only edit needed.
SAMPLE_COLUMNS: tuple[str, ...] = tuple(
    dict.fromkeys([d.column for d in STANDARD if d.column]
                  + ["bicarbonate_mg_l", "carbonate_mg_l"]))

# Equivalent-weight conversions to CaCO3. CaCO3 eq. wt 50; HCO3 61; CO3 30.
_HCO3_TO_CACO3 = 50.0 / 61.0
_CO3_TO_CACO3 = 50.0 / 30.0


def derive_alkalinity(row: dict[str, Any]) -> Optional[float]:
    """Total alkalinity as CaCO3 from bicarbonate and carbonate.

    Returns None if BOTH are missing. If only one is present the other is taken
    as zero, which is the standard field assumption — carbonate is negligible
    below about pH 8.3 — and the result is still flagged `derived` so a reader
    knows it was computed rather than analysed.
    """
    hco3 = row.get("bicarbonate_mg_l")
    co3 = row.get("carbonate_mg_l")
    if hco3 is None and co3 is None:
        return None
    return round((hco3 or 0.0) * _HCO3_TO_CACO3 + (co3 or 0.0) * _CO3_TO_CACO3, 1)


def value_for(d: Determinand, row: dict[str, Any]) -> Optional[float]:
    if d.column is None:
        return derive_alkalinity(row) if d.key == "alkalinity" else None
    v = row.get(d.column)
    return None if v is None else float(v)


def worst_status(statuses: Iterable[str]) -> str:
    """The most severe status present, or `not_tested` if nothing was measured."""
    present = set(statuses)
    for s in _SEVERITY:
        if s in present:
            return s
    return STATUS_NOT_TESTED


def assess_sample(row: dict[str, Any]) -> dict[str, Any]:
    """One sample -> every determinand classified, plus a factual summary.

    The summary deliberately carries `tested` alongside the counts: "0
    exceedances" means something entirely different at 15 determinands tested
    than at 2, and a caller that sees only the exceedance count cannot tell.
    """
    params = []
    for d in STANDARD:
        v = value_for(d, row)
        status = d.classify(v)
        params.append({
            "key": d.key, "label": d.label, "unit": d.unit,
            "value": v, "status": status,
            "acceptable": d.acceptable, "permissible": d.permissible,
            "range": [d.lo, d.hi] if d.kind == "range" else None,
            "times_limit": d.times_limit(v),
            "derived": d.column is None,
            "health": d.health,
            "relaxation": d.relaxation,
            "source": d.source,
            "note": d.note,
        })

    exceed = [p for p in params
              if p["status"] in (STATUS_ABOVE_ACCEPTABLE, STATUS_ABOVE_PERMISSIBLE)]
    tested = [p for p in params if p["status"] != STATUS_NOT_TESTED]
    regulated_tested = [p for p in tested if p["status"] != STATUS_NO_LIMIT]

    # The single most useful sentence: not a score, but which determinand is
    # driving the classification. `times_limit` breaks ties so the worst
    # relative exceedance leads, and pH (no ratio) sorts last among equals.
    driver = None
    if exceed:
        driver = sorted(
            exceed,
            key=lambda p: (p["status"] != STATUS_ABOVE_PERMISSIBLE,
                           -(p["times_limit"] or 0)))[0]

    return {
        "parameters": params,
        "summary": {
            "status": worst_status(p["status"] for p in regulated_tested),
            "tested": len(tested),
            "regulated_tested": len(regulated_tested),
            "not_tested": len(params) - len(tested),
            "exceedances": len(exceed),
            "above_permissible": sum(
                1 for p in exceed if p["status"] == STATUS_ABOVE_PERMISSIBLE),
            "health_exceedances": sum(1 for p in exceed if p["health"]),
            "driver": None if driver is None else {
                "key": driver["key"], "label": driver["label"],
                "value": driver["value"], "unit": driver["unit"],
                "times_limit": driver["times_limit"],
                "status": driver["status"],
            },
            "exceeded": [p["key"] for p in exceed],
        },
    }


# ── The secondary, clearly-labelled composite ────────────────────────
#
# Weighted-arithmetic WQI, as used widely in Indian groundwater assessment
# (Brown et al. 1972; applied in the CGWB/NAQUIM literature). Included because
# one number is genuinely easier to read on a map than fifteen, and excluded
# from the headline because that one number hides which determinand failed.
#
# Weights are inverse-proportional to the standard's own limit, which is the
# published construction and keeps the weighting out of this project's hands —
# there is no analyst judgement encoded here. They are returned with the score
# so a reader can check them, exactly as `/data-gaps/recommendations` does.

#: WQI is computed only over determinands with a one-sided limit that this
#: dataset actually measures. pH is excluded (two-sided; the standard WQI
#: handling of pH uses an ideal value of 7 and is a further assumption), and so
#: are the unmeasured and unregulated ones.
WQI_KEYS = ("uranium", "fluoride", "nitrate", "tds", "hardness",
            "chloride", "sulphate", "calcium", "magnesium")


def wqi_weights() -> dict[str, dict[str, Any]]:
    raw = {k: 1.0 / BY_KEY[k].acceptable for k in WQI_KEYS}
    total = sum(raw.values())
    return {k: {"weight": round(v / total, 5),
                "standard": BY_KEY[k].acceptable,
                "unit": BY_KEY[k].unit,
                "why": f"1/{BY_KEY[k].acceptable:g}, normalised"}
            for k, v in raw.items()}


def wqi(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Weighted-arithmetic WQI, or None if too little was measured.

    Returns None rather than a partial score when fewer than 60 % of the
    contributing determinands are present: a WQI computed over three of nine
    parameters is not comparable with one computed over nine, and publishing
    both on the same colour scale would be the misleading part.
    """
    w = wqi_weights()
    used, num, denom = [], 0.0, 0.0
    contrib: dict[str, float] = {}
    for k in WQI_KEYS:
        d, v = BY_KEY[k], value_for(BY_KEY[k], row)
        if v is None:
            continue
        used.append(k)
        q = 100.0 * v / d.acceptable          # quality rating, ideal value 0
        contrib[k] = w[k]["weight"] * q
        num += contrib[k]
        denom += w[k]["weight"]
    if denom == 0 or len(used) < 0.6 * len(WQI_KEYS):
        return None
    score = num / denom
    if score <= 25:
        band = "Excellent"
    elif score <= 50:
        band = "Good"
    elif score <= 75:
        band = "Poor"
    elif score <= 100:
        band = "Very poor"
    else:
        band = "Unsuitable for drinking"
    return {
        "score": round(score, 1),
        "band": band,
        "parameters_used": used,
        "parameters_possible": list(WQI_KEYS),
        "coverage": round(len(used) / len(WQI_KEYS), 2),
        # WHICH DETERMINAND THE SCORE ACTUALLY IS.
        #
        # Inverse-limit weighting is the published construction and it has a
        # property that misleads anyone reading only the band: the weight is
        # 1/limit, so the determinand with the SMALLEST limit dominates.
        # Fluoride's limit is 1.0 mg/L against hardness at 200, so fluoride
        # carries ~89 % of the weight -- and a well at 1.43 mg/L fluoride, which
        # is BELOW its permissible limit of 1.5, scores 132.7: "Unsuitable for
        # drinking".
        #
        # Found by reading a real well (Dasokhap, Hazaribagh) on the finished
        # screen, not by inspecting the formula. The band is not wrong by the
        # literature's definition; it is unreadable without knowing what produced
        # it. So the dominant contributor ships WITH the score.
        "dominated_by": (None if not contrib else {
            "key": max(contrib, key=lambda k: contrib[k]),
            "label": BY_KEY[max(contrib, key=lambda k: contrib[k])].label,
            "share": round(
                contrib[max(contrib, key=lambda k: contrib[k])] / num, 3)
                if num > 0 else None,
            "why": (
                "weight is 1/limit, and this determinand has the smallest limit "
                "in the set, so it carries most of the score"),
        }),
        "scale": "0 best. <=25 Excellent, <=50 Good, <=75 Poor, "
                 "<=100 Very poor, >100 Unsuitable for drinking.",
        "caveat": (
            "Secondary figure, weighted by 1/limit -- so the determinand with "
            "the smallest limit dominates. A well can read 'Unsuitable for "
            "drinking' on one determinand that is still below its permissible "
            "limit. The per-parameter table, not this number, is the finding."),
    }


def standard_document() -> dict[str, Any]:
    """The whole standard as data, for the Methods page and for audit.

    Published on the same principle as `GET /ml/assumptions`: a threshold that
    decides what a citizen is told should be readable by the citizen.
    """
    return {
        "standard": "IS 10500:2012 Drinking Water - Specification (BIS), "
                    "second revision, with Amendment No. 2 (2015)",
        "columns": {
            "acceptable": "What water should meet.",
            "permissible": "Tolerated only where no alternate source exists. "
                           "'No relaxation' means there is no such band.",
        },
        "determinands": [{
            "key": d.key, "label": d.label, "unit": d.unit,
            "acceptable": d.acceptable, "permissible": d.permissible,
            "range": [d.lo, d.hi] if d.kind == "range" else None,
            "relaxation": d.relaxation, "health": d.health,
            "measured": d.column is not None,
            "derived": d.column is None,
            "source": d.source, "note": d.note,
        } for d in STANDARD],
        "wqi_weights": wqi_weights(),
        "not_tested_rule": (
            "A determinand with no measurement is reported as 'not tested' and "
            "counted separately. It is never folded into 'acceptable' - absence "
            "of evidence is a monitoring gap, not a clean result."),
        "what_this_is": (
            "Laboratory measurements from government groundwater sampling, "
            "compared against a published national standard. Nothing here is "
            "modelled or predicted."),
    }
