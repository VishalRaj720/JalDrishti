"""The citizen surface: registration, subscriptions, alerts, published screenings.

REGISTRATION, AND THE HOLE IT MUST NOT REOPEN.

`POST /auth/signup` was deleted in P2 as a verified privilege-escalation hole:
it read `role` straight from an unauthenticated request body, so anyone who
could reach the API could mint an admin and read the user list.
`tests/test_auth_hardening.py` has guarded the property ever since — *no
unauthenticated route may mint a user*.

But "citizens must sign in" (a product decision) and "no unauthenticated route
may create an account" cannot both hold, and the alternative — an administrator
hand-creating an account for every resident of Jharkhand who wants to check
their water — is not a citizen product.

So the property is NARROWED rather than dropped, and the narrowing is the whole
security argument:

    No unauthenticated route may mint a user **with any role other than
    `citizen`**, and the role must never be read from the request.

`role` is not in `CitizenRegister`. It is not read, defaulted from input, or
overridable — the model has no field for it and the service hard-codes
`UserRole.citizen`. A request carrying `"role": "admin"` is not rejected; the key
simply does not exist as far as this endpoint is concerned, which is a stronger
guarantee than validating it away. `tests/test_p5_citizen.py` asserts exactly
that, by trying it.

The rest of the surface is authenticated and scoped to the caller: a
subscription is a statement about where somebody lives, and Postgres row-level
security (migration 0018) confines it to its own user rather than to a role.
"""
import json
import uuid
from datetime import datetime
from typing import Any, Literal, Mapping, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.advisory import Advisory
from app.models.user import User, UserRole
from app.services import audit
from app.ratelimit import AUTH_RATE_LIMIT, limiter
from app.services import health_bands
from app.services.alerts import URANIUM_LIMIT_PPB, AlertService
from app.services.auth import create_access_token, hash_password

router = APIRouter(prefix="/citizen", tags=["Citizen"])


# ── registration ─────────────────────────────────────────────────────

class CitizenRegister(BaseModel):
    """Note what is NOT here: `role`. See the module docstring."""
    username: str = Field(..., min_length=3, max_length=60)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class TokenAndUser(BaseModel):
    access_token: str
    token_type: str = "bearer"
    id: uuid.UUID
    username: str
    email: str
    role: str


@router.post("/register", response_model=TokenAndUser,
             status_code=status.HTTP_201_CREATED)
@limiter.limit(AUTH_RATE_LIMIT)
async def register_citizen(
    payload: CitizenRegister,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a citizen account. The role is fixed server-side and never read
    from the request."""
    existing = (await db.execute(
        select(User).where(User.email == payload.email.lower()))).scalar_one_or_none()
    if existing is not None:
        # Deliberately the same message a caller gets for any duplicate: this
        # endpoint is unauthenticated, and a distinct "that email is registered"
        # turns it into an account-existence oracle.
        raise HTTPException(status_code=409,
                            detail="That email address cannot be registered.")

    user = User(
        username=payload.username.strip(),
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        # HARD-PINNED. Not a default, not a fallback — there is no path by which
        # a request can influence this.
        role=UserRole.citizen,
    )
    db.add(user)
    try:
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=409,
                            detail="That email address cannot be registered.")

    await audit.record(
        action="citizen.register", entity_type="users", entity_id=str(user.id),
        actor_id=user.id, actor_label=user.email,
        ip_address=(request.client.host if request.client else None),
        detail={"role": "citizen"},
    )
    return TokenAndUser(
        access_token=create_access_token(str(user.id), user.role),
        id=user.id, username=user.username, email=user.email, role=user.role.value,
    )


# ── finding your block ───────────────────────────────────────────────

@router.get("/blocks")
async def search_blocks(
    response: Response,
    q: str = Query("", max_length=80),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Search blocks by name, so a resident can find their own area.

    Block, not village: `Datasets/` has no settlement layer, and offering a
    village search that silently resolves to a block would imply a precision the
    data does not have.
    """
    response.headers["Cache-Control"] = "no-store"
    rows = (await db.execute(text("""
        SELECT b.id::text AS id, b.name, d.name AS district
        FROM blocks b
        LEFT JOIN districts d ON d.id = b.district_id
        WHERE (:q = '' OR b.name ILIKE :like OR d.name ILIKE :like)
        ORDER BY b.name
        LIMIT :cap
    """), {"q": q.strip(), "like": f"%{q.strip()}%", "cap": limit})).mappings().all()
    return [dict(r) for r in rows]


# ── subscriptions ────────────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    block_id: uuid.UUID


@router.get("/subscriptions")
async def list_subscriptions(
    response: Response,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    response.headers["Cache-Control"] = "no-store"
    return await AlertService(db).subscriptions(me.id)


@router.post("/subscriptions", status_code=201)
async def subscribe(
    payload: SubscribeRequest,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    await AlertService(db).subscribe(me.id, payload.block_id)
    return {"subscribed": True, "block_id": str(payload.block_id)}


@router.delete("/subscriptions/{block_id}", status_code=204)
async def unsubscribe(
    block_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    await AlertService(db).unsubscribe(me.id, block_id)


# ── the inbox ────────────────────────────────────────────────────────

@router.get("/alerts")
async def list_alerts(
    response: Response,
    kind: Optional[Literal["measured_exceedance", "published_screening"]] = Query(None),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Alerts for the blocks this user subscribes to.

    `kind` is exposed as a filter because the two channels answer different
    questions — "is my water safe today" and "what has been modelled for my
    area" — and a reader is entitled to look at one without the other.
    """
    response.headers["Cache-Control"] = "no-store"
    svc = AlertService(db)
    return {
        "alerts": await svc.inbox(me.id, kind=kind, limit=limit),
        "unread": await svc.unread_count(me.id),
        "limit_ppb": URANIUM_LIMIT_PPB,
    }


@router.get("/alerts/unread-count")
async def unread_count(
    response: Response,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    response.headers["Cache-Control"] = "no-store"
    return {"unread": await AlertService(db).unread_count(me.id)}


@router.post("/alerts/{alert_id}/read", status_code=204)
async def mark_read(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    await AlertService(db).mark_read(me.id, alert_id)


@router.post("/alerts/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    return {"marked": await AlertService(db).mark_all_read(me.id)}


@router.post("/alerts/scan-measured")
async def scan_measured(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Raise alerts for CGWB samples over the uranium limit. Admin only.

    Triggered rather than scheduled: this deployment has no scheduler, and a
    cron job that silently stops is worse than a button nobody pressed, because
    the button's absence is visible.
    """
    # Own session with the system context, for the same reason as
    # `alerts.raise_for_advisory`: the `alerts_write` RLS policy requires
    # `app.bypass_rls = 'on'`, and this request's session carries the admin's
    # identity with bypass OFF. Every insert here was refused — which is part of
    # why the `alerts` table was empty despite eight published advisories.
    # Raising alerts is system work the admin authorised, not a privilege the
    # admin's own session should carry.
    from app.database import AsyncSessionLocal, set_rls_context
    async with AsyncSessionLocal() as adb:
        await set_rls_context(adb, bypass=True)
        return await AlertService(adb).scan_measured_exceedances()


@router.post("/alerts/scan-breach-due")
async def scan_breach_due(
    dry_run: bool = Query(True, description="report only; raise nothing"),
    _: User = Depends(require_admin),
):
    """Alert where a published screening's modelled breakthrough date has passed.

    Admin only, and **`dry_run` defaults to TRUE** — the opposite of the other
    scans. This is the only alert in the system that fires on elapsed time
    rather than on an event somebody just caused, so the operator should be able
    to see exactly who would be told, and on what basis, before anyone is. The
    dry run returns the full per-screening reasoning including every skip.

    See `AlertService.scan_breach_due` for the five gates and for why the copy
    is written the way it is.
    """
    from app.database import AsyncSessionLocal, set_rls_context
    async with AsyncSessionLocal() as adb:
        await set_rls_context(adb, bypass=True)
        return await AlertService(adb).scan_breach_due(dry_run=dry_run)


# ── published screenings, as a citizen sees them ─────────────────────

class PublicAdvisory(BaseModel):
    id: uuid.UUID
    headline: str
    what_it_means: str
    what_to_do: Optional[str]
    published_at: Optional[datetime]
    footprint_ha: Optional[float]
    blocks: list[dict[str, Any]]
    #: Never the ISR coordinate, the run id, the model card or any band. A
    #: citizen surface reports what was assessed and what it means, not the
    #: machinery — and design §2 keeps a speculative point off a public map.
    what_this_is: str


_WHAT_THIS_IS = (
    "This is a modelled assessment published by the authority operating this "
    "platform. It shows what the "
    "model expects would happen to groundwater if a uranium in-situ recovery "
    "operation were run at a location in this area. No such mine operates in "
    "Jharkhand — this is preparedness screening, not a report of an event."
)


@router.get("/advisories", response_model=list[PublicAdvisory])
async def published_advisories(
    response: Response,
    mine_only: bool = Query(False, description="Only blocks I subscribe to."),
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Published screenings only.

    A separate endpoint from the staff `/advisories` list rather than the same
    one with a filter: that list carries drafts and rejected proposals, and a
    forgotten filter there would publish an unapproved claim about somebody's
    drinking water.
    """
    response.headers["Cache-Control"] = "no-store"
    stmt = select(Advisory).where(Advisory.status == "published") \
                           .order_by(Advisory.published_at.desc()).limit(100)
    rows = list((await db.execute(stmt)).scalars().all())

    if mine_only:
        subs = {s["id"] for s in await AlertService(db).subscriptions(me.id)}
        rows = [a for a in rows
                if any(b.get("id") in subs for b in (a.affected_blocks or []))]

    return [
        PublicAdvisory(
            id=a.id, headline=a.headline, what_it_means=a.what_it_means,
            what_to_do=a.what_to_do, published_at=a.published_at,
            footprint_ha=a.footprint_ha,
            blocks=[{"name": b.get("name"), "district": b.get("district"),
                     "overlap_ha": b.get("overlap_ha")}
                    for b in (a.affected_blocks or [])],
            what_this_is=_WHAT_THIS_IS,
        )
        for a in rows
    ]


async def _published_run_detail(advisory_ids: list[str]) -> dict[str, dict]:
    """Operating parameters and run output for advisories ALREADY published.

    WHY THIS NEEDS ITS OWN SESSION AND A BYPASS, spelled out because adding a
    bypass to a read path deserves justifying rather than assuming.

    `isr_points` and `simulation_runs` are RLS-protected and a citizen reads
    nothing from either. Joining them in the request's own session does not
    error — it returns NULL for every column, so the response looks complete and
    every operating parameter silently reads as "unknown". That is the same
    class of silent-empty failure LIMITATIONS.md section 1c records twice.

    What this widens is bounded on purpose:
      * only advisories whose `status` is already `published` — the deliberate
        administrative act of telling residents about this screening;
      * only the operating parameters and run OUTPUT, never `location`. The ISR
        coordinate is what design section 2 withholds, and it is not selected
        here at all;
      * read-only, and the ids come from a query the caller was already
        entitled to run.

    THE BETTER LONG-TERM FIX is to copy these figures onto the advisory row at
    publication time, so a published finding is self-contained and cannot drift
    when somebody later edits the site — which the R13 site editor now allows.
    That needs a migration and would not backfill the advisories already
    published, so it is recorded in LIMITATIONS.md rather than half-done here.
    """
    if not advisory_ids:
        return {}
    from app.database import AsyncSessionLocal, set_rls_context
    out: dict[str, dict] = {}
    async with AsyncSessionLocal() as db:
        await set_rls_context(db, bypass=True)
        rows = (await db.execute(text("""
            SELECT a.id::text AS id,
                   ip.operation_years, ip.injection_rate_m3_day, ip.ore_depth_m,
                   ip.injection_start_date,
                   sr.metrics, sr.hydro, sr.plume, a.species
            FROM advisories a
            LEFT JOIN isr_points ip      ON ip.id = a.isr_point_id
            LEFT JOIN simulation_runs sr ON sr.id = a.run_id
            WHERE a.status = 'published'
              AND a.id::text = ANY(:ids)
        """), {"ids": advisory_ids})).mappings().all()
        for r in rows:
            d = dict(r)
            d["injection_start_date"] = (
                d["injection_start_date"].isoformat()
                if d["injection_start_date"] else None)
            out[r["id"]] = d
    return out


def _spread_summary(r: Mapping[str, Any]) -> dict[str, Any]:
    """How far and how strong, in the plainest terms the stored run supports.

    Returns `recorded: False` rather than zeros when the run predates geometry
    capture. A missing measurement and a measurement of nothing are different
    claims, and on this surface the difference is the whole point.
    """
    plume = r.get("plume") or {}
    metrics = r.get("metrics") or {}
    if isinstance(plume, str):
        plume = json.loads(plume)
    if isinstance(metrics, str):
        metrics = json.loads(metrics)
    if not plume:
        return {"recorded": False,
                "note": ("This screening was run before the platform stored "
                         "plume geometry. Its extent is not recorded.")}

    analytical = metrics.get("analytical") or {}
    return {
        "recorded": True,
        "furthest_travel_m": plume.get("Xc_m"),
        "peak_concentration": plume.get("peak_conc"),
        "threshold": plume.get("threshold"),
        "unit": r.get("species"),
        "note": ("Modelled distance from the injection area at the evaluation "
                 "time, for a mine that does not exist."),
        "migration_m": analytical.get("migration_m"),
        "area_ha": analytical.get("area_ha"),
    }


def _shallow_summary(r: Mapping[str, Any]) -> dict[str, Any]:
    """Whether the model expects the plume to reach shallow drinking water.

    LIMITATIONS section 4b: runs stored before 2026-08-20 carry no `vertical`
    block at all, and its absence must read as **"not recorded"**, never as "no
    pathway". Both currently published advisories are such runs, so this returns
    `recorded: False` for them — which is the honest answer, not a clean one.
    """
    hydro = r.get("hydro") or {}
    if isinstance(hydro, str):
        hydro = json.loads(hydro)
    v = (hydro or {}).get("vertical")
    if not v:
        return {"recorded": False,
                "note": ("Whether this reaches shallow drinking water was not "
                         "recorded for this screening. That is a gap in the "
                         "record, not a finding that it does not.")}

    seasonal = v.get("seasonal") or {}
    return {
        "recorded": True,
        "probability": v.get("shallow_impact_probability"),
        "risk_band": v.get("risk_band"),
        "years_to_breakthrough": v.get("years_to_vertical_breakthrough"),
        "dominant_pathway": v.get("dominant_pathway"),
        "dry_season_years": seasonal.get("breakthrough_years_dry"),
        "note": ("Modelled time for contamination to rise from the ore zone to "
                 "the shallow aquifer, if such a mine operated."),
    }


@router.get("/advisories/geojson")
async def published_advisory_geojson(
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """The footprints of PUBLISHED screenings, for the citizen map.

    R8. Residents could read that a screening covered their block but had no way
    to see where. Telling somebody they are in an assessed area while withholding
    where it is creates rumour without recourse — so once a screening has been
    published, its modelled extent is shown.

    WHAT IS AND IS NOT EXPOSED. The footprint polygon is, because that is the
    published finding. The ISR point itself is **not**: design section 2 keeps a
    precise coordinate for a hypothetical mine off the public surface, and the
    footprint already answers the question a resident is asking ("does this
    reach me?") without planting a pin next to a named village.

    Only `status = 'published'` is ever returned. Drafts and rejected proposals
    are internal, and this endpoint is deliberately separate from the staff list
    so a forgotten filter cannot leak one.
    """
    response.headers["Cache-Control"] = "no-store"
    # R14 (2026-08-25): the footprint alone answered "does this reach me?" and
    # nothing else. A resident who has been told a screening covers their block
    # then asks the obvious follow-ups — how big was the modelled operation, how
    # long would it run, how far did the contamination travel, and does it reach
    # the shallow water we actually drink. All of that is already stored on the
    # run the advisory was published from; it was simply never joined.
    #
    # STILL WITHHELD, and the reason is unchanged: the ISR point's coordinate.
    # Design section 2 keeps a precise pin for a hypothetical mine off the public
    # surface, because a point next to a named village reads as a plan. The
    # footprint is the published finding and is shown; the pin is not.
    rows = (await db.execute(text("""
        SELECT a.id::text AS id, a.headline, a.what_it_means, a.what_to_do,
               a.species, a.footprint_ha,
               a.time_years, a.restoration_years, a.published_at,
               ST_AsGeoJSON(a.footprint) AS geom
        FROM advisories a
        WHERE a.status = 'published' AND a.footprint IS NOT NULL
        ORDER BY a.published_at DESC
        LIMIT 200
    """))).mappings().all()

    detail = await _published_run_detail([r["id"] for r in rows])

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": json.loads(r["geom"]),
                "properties": {
                    "id": r["id"],
                    "headline": r["headline"],
                    "what_it_means": r["what_it_means"],
                    "what_to_do": r["what_to_do"],
                    "species": r["species"],
                    "footprint_ha": r["footprint_ha"],
                    "published_at": (r["published_at"].isoformat()
                                     if r["published_at"] else None),
                    # THE THREE TIMES A RESIDENT ASKS ABOUT, kept distinct
                    # because they are three different things and the words for
                    # them are easily muddled:
                    #   operation   how long the hypothetical mine injects
                    #   evaluated_at  how far out the model was asked to look
                    #   restoration how long clean-up pumping runs afterwards
                    "operation_years": detail.get(r["id"], {}).get("operation_years"),
                    "evaluated_at_years": r["time_years"],
                    "restoration_years": r["restoration_years"],
                    "injection_rate_m3_day":
                        detail.get(r["id"], {}).get("injection_rate_m3_day"),
                    "ore_depth_m": detail.get(r["id"], {}).get("ore_depth_m"),
                    "injection_start_date":
                        detail.get(r["id"], {}).get("injection_start_date"),
                    "spread": _spread_summary(detail.get(r["id"], {})),
                    "shallow_water": _shallow_summary(detail.get(r["id"], {})),
                    "what_this_is": _WHAT_THIS_IS,
                },
            }
            for r in rows if r["geom"]
        ],
        "what_this_is": _WHAT_THIS_IS,
    }


@router.get("/ore")
async def citizen_ore(response: Response,
                      _: User = Depends(get_current_user)):
    """Known uranium deposits, for the citizen map.

    WHY THIS IS ALLOWED WHERE AN ISR PIN IS NOT, which is the question this
    endpoint has to answer to exist at all.

    Design section 2 withholds the coordinate of a *hypothetical ISR site*
    because that site is this project's invention, and a pin next to a named
    village reads as a plan somebody has made. A uranium DEPOSIT is the
    opposite: it is published Geological Survey of India / UDEPO reference data
    about rock that has been there for a billion years. Withholding it would not
    protect anybody — it is already public — and showing it answers a question
    residents of the Singhbhum belt genuinely ask, which is why the assessed
    areas are where they are.

    Same payload the staff surface reads, so there is one source of truth for
    where the ore is.
    """
    # Reuses the ML router's forwarder rather than a second copy: the engine
    # being down should look the same (503) on both surfaces.
    from app.api.v1.ml import _forward
    return await _forward("/api/ore", response)


# ── "my area" ────────────────────────────────────────────────────────

@router.get("/my-area")
async def my_area(
    response: Response,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Everything about the blocks this person follows, in one call.

    Measured results first and screenings second, always. What was actually
    tested in your water is the more important of the two, and ordering is a
    claim about importance whether or not it is meant to be.
    """
    response.headers["Cache-Control"] = "no-store"
    svc = AlertService(db)
    subs = await svc.subscriptions(me.id)
    if not subs:
        return {"blocks": [], "unread": 0,
                "what_this_is": "Choose your block to see what has been measured there."}

    # THE BAND HERE USED TO BE UNIQUE TO THIS ENDPOINT, AND THAT WAS THE BUG.
    #
    # Until 2026-08-26 this handler carried its own ladder over `max_u` alone,
    # with its own prose. `/public/risk/*` had banded on uranium, nitrate and
    # fluoride since 2026-08-25. Uranium exceeds its limit at zero of the state's
    # uranium-tested wells while nitrate exceeds at 22 and fluoride at 32, so the
    # divergence was not academic: a resident of a block over the fluoride limit
    # saw "High concern" on the public map and "Low concern" here, on the page
    # they open to check their own drinking water. Both were correct about the
    # rule they had been handed, which is what made it survive two reviews.
    #
    # There is now one rule, in `services/health_bands.py`, and this endpoint
    # applies it exactly as the public map does — same SQL, same explanation,
    # same statement of what nobody analysed.
    ids = [s["id"] for s in subs]
    measured = (await db.execute(text(f"""
        WITH per_block AS (
            SELECT b.id::text        AS block_id,
                   count(DISTINCT w.id) AS wells,
                   count(s.id)          AS samples,
                   max(s.sampled_at)    AS last_sampled,
                   {health_bands.HEALTH_MAXES}
            FROM blocks b
            LEFT JOIN monitoring_wells w ON w.block_id = b.id
            LEFT JOIN water_samples s    ON s.well_id = w.id
            WHERE b.id = ANY(:ids)
            GROUP BY b.id
        )
        SELECT block_id, wells, samples, last_sampled,
               n_u, n_no3, n_f,
               round(max_u::numeric, 1)   AS max_uranium_ppb,
               round(max_no3::numeric, 1) AS max_nitrate_mg_l,
               round(max_f::numeric, 2)   AS max_fluoride_mg_l,
               {health_bands.BANDS}    AS band,
               {health_bands.DRIVER}   AS band_driver,
               {health_bands.UNTESTED} AS untested_health
        FROM per_block
    """), dict(health_bands.band_params(),
               ids=[uuid.UUID(i) for i in ids]))).mappings().all()
    by_block = {m["block_id"]: dict(m) for m in measured}

    out = []
    for s in subs:
        m = by_block.get(s["id"], {})
        wells = int(m.get("wells") or 0)
        samples = int(m.get("samples") or 0)
        # `describe` returns the band it settled on, which is not always the one
        # the SQL produced — a block with samples but no health determinand
        # analysed is `Not tested`, not `No data`. Use the returned value.
        band, means, untested = health_bands.describe(m, wells=wells, samples=samples)

        out.append({
            **s,
            "wells": wells,
            "samples": samples,
            "max_uranium_ppb": m.get("max_uranium_ppb"),
            "max_nitrate_mg_l": m.get("max_nitrate_mg_l"),
            "max_fluoride_mg_l": m.get("max_fluoride_mg_l"),
            "last_sampled": m.get("last_sampled"),
            "band": band,
            "band_driver": m.get("band_driver"),
            "untested_health": untested,
            "what_it_means": means,
        })

    return {
        "blocks": out,
        "unread": await svc.unread_count(me.id),
        "safe_limit_ppb": URANIUM_LIMIT_PPB,
        # The first three keys match `/public/risk/at` exactly, name for name,
        # because they mean the same thing and two citizen surfaces disagreeing
        # about the shape of a limit is how they came to disagree about a band.
        #
        # `fluoride_acceptable_mg_l` is the fourth. Fluoride is the one health
        # determinand here with a real band between its two limits — 1.0 is what
        # water should meet, 1.5 is tolerated only where no other source exists
        # — and a client drawing that band needs the lower number. Serving it is
        # the alternative to the portal hard-coding a 1.0 of its own, which is
        # the same duplication this whole change exists to remove.
        "limits": {
            "uranium_ppb": health_bands.URANIUM_LIMIT_PPB,
            "nitrate_mg_l": health_bands.NITRATE_LIMIT_MG_L,
            "fluoride_mg_l": health_bands.FLUORIDE_PERMISSIBLE_MG_L,
            "fluoride_acceptable_mg_l": health_bands.FLUORIDE_ACCEPTABLE_MG_L,
        },
        "what_this_is": (
            "These are real test results from government groundwater sampling — "
            "measurements, not predictions. An area is judged on uranium, nitrate "
            "and fluoride together, the same way the public map judges it."),
    }
