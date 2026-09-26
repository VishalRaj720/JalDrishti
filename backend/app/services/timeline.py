"""Plume timeline frames for a stored run (R17).

WHAT THIS IS. A stored run evaluates the engine at ONE horizon. The lifecycle
endpoint traces metrics across a horizon but stores nothing and carries no
geometry. This module evaluates the engine at a fixed set of horizons when a
run completes and stores, per frame, the screening-limit contour, the source
zone, the footprint, the migration, the ring concentration, the phase and the
calendar date -- so the console and the report can show the plume change over
time from numbers the engine actually produced.

THE RULE. Every frame is a real engine evaluation at that horizon. Nothing is
interpolated between frames, and the ML band carried on a frame is the
surrogate's own evaluation at that horizon (flagged where it extrapolates
beyond the trained horizon), never a value blended between two others.

WHICH HORIZONS. `0, 1, 2, 3, 5, 8, 10, 15, 20, 30, 40, 50` clipped to the
run's own horizon, plus the horizon itself and the two phase boundaries
(end of operation, end of restoration), so the restoration drop -- the single
most informative feature -- is never stepped over. At most ~15 frames.

FIRST EXCEEDANCE. The first frame at which the absolute concentration at the
monitoring ring exceeds the species' screening limit, and separately the
first frame at which the NUREG-style indicator panel declares an excursion.
Both are reported as the frame's year, not interpolated, and `None` when no
frame crosses -- which is the usual answer for uranium in fractured rock and
is reported as such rather than hidden.

RUNS STORED BEFORE R17 carry no timeline. Readers report that as
"not recorded", never as "no change over time".

STORAGE KEY. The frames live at `run.plume["frames"]`. `run.plume["timeline"]`
is the engine's own calendar dict for the single stored horizon (start date,
current date, phase) and is left untouched.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

BASE_YEARS: tuple[float, ...] = (0, 1, 2, 3, 5, 8, 10, 15, 20, 30, 40, 50)
TIMELINE_VERSION = 1


def frame_years(horizon: float, operation_years: float,
                restoration_years: float) -> list[float]:
    """The evaluation years for a run: the base set inside the horizon, the
    horizon, and the phase boundaries. Sorted, de-duplicated."""
    h = float(horizon)
    ys: set[float] = {float(y) for y in BASE_YEARS if y <= h}
    ys.add(round(h, 3))
    op = float(operation_years or 0.0)
    rest = float(restoration_years or 0.0)
    for edge in (op, op + rest):
        if 0.0 < edge <= h:
            ys.add(round(edge, 3))
    return sorted(ys)


def _phase(year: float, op: float, rest: float) -> str:
    if year <= op:
        return "operation"
    if year <= op + rest:
        return "restoration"
    return "post_closure"


def _bis_rings(result: dict[str, Any]) -> list[list[list[float]]]:
    """Only the contour at the screening limit -- the same rule the advisory
    footprint uses (lower contours lie below the limit and would inflate the
    drawn extent in exactly the direction that causes alarm)."""
    plume = result.get("plume") or {}
    out: list[list[list[float]]] = []
    for c in plume.get("contours") or []:
        if not c.get("is_bis"):
            continue
        for poly in c.get("polygons") or []:
            if poly and len(poly) >= 3:
                out.append([[round(float(p[0]), 6), round(float(p[1]), 6)] for p in poly])
    return out


async def compute_timeline(site: Any, request: dict[str, Any], *,
                           predict, payload_from_site) -> dict[str, Any]:
    """Evaluate the engine at every frame year. `predict` and
    `payload_from_site` are injected (the adapter's) so this module has no
    import-time dependency on the engine and the test can substitute a stub."""
    species = request.get("species") or "uranium_ppb"
    horizon = float(request.get("time_years") or 10.0)
    rest = float(request.get("restoration_years") or site.restoration_years or 0.0)
    op = float(site.operation_years or 0.0)
    years = frame_years(horizon, op, rest)

    frames: list[dict[str, Any]] = []
    threshold: Optional[float] = None
    ring_m: Optional[float] = None
    ring_radius_from_centre: Optional[float] = None
    errors = 0
    for y in years:
        # frames keep contours and metrics only, so the engine's display-only
        # rasters and indicator arrivals are skipped (the adapter's
        # METRICS_ONLY, spelled out here to keep this module adapter-free)
        overrides = {**(request or {}), "species": species, "time_years": y,
                     "restoration_years": rest, "display_extras": False}
        try:
            r = await predict(payload_from_site(site, overrides=overrides))
        except Exception as exc:  # noqa: BLE001
            errors += 1
            frames.append({"year": y, "phase": _phase(y, op, rest),
                           "error": f"{type(exc).__name__}: {exc}"})
            continue
        an = (r.get("metrics") or {}).get("analytical") or {}
        ml = (r.get("metrics") or {}).get("ml") or {}
        plume = r.get("plume") or {}
        sz = plume.get("source_zone") or {}
        ring = plume.get("compliance_ring") or {}
        tl = r.get("timeline") or {}
        exc_panel = r.get("isr_excursion") or {}
        if threshold is None:
            threshold = r.get("threshold")
        if ring_m is None:
            # the ring the site DEFINES (metres beyond the wellfield edge); the
            # engine's `radius_m` is the drawn radius from the site centre
            ring_m = getattr(site, "monitor_ring_m", None) or ring.get("radius_m")
            ring_radius_from_centre = ring.get("radius_m")
        frames.append({
            "year": y,
            "phase": tl.get("phase") or _phase(y, op, rest),
            "calendar_date": tl.get("current_date"),
            "contours": _bis_rings(r),
            "source_zone": sz.get("polygon"),
            "source_conc": sz.get("conc"),
            "area_ha": an.get("area_ha"),
            "migration_m": an.get("migration_m"),
            "compliance_conc": an.get("compliance_conc"),
            "excursion_probability": an.get("excursion_probability"),
            "excursion_declared": bool(exc_panel.get("excursion_declared")),
            # the surrogate's OWN evaluation at this horizon -- not interpolated
            "ml_migration_band": (ml.get("migration_m") if ml else None),
            "extrapolating": bool(r.get("extrapolation")),
            "extrapolation": list(r.get("extrapolation") or []),
        })

    def _first(pred) -> Optional[float]:
        for f in frames:
            if "error" in f:
                continue
            if pred(f):
                return f["year"]
        return None

    first_exceedance = (_first(lambda f: f.get("compliance_conc") is not None
                               and threshold is not None
                               and float(f["compliance_conc"]) > float(threshold))
                        if threshold is not None else None)
    first_excursion = _first(lambda f: f.get("excursion_declared"))
    return {
        "version": TIMELINE_VERSION,
        "engine": "analytical (ML band per frame where evaluated)",
        "species": species,
        "threshold": threshold,
        "monitor_ring_m": ring_m,
        "ring_radius_from_centre_m": ring_radius_from_centre,
        "horizon_years": horizon,
        "operation_years": op,
        "restoration_years": rest,
        "years": years,
        "frames": frames,
        "frame_errors": errors,
        "first_exceedance_year": first_exceedance,
        "first_excursion_year": first_excursion,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "note": ("Every frame is a separate engine evaluation at that horizon; "
                 "nothing is interpolated between frames. 'first' years are the "
                 "first evaluated frame that crosses, so the true crossing lies "
                 "between it and the previous frame."),
    }


def not_recorded(run: Any) -> dict[str, Any]:
    """What a reader gets for a run that carries no timeline."""
    return {
        "recorded": False,
        "run_id": str(getattr(run, "id", "")),
        "reason": ("This run was stored before timeline frames were recorded "
                   "(R17). Its single-horizon result is unaffected; re-run the "
                   "site to obtain frames. Absence of a timeline is not a "
                   "finding of no change over time."),
    }


def public_view(timeline: dict[str, Any]) -> dict[str, Any]:
    """The subset a published advisory exposes: geometry the footprint already
    reveals, the metrics, the phases and the first-exceedance years. No
    extrapolation detail or ML band -- the citizen surface carries no model
    internals (PRODUCT_DESIGN section 2)."""
    keep = ("year", "phase", "calendar_date", "contours", "source_zone",
            "area_ha", "migration_m", "compliance_conc", "excursion_declared")
    return {
        "recorded": True,
        "species": timeline.get("species"),
        "threshold": timeline.get("threshold"),
        "monitor_ring_m": timeline.get("monitor_ring_m"),
        "horizon_years": timeline.get("horizon_years"),
        "operation_years": timeline.get("operation_years"),
        "restoration_years": timeline.get("restoration_years"),
        "years": timeline.get("years"),
        "frames": [{k: f.get(k) for k in keep} for f in timeline.get("frames", [])
                   if "error" not in f],
        "first_exceedance_year": timeline.get("first_exceedance_year"),
        "first_excursion_year": timeline.get("first_excursion_year"),
        "note": timeline.get("note"),
        "premise": ("No ISR uranium mine operates in Jharkhand. These frames show "
                    "what the model expects at each horizon if one did."),
    }


def log_summary(run_id: Any, tl: dict[str, Any]) -> None:
    logger.info(f"run {run_id}: timeline {len(tl.get('frames', []))} frames, "
                f"first exceedance {tl.get('first_exceedance_year')}, "
                f"errors {tl.get('frame_errors')}")
