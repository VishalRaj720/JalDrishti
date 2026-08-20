"""Model artifact backup.

The problem: `ml_pipeline/ml/artifacts/` holds the trained surrogate, and only
five of its sixteen files are tracked in git — the JSON metadata. All ten
`.joblib` weight files are untracked, so the model exists in one copy on one
disk. `ml.train` overwrites that directory in place, and the README documents
running it by hand, so the ordinary documented workflow can destroy the only
copy of a model whose conformal coverage was hand-verified.

These tests use a temporary artifacts directory rather than the real one: the
point is to prove the copy/restore mechanics without a bug in them being able to
damage the very thing they exist to protect.
"""
import json

import pytest
import pytest_asyncio

from app.models.user import User, UserRole
from app.services import model_ops as mo
from app.services.auth import create_access_token, hash_password


@pytest_asyncio.fixture()
async def analyst_token(db_session):
    """An analyst: runs the model, does not get to replace it."""
    u = User(username="mbanalyst", email="mbanalyst@example.com",
             hashed_password=hash_password("pass1234"), role=UserRole.analyst)
    db_session.add(u)
    await db_session.commit()
    return create_access_token(str(u.id), u.role)


@pytest.fixture
def fake_artifacts(tmp_path, monkeypatch):
    """Redirect the module at a scratch artifacts dir + bundle dir."""
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "model_card.json").write_text(json.dumps({"version": 3}), encoding="utf-8")
    (art / "band_x_p50.joblib").write_bytes(b"WEIGHTS-V1")
    (art / "metrics.json").write_text(json.dumps({"r2": 0.9}), encoding="utf-8")

    monkeypatch.setattr(mo, "MODEL_ARTIFACTS", art)
    monkeypatch.setattr(mo, "MODEL_BUNDLES", tmp_path / "artifact_bundles")
    return art


def test_state_reports_an_unbacked_up_model_as_unprotected(fake_artifacts):
    st = mo.model_state()
    assert st["live"] is True
    assert st["weight_files"] == 1
    assert st["unprotected"] is True
    assert "single copy" in st["message"]


def test_backup_then_state_is_protected(fake_artifacts):
    out = mo.backup_model("before-train")
    assert out["files"] == 3
    assert "before-train" in out["name"]

    st = mo.model_state()
    assert st["unprotected"] is False
    assert len(st["backups"]) == 1


def test_model_card_sha_matches_the_run_provenance_hash(fake_artifacts):
    """A bundle must be traceable to the runs computed with it.

    `ml_pipeline_adapter` pins `sha256(model_card.json)` onto every stored run.
    If the bundle reported anything else, you could not tell which bundle a filed
    number came from — which is the whole reason to keep old bundles.
    """
    import hashlib

    mo.backup_model()
    bundle = mo.list_model_backups()[0]
    expected = hashlib.sha256(
        (fake_artifacts / "model_card.json").read_bytes()).hexdigest()
    assert bundle["model_card_sha"] == expected


def test_restore_brings_back_the_old_weights(fake_artifacts):
    mo.backup_model("v1")
    name = mo.list_model_backups()[0]["name"]

    # Stand in for a retrain: overwrite the weights in place.
    (fake_artifacts / "band_x_p50.joblib").write_bytes(b"WEIGHTS-V2")
    assert (fake_artifacts / "band_x_p50.joblib").read_bytes() == b"WEIGHTS-V2"

    out = mo.restore_model(name)
    assert (fake_artifacts / "band_x_p50.joblib").read_bytes() == b"WEIGHTS-V1"
    # ...and the overwritten version is itself preserved, so restoring is not
    # the operation that loses data.
    assert out["backup_of_previous"] != name
    pre = mo.MODEL_BUNDLES / out["backup_of_previous"]
    assert (pre / "band_x_p50.joblib").read_bytes() == b"WEIGHTS-V2"


def test_restore_rejects_a_path_outside_the_bundle_directory(fake_artifacts):
    mo.backup_model()
    for bad in ("../../etc", "..", "/etc/passwd", "nope"):
        with pytest.raises(mo.ds.DatasetError):
            mo.restore_model(bad)


def test_label_is_slugified_not_trusted(fake_artifacts):
    """The label reaches a filesystem path."""
    out = mo.backup_model("../../evil name/../")
    assert "/" not in out["name"] and "\\" not in out["name"]
    assert ".." not in out["name"]
    assert (mo.MODEL_BUNDLES / out["name"]).is_dir()


@pytest.mark.asyncio
async def test_backup_endpoint_is_admin_only(client, analyst_token):
    r = await client.post("/api/v1/model-ops/model-backups",
                          headers={"Authorization": f"Bearer {analyst_token}"})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_model_state_endpoint_is_readable_by_staff(client, analyst_token):
    """An analyst reading a number should be able to see which model produced it."""
    r = await client.get("/api/v1/model-ops/model",
                         headers={"Authorization": f"Bearer {analyst_token}"})
    assert r.status_code == 200, r.text
    assert "weight_files" in r.json()
