"""Where to sample next.

Staff-readable, because it is an operational planning list rather than a public
statement about anyone's water. It carries no model output and no ISR geometry
beyond a distance, so nothing here would be unsafe for a resident to see — but a
priority ranking reads as a to-do list, and publishing one the state has not
committed to would promise sampling nobody has funded.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_staff
from app.models.user import User
from app.services import monitoring_gaps as mg

router = APIRouter(prefix="/data-gaps", tags=["Data gaps"])


@router.get("/recommendations")
async def sampling_recommendations(
    response: Response,
    limit: int = Query(25, ge=1, le=200),
    district: Optional[str] = Query(None, description="Restrict to one district"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
) -> dict[str, Any]:
    """Blocks ranked by how badly they need groundwater sampling.

    Answers the proposal's *recommendation* deliverable, which identification
    alone did not: Data & Gaps could already say which blocks were blank, but
    not which one a crew should visit first.

    The response carries its own `weights` block. That is deliberate — the
    ordering rests on a policy judgement with no published optimum behind it, so
    the judgement travels with the answer instead of being buried in code.
    """
    response.headers["Cache-Control"] = "no-store"
    return await mg.recommendations(db, limit=limit, district=district)


@router.get("/recommendations/{block_id}/sites")
async def suggested_well_sites(
    block_id: str,
    n: int = Query(3, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    """Candidate coordinates for a new monitoring well inside one block.

    The ranking says *which block*; this says *where in it*, because a block is
    200-900 km2 and nobody can act on that. The criterion is geometric — maximum
    distance from any existing uranium-tested well — and deliberately not
    predictive: choosing sites by predicted concentration would send crews to
    where the model is already confident.

    Deterministic: the same block always returns the same coordinates.
    """
    from app.exceptions import AppException
    from fastapi import HTTPException
    try:
        return await mg.suggested_sites(db, block_id, n=n)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
