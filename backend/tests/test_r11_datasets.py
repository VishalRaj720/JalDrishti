"""R11 — the `record_source` column and everything that depends on it.

These tests operate on **real dataset files**, restored from a snapshot in a
fixture. That is deliberate: the whole class of bug this feature can produce is
"the write succeeded and the loader can no longer read the file", and a fake CSV
would not catch it. The udepo workbook in particular has an 8-row preamble, a
used range that starts at column B, and duplicate header cells — a synthetic
fixture would have none of those, and the first implementation of the xlsx writer
passed every synthetic check while silently turning grade_c0_factor("Jaduguda")
from (0.6, 0.03) into (1.0, None).
"""
import shutil
import sys
from pathlib import Path

import pytest

from app.services import datasets as ds

REPO_ROOT = ds.REPO_ROOT
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def snapshot(tmp_path):
    """Give each test a genuinely SHIPPED baseline, then put the tree back.

    These tests used to run against whatever was on disk, which was fine while
    the working tree was clean and wrong the moment a real field observation had
    been synced: assertions like "every row is `original`" then failed because a
    legitimate added row was present. A test must control its own fixture state
    rather than depend on the checkout being untouched.

    The baseline comes from `git show HEAD:<path>` — the committed file — so
    "shipped" means exactly what is committed, not merely what happens to be
    there. Anything git cannot produce is left as-is and the test works from the
    live file.
    """
    import subprocess

    saved, restored_from_git = {}, []
    for key, f in ds.REGISTRY.items():
        if not f.path.exists():
            continue
        saved[key] = tmp_path / f"{key}{f.path.suffix}"
        shutil.copy2(f.path, saved[key])
        blob = subprocess.run(
            ["git", "show", f"HEAD:{f.relpath and ('Datasets/' + f.relpath)}"],
            cwd=ds.REPO_ROOT, capture_output=True)
        if blob.returncode == 0 and blob.stdout:
            f.path.write_bytes(blob.stdout)
            restored_from_git.append(key)
    ds.invalidate_caches()
    yield
    for key, src in saved.items():
        shutil.copy2(src, ds.REGISTRY[key].path)
    if ds.BACKUP_DIR.exists():
        shutil.rmtree(ds.BACKUP_DIR, ignore_errors=True)
    ds.invalidate_caches()

def _add_row(key: str, **values) -> str:
    """Append one `added` row directly, standing in for a completed sync."""
    f = ds.get(key)
    if f.kind == "xlsx":
        ds._xlsx_ensure_source(f)
        wb, ws, hrow, header = ds._xlsx_open(f)
        idx = {str(h): i for i, h in enumerate(header, start=1) if h is not None}
        r = ws.max_row + 1
        for col, val in values.items():
            ws.cell(row=r, column=idx[col], value=val)
        ws.cell(row=r, column=idx[ds.SOURCE_COL], value=ds.SOURCE_ADDED)
        ws.cell(row=r, column=idx[ds.REF_COL], value="testref01")
        wb.save(f.path)
    else:
        import pandas as pd
        df = ds._read(f)
        row = {c: "" for c in df.columns}
        row.update(values)
        row[ds.SOURCE_COL] = ds.SOURCE_ADDED
        row[ds.REF_COL] = "testref01"
        ds._write_csv(f, pd.concat([df, pd.DataFrame([row])], ignore_index=True))
    ds.invalidate_caches()
    return str(values[f.id_column])


# ── the column itself ────────────────────────────────────────────────

def test_every_registry_file_reads_with_a_source_column(snapshot):
    """All five files parse, and every shipped row is `original`."""
    for key in ds.REGISTRY:
        df = ds._read(ds.get(key))
        assert ds.SOURCE_COL in df.columns, key
        assert ds.REF_COL in df.columns, key
        assert set(df[ds.SOURCE_COL].unique()) <= {ds.SOURCE_ORIGINAL, ds.SOURCE_ADDED}
        assert (df[ds.SOURCE_COL] == ds.SOURCE_ORIGINAL).all(), (
            f"{key}: shipped rows must all be '{ds.SOURCE_ORIGINAL}'")


def test_summary_reports_the_split(snapshot):
    rows = {e["key"]: e for e in ds.summary()}
    assert set(rows) == set(ds.REGISTRY)
    for key, e in rows.items():
        assert e["available"] is True, f"{key}: {e.get('error')}"
        assert e["original"] == e["rows"]
        assert e["added"] == 0


# ── the immutability rule ────────────────────────────────────────────

@pytest.mark.parametrize("key,row_id", [
    ("water_quality", "1"),
    ("groundwater_levels", "428550"),
    ("ore_deposits", "Jaduguda"),
    ("naquim_vertical", "Bokaro"),
])
def test_original_rows_cannot_be_edited_or_deleted(snapshot, key, row_id):
    """The core guarantee, checked per file and against the bytes on disk."""
    f = ds.get(key)
    before = f.path.read_bytes()

    with pytest.raises(ds.DatasetError) as ei:
        ds.update_row(key, row_id, {ds.get(key).id_column
                                    if False else _any_editable_col(key): "x"})
    assert ei.value.status_code == 409
    assert "original" in str(ei.value.message)

    with pytest.raises(ds.DatasetError) as ei:
        ds.delete_row(key, row_id)
    assert ei.value.status_code == 409

    assert f.path.read_bytes() == before, (
        f"{key}: a refused mutation still altered the file")


def _any_editable_col(key: str) -> str:
    df = ds._read(ds.get(key))
    for c in df.columns:
        if c not in (ds.get(key).id_column, ds.SOURCE_COL, ds.REF_COL):
            return str(c)
    raise AssertionError(f"{key} has no editable column")


def test_source_column_itself_cannot_be_edited(snapshot):
    """A row cannot be relabelled as shipped evidence."""
    _add_row("ore_deposits", name="TestDeposit", district="Test", state="Jharkhand",
             center_lat=23.5, center_lon=86.0, status="Field-observed")
    with pytest.raises(ds.DatasetError) as ei:
        ds.update_row("ore_deposits", "TestDeposit",
                      {ds.SOURCE_COL: ds.SOURCE_ORIGINAL})
    assert "provenance" in str(ei.value.message)


# ── added rows are editable, and the loaders still read the file ─────

def test_added_row_edit_delete_roundtrip_csv(snapshot):
    _add_row("ore_deposits", name="TestDeposit", district="Test", state="Jharkhand",
             center_lat=23.5, center_lon=86.0, status="Field-observed")

    df = ds._read(ds.get("ore_deposits"))
    assert (df[ds.SOURCE_COL] == ds.SOURCE_ADDED).sum() == 1

    out = ds.update_row("ore_deposits", "TestDeposit", {"district": "Bokaro"})
    assert out["before"]["district"] != out["after"]["district"]
    assert Path(REPO_ROOT / out["backup"]).exists(), "no backup was written"

    df = ds._read(ds.get("ore_deposits"))
    assert df.loc[df["name"] == "TestDeposit", "district"].iloc[0] == "Bokaro"

    out = ds.delete_row("ore_deposits", "TestDeposit")
    assert out["record_ref"] == "testref01", "record_ref must survive to the caller"
    df = ds._read(ds.get("ore_deposits"))
    assert "TestDeposit" not in set(df["name"])


def test_xlsx_write_does_not_corrupt_the_grade_lookup(snapshot):
    """The regression that motivated the in-place xlsx writer.

    A no-op round trip through pandas used to blank the `Grade Range` header,
    which changed a real answer with no error and no row-count change.
    """
    from ml_pipeline.data_prep import ore_grades as og

    before = og.grade_c0_factor("Jaduguda")
    assert before[1] is not None, "fixture assumption: Jaduguda has a UDEPO grade"

    ds._xlsx_ensure_source(ds.get("ore_grades"))
    ds.invalidate_caches()
    assert og.grade_c0_factor("Jaduguda") == before, "adding the column changed a grade"

    _add_row("ore_grades", **{
        "Deposit ID": "FIELD-TEST01", "Deposit Name": "Test Deposit",
        "Main Commodity": "Uranium", "Grade Range": "0.10"})
    assert og.grade_c0_factor("Jaduguda") == before, "appending changed another row"
    # The added row is picked up by the real loader, not just present in the file.
    assert og.grade_c0_factor("Test Deposit")[1] is not None, (
        "an added grade row must reach grade_c0_factor")

    ds.update_row("ore_grades", "FIELD-TEST01", {"Grade Range": "0.20"})
    ds.invalidate_caches()
    assert og.grade_c0_factor("Test Deposit")[1] == pytest.approx(0.20)

    ds.delete_row("ore_grades", "FIELD-TEST01")
    ds.invalidate_caches()
    assert og.grade_c0_factor("Jaduguda") == before, "delete changed another row"


def test_chemistry_still_loads_after_an_added_row(snapshot):
    """A column mismatch here would silently corrupt every baseline."""
    from ml_pipeline.data_prep import jharkhand_loader as jl

    before = len(jl.load_jharkhand_water_quality())
    _add_row("water_quality", **{
        "S. No.": 99001, "State": "Jharkhand", "District": "Bokaro",
        "Location": "Test Well", "Longitude": 86.0, "Latitude": 23.5,
        "Year": 2026, "U (ppb)": 4.2, "source_table": "field_observation"})
    after = len(jl.load_jharkhand_water_quality())
    assert after == before + 1, "the appended chemistry row did not reach the loader"


def test_levels_still_load_after_an_added_row(snapshot):
    """flow_field reads this file; a bad row would break the whole rebuild."""
    import pandas as pd

    f = ds.get("groundwater_levels")
    _add_row("groundwater_levels", **{
        "id": 999001, "date": "2026-05-14", "state_name": "Jharkhand",
        "state_code": 20, "district_name": "Bokaro", "station_name": "Test Station",
        "latitude": 23.5, "longitude": 86.0, "source": "FIELD",
        "currentlevel": 3.5})
    df = pd.read_csv(f.path, parse_dates=["date"], encoding="utf-8-sig")
    row = df[df["id"] == 999001]
    assert len(row) == 1
    assert float(row["currentlevel"].iloc[0]) == 3.5
    assert row["date"].iloc[0].year == 2026


# ── strip / restore ──────────────────────────────────────────────────

def test_strip_added_leaves_only_original(snapshot):
    _add_row("ore_deposits", name="TestDeposit", district="Test", state="Jharkhand",
             center_lat=23.5, center_lon=86.0, status="Field-observed")
    before = len(ds._read(ds.get("ore_deposits")))

    dry = ds.strip_added("ore_deposits", dry_run=True)
    assert dry["would_remove"] == 1
    assert len(ds._read(ds.get("ore_deposits"))) == before, "dry run wrote to the file"

    out = ds.strip_added("ore_deposits")
    assert out["removed"] == 1
    df = ds._read(ds.get("ore_deposits"))
    assert (df[ds.SOURCE_COL] == ds.SOURCE_ORIGINAL).all()
    assert len(df) == before - 1


def test_restore_puts_a_file_back(snapshot):
    f = ds.get("ore_deposits")
    original_rows = len(ds._read(f))
    _add_row("ore_deposits", name="TestDeposit", district="Test", state="Jharkhand",
             center_lat=23.5, center_lon=86.0, status="Field-observed")
    out = ds.delete_row("ore_deposits", "TestDeposit")

    backups = ds.list_backups("ore_deposits")
    assert backups, "delete must leave a restore point"
    ds.restore("ore_deposits", backups[0]["name"])
    df = ds._read(f)
    assert len(df) == original_rows + 1, "restore did not bring the row back"


def test_restore_rejects_a_path_outside_the_dataset_directory(snapshot):
    with pytest.raises(ds.DatasetError):
        ds.restore("ore_deposits", "../../../etc/passwd.bak")


def test_unknown_dataset_is_404():
    with pytest.raises(ds.DatasetError) as ei:
        ds.get("nope")
    assert ei.value.status_code == 404
