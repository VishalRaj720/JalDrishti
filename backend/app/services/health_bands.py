"""One banding rule for every citizen-facing surface.

WHY THIS MODULE EXISTS.

The rule for "how concerning is the groundwater here" lived in
`api/v1/public_risk.py` and was reimplemented, differently, in
`api/v1/citizen.py`. Both are read by the same resident, about the same block,
on the same afternoon:

  * `/public/risk/*` banded on uranium, nitrate AND fluoride (since 2026-08-25).
  * `/citizen/my-area` banded on URANIUM ALONE, with its own ladder and its own
    prose.

Uranium exceeds its limit at zero of Jharkhand's 342 uranium-tested wells, while
nitrate exceeds at 22 and fluoride at 32. So the two surfaces did not merely
differ in wording — a block over the fluoride limit read "High concern" on the
public map and "Low concern" on the page a resident opens to check their own
water, and both were faithfully reporting the rule they had been given. The
alert scanner's own docstring already named this as "the same defect as the
uranium-only citizen band", because the identical mistake had made the alerts
table match zero rows for months.

A second, quieter copy of the same problem: three `/public/risk` handlers
computed the multi-determinand band in SQL and then explained it with
`_explain`, a uranium-only prose helper. A block banded "High concern" on fluoride carried the
sentence "Uranium in the 2 wells sampled here was well below the 30 ppb safe
limit" directly beneath the words "High concern".

So the rule — the limits, the SQL that applies them, and the plain-language
reading of the result — lives here, once, and every surface imports it. A rule
that can be stated in only one place cannot drift into two.

WHAT IS DELIBERATELY NOT HERE. Arsenic and iron are health determinands with no
data in the CGWB file (0 of 397 samples). They are absent from the band
expression rather than defaulted to a pass — a block whose arsenic was never
measured must not be banded on the assumption that it is clean. They surface
through `UNTESTED` instead, which is how a "Low concern" block still gets told
what nobody looked for.
"""
from typing import Any, Mapping

# BIS/WHO drinking-water limit for uranium, the same threshold the rest of the
# platform uses. Bands are plain language on purpose (design §4.4): a citizen
# screen shows "Moderate concern", never a P10-P90 band.
URANIUM_LIMIT_PPB = 30.0

# ── Health limits, IS 10500:2012 ─────────────────────────────────────
#
# Kept in step with `services/water_quality.py`, which owns the full
# eighteen-determinand registry. Only the HEALTH-significant ones band a block:
# hardness, alkalinity and TDS exceed at two-thirds of Jharkhand's wells and are
# hard-rock aquifer chemistry, not contamination. Banding a village "High
# concern" for hard water would bury the wells that carry a real nitrate load.
NITRATE_LIMIT_MG_L = 45.0     # "No relaxation" — any exceedance is the worst class
FLUORIDE_ACCEPTABLE_MG_L = 1.0
FLUORIDE_PERMISSIBLE_MG_L = 1.5

#: Columns every banding query must compute. Kept as one string so the queries
#: that band cannot drift apart. Assumes the water-samples table is aliased `s`.
HEALTH_MAXES = """
                   max(s.uranium_ppb)    AS max_u,
                   max(s.nitrate_mg_l)   AS max_no3,
                   max(s.fluoride_mg_l)  AS max_f,
                   count(s.uranium_ppb)  AS n_u,
                   count(s.nitrate_mg_l) AS n_no3,
                   count(s.fluoride_mg_l) AS n_f,
                   count(s.uranium_ppb)
                     + count(s.nitrate_mg_l)
                     + count(s.fluoride_mg_l) AS health_tests
"""

# THE BAND, ACROSS EVERY MEASURED HEALTH DETERMINAND.
#
# Until 2026-08-25 this read `max_u` alone, and that was actively misleading:
# uranium exceeds its limit at ZERO of 342 tested wells in Jharkhand, while
# nitrate exceeds at 22 (peak 121 mg/L, 2.7x the limit) and fluoride at 32. The
# public map therefore told residents of those blocks "Low concern" on the
# strength of the one determinand that never fires.
#
# `Not tested` is a distinct band from `No data` and from `Low concern`: a block
# with wells and samples but no health determinand analysed has not been shown
# to be safe. Neither may ever render green.
#
# THE `samples` TERM WAS ADDED 2026-08-26, AND IT MAKES THE SECOND BRANCH
# REACHABLE FOR THE FIRST TIME. It used to read `health_tests = 0 AND max_u IS
# NULL`, but `health_tests` counts non-null uranium results among other things,
# so `health_tests = 0` already implies `max_u IS NULL` — the 'Not tested'
# branch was dead code, and every query returned 'No data' for a block that had
# been sampled and simply never analysed. `/at` papered over it in Python; the
# other four handlers did not, so the same block was 'Not tested' on one
# endpoint and 'No data' on the next. The distinguishing fact is whether any
# sample exists at all, which is what `samples` carries. Every query that
# interpolates this expression must therefore expose `samples` in scope.
BANDS = """
    CASE
        WHEN health_tests = 0 AND samples = 0   THEN 'No data'
        WHEN health_tests = 0                   THEN 'Not tested'
        WHEN max_u   >= :limit                  THEN 'High concern'
        WHEN max_no3 >  :no3_limit              THEN 'High concern'
        WHEN max_f   >  :f_permissible          THEN 'High concern'
        WHEN max_f   >  :f_acceptable           THEN 'Moderate concern'
        WHEN max_u   >= :limit * 0.5            THEN 'Moderate concern'
        ELSE                                         'Low concern'
    END
"""

#: Which determinand set the band, so a citizen is told WHAT is wrong rather
#: than only that something is. Mirrors the CASE above, in the same order.
DRIVER = """
    CASE
        WHEN health_tests = 0                   THEN NULL
        WHEN max_u   >= :limit                  THEN 'uranium'
        WHEN max_no3 >  :no3_limit              THEN 'nitrate'
        WHEN max_f   >  :f_permissible          THEN 'fluoride'
        WHEN max_f   >  :f_acceptable           THEN 'fluoride'
        WHEN max_u   >= :limit * 0.5            THEN 'uranium'
        ELSE                                         NULL
    END
"""

#: Which health determinands were never analysed here.
#:
#: Arsenic and iron are 0 % populated statewide, so they are listed
#: unconditionally — no block in Jharkhand has been cleared for them, and a
#: "Low concern" band that silently means "clean for the three we happened to
#: measure" is the failure LIMITATIONS.md section 3 exists to prevent.
UNTESTED = """
    array_remove(ARRAY[
        CASE WHEN n_u   = 0 THEN 'uranium'  END,
        CASE WHEN n_no3 = 0 THEN 'nitrate'  END,
        CASE WHEN n_f   = 0 THEN 'fluoride' END,
        'arsenic', 'iron'
    ], NULL)
"""


def band_params() -> dict:
    """Every banding query binds the same four limits."""
    return {
        "limit": URANIUM_LIMIT_PPB,
        "no3_limit": NITRATE_LIMIT_MG_L,
        "f_acceptable": FLUORIDE_ACCEPTABLE_MG_L,
        "f_permissible": FLUORIDE_PERMISSIBLE_MG_L,
    }


def join_and(items: list[str]) -> str:
    """'a', 'a and b', 'a, b and c' — this text is read by the public."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def explain_multi(d: Mapping[str, Any], wells: int) -> str:
    """Plain-language reading of a multi-determinand band.

    Names the substance that set the band. "High concern" with no explanation
    of WHAT is high is not actionable — a resident can boil water for bacteria
    but cannot boil out fluoride, and the advice differs by determinand.
    """
    band, driver = d.get("band"), d.get("band_driver")
    w = "well" if wells == 1 else "wells"

    if band == "No data":
        return ("No groundwater samples have been collected here yet, so there "
                "is nothing to report. That is a gap in monitoring, not a clean "
                "result.")
    if band == "Not tested":
        return ("Samples were collected here but not analysed for any "
                "drinking-water health substance. That is a gap in testing, not "
                "a clean result.")

    detail = {
        "uranium": (f"uranium at {d.get('max_uranium_ppb')} ppb against a "
                    f"{URANIUM_LIMIT_PPB:g} ppb limit"),
        "nitrate": (f"nitrate at {d.get('max_nitrate_mg_l')} mg/L against a "
                    f"{NITRATE_LIMIT_MG_L:g} mg/L limit"),
        "fluoride": (f"fluoride at {d.get('max_fluoride_mg_l')} mg/L against a "
                     f"{FLUORIDE_ACCEPTABLE_MG_L:g} mg/L limit "
                     f"({FLUORIDE_PERMISSIBLE_MG_L:g} where no other source "
                     f"exists)"),
    }.get(driver or "", "")

    if band == "High concern":
        advice = {
            "nitrate": ("Nitrate is mainly a risk to infants under six months. "
                        "Do not use this water to make formula feed."),
            "fluoride": ("Long-term fluoride exposure causes dental and skeletal "
                         "fluorosis. Boiling does not remove it."),
            "uranium": "Boiling does not remove uranium.",
        }.get(driver or "", "")
        return (f"Testing of the {wells} {w} here found {detail}. {advice} "
                f"Contact your block water office about testing and about an "
                f"alternative supply.").strip()

    if band == "Moderate concern":
        return (f"Testing of the {wells} {w} here found {detail}. It is not over "
                f"the limit where no other source exists, but it is worth "
                f"watching and worth asking your block water office about.")

    # Name only what was ACTUALLY analysed. Saying "uranium, nitrate and
    # fluoride were all within limits" at a block where uranium was never
    # measured contradicts the gap sentence appended right after it, and the
    # reassuring half is the half a reader remembers.
    measured = [n for n, c in (("uranium", d.get("n_u")),
                               ("nitrate", d.get("n_no3")),
                               ("fluoride", d.get("n_f"))) if int(c or 0) > 0]
    return (f"{join_and(measured).capitalize()} in the {wells} {w} sampled here "
            f"{'was' if len(measured) == 1 else 'were'} within the "
            f"drinking-water limits.")


def describe(
    d: Mapping[str, Any], wells: int, samples: int,
) -> tuple[str, str, list[str]]:
    """The band, its plain-language reading, and what was never analysed.

    THE WHOLE COMPOSITION, in one place, because getting it right needs three
    steps that are each easy to forget individually:

    1. A block whose samples were never analysed for any health determinand is
       `Not tested`, not `No data`. It has wells, it has samples, and it still
       has no drinking-water result — telling a resident "no samples have been
       collected" while the same response reports two of them is the confidently
       wrong public statement this product exists not to make.
    2. The reading must name the determinand that set the band. A resident can
       act on "fluoride" and cannot act on "High concern".
    3. Whatever the band, the substances nobody measured are stated alongside
       it. This is the step that stops "Low concern" meaning "clean for the
       three we happened to look at".

    Returns `(band, explanation, untested)`. The band may differ from the one
    the SQL produced — see step 1 — so callers must use the returned value
    rather than the row's.
    """
    untested = list(d.get("untested_health") or [])
    health_tested = (int(d.get("n_u") or 0) + int(d.get("n_no3") or 0)
                     + int(d.get("n_f") or 0))
    band = str(d.get("band") or "No data")

    if samples and not health_tested:
        band = "Not tested"
        explanation = (
            f"The {wells} well{'' if wells == 1 else 's'} here have been sampled, "
            f"but none of those samples were analysed for uranium, nitrate or "
            f"fluoride. There is no drinking-water health result to report — "
            f"that is a gap in testing, not a clean result.")
    else:
        explanation = explain_multi(dict(d, band=band), wells)

    if untested and samples:
        explanation += (
            f" Not every substance was analysed here: no result for "
            f"{join_and(untested)}. A substance nobody measured has not been "
            f"shown to be safe.")

    return band, explanation, untested
