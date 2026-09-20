"""Alert tiers and the structured explanation every alert carries (R17).

WHY THIS MODULE EXISTS. Until R17 an alert was a headline, a body of prose and
a `severity` of `info | warning | high`. The prose answered the questions a
reader has -- what happened, which substance, where, how bad, is this a
measurement or a model, how sure, what now -- but only in sentences, and only
where the author had remembered to. The report cannot show a decision-support
workflow as a diagram of prose. It can show it as a table of records with
seven named fields, and that is what this module produces.

THE TIERS ARE THE STANDARD'S, NOT OURS -- with one exception, labelled.
IS 10500:2012 already defines two limits per determinand: the *acceptable*
limit, and the *permissible limit in the absence of an alternate source*,
with "No relaxation" for nitrate, uranium and iron (any exceedance of the
acceptable limit is the worst class). `services/water_quality.py` classifies
every reading into exactly those classes. The ladder below maps them:

    notice    a modelled screening was published for the block (never observed)
    warning   observed: above *acceptable* but within *permissible*
              modelled: possible reach (P90, outside the central footprint),
                        shared shallow aquifer, or a modelled timetable passed
    alert     observed: above *permissible* (or above acceptable where the
                        standard allows no relaxation)
              modelled: the run's own excursion probability at the monitoring
                        ring is >= 0.5 within its horizon
    critical  observed ONLY: at or above CRITICAL_MULTIPLE x the limit that
              triggers `alert`, OR two or more health determinands over their
              limit at the same well.

`CRITICAL_MULTIPLE = 2.0` and the "two or more" rule are PROJECT-DEFINED.
IS 10500 has no third rung; the multiplier is the same one the R14 scanner
used to split `warning` from `high`. It is exposed in every explanation and in
the API's `tiers` legend so a reader can disagree with a number they can see.

A MODELLED RESULT CAN NEVER BE CRITICAL. No ISR mine exists; nothing has been
measured. `modelled_tier` cannot return it, and migration 0026 adds a CHECK
constraint so the database refuses the row if code ever tries.

Pure functions, no database: `tests/test_r17_alert_tiers.py` exercises the
ladder directly.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping, Optional

from app.services.water_quality import (STANDARD, STATUS_ABOVE_ACCEPTABLE,
                                        STATUS_ABOVE_PERMISSIBLE, Determinand)

TIERS: tuple[str, ...] = ("notice", "warning", "alert", "critical")
BASES: tuple[str, ...] = ("observed", "modelled")

#: PROJECT-DEFINED. Multiple of the alert-triggering limit at which an observed
#: exceedance becomes `critical`. Not from IS 10500.
CRITICAL_MULTIPLE = 2.0
#: PROJECT-DEFINED. Health determinands over their alert limit at one well for
#: `critical`. Not from IS 10500.
CRITICAL_MULTI_BREACH = 2
#: The run's excursion probability at the monitoring ring at or above which a
#: published screening is tiered `alert` rather than `notice`. Same value the
#: breach-due scan uses (`AlertService.BREACH_PROBABILITY_THRESHOLD`).
MODELLED_ALERT_PEX = 0.5

#: Legacy `severity` kept in step with the tier so older readers keep working.
SEVERITY_FOR_TIER = {"notice": "info", "warning": "warning",
                     "alert": "high", "critical": "high"}

#: Determinand-specific advice. Boiling concentrates nitrate rather than
#: removing it; uranium, fluoride and arsenic are not removed by boiling either.
ADVICE: dict[str, str] = {
    "uranium": "Boiling does not remove uranium.",
    "nitrate": ("Nitrate is mainly a risk to infants under six months. Do not "
                "use this water to make formula feed. Boiling concentrates it "
                "rather than removing it."),
    "fluoride": ("Long-term fluoride exposure causes dental and skeletal "
                 "fluorosis. Boiling does not remove it."),
    "arsenic": "Arsenic is a long-term poison and boiling does not remove it.",
    "iron": "",
}


def health_determinands() -> list[Determinand]:
    """The IS 10500 health set, in registry order (uranium, fluoride, nitrate,
    arsenic, iron). Single source of truth -- the scanner's SQL, the breach
    list and the tier ladder all read this."""
    return [d for d in STANDARD if d.health and d.column]


def alert_limit(d: Determinand) -> tuple[float, str]:
    """The limit whose exceedance means `alert`: the permissible limit where
    the standard tolerates a band above acceptable, else the acceptable limit
    (no relaxation)."""
    if d.permissible is not None:
        return float(d.permissible), "permissible"
    return float(d.acceptable), "acceptable (no relaxation)"


def breaches_for_sample(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every health determinand this sample is over the ACCEPTABLE limit on,
    worst first. Each entry carries the IS 10500 class, both limits, and the
    ratio to the alert-triggering limit that the tier ladder reads.

    Arsenic and iron are included although the CGWB file carries no values
    for either -- the day a laboratory result arrives, the alert fires without
    anybody remembering to come back and add it here.
    """
    out: list[dict[str, Any]] = []
    for d in health_determinands():
        v = row.get(d.column)
        if v is None:
            continue
        v = float(v)
        status = d.classify(v)
        if status not in (STATUS_ABOVE_ACCEPTABLE, STATUS_ABOVE_PERMISSIBLE):
            continue
        lim, lim_kind = alert_limit(d)
        out.append({
            "key": d.column, "determinand": d.key, "label": d.key,
            "unit": d.unit, "value": v, "status": status,
            "acceptable": float(d.acceptable), "permissible": d.permissible,
            "limit": lim, "limit_kind": lim_kind,
            "times_limit": round(v / lim, 3),
            "times_acceptable": d.times_limit(v),
            "standard": d.source, "advice": ADVICE.get(d.key, ""),
        })
    out.sort(key=lambda b: (-(b["status"] == STATUS_ABOVE_PERMISSIBLE),
                            -b["times_limit"]))
    return out


def observed_tier(breaches: list[dict[str, Any]]) -> tuple[str, str]:
    """(tier, rule) for a set of observed breaches at one well."""
    if not breaches:
        raise ValueError("no breach -- nothing to tier")
    over_alert = [b for b in breaches if b["status"] == STATUS_ABOVE_PERMISSIBLE]
    worst = max(b["times_limit"] for b in over_alert) if over_alert else 0.0
    if over_alert and worst >= CRITICAL_MULTIPLE:
        return "critical", (f"{worst:.2g}x the {over_alert[0]['limit_kind']} limit "
                            f"(project-defined threshold: >= {CRITICAL_MULTIPLE:g}x)")
    if len(over_alert) >= CRITICAL_MULTI_BREACH:
        names = ", ".join(b["label"] for b in over_alert)
        return "critical", (f"{len(over_alert)} health determinands over their limit "
                            f"at one well ({names}); project-defined rule: "
                            f">= {CRITICAL_MULTI_BREACH}")
    if over_alert:
        b = over_alert[0]
        return "alert", (f"above the IS 10500 {b['limit_kind']} limit "
                         f"({b['value']:g} vs {b['limit']:g} {b['unit']})")
    b = breaches[0]
    return "warning", (f"above the IS 10500 acceptable limit ({b['acceptable']:g} "
                       f"{b['unit']}) but within the permissible limit "
                       f"({b['permissible']:g} {b['unit']}) -- tolerated only in "
                       f"the absence of an alternate source")


def modelled_tier(kind: str, *, excursion_probability: Optional[float] = None
                  ) -> tuple[str, str]:
    """(tier, rule) for a modelled alert. Never `critical`."""
    if kind == "published_screening":
        p = excursion_probability
        if p is not None and float(p) >= MODELLED_ALERT_PEX:
            return "alert", (f"the run's excursion probability at the monitoring "
                             f"ring is {float(p):.2f} (>= {MODELLED_ALERT_PEX:g}) "
                             f"within its own horizon -- a modelled result, not a "
                             f"measurement")
        return "notice", "a modelled screening was published for this block"
    if kind == "possible_reach":
        return "warning", ("inside the model's upper (P90) reach but outside its "
                           "central footprint -- the uncertainty band, not a finding")
    if kind == "aquifer_pathway":
        return "warning", ("shares the shallow aquifer a modelled vertical pathway "
                           "would enter; movement inside that aquifer is not modelled")
    if kind == "aquifer_breach_due":
        return "warning", ("a published screening's own modelled breakthrough "
                           "timetable has been passed; nothing has been measured")
    raise ValueError(f"unknown modelled alert kind {kind!r}")


def _iso(d: Any) -> Optional[str]:
    if d is None:
        return None
    if isinstance(d, (datetime, date)):
        return d.isoformat()
    return str(d)


def explain_observed(*, breaches: list[dict[str, Any]], tier: str, rule: str,
                     block: str, district: Optional[str], well_name: Optional[str],
                     sampled_at: Any, source: str = "CGWB laboratory analysis",
                     n_samples_at_well: Optional[int] = None) -> dict[str, Any]:
    """The seven fields for a measured exceedance."""
    lead = breaches[0]
    names = ", ".join(b["label"] for b in breaches)
    when = _iso(sampled_at)
    next_action = [
        f"Have the well re-sampled and analysed for {names} to confirm the "
        f"result -- this alert rests on the most recent single sample.",
    ]
    next_action += [b["advice"] for b in breaches if b["advice"]]
    if tier in ("alert", "critical"):
        next_action.append(
            "Until confirmed, use an alternative supply for drinking and for "
            "infant feeding; ask the district groundwater office or the State "
            "Pollution Control Board about treatment and alternative sources.")
    next_action.append(
        "Arsenic and iron were not analysed in this sampling round anywhere in "
        "Jharkhand; a 'clear' result here does not cover them.")
    return {
        "version": 1,
        "basis": "observed",
        "what_happened": (
            f"A government monitoring well{f' ({well_name})' if well_name else ''} "
            f"in {block} block was sampled"
            f"{f' on {when[:10]}' if when else ''} and {names} came back above "
            f"the IS 10500 limit."),
        "driver": {
            "determinand": lead["determinand"], "value": lead["value"],
            "unit": lead["unit"], "limit": lead["limit"],
            "limit_kind": lead["limit_kind"], "times_limit": lead["times_limit"],
            "status": lead["status"], "standard": lead["standard"],
            "all_breaches": [{k: b[k] for k in ("determinand", "value", "unit",
                                                "limit", "limit_kind",
                                                "times_limit", "status")}
                             for b in breaches],
        },
        "where": {"block": block, "district": district, "well_name": well_name,
                  "scope": "one monitoring well"},
        "tier": {"level": tier, "rule": rule,
                 "ladder": "IS 10500:2012 acceptable / permissible; "
                           f"critical at >= {CRITICAL_MULTIPLE:g}x or "
                           f">= {CRITICAL_MULTI_BREACH} determinands (project-defined)"},
        "confidence": {
            "kind": "measurement",
            "source": source, "sampled_at": when,
            "samples_at_this_well": n_samples_at_well,
            "single_sample": (n_samples_at_well or 1) <= 1,
            "note": ("A laboratory result compared with a published limit. It "
                     "says nothing about exposure, treatment at the point of "
                     "use, or what anybody drinks; and with one sample there is "
                     "no trend, only a reading."),
        },
        "next_action": next_action,
    }


def explain_modelled(*, kind: str, tier: str, rule: str, block: str,
                     district: Optional[str], species: Optional[str],
                     overlap_ha: Optional[float], footprint_ha: Optional[float],
                     horizon_years: Optional[float], engine: Optional[str],
                     metrics: Optional[Mapping[str, Any]],
                     extrapolation: Optional[list[str]],
                     data_confidence: Optional[Mapping[str, Any]],
                     beta_band: Optional[list[float]] = None,
                     wells_in_reach: Optional[list[str]] = None,
                     years_to_breakthrough: Optional[float] = None,
                     breakthrough_probability: Optional[float] = None,
                     injection_start: Any = None, elapsed_years: Optional[float] = None,
                     reach_km: Optional[float] = None,
                     what_it_means: Optional[str] = None) -> dict[str, Any]:
    """The seven fields for a modelled (screening) alert.

    `metrics` is the stored run's `metrics` column: {"analytical": {...},
    "ml": {...}} with P10/P50/P90 per target. The band shown is the ML band
    where the run had one, else the analytical point estimate, and the field
    says which."""
    m = metrics or {}
    ml = m.get("ml") or {}
    an = m.get("analytical") or {}
    band_src = "ml" if ml.get("migration_m") else ("analytical" if an else None)
    src = ml if band_src == "ml" else an

    def band(key: str) -> Optional[dict[str, float]]:
        v = src.get(key) if src else None
        if isinstance(v, Mapping):
            return {k: round(float(v[k]), 3) for k in ("p10", "p50", "p90") if k in v}
        return None

    p_ex = an.get("excursion_probability", ml.get("excursion_probability"))
    what = {
        "published_screening": (
            f"A regulator published a modelled screening of a HYPOTHETICAL "
            f"uranium in-situ recovery operation whose central (P50) footprint "
            f"covers about {overlap_ha or 0:.1f} ha of {block} block. No such "
            f"mine exists."),
        "possible_reach": (
            f"The model's upper (P90) estimate of the same hypothetical "
            f"operation reaches {block} block; its central estimate does not. "
            f"This is the width of the uncertainty band, not a finding."),
        "aquifer_pathway": (
            f"{block} block draws on the shallow aquifer that a modelled "
            f"vertical pathway from the hypothetical operation would enter "
            f"within {years_to_breakthrough:g} years." if years_to_breakthrough
            else f"{block} block shares the shallow aquifer a modelled pathway would enter."),
        "aquifer_breach_due": (
            f"A published screening modelled shallow-aquifer breakthrough after "
            f"{years_to_breakthrough:g} years; counting from the hypothetical "
            f"start date {_iso(injection_start)[:10] if injection_start else '?'}, "
            f"{elapsed_years:g} years have passed. Nothing has been measured."
            if years_to_breakthrough and elapsed_years is not None else
            "A published screening's modelled timetable has been passed."),
    }[kind]

    next_action = []
    if wells_in_reach:
        next_action.append(
            "Monitoring wells inside the modelled reach that should be on the "
            "sampling list for uranium, sulphate, TDS and chloride: "
            + ", ".join(wells_in_reach) + ".")
    elif wells_in_reach is not None:
        next_action.append(
            "No government monitoring well lies inside the modelled reach -- "
            "the area the model points at is unobserved. That is a monitoring "
            "gap, and the Data & Gaps ranking records it.")
    next_action.append(
        "Ask the block water office when wells here were last tested for "
        "uranium, nitrate and fluoride -- that measurement, not this model, is "
        "what tells you about your water.")
    if kind == "aquifer_breach_due":
        next_action.append(
            "On the model's own terms the milestone has passed; a sampling "
            "round in the shallow aquifer is the only thing that can answer "
            "the question it raises.")

    conf: dict[str, Any] = {
        "kind": "model",
        "premise": "No ISR uranium mine operates in Jharkhand. This is a "
                   "screening of a hypothetical scenario, not a report of an event.",
        "engine": engine, "band_source": band_src,
        "migration_m": band("migration_m"),
        "area_ha": band("area_ha"),
        "compliance_conc": band("compliance_conc"),
        "excursion_probability": (round(float(p_ex), 3) if p_ex is not None else None),
        "horizon_years": horizon_years,
        "extrapolation": list(extrapolation or []),
        "in_trained_support": not bool(extrapolation),
        "data_confidence": dict(data_confidence) if data_confidence else None,
        "beta_band": beta_band,
        "note": ("The P10-P90 band is parameter uncertainty inside the model's "
                 "assumptions; it does not cover structural error, and no "
                 "modelled plume has ever been validated against a real one "
                 "in Jharkhand because none exists."),
    }
    if kind in ("aquifer_pathway", "aquifer_breach_due"):
        conf["breakthrough_years"] = years_to_breakthrough
        conf["breakthrough_probability"] = breakthrough_probability
    if reach_km is not None:
        conf["reach_km"] = reach_km

    return {
        "version": 1,
        "basis": "modelled",
        "what_happened": what,
        "driver": {
            "species": species, "quantity": {
                "published_screening": "central (P50) footprint at the screening limit",
                "possible_reach": "upper (P90) migration envelope",
                "aquifer_pathway": "modelled vertical pathway + shallow advective reach",
                "aquifer_breach_due": "elapsed time vs modelled breakthrough",
            }[kind],
            "overlap_ha": overlap_ha, "footprint_ha": footprint_ha,
        },
        "where": {"block": block, "district": district,
                  "scope": {"published_screening": "part of the block (see overlap_ha)",
                            "possible_reach": "part of the block, upper estimate only",
                            "aquifer_pathway": "the block's shallow aquifer, by shared formation",
                            "aquifer_breach_due": "the block's shallow aquifer"}[kind]},
        "tier": {"level": tier, "rule": rule,
                 "ladder": "modelled results are never tiered critical"},
        "confidence": conf,
        "next_action": next_action,
        "what_it_means": what_it_means,
    }


def tiers_legend() -> dict[str, Any]:
    """Returned by the API next to the inbox so the rules travel with the data."""
    return {
        "order": list(TIERS),
        "standard": "IS 10500:2012 (Amendment 2, 2015 for uranium)",
        "observed": {
            "warning": "above the acceptable limit, within the permissible limit",
            "alert": "above the permissible limit, or above acceptable where the "
                     "standard allows no relaxation",
            "critical": f">= {CRITICAL_MULTIPLE:g}x the alert limit, or >= "
                        f"{CRITICAL_MULTI_BREACH} health determinands over their "
                        f"limit at one well (PROJECT-DEFINED)",
        },
        "modelled": {
            "notice": "a screening was published; central footprint reaches the block",
            "warning": "possible reach (P90 only), shared shallow aquifer, or "
                       "timetable passed",
            "alert": f"excursion probability at the monitoring ring >= "
                     f"{MODELLED_ALERT_PEX:g} within the run's horizon",
            "critical": "never -- modelled results cannot be critical",
        },
        "project_defined": ["critical multiple", "critical multi-breach count",
                            "modelled alert excursion-probability threshold"],
    }
