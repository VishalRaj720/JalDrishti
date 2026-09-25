"""
ml_pipeline.validation.water_table_trends -- is the water table falling?
========================================================================
2026-09-25. The vertical screening (LIMITATIONS 1f) and the flow field use
CGWB water levels from 2013-2021. If the water table were falling steadily,
those years would not describe the years a mine would run in. The CGWB record
1994 - January 2026 (`Datasets/cgwb_waterlevel_jharkhand_1994_2026.csv`,
data_prep/cgwb_wl_pdf.py) is long enough to ask.

Per well (coordinates to 0.001 deg) and campaign (pre-monsoon May, post-monsoon
November): one depth per year; wells with at least MIN_YEARS years spanning at
least MIN_SPAN_YEARS. Trend = Theil-Sen slope; significance = Mann-Kendall
(Kendall's tau against time), p < 0.05. Positive = the water table is DEEPER
each year.

WHAT IT DOES NOT SAY. These are unconfined dug wells; a trend in the deeper
fractured aquifer is not measured. A well with no significant trend can still
be falling slowly; "not significant" is not "stable" at any one well -- the
statement is about the network.

Run:  python -m ml_pipeline.validation.water_table_trends
Writes ml_pipeline/validation/water_table_trends.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "water_table_trends.json"
MIN_YEARS = 15
MIN_SPAN_YEARS = 20
ALPHA = 0.05
SEASONS = {"May": "pre-monsoon", "Nov": "post-monsoon"}
#: the Singhbhum uranium belt's districts (Jaduguda, Turamdih, Bagjata,
#: Banduhurang, Mohuldih lie in East Singhbhum and Saraikela-Kharsawan; the
#: shear zone continues into West Singhbhum)
BELT_PATTERN = r"singh|sarai|serai"


def _per_well(d):
    from scipy.stats import kendalltau, theilslopes
    import pandas as pd
    rows = []
    for season in SEASONS:
        s = d[d["season"] == season]
        for sid, g in s.groupby("sid"):
            y = g.groupby(g["date"].dt.year)["depth_to_water_mbgl"].mean()
            if len(y) < MIN_YEARS or (y.index.max() - y.index.min()) < MIN_SPAN_YEARS:
                continue
            t = y.index.to_numpy(float)
            slope = theilslopes(y.to_numpy(), t)[0]
            p = kendalltau(t, y.to_numpy()).pvalue
            rows.append({"season": season, "sid": sid,
                         "district": g["district"].mode().iloc[0],
                         "years": int(len(y)),
                         "first": int(y.index.min()), "last": int(y.index.max()),
                         "slope_m_per_yr": float(slope), "p": float(p)})
    return pd.DataFrame(rows)


def _summary(w) -> dict:
    sig = w[w["p"] < ALPHA]
    return {"wells": int(len(w)),
            "median_slope_m_per_yr": round(float(w["slope_m_per_yr"].median()), 3),
            "significant_deepening": int((sig["slope_m_per_yr"] > 0).sum()),
            "significant_rising": int((sig["slope_m_per_yr"] < 0).sum())}


def run(write: bool = True) -> dict:
    from ml_pipeline.data_prep.cgwb_wl_pdf import load_long_record, water_table_rows
    d = water_table_rows(load_long_record()).copy()
    d["sid"] = d["latitude"].round(3).astype(str) + "|" + d["longitude"].round(3).astype(str)
    w = _per_well(d)
    belt = w[w["district"].str.lower().str.contains(BELT_PATTERN)]
    steep = w.sort_values("slope_m_per_yr", ascending=False).head(5)
    out = {
        "source": "Datasets/cgwb_waterlevel_jharkhand_1994_2026.csv (water-table rows)",
        "rule": {"min_years": MIN_YEARS, "min_span_years": MIN_SPAN_YEARS, "alpha": ALPHA,
                 "trend": "Theil-Sen", "test": "Mann-Kendall (Kendall tau vs year)",
                 "sign": "+ = water table deeper each year"},
        "statewide": {SEASONS[s]: _summary(w[w["season"] == s]) for s in SEASONS},
        "uranium_belt_districts": {
            "districts": sorted(set(belt["district"])),
            **{SEASONS[s]: _summary(belt[belt["season"] == s]) for s in SEASONS}},
        "steepest_deepening": [
            {"season": SEASONS[r.season], "district": r.district, "span": f"{r.first}-{r.last}",
             "years": r.years, "slope_m_per_yr": round(r.slope_m_per_yr, 3), "p": round(r.p, 4)}
            for r in steep.itertuples()],
        "caveat": ("unconfined dug wells; the fractured aquifer below is not measured; "
                   "a statement about the network, not about any one well"),
    }
    if write:
        OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    o = run()
    print(json.dumps({k: o[k] for k in ("statewide", "uranium_belt_districts")}, indent=1))
    print("wrote", OUT)
