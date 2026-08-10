"""
ml_pipeline.validation.end_to_end_audit
=======================================
One pass over the whole pipeline -- data -> physics/features -> labels -> ML
training -> validation -> conformal outputs -> serving/UI -> documentation --
checking the specific properties that have actually broken in this project's
history. Every check prints PASS/FAIL with the measured value, and the exit code
is non-zero if any FAIL.

This is a REPORT, not a test suite. Its job is to make the state of the system
legible in one place; `tests/` is what keeps it there.

Run:  python -m ml_pipeline.validation.end_to_end_audit
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from ml_pipeline.config import parameters as P

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "ml" / "artifacts"
OUT = ROOT / "outputs"

_results: list[tuple[str, str, bool, str]] = []


def check(section: str, name: str, ok: bool, detail: str = "") -> None:
    _results.append((section, name, bool(ok), detail))


# --------------------------------------------------------------------------- #
def audit_data() -> None:
    from ml_pipeline.data_prep.texas_loader import (load_texas_geochem,
                                                    texas_source_provenance,
                                                    EXPECTED_GEOCHEM_ROWS)
    from ml_pipeline.data_prep.jharkhand_loader import load_jharkhand_water_quality
    geo = load_texas_geochem()
    check("data", "Texas sheets parse to pinned row counts",
          all(len(geo[s]) == EXPECTED_GEOCHEM_ROWS[s] for s in geo),
          str({s: len(d) for s, d in geo.items()}))
    prov = texas_source_provenance()
    check("data", "C0 provenance reports sample size",
          prov["n_rows"] == 9 and prov["n_mines"] == 7,
          f"n_rows={prov['n_rows']} n_mines={prov['n_mines']}")
    env = prov["envelope"]["uranium_ppb"]
    per_mine = list(prov["per_mine"]["uranium_ppb"].values())
    check("data", "C0 envelope truncates no observed site value",
          abs(env[0] - min(per_mine)) < 1 and abs(env[1] - max(per_mine)) < 1,
          f"envelope {env} vs observed [{min(per_mine)}, {max(per_mine)}]")
    wq = load_jharkhand_water_quality()
    check("data", "CGWB chemistry has no temporal replicates (limits UCL rules)",
          wq.groupby(["longitude", "latitude"]).size().max() == 1,
          f"{len(wq)} wells, max {wq.groupby(['longitude','latitude']).size().max()} sample/site")


def audit_physics() -> None:
    from ml_pipeline.physics import transport as T
    # t = 0 consistency, both engines
    p0 = T.TransportParams(C0=1e4, aL=5.0, aT=0.5, source_width_m=300.0,
                           Xc=0.0, Xw=0.0, sigma=0.0, t_days=0.0)
    r0 = T.solve_plume(p0, threshold=30.0, background=1.0, grid_n=80)
    mc0 = T.mc_field_metrics([p0], threshold=30.0, background=1.0, grid_n=60)
    check("physics", "t=0 gives zero area AND zero migration (both engines)",
          r0.metrics["affected_area_ha"] == 0 and r0.metrics["max_migration_distance_m"] == 0
          and float(mc0["area_ha"][0]) == 0 and float(mc0["max_dist_m"][0]) == 0)
    # retarded clock closed form vs numeric integration
    beta, omega, t = 8.0, 1e-3, 3650.0
    ts = np.linspace(0, t, 200001)
    num = np.trapezoid(1.0 / (1.0 + beta * (1 - np.exp(-omega * (1 + beta) / beta * ts))), ts)
    check("physics", "retarded_clock closed form == numeric integral",
          abs(T.retarded_clock(t, beta, omega) - num) / num < 1e-4,
          f"closed {T.retarded_clock(t, beta, omega):.4f} vs numeric {num:.4f}")
    # rebound floor
    op, rest = 8 * 365.0, 5 * 365.0
    f50 = T.source_strength_fraction(0.06, 50 * 365.0, op, rest)
    check("physics", "post-restoration source never falls below the measured endpoint",
          f50 >= 0.06 - 1e-9, f"f(t=50yr)={f50:.4f} vs endpoint 0.060")
    # radium residual re-derived
    from ml_pipeline.data_prep.texas_loader import texas_restoration_residual
    N = math.log(1.0 / texas_restoration_residual()["uranium_ppb"])
    Ru = T.matrix_retardation(0.03, 2750.0, P.KD_RANGES["uranium_ppb"]["fractured"][1])
    Rra = T.matrix_retardation(0.03, 2750.0, P.RADIUM_KD_RANGES["fractured"][1])
    implied = math.exp(-N * Ru / Rra)
    check("physics", "radium restoration residual matches its own derivation",
          abs(P.RADIUM_RESTORATION_RESIDUAL - implied) < 0.02,
          f"served {P.RADIUM_RESTORATION_RESIDUAL} vs derived {implied:.3f}")
    # depth decay bounded by the global crustal trend
    mi = 10.0 ** (3.2 * (math.log10(0.300) - math.log10(0.045)))
    worst = max(1.0 / P.depth_decay_factor(300.0, b) for b in (121.0, 180.0, 258.0))
    check("physics", "K(z) drop at 300 m within Manning-Ingebritsen crustal trend",
          worst <= mi, f"model {worst:.0f}x vs global {mi:.0f}x")
    check("physics", "geometry-omega path stays disabled (unit-convention mismatch)",
          P.OMEGA_FROM_GEOMETRY is False)


def audit_labels() -> None:
    csv = OUT / "synthetic_training.csv"
    if not csv.exists():
        check("labels", "training CSV present", False, "missing")
        return
    df = pd.read_csv(csv)
    meta = json.loads((OUT / "synthetic_meta.json").read_text())
    check("labels", "training set size", len(df) > 0,
          f"{len(df)} rows / {df['scenario_id'].nunique()} scenarios / "
          f"{df['polygon_id'].nunique()} polygons")
    viol = sum(int(((df[f"{c}_p10"] > df[f"{c}_p50"]) |
                    (df[f"{c}_p50"] > df[f"{c}_p90"])).sum())
               for c in ("affected_area_ha", "max_migration_distance_m", "compliance_conc"))
    check("labels", "band ordering p10<=p50<=p90", viol == 0, f"{viol} violations")
    num = df.select_dtypes("number")
    check("labels", "no NaN / inf labels",
          int(num.isna().sum().sum()) == 0 and int(np.isinf(num.to_numpy()).sum()) == 0)
    # labels must reflect the CURRENT source envelope (V-2)
    from ml_pipeline.data_prep.texas_loader import texas_source_signature
    env = texas_source_signature()
    ok = True
    detail = []
    for sp, (lo, hi) in env.items():
        s = df[df.species == sp]["source_conc_C0"]
        inside = (s.min() >= lo * 0.98) and (s.max() <= hi * 1.02)
        # and it must actually USE most of the range, not sit in a sub-window
        spans = (s.max() - s.min()) / max(hi - lo, 1e-9)
        ok &= inside and spans > 0.9
        detail.append(f"{sp.split('_')[0]}:{spans:.2f}")
    check("labels", "labels baked on the CURRENT C0 envelope", ok, " ".join(detail))
    check("labels", "compliance ring in meta matches config",
          meta.get("compliance_buffer_m") == P.COMPLIANCE_BUFFER_M)


def audit_model() -> None:
    if not (ART / "metrics.json").exists():
        check("model", "artifacts present", False, "missing metrics.json")
        return
    m = json.loads((ART / "metrics.json").read_text())
    card = json.loads((ART / "model_card.json").read_text())
    check("model", "model card feature list matches metrics config",
          card["features"] == m["config"]["features"],
          f"{len(card['features'])} features")
    # `is_post_closure` is a lifecycle-phase flag, not a species one-hot -- match
    # against the registry's own names rather than the "is_" prefix.
    trained_species = sorted(s for s in card["features"] if s in P.SPECIES_ONEHOT)
    check("model", "species registry matches the trained one-hots",
          trained_species == sorted(P.SPECIES_ONEHOT),
          f"{len(trained_species)} species one-hots")
    for t, b in m["bands"].items():
        cov = b["coverage"]["scenarios_eval"]
        check("model", f"scenario coverage >= 0.80  [{t}]", cov >= 0.80, f"{cov:.4f}")
    worst = {}
    for t, b in m["bands"].items():
        for sp, v in b["r2_log_by_species"].items():
            if v < 0.60:
                worst[f"{t}|{sp}"] = v
    check("model", "per-species R2(log) >= 0.60 on every cell", not worst,
          "MISSES: " + ", ".join(f"{k}={v:.3f}" for k, v in worst.items())
          if worst else "all pass")
    mono = m.get("monotonicity_on_manifold", {})
    check("model", "on-manifold physics laws hold",
          bool(mono.get("qin_law_holds")) and bool(mono.get("bleed_law_holds")))
    fr = m.get("field_resampled_coverage")
    check("model", "field-resampled (serving-distribution) coverage recorded",
          fr is not None,
          "" if fr is None else f"field_mix={fr.get('field_mix')}")
    if fr:
        check("model", "field-resampled coverage passes the 0.80 gate",
              bool(fr.get("all_targets_pass")),
              ", ".join(f"{t}={r['scenarios']:.3f}" for t, r in fr["targets"].items()))


def audit_serving() -> None:
    from fastapi.testclient import TestClient
    from ml_pipeline.dashboard.server import app
    c = TestClient(app)
    j = c.post("/api/predict", json=dict(lon=86.347, lat=22.652,
                                         species="uranium_ppb", time_years=10,
                                         operation_years=8)).json()
    check("serving", "predict returns 200 with plume + metrics",
          "metrics" in j and "plume" in j)
    h = j["hydro"]
    check("serving", "UI retardation matches the physics (effective, not tracer)",
          h["retardation_effective"] >= h["retardation_Rd"],
          f"tracer {h['retardation_Rd']} / effective {h['retardation_effective']}")
    from ml_pipeline.dashboard.resolve import resolve_inputs
    inp, _ = resolve_inputs(dict(lon=86.347, lat=22.652, species="uranium_ppb"))
    check("serving", "served K equals the K reported to the UI",
          abs(inp["K_m_day"] - h["K_m_day"]) < 1e-3,
          f"{inp['K_m_day']:.4f} vs {h['K_m_day']}")
    e = j["isr_excursion"]
    check("serving", "NUREG 2-of-N excursion test present + shortfall disclosed",
          e.get("indicators_required") == 2 and e.get("panel_shortfall") is True)
    check("serving", "uranium/radium excluded as excursion indicators",
          all(sp not in P.ISR_EXCURSION_INDICATORS
              for sp in ("uranium_ppb", "radium_226_mbq_l")))
    check("serving", "monitor ring grounded in licensed practice",
          P.MONITOR_RING_RANGE_M[0] <= P.COMPLIANCE_BUFFER_M <= P.MONITOR_RING_RANGE_M[1])
    r = c.get("/api/boundary")
    check("serving", "static overlays carry cache validators",
          bool(r.headers.get("ETag")) and "max-age" in r.headers.get("Cache-Control", ""))
    from ml_pipeline.dashboard import server as S
    check("serving", "rate limiting configured", S.RATE_LIMIT_PER_MIN > 0,
          f"{S.RATE_LIMIT_PER_MIN}/min burst {S.RATE_LIMIT_BURST}")
    a = c.get("/api/assumptions").json()
    check("serving", "scenario assumptions exposed via API",
          len(a["scenario_assumptions"]) >= 10,
          f"{len(a['scenario_assumptions'])} entries")
    # radium provenance must not cite the rejected compilation as the anchor
    rj = c.post("/api/predict", json=dict(lon=86.347, lat=22.652,
                                          species="radium_226_mbq_l")).json()
    kdc = rj["hydro"]["radium_context"]["kd_citation"]
    check("serving", "radium Kd citation points at the groundwater measurements",
          "p.95" in kdc and "not as the anchor" in kdc)


def audit_docs() -> None:
    from ml_pipeline.tools.sync_docs import sync
    check("docs", "ARCHITECTURE metrics block matches artifacts", sync(check=True))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    check("docs", "README containment formula matches the code",
          "min(1, Q_net / (q·b·W))" in readme)
    fid = (ROOT / "JHARKHAND_FIDELITY_MATRIX.md").read_text(encoding="utf-8")
    for marker in ("2026-08-10", "Rn-222", "rebound", "third seam"):
        check("docs", f"fidelity matrix records '{marker}'", marker in fid)
    # every ungrounded constant must be registered
    check("docs", "assumption register covers the known ungrounded constants",
          len(P.UNGROUNDED_PARAMETERS) >= 10, f"{len(P.UNGROUNDED_PARAMETERS)}")


def main() -> int:
    for fn in (audit_data, audit_physics, audit_labels, audit_model,
               audit_serving, audit_docs):
        try:
            fn()
        except Exception as e:                       # a crash IS a finding
            check(fn.__name__.replace("audit_", ""), f"{fn.__name__} completed",
                  False, f"{type(e).__name__}: {e}")

    width = max(len(n) for _, n, _, _ in _results) + 2
    section = None
    for sec, name, ok, detail in _results:
        if sec != section:
            section = sec
            print(f"\n=== {sec.upper()} ===")
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:<{width}} {detail}")
    fails = [f"{s}/{n}" for s, n, ok, _ in _results if not ok]
    print(f"\n{len(_results) - len(fails)}/{len(_results)} checks pass")
    if fails:
        print("FAILING: " + ", ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
