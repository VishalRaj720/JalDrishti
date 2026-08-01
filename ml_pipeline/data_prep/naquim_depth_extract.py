"""
ml_pipeline.data_prep.naquim_depth_extract   (Phase-1 fix 3.3 -- K(z) grounding)
================================================================================
Mines the CGWB NAQUIM district reports already on disk for the evidence needed to
build a depth-dependent hydraulic-conductivity law K(z) for Jharkhand crystalline
rock -- replacing the current use of shallow drinking-water-depth K at ore depth.

What it looks for, per district report:
  * transmissivity values (T, m2/day)            -> absolute conductivity anchor
  * fracture depth zones + their productivity    -> the depth-decay shape
  * well depth vs discharge / yield statements   -> direct K-vs-depth evidence
  * weathered-zone thickness                     -> top of the fractured system
  * "no fractures beyond X m" statements         -> the practical base of flow

Run:  python -m ml_pipeline.data_prep.naquim_depth_extract
Out:  Datasets/naquim_reference/naquim_depth_evidence.json   (structured hits)
      Datasets/naquim_reference/naquim_depth_evidence.md     (human-readable)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pdfplumber

REPO = Path(__file__).resolve().parents[2]
PDF_DIR = REPO / "Datasets" / "naquim_reference" / "Jharkhand_NAQUIM_Reports"
OUT_DIR = REPO / "Datasets" / "naquim_reference"

# --------------------------------------------------------------------------- #
# Patterns. Each returns (label, regex). Case-insensitive, run per page.
# --------------------------------------------------------------------------- #
NUM = r"\d+(?:\.\d+)?"

PATTERNS = [
    # transmissivity: "T = 207.7 - 570.8 m2/day", "transmissivity ranges from 12 to 350 m2/day"
    ("transmissivity", re.compile(
        rf"transmissivity[^.]{{0,160}}?{NUM}[^.]{{0,80}}?(?:m\s*2\s*/\s*day|m²/day|sq\.?\s*m/day|m2/day)", re.I)),
    ("transmissivity_val", re.compile(
        rf"(?:T\s*=|T\s*value[s]?\s*(?:of|is|are|range)?)[^.]{{0,80}}?{NUM}[^.]{{0,60}}?(?:m\s*2\s*/\s*day|m²/day|m2/day)", re.I)),

    # fracture depth zones
    ("fracture_depth", re.compile(
        rf"fracture[sd]?[^.]{{0,180}}?{NUM}\s*(?:-|to|–|and)\s*{NUM}\s*m(?:\s*bgl)?", re.I)),
    ("fracture_absent_below", re.compile(
        rf"(?:no|not|absent|negligible|without)[^.]{{0,80}}?fractur[^.]{{0,80}}?(?:beyond|below|after|deeper than)[^.]{{0,40}}?{NUM}\s*m", re.I)),
    ("fracture_deep_limit", re.compile(
        rf"fractur[^.]{{0,120}}?(?:beyond|below|deeper than|down to|up to|extend)[^.]{{0,40}}?{NUM}\s*m", re.I)),

    # depth vs productivity / yield
    ("yield_depth", re.compile(
        rf"(?:yield|discharge)[^.]{{0,160}}?(?:depth|m\s*bgl)[^.]{{0,120}}?{NUM}", re.I)),
    ("depth_yield", re.compile(
        rf"depth[^.]{{0,140}}?(?:yield|discharge)[^.]{{0,120}}?{NUM}", re.I)),
    ("productive_zone", re.compile(
        rf"(?:productive|potential|water[- ]bearing)[^.]{{0,140}}?{NUM}\s*(?:-|to|–)\s*{NUM}\s*m", re.I)),

    # weathered zone
    ("weathered", re.compile(
        rf"weather(?:ed|ing)[^.]{{0,140}}?{NUM}\s*(?:-|to|–|and)\s*{NUM}\s*m", re.I)),

    # specific capacity / permeability
    ("specific_capacity", re.compile(
        rf"specific\s+capacity[^.]{{0,140}}?{NUM}", re.I)),
    ("permeability_K", re.compile(
        rf"(?:hydraulic\s+conductivity|permeability)[^.]{{0,140}}?{NUM}", re.I)),
]

MAX_SNIPPET = 400


def clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s[:MAX_SNIPPET]


def scan_pdf(path: Path) -> dict:
    hits: dict[str, list] = {label: [] for label, _ in PATTERNS}
    n_pages = 0
    try:
        with pdfplumber.open(path) as pdf:
            n_pages = len(pdf.pages)
            for pno, page in enumerate(pdf.pages, start=1):
                try:
                    txt = page.extract_text() or ""
                except Exception:
                    continue
                if not txt:
                    continue
                for label, rx in PATTERNS:
                    for m in rx.finditer(txt):
                        snip = clean(m.group(0))
                        # de-duplicate near-identical snippets
                        if any(snip[:120] == h["text"][:120] for h in hits[label]):
                            continue
                        hits[label].append({"page": pno, "text": snip})
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "n_pages": 0, "hits": {}}
    return {"n_pages": n_pages, "hits": {k: v for k, v in hits.items() if v}}


def run():
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    print(f"scanning {len(pdfs)} NAQUIM reports in {PDF_DIR}\n")
    results = {}
    for p in pdfs:
        res = scan_pdf(p)
        results[p.name] = res
        if res.get("error"):
            print(f"  !! {p.name[:52]:54s} {res['error'][:50]}")
            continue
        counts = {k: len(v) for k, v in res["hits"].items()}
        total = sum(counts.values())
        print(f"  {p.name[:52]:54s} {res['n_pages']:>4}p  hits={total:>4}  "
              f"T={counts.get('transmissivity',0)+counts.get('transmissivity_val',0):>2} "
              f"frac={counts.get('fracture_depth',0):>3} "
              f"yield={counts.get('yield_depth',0)+counts.get('depth_yield',0):>3}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "naquim_depth_evidence.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")

    # readable digest -- the categories that actually drive K(z)
    KEY = ["transmissivity", "transmissivity_val", "fracture_absent_below",
           "fracture_deep_limit", "productive_zone", "yield_depth", "depth_yield",
           "permeability_K", "specific_capacity", "fracture_depth", "weathered"]
    lines = ["# NAQUIM depth-evidence digest (auto-extracted)", "",
             "Source: CGWB Jharkhand NAQUIM district reports on disk.",
             "Purpose: ground a depth-dependent K(z) law for crystalline rock (Phase-1 fix 3.3).",
             "**Verify each snippet against its page before use.**", ""]
    for fname, res in results.items():
        if res.get("error") or not res.get("hits"):
            continue
        lines.append(f"## {fname}  ({res['n_pages']} pages)")
        for label in KEY:
            items = res["hits"].get(label)
            if not items:
                continue
            lines.append(f"### {label}  ({len(items)})")
            for it in items[:12]:
                lines.append(f"- p{it['page']}: {it['text']}")
            lines.append("")
    (OUT_DIR / "naquim_depth_evidence.md").write_text("\n".join(lines), encoding="utf-8")

    ok = sum(1 for r in results.values() if not r.get("error"))
    tot = sum(len(v) for r in results.values() for v in r.get("hits", {}).values())
    print(f"\nDONE: {ok}/{len(pdfs)} readable, {tot} evidence snippets")
    print(f"  -> {OUT_DIR / 'naquim_depth_evidence.json'}")
    print(f"  -> {OUT_DIR / 'naquim_depth_evidence.md'}")


if __name__ == "__main__":
    run()
