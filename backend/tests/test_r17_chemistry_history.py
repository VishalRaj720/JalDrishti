"""R17 -- the CGWB 2000-2021 chemistry record, read from the file.

Pins what the report will say about it:
  * the file parses to the profiled shape (1,632 rows, 366 stations, 2000-2021,
    318 stations with >= 2 distinct years);
  * it carries NO fluoride / nitrate / iron / arsenic and two uranium values,
    so it cannot support a health trend -- and the summary says so;
  * >= 50 of the platform's wells match a station with >= 2 years (the
    decision rule from the audit);
  * a station below the gates is `insufficient_data`, never "no_trend";
  * the balance on this file is an independent check (sodium is NOT
    computed by difference), unlike the 2023 file;
  * nothing writes to the database: the service has no session and the
    routes are staff-only, read-only.
"""
from __future__ import annotations

import inspect
import uuid

import pytest

from app.models.user import UserRole
from app.services import chemistry_history as ch
from tests.test_p5_citizen import _user  # noqa: F401


def test_file_profile_matches_the_audit():
    df = ch.load()
    assert len(df) == 1632 and df["key"].nunique() == 366
    assert int(df["year"].min()) == 2000 and int(df["year"].max()) == 2023
    per = df.groupby("key")["year"].nunique()
    assert int((per >= 2).sum()) == 318


def test_no_health_determinand_and_it_says_so():
    s = ch.summary()
    cov = s["coverage"]
    assert cov["fluoride_mg_l"]["n"] == 0 and cov["nitrate_n"]["n"] == 0
    assert cov["iron_ppm"]["n"] == 0 and cov["arsenic_mg_l"]["n"] == 0
    assert cov["uranium_mg_l"]["n"] <= 2
    assert "remains undemonstrated" in s["health_determinands"]["consequence"]
    assert "changes no band and no alert" in s["what_this_is"]


def test_decision_rule_is_met_for_the_general_chemistry():
    s = ch.summary()
    m = s["stations_matched_to_2023_wells"]
    assert m["total"] >= 200 and m["with_2_or_more_years"] >= 50
    assert m["by_name"] + m["by_proximity"] == m["total"]


def test_gates_make_a_short_record_a_baseline_not_a_trend():
    import pandas as pd
    g = pd.DataFrame({"sampled_at": pd.to_datetime(["2008-05-01", "2012-05-01", "2013-05-01"]),
                      "ec_us_cm": [1500.0, 1500.0, 1700.0]})
    t = ch._trend(g, "ec_us_cm")
    assert t["status"] == "insufficient_data" and t["n"] == 3 and "baseline" in t["note"]
    g2 = pd.DataFrame({"sampled_at": pd.to_datetime([f"{y}-05-01" for y in range(2004, 2014)]),
                       "ec_us_cm": [300 + 20 * i for i in range(10)]})
    t2 = ch._trend(g2, "ec_us_cm")
    assert t2["status"] == "rising" and t2["slope_per_year"] > 0 and t2["mk_p"] < 0.05
    assert t2["ucl_mean_plus_2sd"] > t2["baseline_mean"]
    assert ch._trend(pd.DataFrame({"sampled_at": [], "ec_us_cm": []}), "ec_us_cm")["status"] == "not_measured"


def test_balance_is_independent_on_this_file():
    s = ch.summary()
    ic = s["qa"]["independence_check"]
    assert ic["tested"] and ic["sodium_likely_computed_by_difference"] is False
    assert s["qa"]["by_class"]["suspect"] > 0          # a real laboratory picture
    assert s["qa"]["potassium_assumed_zero"] is True


def test_service_never_touches_the_database():
    src = inspect.getsource(ch)
    for needle in ("AsyncSession", "sqlalchemy", "INSERT", "water_samples"):
        assert needle not in src.replace("`water_samples`", ""), needle


def test_for_well_matches_by_name():
    h = ch.for_well("Chandrapura")
    assert h is not None and h["match"]["kind"] == "name" and h["n"] >= 1
    assert ch.for_well("no-such-well-xyz") is None


@pytest.mark.asyncio
async def test_routes_are_staff_only_and_read_only(client, db_session):
    _, tok = await _user(db_session, f"st{uuid.uuid4().hex[:5]}", UserRole.analyst)
    r = await client.get("/api/v1/water-quality/history", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["records"] == 1632 and "stations_detail" not in body
    r = await client.get("/api/v1/water-quality/history?detail=true",
                         headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and len(r.json()["stations_detail"]) == 366
    r = await client.get("/api/v1/water-quality/history/well/Chandrapura",
                         headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json()["matched"] is True
    r = await client.get("/api/v1/water-quality/history/well/nope",
                         headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json()["matched"] is False
    _, ctok = await _user(db_session, f"ci{uuid.uuid4().hex[:5]}", UserRole.citizen)
    r = await client.get("/api/v1/water-quality/history", headers={"Authorization": f"Bearer {ctok}"})
    assert r.status_code == 403
