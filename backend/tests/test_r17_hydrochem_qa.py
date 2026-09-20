"""R17 (2026-09-20) -- hydrochemical QA of the measured record.

Pins:
  * the charge-balance arithmetic against a hand-computed analysis;
  * the class thresholds (5 % / 10 %) and the `incomplete` class for a
    missing required ion -- absence of a test is never a failure class;
  * the ion-sum/EC check and its band;
  * that a flagged sample is NOT excluded: the alert scan still raises on it
    and carries the flag in `confidence.charge_balance`;
  * the independence check: a file whose sodium was computed by difference
    is reported as "not an independent check", and one with measured sodium
    is not;
  * the route is staff-only and the summary has the shape the page reads.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.user import UserRole
from app.services import hydrochem_qa as hq
from app.services.alerts import AlertService
from tests.test_p5_citizen import _user, a_block  # noqa: F401
from tests.test_r17_alert_tiers import _well_with_sample


# a balanced analysis: Ca 40, Mg 12, Na 47, K 3.9 | HCO3 183, Cl 35.5, SO4 48, NO3 6.2, F 0.5
# cations 2.00 + 0.99 + 2.04 + 0.10 = 5.13 meq/L; anions 3.00 + 1.00 + 1.00 + 0.10 + 0.03 = 5.13
SAMPLE = dict(calcium_mg_l=40.0, magnesium_mg_l=12.0, sodium_mg_l=47.0, potassium_mg_l=3.9,
              bicarbonate_mg_l=183.0, carbonate_mg_l=0.0, chloride_mg_l=35.5,
              sulphate_mg_l=48.0, nitrate_mg_l=6.2, fluoride_mg_l=0.5, ec_us_cm=520.0)


def test_charge_balance_arithmetic_by_hand():
    q = hq.charge_balance(SAMPLE)
    # the textbook expression, written out with the same molar masses
    cat = 40 * 2 / 40.078 + 12 * 2 / 24.305 + 47 / 22.990 + 3.9 / 39.098
    an = 183 / 61.017 + 0 + 35.5 / 35.453 + 48 * 2 / 96.06 + 6.2 / 62.004 + 0.5 / 18.998
    assert cat == pytest.approx(5.13, abs=0.01) and an == pytest.approx(5.13, abs=0.01)
    assert q["cations_meq_l"] == pytest.approx(cat, abs=1e-3)
    assert q["anions_meq_l"] == pytest.approx(an, abs=1e-3)
    assert q["cbe_pct"] == pytest.approx(100 * (cat - an) / (cat + an), abs=0.02)
    assert abs(q["cbe_pct"]) < 1.0
    assert q["qa_class"] == "balanced"
    assert q["assumed_zero"] == []


def test_classes_follow_the_conventional_thresholds():
    # push sodium up until the balance breaks (5.13 meq/L each side to start)
    s = dict(SAMPLE, sodium_mg_l=47.0 + 22.99 * 0.75)   # +0.75 meq -> ~+6.8 %
    assert hq.charge_balance(s)["qa_class"] == "questionable"
    s = dict(SAMPLE, sodium_mg_l=47.0 + 22.99 * 1.5)    # +1.5 meq -> ~+12.8 %
    assert hq.charge_balance(s)["qa_class"] == "suspect"
    s = dict(SAMPLE, sodium_mg_l=47.0 - 22.99 * 1.5)    # -1.5 meq -> ~-17 %
    assert hq.charge_balance(s)["qa_class"] == "suspect"   # negative side too


def test_a_missing_required_ion_is_incomplete_not_a_failure():
    q = hq.charge_balance(dict(SAMPLE, sodium_mg_l=None))
    assert q["qa_class"] == "incomplete" and q["cbe_pct"] is None
    assert q["missing"] == ["sodium_mg_l"]
    assert "absence of a test" in q["note"]


def test_minor_ions_missing_are_assumed_zero_and_named():
    q = hq.charge_balance(dict(SAMPLE, nitrate_mg_l=None, fluoride_mg_l=None))
    assert q["qa_class"] in ("balanced", "questionable")
    assert set(q["assumed_zero"]) == {"nitrate_mg_l", "fluoride_mg_l"}


def test_ec_consistency_band():
    q = hq.ec_consistency(SAMPLE)
    assert q["ec_class"] == "consistent" and 0.45 <= q["ec_ratio"] <= 0.90
    assert hq.ec_consistency(dict(SAMPLE, ec_us_cm=5200.0))["ec_class"] == "inconsistent"
    assert hq.ec_consistency(dict(SAMPLE, ec_us_cm=None))["ec_class"] == "incomplete"


def test_independence_check_detects_sodium_by_difference():
    rows = []
    for i in range(30):
        base = dict(SAMPLE, calcium_mg_l=30.0 + i, chloride_mg_l=20.0 + 2 * i)
        # sodium computed from the balance, then rounded to an integer
        an = sum(float(base[c]) * f for c, (_, f) in hq.ANIONS.items())
        other = sum(float(base[c]) * hq.CATIONS[c][1] for c in
                    ("calcium_mg_l", "magnesium_mg_l", "potassium_mg_l"))
        base["sodium_mg_l"] = round((an - other) / hq.CATIONS["sodium_mg_l"][1])
        rows.append(base)
    out = hq.independence_check(rows)
    assert out["tested"] and out["sodium_likely_computed_by_difference"]
    assert "NOT an independent check" in out["verdict"]
    # measured sodium scatters by several mg/L either way
    rows2 = [dict(r, sodium_mg_l=r["sodium_mg_l"] + (9 if i % 2 else -9)) for i, r in enumerate(rows)]
    out2 = hq.independence_check(rows2)
    assert not out2["sodium_likely_computed_by_difference"]


@pytest.mark.asyncio
async def test_a_flagged_sample_still_raises_its_alert_and_carries_the_flag(db_session, a_block):
    # nitrate 121 with a deliberately broken balance (sodium far too high)
    await _well_with_sample(db_session, a_block["id"], "W-qa", nitrate_mg_l=121.0,
                            calcium_mg_l=40.0, magnesium_mg_l=12.0, sodium_mg_l=600.0,
                            potassium_mg_l=3.9, bicarbonate_mg_l=183.0,
                            chloride_mg_l=35.5, sulphate_mg_l=48.0)
    out = await AlertService(db_session).scan_measured_exceedances()
    assert out["alerts_created"] == 1
    row = (await db_session.execute(text(
        "SELECT tier, explanation FROM alerts WHERE well_name = 'W-qa'"))).first()
    assert row[0] == "critical"                       # the exceedance stands
    cb = row[1]["confidence"]["charge_balance"]
    assert cb["qa_class"] == "suspect" and cb["cbe_pct"] is not None


@pytest.mark.asyncio
async def test_summary_and_route(client, db_session, a_block):
    await _well_with_sample(db_session, a_block["id"], "W-ok", **SAMPLE)
    await _well_with_sample(db_session, a_block["id"], "W-inc", nitrate_mg_l=10.0)
    s = await hq.summary(db_session)
    assert s["samples"] >= 2
    assert s["by_class"]["balanced"] >= 1 and s["by_class"]["incomplete"] >= 1
    assert set(s["by_class"]) == set(hq.CLASSES)
    assert "independence_check" in s and "method" in s
    assert "not" in s["method"]["policy"].lower()      # nothing is excluded
    _, tok = await _user(db_session, f"st{uuid.uuid4().hex[:5]}", UserRole.analyst)
    r = await client.get("/api/v1/water-quality/qa", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json()["samples"] == s["samples"]
    _, ctok = await _user(db_session, f"ci{uuid.uuid4().hex[:5]}", UserRole.citizen)
    r = await client.get("/api/v1/water-quality/qa", headers={"Authorization": f"Bearer {ctok}"})
    assert r.status_code == 403
    # and the per-well surface carries the flag
    r = await client.get("/api/v1/water-quality/wells", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    w = next(x for x in r.json()["wells"] if x["well_name"] == "W-ok")
    assert w["qa"]["qa_class"] == "balanced"
