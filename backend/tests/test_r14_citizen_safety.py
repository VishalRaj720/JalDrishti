"""R14 — the citizen surface stops banding on uranium alone, and the time alert.

WHY THESE MATTER MORE THAN MOST TESTS HERE. Everything in this file decides what
a resident is told about water they drink. The uranium-only band was not a
cosmetic limitation: statewide maximum uranium is 28.5 ppb against a 30 ppb
limit, so the public map **could not colour a single district red** no matter
what else was in the water — while 22 wells exceeded the nitrate limit, one of
them at 2.7x.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.api.v1 import public_risk as pr
from app.services.alerts import AlertService


# ── the band expression ──────────────────────────────────────────────

def test_band_limits_match_the_water_quality_registry():
    """Two copies of a safety limit is one copy waiting to go stale.

    `services/water_quality.py` owns the full eighteen-determinand standard;
    the citizen band uses a health-significant subset of it and the numbers must
    agree.
    """
    from app.services import water_quality as wq
    assert pr.URANIUM_LIMIT_PPB == wq.BY_KEY["uranium"].acceptable
    assert pr.NITRATE_LIMIT_MG_L == wq.BY_KEY["nitrate"].acceptable
    assert pr.FLUORIDE_ACCEPTABLE_MG_L == wq.BY_KEY["fluoride"].acceptable
    assert pr.FLUORIDE_PERMISSIBLE_MG_L == wq.BY_KEY["fluoride"].permissible


def test_band_expression_reads_every_health_determinand():
    """Guard against a future edit quietly narrowing this back to uranium."""
    for token in ("max_u", "max_no3", "max_f", "health_tests"):
        assert token in pr._BANDS, f"{token} missing from the band expression"


def test_band_params_bind_every_limit_the_case_uses():
    p = pr._band_params()
    assert set(p) == {"limit", "no3_limit", "f_acceptable", "f_permissible"}


def test_untested_expression_always_lists_the_unmeasured_metals():
    """Arsenic and iron are 0 % populated statewide. No block has been cleared
    for them, and a band that silently means 'clean for the three we happened to
    measure' is the failure LIMITATIONS.md section 3 exists to prevent."""
    assert "'arsenic'" in pr._UNTESTED
    assert "'iron'" in pr._UNTESTED


# ── the plain-language reading ───────────────────────────────────────

def test_low_concern_names_only_what_was_measured():
    """Saying 'uranium, nitrate and fluoride were all within limits' at a block
    where uranium was never analysed contradicts the gap sentence printed right
    after it — and the reassuring half is the half a reader remembers."""
    out = pr._explain_multi(
        {"band": "Low concern", "band_driver": None,
         "n_u": 0, "n_no3": 2, "n_f": 2}, wells=2)
    assert "uranium" not in out.lower()
    assert "nitrate" in out.lower() and "fluoride" in out.lower()


def test_high_concern_names_the_substance_and_its_specific_risk():
    """"High concern" with no statement of WHAT is high is not actionable: a
    resident can boil water for bacteria but cannot boil out fluoride."""
    out = pr._explain_multi(
        {"band": "High concern", "band_driver": "nitrate",
         "max_nitrate_mg_l": 121.0, "n_no3": 2}, wells=2)
    assert "nitrate" in out.lower()
    assert "121" in out
    assert "infant" in out.lower(), "the nitrate-specific risk must be stated"


def test_fluoride_advice_says_boiling_does_not_help():
    out = pr._explain_multi(
        {"band": "High concern", "band_driver": "fluoride",
         "max_fluoride_mg_l": 1.9, "n_f": 1}, wells=1)
    assert "boil" in out.lower()


def test_no_data_is_never_reported_as_clean():
    out = pr._explain_multi({"band": "No data"}, wells=0)
    assert "not a clean result" in out.lower()


def test_not_tested_is_never_reported_as_clean():
    out = pr._explain_multi({"band": "Not tested"}, wells=3)
    assert "not a clean result" in out.lower()


@pytest.mark.parametrize("items,expected", [
    ([], ""),
    (["uranium"], "uranium"),
    (["uranium", "iron"], "uranium and iron"),
    (["uranium", "arsenic", "iron"], "uranium, arsenic and iron"),
])
def test_join_and_reads_as_english(items, expected):
    """This string is read by the public, not by an operator."""
    assert pr._join_and(items) == expected


# ── the API, end to end ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_blocks_summary_reports_what_it_judged_on(client):
    r = await client.get("/api/v1/public/risk/blocks/summary")
    assert r.status_code == 200
    body = r.json()
    assert set(body["judged_on"]) >= {"uranium_ppb", "nitrate_mg_l",
                                      "fluoride_mg_l"}
    # the unknown category must keep its own denominator
    assert "unknown" in body and "measured" in body
    assert "not a safe block" in body["what_unknown_means"]


@pytest.mark.asyncio
async def test_public_risk_stays_unauthenticated(client):
    """This surface is deliberately open — a resident must not need an account
    to find out about their own water."""
    assert (await client.get("/api/v1/public/risk/districts")).status_code == 200


# ── the time-triggered alert ─────────────────────────────────────────

def test_breach_threshold_is_a_named_constant():
    assert AlertService.BREACH_PROBABILITY_THRESHOLD == 0.5


def test_breach_alert_kind_is_permitted_by_the_model():
    """The CHECK constraint lives in the ORM metadata as well as in migration
    0023, because the test database is built from that metadata."""
    from app.models.alert import Alert
    checks = " ".join(str(c.sqltext) for c in Alert.__table__.constraints
                      if hasattr(c, "sqltext"))
    assert "aquifer_breach_due" in checks


@pytest.mark.asyncio
async def test_breach_scan_skips_runs_without_vertical_screening(
        client, admin_token, db_session):
    """LIMITATIONS.md 4b: a run with no `vertical` block means NOT ASSESSED.

    Treating that absence as "no pathway" would silently clear every advisory
    published before 2026-08-20 — which is both of the ones that exist.
    """
    r = await client.post("/api/v1/citizen/alerts/scan-breach-due?dry_run=true",
                          headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    # every skip must carry a reason; a bare count would hide why nobody was told
    for s in body["skipped"]:
        assert s["reason"]
    assert "No ISR mine operates in Jharkhand" in body["what_this_is"]


@pytest.mark.asyncio
async def test_breach_scan_defaults_to_dry_run(client, admin_token):
    """The only alert that fires on elapsed time rather than on an event, so an
    operator should see exactly who would be told before anyone is."""
    r = await client.post("/api/v1/citizen/alerts/scan-breach-due",
                          headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json()["dry_run"] is True


@pytest.mark.asyncio
async def test_breach_scan_refuses_a_citizen(client, db_session):
    from app.models.user import User, UserRole
    from app.services.auth import create_access_token, hash_password
    u = User(username="r14c", email="r14c@example.com",
             hashed_password=hash_password("pass1234"), role=UserRole.citizen)
    db_session.add(u)
    await db_session.commit()
    tok = create_access_token(str(u.id), u.role)
    r = await client.post("/api/v1/citizen/alerts/scan-breach-due",
                          headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


# ── regulator may now run the model ──────────────────────────────────

def test_regulator_may_run_simulations():
    """R14, at the product owner's request. A CGWB/SPCB officer asking 'what
    would happen if' is the primary real-world user of a screening tool."""
    from app.dependencies import require_simulation_roles
    from app.models.user import UserRole
    assert UserRole.regulator in require_simulation_roles.allowed_roles
    assert UserRole.analyst in require_simulation_roles.allowed_roles
    assert UserRole.admin in require_simulation_roles.allowed_roles


def test_regulator_still_cannot_publish_to_citizens():
    """Running a model and announcing its result to a village are different
    authorities, and only one of them was widened."""
    from app.dependencies import require_reviewer
    from app.models.user import UserRole
    assert UserRole.regulator not in require_reviewer.allowed_roles


def test_regulator_still_cannot_touch_datasets_or_accounts():
    from app.dependencies import require_admin
    from app.models.user import UserRole
    assert UserRole.regulator not in require_admin.allowed_roles


# ── the alert channel that had never sent an alert ───────────────────

def test_measured_scan_reads_more_than_uranium():
    """The defect this guards, stated plainly.

    Until 2026-08-25 `scan_measured_exceedances` scanned
    `WHERE uranium_ppb > 30`. Statewide maximum uranium is 28.5 ppb, so the
    query matched ZERO rows every time it ran — while 22 wells exceeded the
    nitrate limit and 11 exceeded fluoride. The `alerts` table held eight rows,
    all `published_screening`: eight warnings about a mine that does not exist
    and none about the contamination measured in people's wells.

    A scan that finds nothing looks exactly like a scan that found nothing
    wrong, which is why this went unnoticed and why it is pinned at the source.
    """
    import inspect
    src = inspect.getsource(AlertService.scan_measured_exceedances)
    for col in ("uranium_ppb", "nitrate_mg_l", "fluoride_mg_l"):
        assert col in src, f"{col} is not scanned"


def test_breaches_finds_every_determinand_over_its_limit():
    out = AlertService._breaches({
        "uranium_ppb": 5.0,        # under
        "nitrate_mg_l": 121.0,     # 2.69x
        "fluoride_mg_l": 1.9,      # 1.27x
        "arsenic_ppb": None, "iron_ppm": None,
    })
    assert [b["label"] for b in out] == ["nitrate", "fluoride"], \
        "worst-first ordering drives both the headline and the severity"
    assert out[0]["times_limit"] > out[1]["times_limit"]


def test_breaches_is_empty_for_a_clean_sample():
    assert AlertService._breaches({
        "uranium_ppb": 5.0, "nitrate_mg_l": 10.0, "fluoride_mg_l": 0.4,
        "arsenic_ppb": None, "iron_ppm": None}) == []


def test_breaches_ignores_unmeasured_determinands():
    """A NULL is not a pass and it is also not an exceedance — it simply cannot
    raise an alert. The monitoring gap is reported on the water-quality and
    public-risk surfaces, not as a notification."""
    assert AlertService._breaches({
        "uranium_ppb": None, "nitrate_mg_l": None, "fluoride_mg_l": None,
        "arsenic_ppb": None, "iron_ppm": None}) == []


def test_nitrate_advice_warns_that_boiling_concentrates_it():
    """The single most dangerous folk remedy for this determinand: boiling
    reduces the volume and raises the concentration."""
    out = AlertService._breaches({
        "uranium_ppb": None, "nitrate_mg_l": 90.0, "fluoride_mg_l": None,
        "arsenic_ppb": None, "iron_ppm": None})
    assert "boiling concentrates" in out[0]["advice"].lower()


def test_arsenic_and_iron_are_scanned_although_unmeasured_today():
    """Both are 0 % populated in the CGWB file. They are in the scan so that the
    day a lab result arrives the alert fires without anybody remembering to come
    back and add it."""
    out = AlertService._breaches({
        "uranium_ppb": None, "nitrate_mg_l": None, "fluoride_mg_l": None,
        "arsenic_ppb": 80.0, "iron_ppm": 1.2})
    assert {b["label"] for b in out} == {"arsenic", "iron"}


def test_not_tested_band_is_distinct_from_low_concern_and_no_data():
    """The three ways a block can fail to be "safe", kept apart.

    R14 renamed this band from "Not tested for uranium" to "Not tested" because
    the surface now judges three determinands: naming uranium alone understates
    the gap at a block where nothing was analysed, and overstates it at a block
    where nitrate and fluoride were. What must not change is that neither this
    band nor "No data" may ever be treated as a pass.
    """
    for band in ("Not tested", "No data"):
        out = pr._explain_multi({"band": band}, wells=2)
        assert "not a clean result" in out.lower()
    # and the CASE ladder distinguishes them by whether anything was sampled
    assert "health_tests = 0 AND max_u IS NULL" in pr._BANDS
    assert "'No data'" in pr._BANDS and "'Not tested'" in pr._BANDS


def test_a_block_analysed_for_nitrate_but_not_uranium_still_bands():
    """The case the rename exists for.

    Musabani has two sampled wells with no uranium result but with nitrate and
    fluoride results. Throwing away a real nitrate measurement because a
    different determinand is missing tells a resident less than the data
    supports — so it bands on what WAS measured and reports the gap alongside.
    """
    out = pr._explain_multi(
        {"band": "Low concern", "band_driver": None,
         "n_u": 0, "n_no3": 2, "n_f": 2}, wells=2)
    assert "within the drinking-water limits" in out
    assert "uranium" not in out.lower(), \
        "an unanalysed determinand must not be reported as within limits"
