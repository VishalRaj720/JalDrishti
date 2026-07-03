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


def field_to_contours(field, *, lon0, lat0, azimuth_deg, threshold, background):
    """PlumeResult -> list of contour dicts in lon/lat for Leaflet polygons."""
    X, Y, C = field.X, field.Y, field.C
    c_abs = C + background
    out = []
    for spec in _choose_levels(c_abs, threshold, background):
        rings_m = _extract_rings(X, Y, c_abs, spec["level"])
        polys = []
        for ring in rings_m:
            ring = _decimate(np.asarray(ring))
            polys.append([list(local_to_lonlat(px, py, lon0, lat0, azimuth_deg))
                          for px, py in ring])
        if polys:
            out.append({"level": round(spec["level"], 4), "is_bis": spec["is_bis"],
                        "polygons": polys})
    return out


def compliance_ring(lon0, lat0, azimuth_deg, radius_m, n=72):
    """Monitoring ring (circle of given radius) as a lon/lat polygon."""
    ring = []
    for k in range(n + 1):
        th = 2 * math.pi * k / n
        ring.append(list(local_to_lonlat(radius_m * math.cos(th),
                                          radius_m * math.sin(th),
                                          lon0, lat0, azimuth_deg)))
    return ring


def ml_envelope_ellipses(lon0, lat0, azimuth_deg, migration_bands: dict,
                         aspect_ratio: float, n=64):
    """Dashed ML migration envelopes (P10/P50/P90) as oriented ellipses:
    semi-major = migration distance along strike, semi-minor = major/aspect."""
    aspect = max(aspect_ratio, 1.0)
    res = {}
    for q, dist in migration_bands.items():
        a = float(dist)          # downgradient (semi-major)
        b = a / aspect           # cross-gradient (semi-minor)
        ring = []
        for k in range(n + 1):
            th = 2 * math.pi * k / n
            ring.append(list(local_to_lonlat(a * math.cos(th), b * math.sin(th),
                                              lon0, lat0, azimuth_deg)))
        res[q] = ring
    return res
