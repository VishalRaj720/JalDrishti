"""
2026-09-25 -- the CGWB 2024 quality extract and what is measured from it
(data_prep/cgwb_gwq_pdf.py, validation/baseline_variability.py, LIMITATIONS 1h).

The PDF itself is not in the repository, so these pin the committed CSV (no
row lost, no column shifted into another) and that the variability artifact is
reproducible from it -- the numbers LIMITATIONS 1h quotes.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ml_pipeline.data_prep.cgwb_gwq_pdf import CSV_COLUMNS, EXPECTED_HEADER, _norm
from ml_pipeline.validation import baseline_variability as bv


def _csv() -> pd.DataFrame:
    return pd.read_csv(bv.CSV_2024)


def test_every_jharkhand_row_is_there_and_contiguous():
    d = _csv()
    assert len(d) == 288
    assert list(d.columns) == CSV_COLUMNS + ["source_page"]
    assert (d["state"] == "Jharkhand").all() and d["district"].nunique() == 24
    for _season, g in d.groupby("season"):
        sn = np.sort(g["s_no"].astype(int).to_numpy())
        assert np.all(np.diff(sn) == 1), "a row was dropped inside a season block"


def test_no_column_was_shifted():
    """Physical sanity per column: a one-column shift would put pH values in the
    EC column, or chloride into nitrate, and these ranges would break."""
    d = _csv()
    assert d["pH"].between(5.5, 9.5).all()
    assert (d["EC_uS_cm"] > 50).all()
    # TDS is reported alongside EC; the usual ratio is 0.55-0.75
    r = d["TDS_mg_L"] / d["EC_uS_cm"]
    assert r.between(0.5, 0.8).mean() > 0.95
    assert d["longitude"].between(83.3, 87.95).all() and d["latitude"].between(21.9, 25.35).all()
    # uranium and arsenic are NOT reported for Jharkhand in 2024 -- stated, not assumed
    assert d["U_ppb"].isna().all() and d["As_ppb"].isna().all()


def test_the_header_guard_normalises_only_what_it_should():
    assert _norm("EC\n(µ S/cm at 25\n° C)").replace(" ", "") == \
        EXPECTED_HEADER[10].replace(" ", "")
    assert len(EXPECTED_HEADER) == len(CSV_COLUMNS) == 36


def test_the_variability_artifact_is_reproducible():
    committed = json.loads(bv.OUT.read_text(encoding="utf-8"))
    fresh = bv.run()
    assert fresh["two_of_three_false_alarm_share"] == committed["two_of_three_false_alarm_share"]
    # the headline LIMITATIONS 1h quotes
    assert committed["two_of_three_false_alarm_share"]["x1.2"] > 0.25
    assert committed["two_of_three_false_alarm_share"]["x3.0"] < 0.05
