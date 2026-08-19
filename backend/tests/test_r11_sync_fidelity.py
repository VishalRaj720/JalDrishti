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
    """Build a genuinely pristine baseline, then put the working tree back.

    This fixture has now been wrong twice, in opposite directions, and both
    failures were the same mistake: trusting an external source to be pristine.

      1. Reading whatever was on disk — broke the moment a real field
         observation had been synced, because assertions like "every row is
         `original`" then failed on legitimate data.
      2. Reading `git show HEAD:` — broke the moment those synced datasets were
         COMMITTED, because HEAD stopped being the shipped state and started
         being the current one.

    So the baseline is CONSTRUCTED here rather than fetched: strip every `added`
    row and drop the provenance columns. That is the definition of "as shipped"
    and it holds no matter what is on disk or in the history.
    """
    saved = {}
    for key, f in ds.REGISTRY.items():
        if not f.path.exists():
            continue
        saved[key] = tmp_path / f"{key}{f.path.suffix}"
        shutil.copy2(f.path, saved[key])
        if f.kind == "csv":
            header, rows, enc = ds._read_raw(f)
            si = ds._col(header, ds.SOURCE_COL)
            keep = [r for r in rows
                    if not (0 <= si < len(r) and r[si] == ds.SOURCE_ADDED)]
            for name in (ds.REF_COL, ds.SOURCE_COL):
                i = ds._col(header, name)
                if i >= 0:
                    header.pop(i)
                    for r in keep:
                        if i < len(r):
                            r.pop(i)
            ds._write_raw(f, header, keep, enc)
        else:
            # The xlsx needs normalising too, or "every row is original" cannot
            # hold for it. Safe to rewrite: no test compares xlsx bytes against
            # an external reference — the one that compares bytes takes its own
            # `before` snapshot inside the test body, after this has run.
            try:
                ds.strip_added(key)
            except Exception:  # noqa: BLE001 — a missing/odd file must not break setup
                pass
    # Normalising above went through the write path, which takes a "pristine"
    # snapshot of the file as it was BEFORE stripping — i.e. of the un-normalised
    # state. Leaving that behind hands the next test a snapshot that disagrees
    # with the baseline it was just given. Cleared so each test starts with none.
    if ds.BACKUP_DIR.exists():
        shutil.rmtree(ds.BACKUP_DIR, ignore_errors=True)
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

    # Make this test independent of everything that ran before it.
    #
    # It passed alone and failed in the full suite: earlier files
    # (test_dataset_sync.py) sync ore into this same workbook, so by the time it
    # runs the xlsx may already carry the provenance column — and a snapshot of
    # THAT is correctly judged not-pristine, which is the very thing being
    # asserted. Normalising here rather than trusting the fixture's pass makes
    # the precondition explicit instead of incidental.
    if ds.BACKUP_DIR.exists():
        shutil.rmtree(ds.BACKUP_DIR, ignore_errors=True)
    ds.drop_provenance_columns(f)
    ds.invalidate_caches()

    before = f.path.read_bytes()
    ds.backup_file(f, "testref")
    assert ds._pristine_path(f).exists(), "no pristine snapshot was taken"

    # The contract is the RESTORE, not the bytes of the copy. Asserting
    # `snapshot == live at snapshot time` only tests shutil.copy2, and it is
    # brittle: openpyxl stamps a fresh timestamp into the zip on every save, so
    # the fixture's own normalisation pass changes those bytes before the test
    # body ever runs.
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


def test_is_pristine_snapshot_judges_a_snapshot_by_its_contents(tmp_path, monkeypatch):
    """The predicate that decides whether a reset may restore, tested alone.

    Kept out of the integration test above: asserting it there made that test
    depend on what every earlier file had left in the shared workbook, and it
    failed in the full suite while passing on its own — which says more about
    suite ordering than about the predicate. Here the inputs are built from
    scratch, so a failure means the rule itself is wrong.

    The rule: a snapshot is only "pristine" if it carries no provenance column.
    A snapshot taken after this system had already written is NOT a valid
    restore target — restoring it would put the added rows back and undo the
    reset it was meant to complete.
    """
    monkeypatch.setattr(ds, "DATASETS", tmp_path)
    monkeypatch.setattr(ds, "BACKUP_DIR", tmp_path / ".backups")
    monkeypatch.setattr(ds, "PRISTINE_DIR", tmp_path / ".backups" / "pristine")

    f = ds.DatasetFile(key="t", relpath="t.csv", kind="csv", id_column="name",
                       label="t", governs="t")
    f.path.write_text("name,value" + ds.LF + "A,1" + ds.LF, encoding="utf-8")

    assert not ds.is_pristine_snapshot(f), "no snapshot yet — cannot be pristine"

    ds.ensure_pristine(f)
    assert ds.is_pristine_snapshot(f), "a snapshot of an untouched file IS pristine"

    # Now simulate a snapshot taken too late: one that already has the column.
    ds._pristine_path(f).write_text(
        f"name,value,{ds.SOURCE_COL},{ds.REF_COL}" + ds.LF
        + "A,1,original," + ds.LF
        + "B,2,added,r1" + ds.LF,
        encoding="utf-8")
    assert not ds.is_pristine_snapshot(f), (
        "a snapshot carrying the provenance column must be refused — restoring "
        "it would put the added rows back and undo the reset")
