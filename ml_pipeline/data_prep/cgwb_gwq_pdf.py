"""
ml_pipeline.data_prep.cgwb_gwq_pdf  --  Jharkhand rows from the CGWB quality PDF
===============================================================================
2026-09-25. CGWB publishes its national "Ground Water Quality Data (2024)" as a
163-page PDF table: one row per sample, all states, pre- and post-monsoon. This
extracts the Jharkhand rows to a CSV in `Datasets/`.

Why it matters: the 2000-2021 NWDP files carry NO health determinands, and the
2023 table (`Datasets/waterQuality_jharkhand.csv`) is a single year. The 2024
table carries uranium, arsenic, fluoride and nitrate again, at many of the same
stations -- the first year-on-year replicate for the determinands residents are
actually alerted on.

HOW IT READS THE PDF. The table is ruled, so pdfplumber's line-based table
extraction returns clean cells (station and block names keep their spaces). The
header of EVERY page is compared with the expected 36 columns before any row is
read -- a page whose layout differs is refused, never parsed by position, so a
shifted column cannot silently turn arsenic into uranium.

Values: "-" and "NA" in the PDF both mean "not analysed" and become empty
cells. Anything else non-numeric (e.g. a "<" detection-limit note) is kept
verbatim and reported, never coerced.

Usage:
    python -m ml_pipeline.data_prep.cgwb_gwq_pdf path/to/CGWB_GWQ_2024.pdf
        [--state Jharkhand] [--out Datasets/cgwb_gwq_2024_jharkhand.csv]
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The PDF's own header, normalised (whitespace collapsed, the mis-encoded
#: micro sign dropped). Order is the order of the cells.
EXPECTED_HEADER = [
    "S. No.", "Year", "Season", "State/ UT", "District", "Block/ Taluka",
    "Station Name/ Location", "Longitude (DD)", "Latitude (DD)", "pH",
    "EC (S/cm at 25 C)", "TDS (mg/L)", "CO3 (mg/L)", "HCO3 (mg/L)",
    "Total Alkalinity (mg/L)", "Cl (mg/L)", "NO3 (mg/L)", "SO4 (mg/L)",
    "PO4 (mg/L)", "SiO2 (mg/L)", "F (mg/L)", "Total Hardness (mg/L)",
    "Ca (mg/L)", "Mg (mg/L)", "Na (mg/L)", "K (mg/L)", "Fe (mg/L)", "As (ppb)",
    "U (ppb)", "Mn (mg/L)", "Cu (mg/L)", "Pb (mg/L)", "Zn (mg/L)", "Ni (mg/L)",
    "Cd (mg/L)", "Cr (mg/L)",
]

#: CSV column names, one per header cell, units kept in the name.
CSV_COLUMNS = [
    "s_no", "year", "season", "state", "district", "block", "station",
    "longitude", "latitude", "pH", "EC_uS_cm", "TDS_mg_L", "CO3_mg_L",
    "HCO3_mg_L", "total_alkalinity_mg_L", "Cl_mg_L", "NO3_mg_L", "SO4_mg_L",
    "PO4_mg_L", "SiO2_mg_L", "F_mg_L", "total_hardness_mg_L", "Ca_mg_L",
    "Mg_mg_L", "Na_mg_L", "K_mg_L", "Fe_mg_L", "As_ppb", "U_ppb", "Mn_mg_L",
    "Cu_mg_L", "Pb_mg_L", "Zn_mg_L", "Ni_mg_L", "Cd_mg_L", "Cr_mg_L",
]
_EXPECTED_KEY = [h.replace(" ", "") for h in EXPECTED_HEADER]
TEXT_COLUMNS = {"season", "state", "district", "block", "station"}
NOT_ANALYSED = {"-", "NA", "N.A.", "N/A", ""}


def _norm(cell: str | None) -> str:
    s = (cell or "").replace("\n", " ")
    s = re.sub(r"[^\x20-\x7E]", "", s)          # the mis-encoded micro/degree signs
    return re.sub(r"\s+", " ", s).strip()


def _value(col: str, cell: str | None, issues: list, where: str):
    s = _norm(cell)
    if col in TEXT_COLUMNS:
        return s
    if s in NOT_ANALYSED:
        return ""
    try:
        float(s)
        return s
    except ValueError:
        issues.append(f"{where} {col}={s!r}")
        return s


def extract(pdf_path: Path, state: str = "Jharkhand") -> tuple[list[dict], dict]:
    """Rows for `state`, and a report of pages read, refused and odd values."""
    import pdfplumber
    rows, issues, pages_read, pages_refused = [], [], [], []
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            if state.lower() not in (page.extract_text() or "").lower():
                continue
            for table in page.extract_tables():
                header_at = next((k for k, r in enumerate(table)
                                  if r and _norm(r[0]) == "S. No."), None)
                if header_at is None:
                    continue
                header = [_norm(c) for c in table[header_at]]
                # compared with spaces removed: exact on content, blind only to
                # the gap a stripped micro sign leaves ("EC ( S/cm ...")
                if [h.replace(" ", "") for h in header] != _EXPECTED_KEY:
                    pages_refused.append({"page": pno, "header": header})
                    continue
                pages_read.append(pno)
                for r in table[header_at + 1:]:
                    if not r or len(r) != len(CSV_COLUMNS):
                        continue
                    if _norm(r[3]).lower() != state.lower():
                        continue
                    where = f"p{pno} s_no={_norm(r[0])}"
                    rec = {c: _value(c, v, issues, where) for c, v in zip(CSV_COLUMNS, r)}
                    rec["source_page"] = pno
                    rows.append(rec)
    return rows, {"pages_read": sorted(set(pages_read)),
                  "pages_refused": pages_refused, "non_numeric": issues}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Extract one state's rows from the "
                                             "CGWB Ground Water Quality PDF table.")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--state", default="Jharkhand")
    ap.add_argument("--out", type=Path,
                    default=REPO_ROOT / "Datasets" / "cgwb_gwq_2024_jharkhand.csv")
    a = ap.parse_args(argv)
    rows, report = extract(a.pdf, a.state)
    if report["pages_refused"]:
        print("REFUSED pages (header differs):", report["pages_refused"], file=sys.stderr)
    if not rows:
        print("no rows extracted", file=sys.stderr)
        return 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS + ["source_page"])
        w.writeheader()
        w.writerows(rows)
    seasons = {}
    for r in rows:
        seasons[r["season"]] = seasons.get(r["season"], 0) + 1
    print(f"wrote {a.out} -- {len(rows)} rows {seasons}; pages {report['pages_read']}")
    if report["non_numeric"]:
        print(f"{len(report['non_numeric'])} non-numeric value(s) kept verbatim:",
              report["non_numeric"][:20])
    return 0


if __name__ == "__main__":
    sys.exit(main())
