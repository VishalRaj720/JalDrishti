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
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.advisory import Advisory
from app.models.user import User, UserRole
from app.services import audit
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
    return await AlertService(db).scan_measured_exceedances()


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
    rows = (await db.execute(text("""
        SELECT a.id::text AS id, a.headline, a.species, a.footprint_ha,
               a.time_years, a.restoration_years, a.published_at,
               ST_AsGeoJSON(a.footprint) AS geom
        FROM advisories a
        WHERE a.status = 'published' AND a.footprint IS NOT NULL
        ORDER BY a.published_at DESC
        LIMIT 200
    """))).mappings().all()

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": json.loads(r["geom"]),
                "properties": {
                    "id": r["id"],
                    "headline": r["headline"],
                    "species": r["species"],
                    "footprint_ha": r["footprint_ha"],
                    "time_years": r["time_years"],
                    "restoration_years": r["restoration_years"],
                    "published_at": (r["published_at"].isoformat()
                                     if r["published_at"] else None),
                    "what_this_is": _WHAT_THIS_IS,
                },
            }
            for r in rows if r["geom"]
        ],
        "what_this_is": _WHAT_THIS_IS,
    }


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

    ids = [s["id"] for s in subs]
    measured = (await db.execute(text("""
        SELECT b.id::text AS block_id,
               count(DISTINCT mw.id) AS wells,
               count(ws.id) AS samples,
               max(ws.uranium_ppb) AS max_uranium_ppb,
               max(ws.sampled_at) AS last_sampled
        FROM blocks b
        LEFT JOIN monitoring_wells mw ON mw.block_id = b.id
        LEFT JOIN water_samples ws ON ws.well_id = mw.id
        WHERE b.id = ANY(:ids)
        GROUP BY b.id
    """), {"ids": [uuid.UUID(i) for i in ids]})).mappings().all()
    by_block = {m["block_id"]: dict(m) for m in measured}

    out = []
    for s in subs:
        m = by_block.get(s["id"], {})
        mx = m.get("max_uranium_ppb")
        samples = int(m.get("samples") or 0)
        if mx is None:
            # TWO DIFFERENT GAPS, and conflating them produced a screen that
            # said "no sample from this block is in the dataset" directly above
            # "2 wells tested · 2 samples". Found in browser verification.
            #
            # A block can have samples that were never analysed for uranium —
            # the CGWB quality file does not report every determinand at every
            # well. Telling a resident nothing was sampled when wells near them
            # were sampled (just not for this) is the kind of confidently wrong
            # public statement this product exists not to make.
            band = "No data"
            if samples > 0:
                means = (
                    f"{samples} groundwater sample{'s' if samples != 1 else ''} from "
                    f"this block {'are' if samples != 1 else 'is'} in the government "
                    f"dataset, but none was analysed for uranium. So nothing here can "
                    f"tell you about uranium either way — that is a gap in testing, "
                    f"not a clean result.")
            else:
                means = (
                    "No groundwater sample from this block is in the government "
                    "dataset used here. That is a gap in monitoring — it is not a "
                    "clean result.")
        elif mx >= URANIUM_LIMIT_PPB:
            band, means = "High concern", (
                f"The highest uranium reading from a tested well here is "
                f"{mx:.1f} ppb. The safe limit for drinking water is "
                f"{URANIUM_LIMIT_PPB:.0f} ppb, so at least one well is above it.")
        elif mx >= URANIUM_LIMIT_PPB / 2:
            band, means = "Moderate concern", (
                f"The highest uranium reading here is {mx:.1f} ppb — below the "
                f"{URANIUM_LIMIT_PPB:.0f} ppb safe limit, but close enough that it "
                f"is worth watching.")
        else:
            band, means = "Low concern", (
                f"The highest uranium reading from a tested well here is "
                f"{mx:.1f} ppb, well below the {URANIUM_LIMIT_PPB:.0f} ppb "
                f"safe limit.")

        out.append({
            **s,
            "wells": int(m.get("wells") or 0),
            "samples": int(m.get("samples") or 0),
            "max_uranium_ppb": round(float(mx), 2) if mx is not None else None,
            "last_sampled": m.get("last_sampled"),
            "band": band,
            "what_it_means": means,
        })

    return {
        "blocks": out,
        "unread": await svc.unread_count(me.id),
        "safe_limit_ppb": URANIUM_LIMIT_PPB,
        "what_this_is": (
            "These are real test results from government groundwater sampling — "
            "measurements, not predictions."),
    }
