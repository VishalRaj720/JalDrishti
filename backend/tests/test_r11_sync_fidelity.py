"""Three bugs found by testing the sync end to end, pinned so they stay fixed.

All three shared a shape: the feature *reported success* while doing the wrong
thing, so nothing failed and nothing was visibly broken until someone compared
the files against what shipped.
"""
import shutil
import subprocess

import pytest

from app.services import datasets as ds


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

# ── bug 1: the sync joined on a column that is always NULL ───────────

def test_the_sync_query_joins_on_applied_id_not_target_id():
    """`target_id` is NULL for every field-officer submission.

    `ck_field_obs_target` enforces `operation = 'create' AND target_id IS NULL`,
    and every submission from the field is a create — so joining `water_samples`
    on `f.target_id` matched nothing at all. Both the chemistry and level syncs
    reported "Nothing to sync" while `/dataset-sync/status` correctly counted the
    same observations as approved-and-pending: the exact split-brain the feature
    exists to close, reported as success.

    Asserted against the SQL text because the failure was silent — there is no
    error to catch, only an empty result set.
    """
    import inspect

    from app.services import dataset_sync as sync

    for fn in (sync._unsynced_water_samples, sync._unsynced_levels):
        src = inspect.getsource(fn)
        assert "COALESCE(f.applied_id, f.target_id)" in src, (
            f"{fn.__name__} must join on applied_id — target_id is NULL for "
            f"every 'create', which is every field submission")


# ── bug 2: writes reformatted rows nobody touched ────────────────────

@pytest.mark.parametrize("key", ["ore_deposits", "water_quality",
                                 "groundwater_levels", "naquim_vertical"])
def test_a_csv_survives_an_append_and_strip_byte_for_byte(snapshot, key):
    """Appending a row must not rewrite the rest of the file.

    Round-tripping through pandas silently reformatted every number in the file
    — `22.7332550` came back as `22.733255`, `0.00` as `0.0` — so a three-row
    append produced a 794-line diff against rows nobody had edited. On a project
    whose whole claim is provenance, quietly rewriting the shipped evidence base
    as a side effect of adding to it is not acceptable.
    """
    f = ds.get(key)
    before = f.path.read_bytes()

    header, rows, _ = ds._read_raw(f)
    row = {header[0]: "R11-FIDELITY-TEST"}
    ds.append_rows(f, [row], "testref")

    after_append = f.path.read_bytes()
    assert after_append != before, "the append did not happen"

    out = ds.strip_added(key)
    assert out["removed"] == 1

    assert f.path.read_bytes() == before, (
        f"{f.relpath} did not come back byte-for-byte after append + strip")


def test_a_write_never_adds_a_byte_order_mark(snapshot):
    """`utf-8-sig` on write emits a BOM unconditionally.

    Using it for every file gave `jharkhand_uranium_deposits.csv` a BOM it never
    shipped with, so the file differed from the committed version forever after
    the first sync — even with every added row removed. Only
    `waterQuality_jharkhand.csv` genuinely has one.
    """
    for key in ("ore_deposits", "groundwater_levels", "naquim_vertical"):
        f = ds.get(key)
        had_bom = f.path.read_bytes()[:3] == ds._BOM
        assert not had_bom, f"fixture assumption: {f.relpath} has no BOM"

        ds.append_rows(f, [{ds._read_raw(f)[0][0]: "BOM-TEST"}], "testref")
        assert f.path.read_bytes()[:3] != ds._BOM, (
            f"{f.relpath} gained a BOM it never shipped with")
        ds.strip_added(key)


# ── bug 3: reset removed rows but not the file's shape ───────────────

def test_reset_removes_the_provenance_columns_too(snapshot):
    """Stripping rows is not enough to restore the file.

    `record_source` and `record_ref` are added on first write and used to stay
    forever, so a file with every added row removed STILL differed from what
    shipped by two header columns — and showed up in `git status` permanently,
    which read as "the reset did not work". It had; the file's shape had changed.
    """
    f = ds.get("ore_deposits")
    ds.append_rows(f, [{"name": "R11-SHAPE-TEST"}], "testref")

    header, _, _ = ds._read_raw(f)
    assert ds.SOURCE_COL in header and ds.REF_COL in header

    ds.strip_added("ore_deposits")
    header, _, _ = ds._read_raw(f)
    assert ds.SOURCE_COL not in header, "record_source outlived the reset"
    assert ds.REF_COL not in header, "record_ref outlived the reset"


def test_a_pristine_snapshot_is_taken_before_the_first_write(snapshot):
    """The xlsx can never round-trip: openpyxl re-serialises the workbook.

    Byte-preserving CSV writers fixed three of the four files; the fourth needed
    a snapshot instead, because no amount of care in the write path survives a
    library that rewrites zip member order and metadata on save.
    """
    f = ds.get("ore_grades")
    before = f.path.read_bytes()

    ds.backup_file(f, "testref")
    pristine = ds._pristine_path(f)
    assert pristine.exists(), "no pristine snapshot was taken"
    assert pristine.read_bytes() == before

    # Corrupt the live file, then prove strip_added restores the snapshot.
    f.path.write_bytes(before + b"\x00junk")
    ds.strip_added("ore_grades")
    assert f.path.read_bytes() == before, "reset did not restore the pristine copy"


def test_backups_do_not_litter_the_tracked_data_directory(snapshot):
    """Backups used to be written beside the original.

    Four `.bak` files accumulated directly in `Datasets/` during testing and
    appeared in every `git status` — exactly the noise that makes a real change
    hard to spot.
    """
    f = ds.get("ore_deposits")
    ds.backup_file(f, "testref")

    stray = list(f.path.parent.glob("*.bak"))
    assert stray == [], f"backups written into the tracked tree: {stray}"
    assert ds.BACKUP_DIR.exists()
    assert ds.BACKUP_DIR.name.startswith("."), "backup dir should be dot-prefixed"
