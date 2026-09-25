"""
2026-09-25 -- the CGWB depth-to-water record 1994 - Jan 2026 for Jharkhand
(data_prep/cgwb_wl_pdf.py -> Datasets/cgwb_waterlevel_jharkhand_1994_2026.csv,
LIMITATIONS 1i).

The PDFs are not in the repository, so these pin the extraction rules and the
committed CSV -- including an independent cross-check against the 2013-2021
file already on disk, which no misread column could pass.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml_pipeline.data_prep.cgwb_wl_pdf import (
    NOTE_REPAIRED, NOTE_SAME_SPOT, NOTE_SUPPLEMENTARY, _repair_overlap, combine,
    load_long_record, water_table_rows)

REPO = Path(__file__).resolve().parents[2]
RECORD = REPO / "Datasets" / "cgwb_waterlevel_jharkhand_1994_2026.csv"
OLD = REPO / "Datasets" / "cgwb_waterlevel_jharkhand.csv"


# ── the overlap repair ─────────────────────────────────────────────────


@pytest.mark.parametrize("garbled", ["Ag.Of2fi3c.e3)4110", "Ag.Offic2e3).34110",
                                     "Ag.Office)23.34110"])
def test_an_interleaved_latitude_is_recovered_with_the_name(garbled):
    assert _repair_overlap(garbled) == ("23.34110", "Ag.Office)")


@pytest.mark.parametrize("tok", ["Office)", "Road2No5", "Ward12"])
def test_anything_that_is_not_a_jharkhand_latitude_is_refused(tok):
    assert _repair_overlap(tok) is None


# ── the merge ──────────────────────────────────────────────────────────


def _row(depth, date="2020-05-01", lat=23.1, lon=85.1, note="", f="a.pdf"):
    return {"date": date, "latitude": lat, "longitude": lon, "district": "D",
            "block": "B", "village": "V", "depth_to_water_mbgl": depth,
            "note": note, "source_file": f}


def test_identical_repeats_collapse_and_a_second_well_is_kept_flagged():
    rows, st = combine([_row(5.0), _row(5.0), _row(9.0)])
    assert st["collapsed_identical"] == 1 and st["same_spot_pairs"] == 1
    assert len(rows) == 2 and all(r["note"] == NOTE_SAME_SPOT for r in rows)


def test_supplementary_files_raise_precision_add_missing_and_never_override():
    prim = [_row(9.2), _row(7.0, date="2021-05-01")]
    supp = [_row(9.18),                         # same reading, more precise
            _row(12.0, date="2021-05-01"),      # a real difference: primary stands
            _row(30.6, date="2024-05-10", lat=23.5)]   # absent: added, flagged
    rows, st = combine(prim, supp)
    by_date = {(r["date"], r["latitude"]): r for r in rows}
    assert by_date[("2020-05-01", 23.1)]["depth_to_water_mbgl"] == 9.18
    assert by_date[("2021-05-01", 23.1)]["depth_to_water_mbgl"] == 7.0
    assert by_date[("2024-05-10", 23.5)]["note"] == NOTE_SUPPLEMENTARY
    assert (st["precision_upgraded"], st["supplementary_conflicts"],
            st["supplementary_added"]) == (1, 1, 1)


# ── the committed record ───────────────────────────────────────────────


def _record() -> pd.DataFrame:
    return load_long_record(RECORD)


def test_the_record_spans_1994_to_january_2026_in_four_campaigns():
    d = _record()
    assert d["date"].min().year == 1994 and d["date"].max() >= pd.Timestamp("2026-01-01")
    assert set(d["season"]) == {"Jan", "May", "Aug", "Nov"}
    assert len(d) > 25_000
    assert d["latitude"].between(21.8, 25.5).all() and d["longitude"].between(83.2, 88.2).all()
    assert set(d["note"]) <= {"", NOTE_REPAIRED, NOTE_SUPPLEMENTARY, NOTE_SAME_SPOT}


def test_the_overlapping_station_is_present_not_dropped():
    """Its long name overprints the latitude in the recent years' tables
    (earlier years print cleanly); every year is kept, the repaired ones say so."""
    d = _record()
    s = d[d["village"].str.contains("Hanuman Mandir", na=False)]
    assert len(s) >= 10
    assert np.allclose(s["latitude"], 23.3411) and np.allclose(s["longitude"], 85.3158)
    repaired = s[s["note"] == NOTE_REPAIRED]
    assert len(repaired) >= 10
    assert repaired["village"].str.endswith("Ag.Office)").all()


def test_every_row_has_its_three_names_and_a_known_district():
    """A misassigned column empties district/block or piles every name into the
    village; a district outside Jharkhand's list would be a column shift."""
    d = _record()
    for col in ("district", "block", "village"):
        assert (d[col].str.strip() != "").all(), f"empty {col}"
    known = {"bokaro", "chatra", "deoghar", "dhanbad", "dumka", "east singhbum",
             "east singhbhum", "purbi singhbhum", "garhwa", "giridih", "godda",
             "gumla", "hazaribagh", "hazaribag", "jamtara", "khunti", "koderma",
             "latehar", "lohardaga", "pakur", "palamu", "palamau", "ramgarh",
             "ranchi", "sahebganj", "sahibganj", "saraikela kharsawan",
             "seraikela kharsawan", "saraikela", "simdega", "west singhbhum",
             "west singhbum", "pashchimi singhbhum"}
    unknown = sorted(set(d["district"].str.lower()) - known)
    assert not unknown, f"district names outside Jharkhand's list: {unknown[:10]}"


def test_water_table_rows_leave_out_what_may_not_be_the_water_table():
    """Possible bore wells and unassignable same-spot pairs are out; the
    repaired Bero rows (exact coordinates) are in; an empty note is read as ""
    not NaN, or every clean row would silently drop."""
    d = _record()
    w = water_table_rows(d)
    assert set(w["note"]) == {"", NOTE_REPAIRED}
    assert len(w) == int(d["note"].isin(["", NOTE_REPAIRED]).sum())
    assert len(w) > 25_000


def test_the_trend_summary_is_what_the_record_gives():
    """validation/water_table_trends.json (quoted in LIMITATIONS 1i) must be
    re-derivable from the committed CSV."""
    import json
    from ml_pipeline.validation.water_table_trends import OUT, run
    assert json.loads(OUT.read_text(encoding="utf-8")) == json.loads(json.dumps(run(write=False)))


def test_the_record_agrees_with_the_independent_2013_2021_file():
    """Station by station, the same well in the same month reads the same depth
    in both sources (medians) -- a misassigned column would break this."""
    d = _record()
    d = d[d["note"] == ""]
    old = pd.read_csv(OLD, parse_dates=["date"])
    old = old[(old["currentlevel"] >= 0) & (old["currentlevel"] < 100)]
    for x in (d, old):
        x["la"], x["lo"] = x["latitude"].round(3), x["longitude"].round(3)
        x["ym"] = x["date"].dt.to_period("M")
    m = old.merge(d[["la", "lo", "ym", "depth_to_water_mbgl"]], on=["la", "lo", "ym"])
    m["diff"] = m["currentlevel"] - m["depth_to_water_mbgl"]
    per = m.groupby(["la", "lo"])["diff"].agg(["median", "count"])
    per = per[per["count"] >= 4]
    assert len(per) > 250
    assert (per["median"].abs() <= 0.1).mean() > 0.95
