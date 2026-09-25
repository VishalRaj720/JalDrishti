"""
ml_pipeline.data_prep.cgwb_wl_pdf  --  Jharkhand rows from CGWB water-level PDFs
===============================================================================
2026-09-25. CGWB publishes its national depth-to-water record for the
unconfined aquifer as season-wise PDF tables (January, pre-monsoon, August,
post-monsoon), 1994 onward, ~10,000 pages each. This extracts the Jharkhand
rows into one long CSV.

Why: the water levels on disk (`Datasets/cgwb_waterlevel_jharkhand.csv`) cover
2013-2021 only. The flow field's direction uncertainty (flow_direction.py)
checks the fitted direction year by year, and eight years is a short record;
these tables reach back to 1994 and forward to January 2026.

HOW IT READS THE PDFs. The tables are not ruled, and district, block and
village names contain spaces, so a row cannot be split on whitespace. The
column start positions are learned per page from the data rows (_header_x);
the four numeric fields (latitude, longitude, date, depth) are read from the
RIGHT end of the row and range-checked; the name words between the state and
the latitude are assigned to district / block / village by their x-position
against those starts. Pages are located first with pdfium's fast text layer (a
page is parsed only if a line STARTS with the state name -- "Jharkhandi", a
village in Uttarakhand, is not Jharkhand).

Nothing is coerced: a row whose numeric tail does not parse, or whose
coordinates fall outside Jharkhand's bounding box, is reported and skipped,
never guessed. The one repair (_repair_overlap) is exact and flagged.

Usage:
    python -m ml_pipeline.data_prep.cgwb_wl_pdf record  path/to/folder/of/pdfs
    python -m ml_pipeline.data_prep.cgwb_wl_pdf extract --season Jan --out x.csv  a.pdf [b.pdf ...]
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

LAT_RANGE = (21.8, 25.5)
LON_RANGE = (83.2, 88.2)
_NUM = re.compile(r"^-?\d+(\.\d+)?$")
#: a gap wider than this between two words separates COLUMNS; a single space in
#: these tables is ~3-4 pt, the narrowest column gutter measured ~10 pt
_COLUMN_GAP_PT = 6.0
_DATE = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})$")

COLUMNS = ["date", "year", "month", "season", "district", "block", "village",
           "latitude", "longitude", "depth_to_water_mbgl", "source_file", "source_page",
           "note"]

#: notes a row can carry -- anything but "" means "read this before using it"
NOTE_REPAIRED = "latitude recovered from an overlapping village name"
NOTE_SUPPLEMENTARY = "only in a partial-period file"
NOTE_SAME_SPOT = "another reading at the same coordinates and date differs"

#: rows that are unconfined water-table readings of a known well. A repaired
#: row is (its coordinates are recovered exactly); a supplementary row may be a
#: bore well, and a same-spot pair cannot say which reading belongs to the well
#: at those coordinates, so both are left out of water-table analyses.
WATER_TABLE_NOTES = frozenset({"", NOTE_REPAIRED})


def water_table_rows(df):
    """The rows of the long-record CSV usable as water-table readings, with a
    plausible depth (0-100 m). Read the CSV with keep_default_na=False so an
    empty note stays "" (load_long_record does)."""
    dep = df["depth_to_water_mbgl"]
    return df[df["note"].isin(WATER_TABLE_NOTES) & (dep >= 0) & (dep < 100)]


def load_long_record(path: Path | None = None):
    import pandas as pd
    return pd.read_csv(path or REPO_ROOT / "Datasets" / "cgwb_waterlevel_jharkhand_1994_2026.csv",
                       parse_dates=["date"], keep_default_na=False,
                       na_values={"depth_to_water_mbgl": [""]})


def _pages_with_state(pdf_path: Path, state: str) -> list[int]:
    import pypdfium2 as pdfium
    rx = re.compile(r"(?m)^\s*" + re.escape(state) + r"\s")
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        return [i for i in range(len(doc))
                if rx.search(doc[i].get_textpage().get_text_range())]
    finally:
        doc.close()


def _parse_date(tok: str) -> date | None:
    m = _DATE.match(tok)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
    y = int(y) if len(y) == 4 else (1900 + int(y) if int(y) >= 70 else 2000 + int(y))
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _lines(words: list[dict], tol: float = 2.5) -> list[list[dict]]:
    """Group words into text lines by their top coordinate."""
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
        if lines and abs(lines[-1][0]["top"] - w["top"]) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(ln, key=lambda w: w["x0"]) for ln in lines]


def _header_x(lines: list[list[dict]]) -> list[float] | None:
    """x0 where the four NAME columns (state, district, block, village) start.

    Learned from the DATA rows, not the header: the header labels are placed
    ~30 pt right of the columns they name (measured: DISTRICT label at 207,
    district values at 168), so header positions misassign names. Text in each
    name column is left-aligned, so a column start is an x0 shared by nearly
    every data row on the page; the four leftmost such positions are the name
    columns (the next three are latitude, longitude and date)."""
    from collections import Counter
    data = [ln for ln in lines
            if any(_parse_date(w["text"]) for w in ln) and len(ln) >= 7]
    if len(data) < 2:
        return None
    counts = Counter()
    for ln in data:
        # only a word that follows a COLUMN gap can start a column. Words
        # inside a name are one space apart (~3-4 pt); without this, a page
        # dominated by "Jammu & Kashmir" rows made "&" and "Kashmir" look like
        # column starts and put Jharkhand's district and block in the village
        # column (116 rows, found by the empty-name check, 2026-09-25)
        starts = {round(ln[0]["x0"])}
        for prev, w in zip(ln, ln[1:]):
            if w["x0"] - prev["x1"] > _COLUMN_GAP_PT:
                starts.add(round(w["x0"]))
        counts.update(starts)
    need = 0.6 * len(data)
    starts = sorted(x for x, c in counts.items() if c >= need)
    # merge starts within 2 pt (sub-point jitter between rows)
    merged: list[float] = []
    for x in starts:
        if not merged or x - merged[-1] > 2:
            merged.append(x)
    return [float(x) for x in merged[:4]] if len(merged) >= 7 else None


def _repair_overlap(tok: str) -> tuple[str, str] | None:
    """A long village name printed over the latitude column interleaves the
    two strings character by character ("Ag.Of2fi3c.e3)4110" is "Ag.Office)"
    over "23.34110"). In the latitude column only digits and the decimal point
    belong to the number, so the latitude is the digits-and-dots subsequence
    ending the token, and must look like a Jharkhand latitude; the name is what
    remains after removing exactly those characters (right to left). Returns
    (latitude_text, name_part) or None when no such latitude is there."""
    kept = "".join(ch for ch in tok if ch.isdigit() or ch == ".")
    m = re.search(r"(2[1-5]\.\d{3,6})$", kept)
    if not m:
        return None
    lat = m.group(1)
    chars, j = list(tok), len(lat) - 1
    for i in range(len(chars) - 1, -1, -1):
        if j >= 0 and chars[i] == lat[j]:
            chars[i], j = "", j - 1
    if j >= 0:
        return None
    return lat, "".join(chars)


def extract(pdf_path: Path, season: str, state: str = "Jharkhand") -> tuple[list[dict], dict]:
    import pdfplumber
    rows, skipped, header_missing = [], [], []
    pages = _pages_with_state(pdf_path, state)
    with pdfplumber.open(pdf_path) as pdf:
        # pass 1: learn each page's column layout
        page_lines, layouts = {}, {}
        for idx in pages:
            page_lines[idx] = _lines(pdf.pages[idx].extract_words(
                keep_blank_chars=False, use_text_flow=False))
            layouts[idx] = _header_x(page_lines[idx])
        learned = [i for i in pages if layouts[i] is not None]
        for idx in pages:
            lines = page_lines[idx]
            hx = layouts[idx]
            if hx is None:
                # this page's rows do not share enough column starts to learn
                # the layout (ragged numbers); the layout is fixed within a
                # file, so the NEAREST page's applies -- before or after, so the
                # file's first page is covered too (it was dropped once, silently)
                header_missing.append(idx + 1)
                if learned:
                    nearest = min(learned, key=lambda i: abs(i - idx))
                    hx = layouts[nearest]
            for ln in lines:
                if not ln or ln[0]["text"] != state:
                    continue
                toks = [w["text"] for w in ln]
                if hx is None:
                    skipped.append((idx + 1, " ".join(toks), "no column layout in this file"))
                    continue
                # numeric tail: ... lat lon date depth   (depth may be absent)
                di = next((k for k in range(len(toks) - 1, 0, -1) if _parse_date(toks[k])), None)
                if di is None or di < 3:
                    skipped.append((idx + 1, " ".join(toks), "no date"))
                    continue
                lat_t, lon_t = toks[di - 2], toks[di - 1]
                depth_t = toks[di + 1] if di + 1 < len(toks) else ""
                note, name_words = "", list(ln[1:di - 2])
                if _NUM.match(lon_t) and not _NUM.match(lat_t):
                    fixed = _repair_overlap(lat_t)
                    if fixed is not None:
                        lat_t, rest = fixed
                        note = NOTE_REPAIRED
                        if rest:
                            name_words.append({**ln[di - 2], "text": rest})
                if not (_NUM.match(lat_t) and _NUM.match(lon_t)):
                    skipped.append((idx + 1, " ".join(toks), "lat/lon not numeric"))
                    continue
                lat, lon = float(lat_t), float(lon_t)
                if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
                    skipped.append((idx + 1, " ".join(toks), "coordinates outside Jharkhand"))
                    continue
                depth = float(depth_t) if _NUM.match(depth_t or "") else None
                d = _parse_date(toks[di])
                names = {"district": [], "block": [], "village": []}
                for w in name_words:
                    col = max((k for k in range(4) if hx[k] - 2.0 <= w["x0"]), default=0)
                    key = ("district", "district", "block", "village")[col]
                    names[key].append(w["text"])
                rows.append({
                    "date": d.isoformat(), "year": d.year, "month": d.month,
                    "season": season,
                    "district": " ".join(names["district"]),
                    "block": " ".join(names["block"]),
                    "village": " ".join(names["village"]),
                    "latitude": lat, "longitude": lon,
                    "depth_to_water_mbgl": depth,
                    "source_file": pdf_path.name, "source_page": idx + 1,
                    "note": note,
                })
    return rows, {"pages": len(pages), "rows": len(rows),
                  "skipped": skipped, "pages_without_header": header_missing}


def write_csv(rows: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def _decimals(x) -> int:
    t = repr(float(x))
    return 0 if "." not in t else len(t.split(".")[1].rstrip("0"))


def combine(primary: list[dict], supplementary: list[dict] | None = None
            ) -> tuple[list[dict], dict]:
    """Merge rows into one record: one reading per well per date.

    The key is the coordinates rounded to 1e-4 deg (~11 m) plus the date.
      * primary rows (the full-span files): a repeat of a key with the SAME
        depth collapses -- CGWB's tables print some wells twice (the Simdega
        well also under Gumla, its district until 2001; one Basia well under
        two block names; Raidih and Karra rows twice); a repeat with a
        DIFFERENT depth cannot be assigned (at Simdega's coordinates in
        2021-2024 the second row carries the Gumla-town reading), so both are
        kept, each flagged NOTE_SAME_SPOT.
      * supplementary rows (partial-period files): where the key exists and the
        depths agree to rounding (<= 0.05 m), the more precise value is kept --
        the partial files round differently in different decades; where the key
        is absent the row is added, flagged NOTE_SUPPLEMENTARY; where it exists
        with a real difference the full-span value stands (counted).
    Nothing is averaged into a number nobody measured."""
    out: list[dict] = []
    index: dict[tuple, int] = {}
    stats = {"primary_rows": len(primary), "collapsed_identical": 0,
             "same_spot_pairs": 0, "precision_upgraded": 0,
             "supplementary_added": 0, "supplementary_conflicts": 0,
             "supplementary_rows": len(supplementary or [])}

    def key(r):
        return (round(float(r["latitude"]), 4), round(float(r["longitude"]), 4), r["date"])

    for r in primary:
        k = key(r)
        if k not in index:
            index[k] = len(out)
            out.append(dict(r))
            continue
        kept = out[index[k]]
        a, b = kept["depth_to_water_mbgl"], r["depth_to_water_mbgl"]
        if a is None or b is None or abs(float(a) - float(b)) <= 1e-6:
            stats["collapsed_identical"] += 1
        else:
            stats["same_spot_pairs"] += 1
            kept["note"] = kept["note"] or NOTE_SAME_SPOT
            out.append({**r, "note": r["note"] or NOTE_SAME_SPOT})
    for r in supplementary or []:
        k = key(r)
        if k not in index:
            index[k] = len(out)
            out.append({**r, "note": r["note"] or NOTE_SUPPLEMENTARY})
            stats["supplementary_added"] += 1
            continue
        kept = out[index[k]]
        a, b = kept["depth_to_water_mbgl"], r["depth_to_water_mbgl"]
        if a is None or b is None:
            continue
        if abs(float(a) - float(b)) <= 0.051:
            if _decimals(b) > _decimals(a):
                kept["depth_to_water_mbgl"] = b
                stats["precision_upgraded"] += 1
        else:
            stats["supplementary_conflicts"] += 1
    out.sort(key=lambda r: (r["date"], r["district"], r["block"], r["village"]))
    return out, stats


#: The files the 1994-2026 record is built from. Full-span files are primary;
#: the partial-period files CGWB also published are supplementary. Checked
#: 2026-09-25 reading by reading: August 1994-2023 and pre-monsoon 1994-2003 /
#: 2004-2013 add nothing (kept here so a rebuild reproduces the CSV; a missing
#: file is reported, not fatal); pre-monsoon 2014-2024 adds 732 more precise
#: readings and 187 at wells absent from the full-span file, markedly deeper
#: (median 9.2 m vs 7.3 m), kept but flagged NOTE_SUPPLEMENTARY. LIMITATIONS 1i.
LONG_RECORD_SOURCES = {
    "Jan": ["January_WL_1994-2025.pdf", "January_2026.pdf"],
    "May": ["Pre-monsoon_WL_1994-2025.pdf"],
    "Aug": ["August_WL_1994-2025.pdf"],
    "Nov": ["post-monsoon_wl_1994-2023_compressed.pdf"],
}
LONG_RECORD_SUPPLEMENTARY = {
    "May": ["pre-monsoon_1994-2003.pdf", "pre-monsoon_2004-2013.pdf",
            "pre-monsoon_2014-2024.pdf"],
    "Aug": ["august_wl_1994-2023_compressed.pdf"],
}


def build_long_record(pdf_dir: Path, out: Path) -> dict:
    report, primary, supplementary = {}, [], []
    for sources, bucket in ((LONG_RECORD_SOURCES, primary),
                            (LONG_RECORD_SUPPLEMENTARY, supplementary)):
        for season, files in sources.items():
            for f in files:
                path = pdf_dir / f
                if not path.exists():
                    report[f] = "missing"
                    continue
                rows, rep = extract(path, season)
                report[f] = {"rows": rep["rows"], "skipped": len(rep["skipped"]),
                             "fallback_pages": len(rep["pages_without_header"])}
                bucket += rows
    rows, crep = combine(primary, supplementary)
    write_csv(rows, out)
    return {"files": report, **crep, "written": len(rows)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Extract Jharkhand rows from CGWB water-level PDFs.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("extract", help="one season's PDFs -> CSV")
    one.add_argument("--season", required=True, choices=["Jan", "May", "Aug", "Nov"])
    one.add_argument("--out", type=Path, required=True)
    one.add_argument("pdfs", type=Path, nargs="+")
    rec = sub.add_parser("record", help="the full 1994-2026 record from a folder of the PDFs")
    rec.add_argument("pdf_dir", type=Path)
    rec.add_argument("--out", type=Path,
                     default=REPO_ROOT / "Datasets" / "cgwb_waterlevel_jharkhand_1994_2026.csv")
    a = ap.parse_args(argv)
    if a.cmd == "record":
        print(build_long_record(a.pdf_dir, a.out))
        print("wrote", a.out)
        return 0
    allrows = []
    for p in a.pdfs:
        rows, rep = extract(p, a.season)
        print(f"{p.name}: {rep['pages']} pages -> {rep['rows']} rows; "
              f"skipped {len(rep['skipped'])}; fallback pages {rep['pages_without_header'][:5]}")
        for s in rep["skipped"][:8]:
            print("   skipped:", s)
        allrows += rows
    write_csv(allrows, a.out)
    print("wrote", a.out, len(allrows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
