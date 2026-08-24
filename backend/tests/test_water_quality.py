"""IS 10500:2012 assessment — the standard, the classification, the honesty rules.

Mostly DB-free: `services/water_quality.py` takes a plain dict, which is why it
takes a plain dict. The rules that matter here are not arithmetic, they are
editorial — "not tested" must never become "safe", and a two-sided parameter must
fail in both directions — and those are the ones a future edit is most likely to
get wrong.
"""
import pytest
import pytest_asyncio

from app.models.user import User, UserRole
from app.services import water_quality as wq
from app.services.auth import create_access_token, hash_password


@pytest_asyncio.fixture()
async def citizen_token(db_session):
    user = User(username="wqcitizen", email="wqcitizen@example.com",
                hashed_password=hash_password("pass1234"),
                role=UserRole.citizen)
    db_session.add(user)
    await db_session.commit()
    return create_access_token(str(user.id), user.role)


def sample(**kw):
    """A blank sample with nothing measured, overridden per test."""
    return {c: None for c in wq.SAMPLE_COLUMNS} | kw


# ── the rule this module exists to enforce ───────────────────────────

def test_unmeasured_determinand_is_not_tested_never_acceptable():
    """The single most misleading thing this module could do.

    Absence of evidence is a monitoring gap. Folding it into 'acceptable' is how
    a district nobody sampled ends up coloured the same as a clean one.
    """
    out = wq.assess_sample(sample())
    assert {p["status"] for p in out["parameters"]} <= {
        wq.STATUS_NOT_TESTED, wq.STATUS_NO_LIMIT}
    assert out["summary"]["status"] == wq.STATUS_NOT_TESTED
    assert out["summary"]["exceedances"] == 0
    assert out["summary"]["tested"] == 0


def test_a_clean_sample_is_acceptable():
    out = wq.assess_sample(sample(uranium_ppb=5.0, fluoride_mg_l=0.4,
                                  nitrate_mg_l=10.0, tds_mg_l=300.0))
    assert out["summary"]["status"] == wq.STATUS_ACCEPTABLE
    assert out["summary"]["exceedances"] == 0
    assert out["summary"]["tested"] == 4


# ── acceptable vs permissible ────────────────────────────────────────

def test_between_acceptable_and_permissible_is_above_acceptable():
    """Fluoride 1.2: over the 1.0 acceptable limit, under the 1.5 permissible."""
    out = wq.assess_sample(sample(fluoride_mg_l=1.2))
    f = next(p for p in out["parameters"] if p["key"] == "fluoride")
    assert f["status"] == wq.STATUS_ABOVE_ACCEPTABLE


def test_above_permissible_is_the_worst_class():
    out = wq.assess_sample(sample(fluoride_mg_l=1.9))
    f = next(p for p in out["parameters"] if p["key"] == "fluoride")
    assert f["status"] == wq.STATUS_ABOVE_PERMISSIBLE
    assert out["summary"]["above_permissible"] == 1


@pytest.mark.parametrize("key,column,value", [
    ("nitrate", "nitrate_mg_l", 46.0),
    ("uranium", "uranium_ppb", 31.0),
    ("iron", "iron_ppm", 0.4),
])
def test_no_relaxation_determinands_jump_straight_to_above_permissible(
        key, column, value):
    """IS 10500 marks these "No relaxation" — there is no tolerated band above
    the acceptable limit, so any exceedance is the worst class."""
    out = wq.assess_sample(sample(**{column: value}))
    p = next(x for x in out["parameters"] if x["key"] == key)
    assert p["status"] == wq.STATUS_ABOVE_PERMISSIBLE
    assert wq.BY_KEY[key].relaxation == "No relaxation"


# ── pH fails in both directions ──────────────────────────────────────

@pytest.mark.parametrize("ph,expected", [
    (6.0, wq.STATUS_ABOVE_ACCEPTABLE),   # acidic
    (7.0, wq.STATUS_ACCEPTABLE),
    (9.0, wq.STATUS_ABOVE_ACCEPTABLE),   # alkaline
    (6.5, wq.STATUS_ACCEPTABLE),         # boundaries are inclusive
    (8.5, wq.STATUS_ACCEPTABLE),
])
def test_ph_is_a_two_sided_range(ph, expected):
    out = wq.assess_sample(sample(ph=ph))
    p = next(x for x in out["parameters"] if x["key"] == "ph")
    assert p["status"] == expected


def test_ph_has_no_times_limit():
    """A ratio against a two-sided range means nothing, and charting it beside
    the one-sided ratios would invite exactly that comparison."""
    out = wq.assess_sample(sample(ph=9.0))
    p = next(x for x in out["parameters"] if x["key"] == "ph")
    assert p["times_limit"] is None


# ── unregulated determinands ─────────────────────────────────────────

def test_measured_but_unregulated_is_its_own_status():
    """Sodium is measured and IS 10500 sets no drinking-water limit. That is a
    different fact from 'nobody measured it' and from 'it passed'."""
    out = wq.assess_sample(sample(sodium_mg_l=250.0))
    p = next(x for x in out["parameters"] if x["key"] == "sodium")
    assert p["status"] == wq.STATUS_NO_LIMIT
    assert out["summary"]["exceedances"] == 0
    # counted as tested, but not as a regulated pass
    assert out["summary"]["tested"] == 1
    assert out["summary"]["regulated_tested"] == 0


# ── derived alkalinity ───────────────────────────────────────────────

def test_alkalinity_is_derived_from_bicarbonate_and_carbonate():
    # 244 mg/L HCO3 -> 244 * 50/61 = 200.0 as CaCO3, exactly the limit
    v = wq.derive_alkalinity({"bicarbonate_mg_l": 244.0, "carbonate_mg_l": 0.0})
    assert v == pytest.approx(200.0, abs=0.1)


def test_alkalinity_counts_carbonate_at_its_own_equivalent_weight():
    v = wq.derive_alkalinity({"bicarbonate_mg_l": 0.0, "carbonate_mg_l": 30.0})
    assert v == pytest.approx(50.0, abs=0.1)


def test_alkalinity_is_none_when_neither_component_measured():
    assert wq.derive_alkalinity({"bicarbonate_mg_l": None,
                                 "carbonate_mg_l": None}) is None


def test_alkalinity_is_flagged_as_derived():
    out = wq.assess_sample(sample(bicarbonate_mg_l=300.0))
    p = next(x for x in out["parameters"] if x["key"] == "alkalinity")
    assert p["derived"] is True, "a computed value must not read as a measurement"


# ── the driver: which determinand is responsible ─────────────────────

def test_driver_names_the_worst_exceedance_not_the_first():
    out = wq.assess_sample(sample(
        total_hardness=210.0,    # 1.05x the limit, mild, aesthetic
        nitrate_mg_l=121.0,      # 2.69x, "No relaxation" -> above permissible
    ))
    assert out["summary"]["driver"]["key"] == "nitrate"


def test_driver_is_none_when_nothing_exceeds():
    out = wq.assess_sample(sample(nitrate_mg_l=1.0))
    assert out["summary"]["driver"] is None


def test_health_exceedances_are_counted_apart_from_aesthetic():
    """The split that stops '71 % of wells exceed a limit' being read as
    '71 % of wells are contaminated'. Hard water is not a health finding."""
    out = wq.assess_sample(sample(total_hardness=700.0, calcium_mg_l=250.0))
    assert out["summary"]["exceedances"] == 2
    assert out["summary"]["health_exceedances"] == 0

    out = wq.assess_sample(sample(total_hardness=700.0, nitrate_mg_l=90.0))
    assert out["summary"]["health_exceedances"] == 1


# ── worst_status ordering ────────────────────────────────────────────

def test_worst_status_prefers_the_more_severe():
    assert wq.worst_status([wq.STATUS_ACCEPTABLE,
                            wq.STATUS_ABOVE_PERMISSIBLE,
                            wq.STATUS_ABOVE_ACCEPTABLE]) == wq.STATUS_ABOVE_PERMISSIBLE


def test_worst_status_of_nothing_is_not_tested():
    assert wq.worst_status([]) == wq.STATUS_NOT_TESTED


# ── the composite, and its refusals ──────────────────────────────────

def test_wqi_refuses_a_score_on_thin_coverage():
    """A WQI over two of nine determinands is not comparable with one over nine,
    and putting both on the same colour scale is the misleading part."""
    assert wq.wqi(sample(uranium_ppb=5.0, fluoride_mg_l=0.5)) is None


def test_wqi_scores_when_coverage_is_sufficient():
    out = wq.wqi(sample(uranium_ppb=5.0, fluoride_mg_l=0.5, nitrate_mg_l=10.0,
                        tds_mg_l=300.0, total_hardness=150.0,
                        chloride_mg_l=100.0, sulphate_mg_l=50.0,
                        calcium_mg_l=40.0, magnesium_mg_l=20.0))
    assert out is not None
    assert out["coverage"] == 1.0
    assert out["band"] in ("Excellent", "Good", "Poor", "Very poor",
                           "Unsuitable for drinking")


def test_wqi_weights_are_normalised_and_disclosed():
    w = wq.wqi_weights()
    assert set(w) == set(wq.WQI_KEYS)
    assert sum(v["weight"] for v in w.values()) == pytest.approx(1.0, abs=1e-4)
    # every weight explains itself, as /data-gaps/recommendations does
    assert all(v["why"] for v in w.values())


# ── the standard itself ──────────────────────────────────────────────

def test_uranium_limit_matches_the_rest_of_the_platform():
    """Two copies of a safety limit is one copy waiting to go stale."""
    from app.api.v1.public_risk import URANIUM_LIMIT_PPB
    assert wq.BY_KEY["uranium"].acceptable == URANIUM_LIMIT_PPB


def test_standard_document_is_publishable():
    doc = wq.standard_document()
    assert "IS 10500:2012" in doc["standard"]
    assert len(doc["determinands"]) == len(wq.STANDARD)
    assert doc["not_tested_rule"]
    # every determinand cites where its limit came from
    assert all(d["source"] for d in doc["determinands"])


def test_unmeasured_determinands_are_declared_in_the_standard():
    """Arsenic and iron are named in the proposal and are 0 % populated in this
    dataset. The standard document must say so rather than letting every well
    silently report `not_tested` with no explanation."""
    doc = wq.standard_document()
    for key in ("arsenic", "iron", "turbidity"):
        d = next(x for x in doc["determinands"] if x["key"] == key)
        assert "NOT MEASURED" in d["note"] or "unmeasured" in d["note"].lower()


# ── API surface ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_standard_endpoint_is_readable_by_a_citizen(client, citizen_token):
    """A threshold that decides what somebody is told about their own drinking
    water should be inspectable by them."""
    r = await client.get("/api/v1/water-quality/standard",
                         headers={"Authorization": f"Bearer {citizen_token}"})
    assert r.status_code == 200
    assert r.json()["determinands"]


@pytest.mark.asyncio
async def test_well_detail_refuses_a_citizen(client, citizen_token):
    """Well-level routes carry coordinates and names, so they are staff-only —
    the same boundary design §2 draws for ISR sites."""
    r = await client.get("/api/v1/water-quality/wells",
                         headers={"Authorization": f"Bearer {citizen_token}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_unknown_determinand_filter_is_404_not_empty(client, admin_token):
    """An empty list would read as 'no wells exceed this', which is a different
    claim from 'that determinand does not exist'."""
    r = await client.get("/api/v1/water-quality/wells?parameter=lead",
                         headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 404


# ── the WQI's weighting, surfaced rather than hidden ─────────────────

def test_wqi_reports_which_determinand_dominates_the_score():
    """Found on the finished screen, not in the formula.

    Dasokhap (Hazaribagh) scores 132.7 — "Unsuitable for drinking" — on a
    fluoride reading of 1.43 mg/L that is BELOW its own permissible limit of
    1.5. Inverse-limit weighting gives fluoride 96 % of the score because its
    limit is the smallest in the set. The band is correct by the literature's
    definition and unreadable without that fact, so the fact ships with it.
    """
    out = wq.wqi(sample(uranium_ppb=1.32, fluoride_mg_l=1.43, nitrate_mg_l=11,
                        tds_mg_l=477.75, total_hardness=255, chloride_mg_l=39,
                        sulphate_mg_l=45, calcium_mg_l=64, magnesium_mg_l=23))
    assert out["dominated_by"]["key"] == "fluoride"
    assert out["dominated_by"]["share"] > 0.9
    # and the well itself is NOT above any permissible limit
    assessed = wq.assess_sample(sample(
        uranium_ppb=1.32, fluoride_mg_l=1.43, nitrate_mg_l=11, tds_mg_l=477.75,
        total_hardness=255, chloride_mg_l=39, sulphate_mg_l=45,
        calcium_mg_l=64, magnesium_mg_l=23))
    assert assessed["summary"]["above_permissible"] == 0


def test_wqi_caveat_warns_about_the_weighting():
    out = wq.wqi(sample(uranium_ppb=5.0, fluoride_mg_l=0.5, nitrate_mg_l=10.0,
                        tds_mg_l=300.0, total_hardness=150.0,
                        chloride_mg_l=100.0, sulphate_mg_l=50.0,
                        calcium_mg_l=40.0, magnesium_mg_l=20.0))
    assert "1/limit" in out["caveat"]
