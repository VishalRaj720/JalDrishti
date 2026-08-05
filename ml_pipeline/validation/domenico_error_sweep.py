"""
Domenico error envelope over THIS model's own parameter box.

review2.md finding V-1: the production engine's transport kernel is the Domenico
(1987) product approximation, whose error West, Kueper & Ungs (2007) report as
2-80% -- underpredicting CENTRELINE concentrations by up to 80% -- yet this
project had never bounded it. The remediation then re-based the headline
migration metric onto the centreline, i.e. exactly where that error is largest.

This sweep measures it, using the exact convolution in physics.exact_reference
(self-validated against Ogata-Banks to machine precision).

Parameters are drawn from the ACTUAL joint distribution in
outputs/synthetic_training.csv, not from a plausible-looking grid -- the error
depends on where in parameter space you sit, so it must be measured where the
model actually operates.

Two approximations are separated, because they have different fixes:
  (A) PRODUCT DECOUPLING -- the transverse factor pulled out of the convolution
      and frozen at tau = x/v. This is the Domenico approximation proper.
  (B) DROPPED OGATA-BANKS TERM -- the second exp/erfc term omitted, which is
      what paints the upstream half-plane at C0 (already documented in
      ARCHITECTURE section 10).

Run:  myvenv/Scripts/python.exe -m ml_pipeline.validation.domenico_error_sweep
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml_pipeline.physics.exact_reference import (
    exact_concentration, domenico_concentration, validate_against_ogata_banks)

OUT = Path(__file__).resolve().parents[1] / "outputs"
TRAINING = OUT / "synthetic_training.csv"
N_CASES = 240
RNG = np.random.default_rng(20260805)


def _load_box(n: int) -> pd.DataFrame:
    """Sample real (Xc, aL, aT, W, t) tuples from the training labels."""
    d = pd.read_csv(TRAINING)
    d = d[(d.Xc_m > 1.0) & (d.time_years > 0)]
    cols = ["Xc_m", "alpha_L", "alpha_T", "wellfield_width_m", "time_years",
            "regime", "species", "peclet_L"]
    return d[cols].sample(n=min(n, len(d)), random_state=7).reset_index(drop=True)


def _profile_reach(fn, *, thr_rel, Xc, aL, aT, W, t, v, n=340):
    """Down-gradient distance at which C/C0 falls below thr_rel on y=0."""
    x_max = Xc + 8.0 * np.sqrt(max(aL, 1e-3) * max(Xc, 1.0)) + 10.0
    xs = np.linspace(x_max / n, x_max, n)
    D_L, D_T = aL * v, aT * v
    last = 0.0
    for x in xs:
        c = fn(x, 0.0, t, v=v, D_L=D_L, D_T=D_T, W=W, C0=1.0)
        if c >= thr_rel:
            last = x
    return last


def run(n_cases: int = N_CASES) -> dict:
    assert validate_against_ogata_banks(verbose=True), \
        "exact reference failed its own self-check -- results would be meaningless"
    print()
    box = _load_box(n_cases)
    # incremental-exceedance level as a fraction of C0, the level the migration
    # metric is actually scored at (uranium: max(30-1, 3)/13272 ~ 0.0022)
    THR_REL = 0.0022

    rec = []
    for i, r in box.iterrows():
        Xc, aL, aT = float(r.Xc_m), float(r.alpha_L), float(r.alpha_T)
        W, t = float(r.wellfield_width_m), float(r.time_years) * 365.0
        v = Xc / t                                    # effective front velocity
        D_L, D_T = aL * v, aT * v

        row = {"regime": r.regime, "species": r.species, "Xc_m": Xc,
               "alpha_L": aL, "alpha_T": aT, "W": W, "t_days": t,
               "peclet": float(r.peclet_L), "aT_over_aL": aT / max(aL, 1e-12)}

        # --- concentration error on the centreline at fixed fractions of Xc ---
        for frac in (0.5, 0.8, 1.0, 1.2):
            x = max(frac * Xc, 1e-3)
            ex = exact_concentration(x, 0.0, t, v=v, D_L=D_L, D_T=D_T, W=W)
            dom = domenico_concentration(x, 0.0, t, v=v, D_L=D_L, D_T=D_T, W=W)
            dom_ob = domenico_concentration(x, 0.0, t, v=v, D_L=D_L, D_T=D_T,
                                            W=W, second_ob_term=True)
            row[f"rel_err_x{frac}"] = (dom - ex) / ex if ex > 1e-12 else np.nan
            # (A) alone: keep the full Ogata-Banks longitudinal term
            row[f"rel_err_productonly_x{frac}"] = ((dom_ob - ex) / ex
                                                   if ex > 1e-12 else np.nan)

        # --- error in the DECISION metric: down-gradient reach ---
        reach_ex = _profile_reach(exact_concentration, thr_rel=THR_REL, Xc=Xc,
                                  aL=aL, aT=aT, W=W, t=t, v=v)
        reach_dom = _profile_reach(domenico_concentration, thr_rel=THR_REL,
                                   Xc=Xc, aL=aL, aT=aT, W=W, t=t, v=v)
        row["reach_exact_m"] = reach_ex
        row["reach_domenico_m"] = reach_dom
        row["reach_rel_err"] = ((reach_dom - reach_ex) / reach_ex
                                if reach_ex > 1e-9 else np.nan)
        rec.append(row)
        if (i + 1) % 40 == 0:
            print(f"  ...{i+1}/{len(box)} cases", flush=True)

    df = pd.DataFrame(rec)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "domenico_error_sweep.csv", index=False)

    def pct(s):
        s = pd.Series(s).replace([np.inf, -np.inf], np.nan).dropna()
        return {f"p{q}": float(np.percentile(s, q)) for q in (5, 25, 50, 75, 95)} | \
               {"min": float(s.min()), "max": float(s.max()), "n": int(len(s))}

    summary = {
        "n_cases": int(len(df)),
        "threshold_rel_C0": THR_REL,
        "self_check": "exact convolution == Ogata-Banks to <1e-15 rel",
        "centreline_conc_rel_err": {f"x={f}*Xc": pct(df[f"rel_err_x{f}"])
                                     for f in (0.5, 0.8, 1.0, 1.2)},
        "centreline_conc_rel_err_PRODUCT_DECOUPLING_ONLY":
            {f"x={f}*Xc": pct(df[f"rel_err_productonly_x{f}"])
             for f in (0.5, 0.8, 1.0, 1.2)},
        "downgradient_reach_rel_err": pct(df["reach_rel_err"]),
        "by_regime": {rg: pct(g["reach_rel_err"])
                      for rg, g in df.groupby("regime")},
    }
    (OUT / "domenico_error_summary.json").write_text(json.dumps(summary, indent=2))

    print("\n" + "=" * 82)
    print("CENTRELINE CONCENTRATION: (Domenico - exact)/exact   [negative = UNDER-predicts]")
    print("=" * 82)
    print(f"  {'position':<14}{'p5':>10}{'p25':>10}{'p50':>10}{'p75':>10}{'p95':>10}{'max|err|':>11}")
    for f in (0.5, 0.8, 1.0, 1.2):
        s = summary["centreline_conc_rel_err"][f"x={f}*Xc"]
        worst = max(abs(s["min"]), abs(s["max"]))
        print(f"  x={f:<12}{s['p5']:>+10.2%}{s['p25']:>+10.2%}{s['p50']:>+10.2%}"
              f"{s['p75']:>+10.2%}{s['p95']:>+10.2%}{worst:>10.1%}")

    print("\n  isolating the PRODUCT-DECOUPLING error alone (full Ogata-Banks kept):")
    for f in (0.5, 0.8, 1.0, 1.2):
        s = summary["centreline_conc_rel_err_PRODUCT_DECOUPLING_ONLY"][f"x={f}*Xc"]
        print(f"  x={f:<12}{s['p5']:>+10.2%}{s['p25']:>+10.2%}{s['p50']:>+10.2%}"
              f"{s['p75']:>+10.2%}{s['p95']:>+10.2%}")

    print("\n" + "=" * 82)
    print("DOWN-GRADIENT REACH (the served migration metric)")
    print("=" * 82)
    s = summary["downgradient_reach_rel_err"]
    print(f"  rel err  p5={s['p5']:+.2%}  p25={s['p25']:+.2%}  p50={s['p50']:+.2%}  "
          f"p75={s['p75']:+.2%}  p95={s['p95']:+.2%}")
    print(f"           min={s['min']:+.2%}  max={s['max']:+.2%}  n={s['n']}")
    for rg, sr in summary["by_regime"].items():
        print(f"    {rg:<11} p50={sr['p50']:+.2%}  p95={sr['p95']:+.2%}  max={sr['max']:+.2%}")
    print(f"\nwrote {OUT/'domenico_error_sweep.csv'} and domenico_error_summary.json")
    return summary


if __name__ == "__main__":
    run()
