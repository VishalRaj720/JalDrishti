"""
ml_pipeline.dashboard.plume_geometry
==================================
Turn the analytical plume field (flow-aligned, metres) into georeferenced,
strike-rotated contours Leaflet can draw directly.

The transport engine solves with flow along +x. The user's "Fracture Strike
Azimuth" sets the real-world bearing of that +x axis, so rendering is just a
rotation + local ENU->lon/lat conversion (rotation-invariant metrics unaffected).
"""
from __future__ import annotations

import math
import numpy as np

# local-tangent-plane conversion constants
_M_PER_DEG_LAT = 111_320.0


def local_to_lonlat(x_m, y_m, lon0: float, lat0: float, azimuth_deg: float):
    """Map flow-frame metres (x downgradient, y cross-gradient, +y to the left)
    to (lon, lat). azimuth_deg = bearing of +x clockwise from North."""
    A = math.radians(azimuth_deg)
    sinA, cosA = math.sin(A), math.cos(A)
    # +x along azimuth A; +y is 90deg CCW (to the left) of +x
    east = x_m * sinA - y_m * cosA
    north = x_m * cosA + y_m * sinA
    dlat = north / _M_PER_DEG_LAT
    dlon = east / (_M_PER_DEG_LAT * math.cos(math.radians(lat0)))
    return lon0 + dlon, lat0 + dlat


def _choose_levels(c_abs: np.ndarray, threshold: float, background: float) -> list[dict]:
    cmax = float(np.nanmax(c_abs))
    base = max(background * 1.05, threshold * 0.05, 1e-9)
    levels = []
    if cmax > threshold:
        cand = [threshold, threshold * 3, threshold * 10, threshold * 30, threshold * 100]
        cand = [L for L in cand if base < L < cmax * 0.995]
        if not cand:
            cand = [threshold]
        # add an inner "core" level for shading depth
        cand.append(min(cmax * 0.85, max(cand) * 3))
        levels = cand
    else:
        # sub-threshold plume: still show its shape via fractions of the max
        levels = [cmax * f for f in (0.2, 0.4, 0.6, 0.8) if cmax * f > base]
    out = []
    for L in sorted(set(round(v, 6) for v in levels)):
        out.append({"level": L, "is_bis": abs(L - threshold) < 1e-6})
    return out


def _extract_rings(X, Y, C, level: float):
    """Closed contour rings (metres) at a level, via matplotlib (Agg, no GUI)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    rings = []
    try:
        cs = ax.contour(X, Y, C, levels=[level])
        for path in cs.get_paths():
            for poly in path.to_polygons():
                if len(poly) >= 3:
                    rings.append(poly)   # (N,2) metres
    finally:
        plt.close(fig)
    return rings


def _decimate(ring: np.ndarray, max_pts: int = 160) -> np.ndarray:
    if len(ring) <= max_pts:
        return ring
    idx = np.linspace(0, len(ring) - 1, max_pts).astype(int)
    return ring[idx]


def field_to_contours(field, *, lon0, lat0, azimuth_deg, threshold, background,
                      x_offset_m: float = 0.0):
    """PlumeResult -> list of contour dicts in lon/lat for Leaflet polygons.

    x_offset_m shifts the solver frame along the flow axis before rotation:
    the transport engine puts x=0 at the DOWNGRADIENT WELLFIELD EDGE, while the
    map pin marks the wellfield centre -> pass x_offset_m = W/2.
    """
    X, Y, C = field.X, field.Y, field.C
    c_abs = C + background
    out = []
    for spec in _choose_levels(c_abs, threshold, background):
        rings_m = _extract_rings(X, Y, c_abs, spec["level"])
        polys = []
        for ring in rings_m:
            ring = _decimate(np.asarray(ring))
            polys.append([list(local_to_lonlat(px + x_offset_m, py, lon0, lat0, azimuth_deg))
                          for px, py in ring])
        if polys:
            out.append({"level": round(spec["level"], 4), "is_bis": spec["is_bis"],
                        "polygons": polys})
    return out


def source_zone_polygon(lon0, lat0, azimuth_deg, radius_m, center_x_m,
                        n=72, x_offset_m: float = 0.0):
    """The E1 leach-zone disc as its OWN lon/lat ring (bug A, 2026-08-11).

    WHY IT IS DRAWN SEPARATELY. The display field unions the disc into the
    concentration grid, so contouring it produced ONE polygon that welded a
    circle (the source zone) to the plume lobe, with re-entrant notches where
    they met -- which reads as a rendering glitch rather than as a plume.

    The two shapes are different objects and the mismatch is structural: the
    transport solution emits from a LINE SOURCE of half-width W_eff/2 at x = 0,
    while the disc is a CIRCLE of radius W_eff/2 centred at x = -W/2. The circle
    has narrowed to sqrt(r^2 - (W/2)^2) by the time it reaches x = 0 -- 50 m
    against the plume's 158 m at a 300 m pattern -- so the plume necessarily
    emerges wider than the disc meant to represent its source. Reconciling them
    means changing the source geometry, which is a label-affecting physics change
    and is frozen (ML_PIPELINE_READINESS.md section 7).

    So they are rendered as what they are: a source-zone footprint, and a plume
    contoured from the plume-only field. No welding, no notches.
    """
    ring = []
    for k in range(n + 1):
        th = 2 * math.pi * k / n
        ring.append(list(local_to_lonlat(x_offset_m + center_x_m + radius_m * math.cos(th),
                                         radius_m * math.sin(th),
                                         lon0, lat0, azimuth_deg)))
    return ring


def compliance_ring(lon0, lat0, azimuth_deg, radius_m, n=72):
    """Monitoring ring (circle of given radius) as a lon/lat polygon."""
    ring = []
    for k in range(n + 1):
        th = 2 * math.pi * k / n
        ring.append(list(local_to_lonlat(radius_m * math.cos(th),
                                          radius_m * math.sin(th),
                                          lon0, lat0, azimuth_deg)))
    return ring


#: an envelope whose whole extent is under this many metres cannot be told from
#: the pin at any usable zoom; drawing it produces a dot the user reads as noise.
MIN_RENDERABLE_EXTENT_M = 2.0


def ml_envelope_ellipses(lon0, lat0, azimuth_deg, migration_bands: dict,
                         aspect_ratio: float, n=64, x_offset_m: float = 0.0,
                         halfwidth_m: float | None = None):
    """Dashed ML migration envelopes (P10/P50/P90) as DOWN-GRADIENT lobes.

    Returns {"rings": {band: ring}, "skipped": {band: reason}} so the caller can
    say why a band is missing instead of silently dropping it.

    TWO BUGS FIXED HERE (bug B, 2026-08-11).

    1. THE ENVELOPE USED TO EXTEND UP-GRADIENT. The ellipse was CENTRED on the
       source plane and swept theta over 0..2pi with semi-major = the migration
       distance, so it spanned x in [x_offset - a, x_offset + a]. At a P90 of
       1018.6 m that put the ring 869 m UPSTREAM of the pin -- drawing predicted
       contamination in the one direction the model says has none. Same class of
       error as the migration metric fixed in review3.md. The lobe is now
       anchored AT the source plane and extends only down-gradient: centre
       x_offset + a/2, semi-major a/2.

    2. THE SHAPE CARRIED NO INFORMATION IN THE COMMON CASE. `aspect` was clamped
       with max(aspect_ratio, 1.0), but the analytical aspect ratio is BELOW 1
       whenever the plume is wider than it is long -- 0.214 at op = 20, 0.472 at
       op = 10 -- which is the normal radial-dominated case. Every one of those
       rendered as a circle. The cross-gradient half-width is now taken from the
       plume's own measured half-width when available, and only falls back to the
       aspect ratio (unclamped) otherwise.
    """
    res, skipped = {}, {}
    for q, dist in migration_bands.items():
        a = float(dist)
        if not (a > MIN_RENDERABLE_EXTENT_M):
            skipped[q] = (f"migration {a:.2f} m is below the {MIN_RENDERABLE_EXTENT_M:.0f} m "
                          f"minimum drawable extent — the plume has not measurably moved")
            continue
        if halfwidth_m and halfwidth_m > 0:
            b = float(halfwidth_m)          # measured cross-gradient half-width
        else:
            b = a / aspect_ratio if aspect_ratio > 0 else a
        semi = a / 2.0                      # lobe spans the source plane -> a
        cx = x_offset_m + semi
        ring = []
        for k in range(n + 1):
            th = 2 * math.pi * k / n
            ring.append(list(local_to_lonlat(cx + semi * math.cos(th),
                                             b * math.sin(th),
                                             lon0, lat0, azimuth_deg)))
        res[q] = ring
    return {"rings": res, "skipped": skipped}
