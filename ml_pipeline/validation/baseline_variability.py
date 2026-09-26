"""
ml_pipeline.validation.baseline_variability -- how much clean groundwater swings
================================================================================
2026-09-25. The NUREG-1569 excursion test fires when two or more indicators
exceed an upper control limit (UCL); this model sets UCL = baseline x (1 +
P.ISR_UCL_BASELINE_INCREASE) because, until now, every CGWB well on disk had ONE
sample and no temporal variance existed to set a statistical UCL from.

The CGWB 2024 quality table (`Datasets/cgwb_gwq_2024_jharkhand.csv`, extracted
by data_prep/cgwb_gwq_pdf.py) adds a pre- AND post-monsoon sample at the same
stations, most of which also appear in the 2023 table. That gives the first
measured answer to: with no mine at all, how often does a clean well's TDS,
sulfate or chloride move past a given multiple of its own earlier value?

Two kinds of pair, each ratio taken in BOTH directions (either sample could
have been the baseline):
  * season  -- same 2024 station, pre- vs post-monsoon;
  * year    -- a 2023 station and the 2024 sample within 500 m of it.

WHAT IT MEASURES AND WHAT IT DOES NOT. These are the SHALLOW monitoring wells
(dug wells and shallow bore wells) -- the aquifer an overlying-aquifer monitor
well for a VERTICAL excursion would sample. The ore-zone aquifer a perimeter
ring samples is deeper and damps seasonal signals, so this is an upper bound on
the natural swing THERE, not a measurement of it. Sampling and laboratory
scatter are inside the ratios; they are part of what a real UCL must clear.

Run:  python -m ml_pipeline.validation.baseline_variability
Writes ml_pipeline/validation/baseline_variability.json
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
CSV_2024 = REPO / "Datasets" / "cgwb_gwq_2024_jharkhand.csv"
CSV_2023 = REPO / "Datasets" / "waterQuality_jharkhand.csv"
OUT = Path(__file__).resolve().parent / "baseline_variability.json"
MATCH_KM = 0.5
MULTIPLES = (1.2, 1.5, 2.0, 2.5, 3.0)


def _ratios(a, b) -> np.ndarray:
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b) & (a > 0) & (b > 0)
    return np.concatenate([b[ok] / a[ok], a[ok] / b[ok]])


def _summary(r: np.ndarray) -> dict:
    return {"n_ratios": int(r.size),
            "p50": round(float(np.median(r)), 3),
            "p90": round(float(np.quantile(r, 0.90)), 3),
            "p95": round(float(np.quantile(r, 0.95)), 3),
            "share_over": {f"x{m}": round(float(np.mean(r > m)), 3) for m in MULTIPLES}}


def run() -> dict:
    import pandas as pd
    d = pd.read_csv(CSV_2024)
    w = pd.read_csv(CSV_2023, encoding="utf-8-sig")
    for c in ("EC (µS/cm at", "Cl (mg/L)", "SO4"):
        w[c] = pd.to_numeric(w[c], errors="coerce")

    # season pairs: same station, same coordinates
    key = ["station", "longitude", "latitude"]
    pre = d[d.season == "Pre-Monsoon"].set_index(key)
    post = d[d.season == "Post-Monsoon"].set_index(key)
    s = pre.join(post, lsuffix="_pre", rsuffix="_post", how="inner")
    season = {ind: _summary(_ratios(s[f"{ind}_pre"], s[f"{ind}_post"]))
              for ind in ("TDS_mg_L", "SO4_mg_L", "Cl_mg_L")}

    # 2-of-3 on the season pairs, both directions
    def two_of_three(mult: float) -> float:
        hits = []
        for a_suf, b_suf in (("_pre", "_post"), ("_post", "_pre")):
            n = sum((s[f"{ind}{b_suf}"] / s[f"{ind}{a_suf}"] > mult).astype(int)
                    for ind in ("TDS_mg_L", "SO4_mg_L", "Cl_mg_L"))
            hits.append((n >= 2).to_numpy())
        return round(float(np.concatenate(hits).mean()), 3)

    # year pairs: 2023 station <-> 2024 sample within MATCH_KM
    cos = math.cos(math.radians(23.5))
    lon23, lat23 = w["Longitude"].to_numpy(), w["Latitude"].to_numpy()
    pairs = {"EC": ([], []), "Cl": ([], []), "SO4": ([], [])}
    for _, r in d.iterrows():
        dist = np.hypot((lon23 - r["longitude"]) * 111.32 * cos, (lat23 - r["latitude"]) * 111.32)
        k = int(np.argmin(dist))
        if dist[k] <= MATCH_KM:
            for name, c23, c24 in (("EC", "EC (µS/cm at", "EC_uS_cm"),
                                   ("Cl", "Cl (mg/L)", "Cl_mg_L"),
                                   ("SO4", "SO4", "SO4_mg_L")):
                pairs[name][0].append(w.iloc[k][c23])
                pairs[name][1].append(r[c24])
    year = {name: _summary(_ratios(a, b)) for name, (a, b) in pairs.items()}

    current = None
    try:
        from ml_pipeline.config import parameters as P
        current = 1.0 + float(P.ISR_UCL_BASELINE_INCREASE)
    except Exception:
        pass
    out = {
        "sources": {"2024": str(CSV_2024.relative_to(REPO)),
                    "2023": str(CSV_2023.relative_to(REPO))},
        "season_pairs_2024": {"n_stations": int(len(s)), "indicators": season},
        "year_pairs_2023_2024": {"match_km": MATCH_KM, "indicators": year},
        "two_of_three_false_alarm_share": {f"x{m}": two_of_three(m) for m in MULTIPLES},
        "served_ucl_multiple": current,
        "caveat": ("shallow CGWB wells: the aquifer an overlying-aquifer monitor "
                   "samples; an upper bound for the deeper ore-zone ring"),
    }
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    o = run()
    print(json.dumps(o["two_of_three_false_alarm_share"], indent=1))
    print("wrote", OUT)
