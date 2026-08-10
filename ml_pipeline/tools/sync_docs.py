"""
ml_pipeline.tools.sync_docs  --  generate ARCHITECTURE.md Section 6.5 from the
artifacts, so the documented model metrics cannot drift from the deployed ones.

WHY THIS EXISTS. ARCHITECTURE.md Section 6.5 has gone stale across a retrain
THREE times, each time in the same way: someone retrains, the numbers in the
prose stay behind, and a document that opens with "every limitation is stated
honestly" quietly stops being true. The second occurrence was caught by an audit
and annotated with a warning box; the third happened anyway, two commits later,
and by then the doc claimed migration R2 = 0.896 against a deployed 0.535 and
compliance 0.738 against a deployed -3.137.

Prose cannot be trusted to track artifacts by discipline alone, which is exactly
what REMEDIATION_PROMPT.md Phase 7 said ("Prefer generating this section from the
artifacts so it cannot go stale again"). This module makes it mechanical:

    python -m ml_pipeline.tools.sync_docs            # rewrite the block
    python -m ml_pipeline.tools.sync_docs --check    # fail if it is stale

`tests/test_docs_in_sync.py` runs the --check path, so a retrain that does not
re-run this turns the suite red instead of shipping a stale claim.

The generated block lives between two HTML-comment markers; everything outside
them is hand-written and untouched.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCH = ROOT / "ARCHITECTURE.md"
METRICS = ROOT / "ml" / "artifacts" / "metrics.json"
CARD = ROOT / "ml" / "artifacts" / "model_card.json"

BEGIN = "<!-- BEGIN GENERATED: metrics (ml_pipeline.tools.sync_docs) -->"
END = "<!-- END GENERATED: metrics -->"

# The project's own acceptance bar, from REMEDIATION_PROMPT.md Gate 4.
R2LOG_GATE = 0.60
COVERAGE_GATE = 0.80


def render() -> str:
    m = json.loads(METRICS.read_text())
    card = json.loads(CARD.read_text())
    bands = m["bands"]
    L = [BEGIN,
         "",
         "**These numbers are GENERATED from `ml/artifacts/metrics.json` by "
         "`python -m ml_pipeline.tools.sync_docs`. Do not hand-edit this block "
         "— edit the model, retrain, and re-run the generator.**",
         "",
         f"Model card version {card.get('version')} · "
         f"{len(card.get('features', []))} features · "
         f"{len(card.get('band_targets', []))} band targets · "
         # `is_post_closure` is a phase flag, not a species one-hot -- take the
         # species list from the registry rather than string-matching "is_".
         f"species: {', '.join(sorted(bands[next(iter(bands))]['r2_log_by_species']))}",
         "",
         "| target | R² (P50, back-transformed) | R² (log) | scenario coverage | rows coverage |",
         "|---|---|---|---|---|"]
    for t, b in bands.items():
        cov = b["coverage"]
        L.append(f"| `{t}` | {b['r2']['p50']:.4f} | {b['r2_log']:.4f} | "
                 f"{cov['scenarios_eval']:.4f} | {cov['rows_eval']:.4f} |")
    if "pex" in m:
        L.append(f"| `excursion_probability` | {m['pex']['r2']:.4f} | — | — | — |")
    L += ["",
          "**Per-species R² (log space).** The pooled back-transformed figure "
          "mixes ppb, mg/L and mBq/L, so its denominator depends on the species "
          "*mix* rather than on model quality — judge on these.",
          "",
          "| target | " + " | ".join(
              sorted(next(iter(bands.values()))["r2_log_by_species"])) + " |",
          "|---" * (1 + len(next(iter(bands.values()))["r2_log_by_species"])) + "|"]
    species = sorted(next(iter(bands.values()))["r2_log_by_species"])
    for t, b in bands.items():
        cells = []
        for sp in species:
            v = b["r2_log_by_species"].get(sp)
            cells.append("—" if v is None
                         else (f"**{v:.3f}**" if v < R2LOG_GATE else f"{v:.3f}"))
        L.append(f"| `{t}` | " + " | ".join(cells) + " |")

    # ---- honest gate reporting: name every miss, never silently pass ----
    misses = [f"`{t}` / {sp} = {b['r2_log_by_species'][sp]:.3f}"
              for t, b in bands.items() for sp in b["r2_log_by_species"]
              if b["r2_log_by_species"][sp] < R2LOG_GATE]
    cov_misses = [f"`{t}` = {b['coverage']['scenarios_eval']:.3f}"
                  for t, b in bands.items()
                  if b["coverage"]["scenarios_eval"] < COVERAGE_GATE]
    L += ["", f"**Acceptance gates.** Per-species R²(log) ≥ {R2LOG_GATE:.2f}; "
              f"scenario coverage ≥ {COVERAGE_GATE:.2f}.", ""]
    L.append(f"- Coverage: {'**FAILS** — ' + ', '.join(cov_misses) if cov_misses else 'all targets pass.'}")
    if misses:
        L.append(f"- Per-species R²(log): **FAILS on {len(misses)} cell(s)** — "
                 + "; ".join(misses)
                 + ". Reported as a miss, not reframed. The conformal bands on "
                   "those cells still cover (see the coverage columns), and the "
                   "ANALYTICAL engine serves the authoritative central value, so "
                   "the failure is in the surrogate's point estimate, not in the "
                   "uncertainty guarantee.")
    else:
        L.append("- Per-species R²(log): all cells pass.")

    if "field_resampled_coverage" in m:
        f = m["field_resampled_coverage"]
        L += ["",
              f"**Field-resampled coverage** (the serving-distribution gate "
              f"mandated by `E1_geometry_design.md` §6 gate 5): "
              f"{f['n_scenarios']} scenarios pinned to the real flow/strike "
              f"field, held out from training.", "",
              "| target | scenario coverage | rows | verdict |", "|---|---|---|---|"]
        for t, r in f["targets"].items():
            L.append(f"| `{t}` | {r['scenarios']:.4f} | {r['rows']:.4f} | "
                     f"{'PASS' if r['passes_gate'] else '**FAIL**'} |")
    else:
        L += ["", "**Field-resampled coverage: NOT RECORDED.** Run "
                  "`python -m ml_pipeline.validation.field_coverage "
                  "--write-metrics`."]
    L += ["", END]
    return "\n".join(L)


def sync(check: bool = False) -> bool:
    text = ARCH.read_text(encoding="utf-8")
    block = render()
    if BEGIN in text and END in text:
        pre = text.split(BEGIN)[0]
        post = text.split(END, 1)[1]
        new = pre + block + post
    else:
        raise SystemExit(f"markers {BEGIN} / {END} not found in {ARCH}")
    if check:
        return new == text
    if new != text:
        ARCH.write_text(new, encoding="utf-8")
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    ok = sync(check=args.check)
    if args.check and not ok:
        raise SystemExit("ARCHITECTURE.md metrics block is STALE — run "
                         "`python -m ml_pipeline.tools.sync_docs`")
    print("docs in sync" if args.check else "docs written")
