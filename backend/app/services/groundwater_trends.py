"""Groundwater level trend and seasonal behaviour, per monitoring station.

WHY THIS EXISTS
---------------
`groundwater_level_readings` holds 8,345 measurements from 415 CGWB stations
spanning 2013-2021 — the only genuinely temporal dataset this project has. The
2026-08-24 audit found it was read for exactly one purpose: baking a single
static flow field (gradient and azimuth) that the transport engine consumes. The
time axis was averaged away and then discarded.

The proposal names "groundwater level fluctuations" and "seasonal / monsoon
variation" among its input parameters, and asks for degradation *trends*. Both
are answerable from data already on disk, and neither needs the surrogate: this
module fits no model and predicts nothing forward. It describes what the
measurements did.

THE SIGN CONVENTION, WHICH IS EASY TO GET BACKWARDS
---------------------------------------------------
CGWB `currentlevel` — stored here as `groundwater_level` — is **depth to water
below ground level**, in metres. It is not an elevation. So:

    value goes UP   ->  water table goes DOWN  ->  worse
    positive slope  ->  DECLINING groundwater   ->  worse

`flow_field.py` already relies on this (`h = DEM_elevation - depth_to_water`),
and this module states it in `direction` on every result rather than leaving a
caller to infer it from a sign. A trend reported the wrong way round would turn
a depleting aquifer into a recovering one.

METHOD, AND WHY THIS ONE
------------------------
**Theil-Sen slope** with a **Mann-Kendall** significance test. Both are
non-parametric and standard practice for groundwater series (WMO-168; CGWB uses
the pair in its own assessment reports). They are chosen over ordinary least
squares because these series are short, irregularly spaced, seasonally forced
and contain outliers — every assumption OLS needs is violated, and OLS would
report a confident slope anyway.

Neither is machine learning and neither touches the frozen `ml_pipeline/`.

WHAT IS REFUSED RATHER THAN ESTIMATED
-------------------------------------
A station with too few readings, or too short a record, gets `None` and a reason
— not a slope with a wide error bar. Records here run from a single reading to
1,242, and a trend fitted through three points spanning eight months would be
reported on the same map as one fitted through nine years. `MIN_READINGS` and
`MIN_SPAN_YEARS` are the gates, and `insufficient_data` is a first-class result.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Optional, Sequence

import numpy as np

#: A trend needs enough points to be more than noise, and enough span that a
#: seasonal cycle cannot masquerade as a trend. Eight readings over three years
#: is the floor; below it the answer is "we cannot say", which is a real answer.
MIN_READINGS = 8
MIN_SPAN_YEARS = 3.0

#: Two-sided Mann-Kendall significance. 0.05 is conventional.
ALPHA = 0.05

#: Metres per year. Below this the slope is reported as `stable` regardless of
#: statistical significance: with enough points a 5 mm/yr trend becomes
#: "significant" and is still hydrologically meaningless.
NEGLIGIBLE_M_PER_YEAR = 0.05

#: Monsoon calendar for Jharkhand. The south-west monsoon runs roughly
#: mid-June to September, so the water table is deepest just before it and
#: shallowest just after.
PRE_MONSOON_MONTHS = (3, 4, 5, 6)
POST_MONSOON_MONTHS = (10, 11, 12, 1)


def _to_years(ts: Sequence[datetime]) -> np.ndarray:
    """Decimal years since the first reading. Irregular spacing is preserved —
    that is the point of using a slope estimator that tolerates it."""
    t0 = min(ts)
    return np.array([(t - t0).total_seconds() / (365.2425 * 86400.0) for t in ts])


def theil_sen(t: np.ndarray, y: np.ndarray) -> float:
    """Median of all pairwise slopes. O(n^2) pairs, which is fine here — the
    busiest station in this dataset has 1,242 readings."""
    n = len(t)
    i, j = np.triu_indices(n, k=1)
    dt = t[j] - t[i]
    ok = dt != 0
    if not ok.any():
        return 0.0
    return float(np.median((y[j][ok] - y[i][ok]) / dt[ok]))


def mann_kendall(y: np.ndarray) -> tuple[float, float]:
    """Return `(z, p)` for the two-sided Mann-Kendall trend test.

    Ties are handled in the variance term, which matters here: groundwater
    depths are reported to 2 decimal places and repeat often.
    """
    n = len(y)
    if n < 3:
        return 0.0, 1.0
    s = 0
    for k in range(n - 1):
        s += int(np.sum(np.sign(y[k + 1:] - y[k])))

    _, counts = np.unique(y, return_counts=True)
    tie_term = float(np.sum(counts * (counts - 1) * (2 * counts + 5)))
    var = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if var <= 0:
        return 0.0, 1.0

    # Continuity correction: S is discrete, the normal approximation is not.
    if s > 0:
        z = (s - 1) / math.sqrt(var)
    elif s < 0:
        z = (s + 1) / math.sqrt(var)
    else:
        z = 0.0
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))
    return float(z), float(min(1.0, max(0.0, p)))


def _classify(slope: float, p: float) -> tuple[str, str]:
    """`(trend, direction)` in the reader's terms, not the data's.

    `slope` is metres per year of DEPTH. Positive depth-slope means the water
    table is getting deeper, which is decline.
    """
    if p > ALPHA or abs(slope) < NEGLIGIBLE_M_PER_YEAR:
        return "stable", "no significant change"
    if slope > 0:
        return "declining", "water table falling"
    return "recovering", "water table rising"


def seasonal_swing(months: Sequence[int], y: np.ndarray) -> Optional[dict[str, Any]]:
    """Pre- vs post-monsoon mean depth, when both windows have readings.

    Reported as a positive number when the aquifer behaves as expected — deeper
    before the monsoon, shallower after. A negative swing is unusual and worth
    seeing rather than hiding, so it is not clamped.
    """
    m = np.asarray(months)
    pre = y[np.isin(m, PRE_MONSOON_MONTHS)]
    post = y[np.isin(m, POST_MONSOON_MONTHS)]
    if pre.size == 0 or post.size == 0:
        return None
    pre_mean, post_mean = float(np.mean(pre)), float(np.mean(post))
    return {
        "pre_monsoon_depth_m": round(pre_mean, 2),
        "post_monsoon_depth_m": round(post_mean, 2),
        "swing_m": round(pre_mean - post_mean, 2),
        "pre_n": int(pre.size),
        "post_n": int(post.size),
        "note": ("Depth below ground. A positive swing is the normal pattern: "
                 "deepest before the monsoon, shallowest after it recharges."),
    }


def analyse_station(readings: Sequence[tuple[datetime, float]]) -> dict[str, Any]:
    """One station's whole record -> trend, seasonality and the reason if neither.

    `readings` is `(recorded_at, depth_m)`. Order does not matter.
    """
    clean = [(t, float(v)) for t, v in readings if v is not None]
    n = len(clean)
    base: dict[str, Any] = {
        "readings": n, "first": None, "last": None, "span_years": None,
        "trend": None, "slope_m_per_year": None, "direction": None,
        "p_value": None, "significant": None,
        "mean_depth_m": None, "min_depth_m": None, "max_depth_m": None,
        "seasonal": None, "insufficient_data": None,
    }
    if n == 0:
        base["insufficient_data"] = "No readings recorded for this station."
        return base

    clean.sort(key=lambda r: r[0])
    ts = [t for t, _ in clean]
    y = np.array([v for _, v in clean], dtype=float)
    t = _to_years(ts)
    span = float(t[-1])

    base.update({
        "first": ts[0], "last": ts[-1], "span_years": round(span, 2),
        "mean_depth_m": round(float(np.mean(y)), 2),
        "min_depth_m": round(float(np.min(y)), 2),
        "max_depth_m": round(float(np.max(y)), 2),
        "seasonal": seasonal_swing([d.month for d in ts], y),
    })

    if n < MIN_READINGS or span < MIN_SPAN_YEARS:
        base["insufficient_data"] = (
            f"{n} reading(s) over {span:.1f} year(s). A trend needs at least "
            f"{MIN_READINGS} readings spanning {MIN_SPAN_YEARS:g} years, so "
            f"that a seasonal cycle cannot be mistaken for a trend.")
        return base

    slope = theil_sen(t, y)
    z, p = mann_kendall(y)
    trend, direction = _classify(slope, p)
    base.update({
        "trend": trend,
        "direction": direction,
        # Reported as depth-change per year. Positive = deepening = decline.
        "slope_m_per_year": round(slope, 4),
        "p_value": round(p, 4),
        "significant": bool(p <= ALPHA),
    })
    return base


def method_note() -> dict[str, Any]:
    """Published with the numbers, as this project does for every other method."""
    return {
        "measurement": (
            "CGWB depth to water below ground level, in metres. This is a "
            "depth, not an elevation: a rising value means a FALLING water "
            "table."),
        "trend": "Theil-Sen (median pairwise) slope, metres of depth per year.",
        "significance": (
            f"Mann-Kendall two-sided test with tie correction, alpha = {ALPHA}."),
        "why_non_parametric": (
            "These series are short, irregularly spaced, seasonally forced and "
            "contain outliers. Ordinary least squares assumes none of that and "
            "would report a confident slope regardless."),
        "gates": (
            f"A station needs at least {MIN_READINGS} readings spanning "
            f"{MIN_SPAN_YEARS:g} years. Below that the result is "
            f"'insufficient_data' rather than an uncertain slope."),
        "negligible": (
            f"A significant slope smaller than {NEGLIGIBLE_M_PER_YEAR} m/yr is "
            f"reported as stable. With enough points a 5 mm/yr trend becomes "
            f"statistically significant and is still hydrologically meaningless."),
        "seasonal": (
            f"Pre-monsoon = months {list(PRE_MONSOON_MONTHS)}, post-monsoon = "
            f"months {list(POST_MONSOON_MONTHS)}, for the Jharkhand south-west "
            f"monsoon."),
        "not_a_forecast": (
            "This describes what the measurements did between 2013 and 2021. "
            "Nothing here is extrapolated forward, and it is unrelated to the "
            "ISR transport model."),
    }
