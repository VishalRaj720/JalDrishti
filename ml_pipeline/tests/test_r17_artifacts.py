"""R17 -- the v4/v5/v6 artifacts carry baselines, provenance and a sensitivity
record.

  * metrics.json: every band target reports the three reference models on
    the same folds, and the surrogate beats all of them in log space;
  * model_card.json: version 6 (the 2026-09-26 grounding-pass retrain,
    LIMITATIONS.md 1k; v5 was the post-freeze background-floor retrain, v4
    the beta retrain), the beta prior, and a reproducibility block whose
    training-CSV SHA-256 matches the file on disk when it is present;
  * the sensitivity script produces the documented schema on a tiny design
    and restores every config constant it patched;
  * the audit's radium gate is still reported as failing -- it must not have
    been quietly removed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ml_pipeline.config import parameters as P

ART = Path(__file__).resolve().parents[1] / "ml" / "artifacts"
OUT = Path(__file__).resolve().parents[1] / "outputs"


def _metrics():
    return json.loads((ART / "metrics.json").read_text())


def _card():
    return json.loads((ART / "model_card.json").read_text())


def test_baselines_are_reported_and_beaten():
    m = _metrics()
    for target, b in m["bands"].items():
        bl = b["baselines"]
        assert set(bl) >= {"mean", "ridge", "stump", "surrogate_p50"}, target
        assert abs(bl["mean"]["r2_log"]) < 0.05                       # the floor
        assert bl["surrogate_p50"]["r2_log"] > bl["ridge"]["r2_log"] > bl["stump"]["r2_log"], target
        assert bl["surrogate_p50"]["r2_log"] == pytest.approx(b["r2_log"])


def test_model_card_is_v6_with_the_beta_prior_and_provenance():
    """v6 = the 2026-09-26 grounding-pass retrain (LIMITATIONS.md 1k): depth-
    decayed K coverage, survey-blended backgrounds, species support recorded."""
    c = _card()
    assert c["version"] == 6
    r = c["reproducibility"]
    assert r["beta_prior"] == list(P.DUAL_POROSITY["beta_prior"])
    assert r["beta_mc_factor"] == P.DUAL_POROSITY["beta_mc_factor"]
    assert r["training_rows"] == 18000 and r["training_scenarios"] == 900
    assert len(r["training_csv_sha256"]) == 64
    assert r["bake_meta"] is None or r["bake_meta"]["version"] == 6
    assert r["regenerate"][0].startswith("python -m ml_pipeline.synthetic.generate")
    csv = OUT / r["training_csv"]
    if csv.exists():
        h = hashlib.sha256()
        with open(csv, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        assert h.hexdigest() == r["training_csv_sha256"], (
            "the training CSV on disk is not the one the artifacts were trained on")


def test_hydro_support_covers_the_porosity_derived_beta():
    """The served beta for every lithology must sit inside the retrained
    support (Rd = 1 + beta) -- this is what the v4 retrain was for."""
    box = _card()["hydro_support"]["fractured"]["retardation_Rd"]
    for litho, n_total in P.TOTAL_POROSITY.items():
        if P.LITHOLOGY_REGIME.get(litho) != "fractured":
            continue
        b = P.beta_from_porosities(n_total, P.DEFAULT_EFFECTIVE_POROSITY.get(litho, 0.05))
        assert box[0] <= 1.0 + b <= box[1], (litho, b, box)


def test_radium_gate_is_still_reported_as_failing():
    """The register says radium misses the project's own R2(log) >= 0.60 gate
    and explains why (point-mass labels). It must be reported, not removed.

    v6 (2026-09-26): the COMPLIANCE head now clears the bar (0.746) because the
    background it is pinned to varies across scenarios and is a feature;
    LIMITATIONS.md 1 says so and why it is not a transport gain. MIGRATION is
    still ~86 % exact zeros and still misses -- that is the gate now pinned."""
    m = _metrics()
    mig = m["bands"]["max_migration_distance_m"]["r2_log_by_species"]["radium_226_mbq_l"]
    assert mig < 0.60         # if this ever passes, update LIMITATIONS.md 1
    comp = m["bands"]["compliance_conc"]["r2_log_by_species"]["radium_226_mbq_l"]
    assert comp >= 0.60       # the v6 change LIMITATIONS.md 1 explains
    for t in ("compliance_conc", "max_migration_distance_m"):
        cov = m["bands"][t]["coverage"]["per_cell_rows"]
        assert cov["fractured|radium_226_mbq_l"] >= 0.80   # the band still covers


def test_sensitivity_script_contract_and_config_restoration():
    from ml_pipeline.validation import sensitivity as S
    before = (P.SOURCE_BV_GAIN, P.SOURCE_BV_REF, P.INCREMENTAL_FLOOR,
              P.FRACTURE["De_m2_day"], P.FRACTURE["full_aperture_m"],
              P.DUAL_POROSITY["mass_transfer_omega"])
    r = S.run_site("jaduguda_deposit", "uranium_ppb", n=4)
    after = (P.SOURCE_BV_GAIN, P.SOURCE_BV_REF, P.INCREMENTAL_FLOOR,
             P.FRACTURE["De_m2_day"], P.FRACTURE["full_aperture_m"],
             P.DUAL_POROSITY["mass_transfer_omega"])
    assert before == after, "the sensitivity run leaked a patched constant"
    names = {d["name"] for d in r["inputs"]}
    assert "beta (capacity ratio)" in names and "K (m/day)" in names
    assert {d["group"] for d in r["inputs"]} == {"A", "B"}
    for k in S.OUTPUTS:
        idx = r["sobol"]["indices"][k]
        assert set(idx["ST"]) == names and set(idx["S1"]) == names
        if idx.get("degenerate"):
            # 2026-09-26: with the measured shear-zone K, uranium never reaches
            # the Jaduguda ring (the output sits at background), so its indices
            # are undefined and the script says so instead of printing numbers
            assert all(v is None for v in idx["ST"].values()), k
        else:
            assert all(0.0 <= v <= 1.5 for v in idx["ST"].values())
        assert k in r["oat"]["inputs"]["beta (capacity ratio)"]
    assert r["sobol"]["evaluations"] == 4 * (len(names) + 2)
    assert r["beta_basis"] == "porosity_derived"
