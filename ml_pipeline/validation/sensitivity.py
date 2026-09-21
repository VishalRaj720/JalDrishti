"""
ml_pipeline.validation.sensitivity  (R17, 2026-09-20)
======================================================
Global sensitivity of the plume outputs to the parameters the model rests on,
at three reference sites. Answers the proposal's "sensitivity analysis" box
with numbers: which assumptions materially move the extent, the footprint and
the concentration at the monitoring ring -- and which do not.

TWO GROUPS OF INPUTS, reported separately because they mean different things:

  A. REGISTERED UNGROUNDED CONSTANTS (`P.UNGROUNDED_PARAMETERS`) that enter the
     plan-view solve: the dual-porosity capacity ratio beta, the matrix-transfer
     rate omega, the fracture aperture and matrix diffusion coefficient (the
     Tang group), the leach-zone growth gain and scale, and the incremental
     attribution floor. None has a Singhbhum measurement behind it.
  B. RESOLVED HYDROGEOLOGICAL INPUTS the run derives from data with a stated
     range: K, gradient, mobile porosity, Kd, C0 and the uranium attenuation
     rate. These are "measured somewhere" but uncertain here, and the Monte
     Carlo already samples most of them into the P10-P90 band.

Group A ranges are the config's own (low, high) where it carries one, else a
factor-of-3 either side of the served value -- stated in the output. Group B
ranges are the same ranges the Monte Carlo draws from.

Vertical-screening constants (Kv/Kh, upward gradient, wellbore probability)
do not enter the plan-view outputs and are NOT analysed here; the register
and LIMITATIONS.md carry their status. ISR_UCL_BASELINE_INCREASE enters only
the indicator excursion test, not these outputs, and is likewise out of scope.

METHODS
  * One-at-a-time (OAT): each input swept over its range at 7 points with the
    others at their served values; reported as the output's range and the
    elasticity  d ln(output) / d ln(input) at the served point.
  * Sobol first-order and total-order indices by the Saltelli (2010) scheme:
    A, B and A_B(i) matrices from a Sobol quasi-random sequence, N base
    samples -> N(D+2) engine evaluations per (site, species, output). Indices
    are Jansen estimators. Inputs with a multiplicative range are sampled
    log-uniformly.
  * The analytical engine only (no surrogate): ~8 ms per evaluation, so the
    full design runs in minutes.

OUTPUTS
  ml/artifacts/sensitivity.json   -- everything, machine-readable
  ml/artifacts/sensitivity_*.png  -- total-order indices per site, report figure
  stdout                          -- the summary table

Run:  python -m ml_pipeline.validation.sensitivity [--n 256] [--no-plot]
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ml_pipeline.config import parameters as P
from ml_pipeline.dashboard.resolve import resolve_inputs
from ml_pipeline.ml.predict import features_from_inputs
from ml_pipeline.physics.transport import simulate_plume

ART = Path(__file__).resolve().parents[1] / "ml" / "artifacts"

SITES = {
    "jaduguda_deposit": {"lon": 86.3468, "lat": 22.6520, "label": "Jaduguda (deposit)"},
    "belt_point": {"lon": 86.29, "lat": 22.69, "label": "Singhbhum belt (between deposits)"},
    "non_belt_ranchi": {"lon": 85.33, "lat": 23.36, "label": "Ranchi plateau (non-belt)"},
}
SPECIES = ("uranium_ppb", "sulfate_mg_l")
OUTPUTS = ("max_migration_distance_m", "affected_area_ha", "compliance_conc")
HORIZON = 20.0
OPERATION = 8.0
RESTORATION = 3.0


# --------------------------------------------------------------------------- #
# input definitions
# --------------------------------------------------------------------------- #
def _inputs_for(inputs: dict, species: str) -> list[dict[str, Any]]:
    """The input list for a site: name, group, served value, (lo, hi), log
    flag, and how to apply it (an `inputs` key, or a config patch)."""
    fractured = inputs["regime"] == "fractured"
    kd_lo, kd_c, kd_hi = P.kd_range_for(species, inputs["regime"])
    beta_lo, beta_hi = P.DUAL_POROSITY["beta_prior"]
    ap = P.FRACTURE["full_aperture_m"]
    a_lo, a_mode, a_hi = P.U_ATTENUATION_K_PER_YR
    defs: list[dict[str, Any]] = []

    def add(name, group, served, lo, hi, log, apply, note=""):
        if hi <= lo or served is None:
            return
        defs.append({"name": name, "group": group, "served": float(served),
                     "lo": float(lo), "hi": float(hi), "log": bool(log),
                     "apply": apply, "note": note})

    # ---- group A: registered ungrounded constants ----
    if fractured:
        add("beta (capacity ratio)", "A", inputs["beta"], beta_lo, beta_hi, True,
            ("input", "beta"), "prior [0.3, 20]; served = porosity-derived")
        om = P.DUAL_POROSITY["mass_transfer_omega"]
        add("omega (matrix transfer, 1/day)", "A", om, om / 10, om * 10, True,
            ("config", ("DUAL_POROSITY", "mass_transfer_omega")), "x/10 .. x10 of the pinned 1e-3")
        add("fracture aperture (m)", "A", ap[1], ap[0], ap[2], True,
            ("config_tuple", ("FRACTURE", "full_aperture_m")), "config range 1e-4 .. 5e-4")
        de = P.FRACTURE["De_m2_day"]
        add("matrix De (m2/day)", "A", de, de / 5, de * 5, True,
            ("config", ("FRACTURE", "De_m2_day")), "x/5 .. x5 (no defensible range in config)")
    add("SOURCE_BV_GAIN", "A", P.SOURCE_BV_GAIN, 0.1, 1.0, False,
        ("config", ("SOURCE_BV_GAIN",)), "0.1 .. 1.0 around the served 0.4")
    add("SOURCE_BV_REF", "A", P.SOURCE_BV_REF, 0.5, 6.0, True,
        ("config", ("SOURCE_BV_REF",)), "0.5 .. 6 bulk volumes around the served 2")
    add("INCREMENTAL_FLOOR", "A", P.INCREMENTAL_FLOOR, 0.02, 0.5, True,
        ("config", ("INCREMENTAL_FLOOR",)), "attribution policy 0.02 .. 0.5")
    # ---- group B: resolved hydrogeological inputs ----
    add("K (m/day)", "B", inputs["K_m_day"], inputs["K_m_day"] / 3, inputs["K_m_day"] * 3, True,
        ("input", "K_m_day"), "MC local heterogeneity clip (x/3 .. x3)")
    add("hydraulic gradient", "B", inputs["gradient_i"], inputs["gradient_i"] * 0.5,
        inputs["gradient_i"] * 2.0, True, ("input", "gradient_i"), "x0.5 .. x2")
    add("mobile porosity", "B", inputs["phi_mobile"], inputs["phi_mobile"] / 2,
        inputs["phi_mobile"] * 2, True, ("input", "phi_mobile"),
        "x/2 .. x2 (beta held at its served value, so this is the velocity effect only)")
    add("Kd (L/kg)", "B", inputs["kd_L_kg"], max(kd_lo, 1e-3), kd_hi, True,
        ("input", "kd_L_kg"), f"regime Kd range {kd_lo}-{kd_hi}")
    add("C0 (source conc)", "B", inputs["source_conc_C0"], inputs["source_conc_C0"] * 0.5,
        inputs["source_conc_C0"] * 1.5, False, ("input", "source_conc_C0"), "x0.5 .. x1.5")
    if species == "uranium_ppb":
        add("U attenuation k (1/yr)", "B", inputs.get("u_attenuation_k_per_yr") or a_mode,
            a_lo, a_hi, True, ("input", "u_attenuation_k_per_yr"), "literature range")
    return defs


@contextlib.contextmanager
def _patched(defs: list[dict[str, Any]], values: dict[str, float]):
    """Temporarily set the config constants named by `defs` for one
    evaluation. Restored in `finally`, so a failure never leaks a value."""
    saved: list[tuple[Callable[[], None]]] = []
    try:
        for d in defs:
            kind, key = d["apply"]
            v = values[d["name"]]
            if kind == "config":
                if len(key) == 1:
                    old = getattr(P, key[0])
                    setattr(P, key[0], v)
                    saved.append((lambda k=key[0], o=old: setattr(P, k, o),))
                else:
                    dct = getattr(P, key[0])
                    old = dct[key[1]]
                    dct[key[1]] = v
                    saved.append((lambda dd=dct, k=key[1], o=old: dd.__setitem__(k, o),))
            elif kind == "config_tuple":
                dct = getattr(P, key[0])
                old = dct[key[1]]
                dct[key[1]] = (old[0], v, old[2])
                saved.append((lambda dd=dct, k=key[1], o=old: dd.__setitem__(k, o),))
        yield
    finally:
        for (restore,) in reversed(saved):
            restore()


def _evaluate(base_inputs: dict, defs: list[dict[str, Any]],
              values: dict[str, float]) -> dict[str, float]:
    """One analytical engine evaluation with the given input values."""
    inputs = dict(base_inputs)
    for d in defs:
        kind, key = d["apply"]
        if kind == "input":
            inputs[key] = values[d["name"]]
    with _patched(defs, values):
        ring_x = float(inputs.pop("monitor_ring_m", None) or P.COMPLIANCE_BUFFER_M)
        X, feat, Xc = features_from_inputs(**inputs)
        species = inputs["species"]
        thr = P.EXCURSION_THRESHOLDS[species]
        res = simulate_plume(
            feat, species_C0=inputs["source_conc_C0"],
            background=inputs["background_conc_Cb"], threshold=thr,
            t_days=inputs["time_years"] * 365.0,
            operation_days=inputs["operation_years"] * 365.0,
            restoration_days=float(inputs.get("restoration_years") or 0.0) * 365.0,
            residual_fraction=feat.get("_residual_endpoint", feat["residual_fraction"]),
            grid_n=160, compliance_x=ring_x,
            # this is "one analytical engine evaluation" -- match the LIVE
            # served answer (predict_analytical), not generate.py's frozen
            # training labels. See LIMITATIONS.md 4h-ii.
            floor_source_at_background=True)
    m = res.metrics
    return {k: float(m[k]) for k in OUTPUTS}


# --------------------------------------------------------------------------- #
# sampling helpers
# --------------------------------------------------------------------------- #
def _scale(u: np.ndarray, d: dict[str, Any]) -> np.ndarray:
    if d["log"]:
        return np.exp(np.log(d["lo"]) + u * (np.log(d["hi"]) - np.log(d["lo"])))
    return d["lo"] + u * (d["hi"] - d["lo"])


def _sobol_matrix(n: int, dim: int, seed: int) -> np.ndarray:
    try:
        from scipy.stats import qmc
        return qmc.Sobol(d=dim, scramble=True, seed=seed).random(n)
    except Exception:  # pragma: no cover -- scipy < 1.7
        return np.random.default_rng(seed).uniform(size=(n, dim))


def oat(base_inputs: dict, defs: list[dict[str, Any]], served: dict[str, float],
        points: int = 7) -> dict[str, Any]:
    """One-at-a-time sweeps and the local elasticity at the served point."""
    base = _evaluate(base_inputs, defs, served)
    out: dict[str, Any] = {"served_outputs": base, "inputs": {}}
    for d in defs:
        us = np.linspace(0.0, 1.0, points)
        xs = _scale(us, d)
        ys = []
        for x in xs:
            v = dict(served)
            v[d["name"]] = float(x)
            ys.append(_evaluate(base_inputs, defs, v))
        rec: dict[str, Any] = {"group": d["group"], "served": d["served"],
                               "range": [d["lo"], d["hi"]], "log": d["log"],
                               "note": d["note"], "x": [float(x) for x in xs]}
        for k in OUTPUTS:
            col = [y[k] for y in ys]
            rec[k] = {"values": [round(c, 4) for c in col],
                      "min": round(min(col), 4), "max": round(max(col), 4),
                      "elasticity": _elasticity(d, base_inputs, defs, served, k)}
        out["inputs"][d["name"]] = rec
    return out


def _elasticity(d, base_inputs, defs, served, k, eps=0.05) -> float | None:
    """d ln(output) / d ln(input) at the served point, central difference."""
    x0 = served[d["name"]]
    if x0 <= 0:
        return None
    lo_v, hi_v = dict(served), dict(served)
    lo_v[d["name"]] = x0 * (1 - eps)
    hi_v[d["name"]] = x0 * (1 + eps)
    y_lo = _evaluate(base_inputs, defs, lo_v)[k]
    y_hi = _evaluate(base_inputs, defs, hi_v)[k]
    if y_lo <= 0 or y_hi <= 0:
        return None
    return round(float((math.log(y_hi) - math.log(y_lo))
                       / (math.log(1 + eps) - math.log(1 - eps))), 3)


def sobol(base_inputs: dict, defs: list[dict[str, Any]], n: int, seed: int = 7,
          pins: dict[str, float] | None = None) -> dict[str, Any]:
    """Saltelli design; Jansen estimators for S1 and ST.

    `pins` names outputs pinned at a floor, as (floor, tolerance): when the
    output never rises more than `tolerance` above the floor over the whole
    design, the variance is a wiggle on a constant and the indices are
    reported as undefined rather than as noise. For the ring concentration the
    floor is the background and the tolerance is the engine's own attribution
    floor, INCREMENTAL_FLOOR x threshold -- variation the engine itself does
    not count as an exceedance."""
    D = len(defs)
    U = _sobol_matrix(n, 2 * D, seed)
    A, B = U[:, :D], U[:, D:]

    def run(u_rows: np.ndarray) -> np.ndarray:
        ys = np.empty((len(u_rows), len(OUTPUTS)))
        for i, u in enumerate(u_rows):
            v = {d["name"]: float(_scale(np.array([u[j]]), d)[0]) for j, d in enumerate(defs)}
            y = _evaluate(base_inputs, defs, v)
            ys[i] = [y[k] for k in OUTPUTS]
        return ys

    yA, yB = run(A), run(B)
    yAB = np.empty((D, n, len(OUTPUTS)))
    for i in range(D):
        AB = A.copy()
        AB[:, i] = B[:, i]
        yAB[i] = run(AB)

    out: dict[str, Any] = {"n_base": n, "evaluations": n * (D + 2), "indices": {}}
    for oi, k in enumerate(OUTPUTS):
        a, b = yA[:, oi], yB[:, oi]
        # log-transform positive outputs so a heavy tail does not dominate
        y_all = np.concatenate([a, b, yAB[:, :, oi].ravel()])
        use_log = np.all(y_all > 0) and (np.max(y_all) / max(np.min(y_all), 1e-12) > 20)
        f = (lambda z: np.log(z)) if use_log else (lambda z: z)
        fa, fb = f(a), f(b)
        var = np.var(np.concatenate([fa, fb]), ddof=1)
        # DEGENERATE: the output does not vary over the design (e.g. uranium
        # at a non-ore pin, where the source term is clamped to background).
        # A Sobol index of a constant is 0/0; report that, never a number.
        # a relative spread under 0.1 % of the median is a constant output for
        # every purpose here (the engine's grid resolution is coarser than that)
        spread = float(np.max(y_all) - np.min(y_all))
        scale = max(abs(float(np.median(y_all))), 1e-12)
        degenerate = (var <= 1e-12) or (spread / scale < 1e-3)
        pin = (pins or {}).get(k)
        pinned = (pin is not None
                  and float(np.max(y_all)) - float(pin[0]) <= float(pin[1]))
        degenerate = degenerate or pinned
        rec = {"log_transformed": bool(use_log), "variance": round(float(var), 6),
               "degenerate": bool(degenerate), "S1": {}, "ST": {}}
        for i, d in enumerate(defs):
            fab = f(yAB[i, :, oi])
            if degenerate:
                rec["S1"][d["name"]] = None
                rec["ST"][d["name"]] = None
                continue
            s1 = float(np.mean(fb * (fab - fa)) / var)             # Saltelli 2010
            st = float(0.5 * np.mean((fa - fab) ** 2) / var)         # Jansen 1999
            rec["S1"][d["name"]] = round(max(min(s1, 1.0), -0.05), 4)
            rec["ST"][d["name"]] = round(max(min(st, 1.5), 0.0), 4)
        if degenerate:
            rec["note"] = (f"output stays within {pin[1]:g} of its floor {pin[0]:g} over "
                           f"the whole design (below the engine's attribution floor) -- "
                           f"indices undefined" if pinned else
                           "output constant over the whole design -- indices undefined "
                           "(source term suppressed or output pinned)")
        out["indices"][k] = rec
    return out


# --------------------------------------------------------------------------- #
def run_site(site_key: str, species: str, n: int) -> dict[str, Any]:
    site = SITES[site_key]
    payload = {"lon": site["lon"], "lat": site["lat"], "species": species,
               "time_years": HORIZON, "operation_years": OPERATION,
               "restoration_years": RESTORATION, "monitor_ring_m": 100.0}
    inputs, hydro = resolve_inputs(payload)
    inputs = dict(inputs)
    inputs.setdefault("monitor_ring_m", 100.0)
    defs = _inputs_for(inputs, species)
    served = {d["name"]: d["served"] for d in defs}
    t0 = time.time()
    o = oat(inputs, defs, served)
    thr = P.EXCURSION_THRESHOLDS[species]
    s = sobol(inputs, defs, n, pins={"compliance_conc": (
        float(inputs["background_conc_Cb"]), float(P.INCREMENTAL_FLOOR) * thr)})
    return {
        "site": site_key, "label": site["label"], "species": species,
        "regime": inputs["regime"], "ore_zone": (hydro.get("ore_zone") or {}).get("zone"),
        "u_suppressed": bool(hydro.get("u_suppressed")),
        "resolved": {k: inputs[k] for k in ("K_m_day", "gradient_i", "phi_mobile",
                                            "n_total", "kd_L_kg", "beta",
                                            "source_conc_C0", "background_conc_Cb")},
        "beta_basis": hydro.get("beta_basis"),
        "inputs": [{k: d[k] for k in ("name", "group", "served", "lo", "hi", "log", "note")}
                   for d in defs],
        "oat": o, "sobol": s,
        "seconds": round(time.time() - t0, 1),
    }


def _plot(results: list[dict[str, Any]]) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return []
    written = []
    for r in results:
        idx = r["sobol"]["indices"]
        names = [d["name"] for d in r["inputs"]]
        fig, axes = plt.subplots(1, len(OUTPUTS), figsize=(4.2 * len(OUTPUTS), 3.6), sharey=True)
        for ax, k in zip(axes, OUTPUTS):
            if idx[k].get("degenerate"):
                ax.text(0.5, 0.5, "constant output (indices undefined)", ha="center",
                        va="center", transform=ax.transAxes, fontsize=9, color="#7a8699")
                ax.set_title(k.replace("_", " "), fontsize=9)
                ax.set_yticks(np.arange(len(names)))
                ax.set_yticklabels(names, fontsize=8)
                continue
            st = [idx[k]["ST"][nm] for nm in names]
            s1 = [idx[k]["S1"][nm] for nm in names]
            y = np.arange(len(names))
            ax.barh(y + 0.18, st, height=0.36, label="total-order S_T", color="#2b6cb0")
            ax.barh(y - 0.18, s1, height=0.36, label="first-order S_1", color="#f5a524")
            ax.set_yticks(y)
            ax.set_yticklabels(names, fontsize=8)
            ax.set_title(k.replace("_", " ") + (" (log)" if idx[k]["log_transformed"] else ""),
                         fontsize=9)
            ax.set_xlim(0, 1.05)
            ax.grid(axis="x", alpha=0.3)
        axes[0].legend(fontsize=7, loc="lower right")
        fig.suptitle(f"Sobol sensitivity -- {r['label']}, {r['species']} "
                     f"({r['regime']}, {HORIZON:g} yr)", fontsize=10)
        fig.tight_layout()
        name = f"sensitivity_{r['site']}_{r['species'].split('_')[0]}.png"
        fig.savefig(ART / name, dpi=150)
        plt.close(fig)
        written.append(name)
    return written


def summary_table(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per (site, species, output): the inputs ranked by total-order index."""
    rows = []
    for r in results:
        for k in OUTPUTS:
            idx = r["sobol"]["indices"][k]
            if idx.get("degenerate"):
                rows.append({"site": r["site"], "species": r["species"], "output": k,
                             "degenerate": True, "note": idx.get("note"), "top": [],
                             "share_group_A": None})
                continue
            st = idx["ST"]
            ranked = sorted(st.items(), key=lambda kv: -kv[1])
            rows.append({"site": r["site"], "species": r["species"], "output": k,
                         "top": [{"input": nm, "ST": v,
                                  "group": next(d["group"] for d in r["inputs"] if d["name"] == nm)}
                                 for nm, v in ranked[:4]],
                         "share_group_A": round(sum(v for nm, v in st.items()
                                                    if next(d["group"] for d in r["inputs"] if d["name"] == nm) == "A")
                                                / max(sum(st.values()), 1e-9), 3)})
    return rows


def main(n: int = 256, plot: bool = True, sites=None, species=None) -> dict[str, Any]:
    results = []
    for sk in (sites or SITES):
        for sp in (species or SPECIES):
            print(f"[sensitivity] {sk} / {sp} ...", flush=True)
            r = run_site(sk, sp, n)
            results.append(r)
            print(f"   {r['sobol']['evaluations']} evaluations in {r['seconds']} s; "
                  f"regime={r['regime']} zone={r['ore_zone']} "
                  f"u_suppressed={r['u_suppressed']}")
            for k in OUTPUTS:
                idx = r["sobol"]["indices"][k]
                if idx.get("degenerate"):
                    print(f"   {k:26s} degenerate -- {idx.get('note')}")
                    continue
                top = sorted(idx["ST"].items(), key=lambda kv: -kv[1])[:3]
                print(f"   {k:26s} " + "  ".join(f"{nm}={v:.2f}" for nm, v in top))
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": {"oat_points": 7, "sobol_n_base": n,
                   "estimators": "Saltelli 2010 (S1), Jansen 1999 (ST); log-transformed "
                                 "outputs where the range exceeds 20x",
                   "engine": "analytical (simulate_plume); no surrogate",
                   "horizon_years": HORIZON, "operation_years": OPERATION,
                   "restoration_years": RESTORATION},
        "groups": {"A": "registered ungrounded constants (P.UNGROUNDED_PARAMETERS) "
                        "entering the plan-view solve",
                   "B": "resolved hydrogeological inputs with their MC/literature ranges"},
        "results": results,
        "summary": summary_table(results),
    }
    if plot:
        out["figures"] = _plot(results)
    ART.mkdir(exist_ok=True)
    (ART / "sensitivity.json").write_text(json.dumps(out, indent=1, default=float))
    print(f"\nwrote {ART / 'sensitivity.json'}" + (f" + {len(out.get('figures', []))} figures" if plot else ""))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=256, help="Sobol base sample size")
    ap.add_argument("--no-plot", action="store_true")
    args = ap.parse_args()
    main(n=args.n, plot=not args.no_plot)
