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

from ml_pipeline.config import parameters as P

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


def lonlat_to_local(lon, lat, lon0: float, lat0: float, azimuth_deg: float):
    """Inverse of `local_to_lonlat`: (lon, lat) -> flow-frame metres (x, y).
    Vectorised over numpy arrays."""
    A = math.radians(azimuth_deg)
    sinA, cosA = math.sin(A), math.cos(A)
    east = (np.asarray(lon) - lon0) * _M_PER_DEG_LAT * math.cos(math.radians(lat0))
    north = (np.asarray(lat) - lat0) * _M_PER_DEG_LAT
    # rows of the forward rotation are orthonormal, so the inverse is its transpose
    x = east * sinA + north * cosA
    y = -east * cosA + north * sinA
    return x, y


#: Longest side of a plume raster, in pixels. 160 keeps a stored run's two
#: layers near 60 kB of base64 while resolving a 300 m wellfield in ~15 px.
RASTER_MAX_PX = 160


def _b64_u8(a: np.ndarray) -> str:
    import base64
    return base64.b64encode(np.ascontiguousarray(a, dtype=np.uint8).tobytes()).decode("ascii")


def raster_grid(x_extent, y_extent, *, lon0: float, lat0: float, azimuth_deg: float,
                x_offset_m: float = 0.0, max_px: int = RASTER_MAX_PX) -> dict | None:
    """A north-up pixel grid covering a flow-frame box, with every pixel centre
    mapped back into the SOLVER frame (x from the source plane, y across flow).

    One grid is shared by every layer so the concentration and probability
    pictures register exactly. Row 0 is the north edge.
    """
    xs = (float(x_extent[0]) + x_offset_m, float(x_extent[1]) + x_offset_m)
    ys = (float(y_extent[0]), float(y_extent[1]))
    corners = [local_to_lonlat(x, y, lon0, lat0, azimuth_deg) for x in xs for y in ys]
    lon_w, lon_e = min(c[0] for c in corners), max(c[0] for c in corners)
    lat_s, lat_n = min(c[1] for c in corners), max(c[1] for c in corners)
    w_m = (lon_e - lon_w) * _M_PER_DEG_LAT * math.cos(math.radians(lat0))
    h_m = (lat_n - lat_s) * _M_PER_DEG_LAT
    if not (w_m > 0 and h_m > 0):
        return None
    scale = max(w_m, h_m) / float(max_px)
    nx, ny = max(int(round(w_m / scale)), 2), max(int(round(h_m / scale)), 2)
    lons = lon_w + (np.arange(nx) + 0.5) / nx * (lon_e - lon_w)
    lats = lat_n - (np.arange(ny) + 0.5) / ny * (lat_n - lat_s)
    LON, LAT = np.meshgrid(lons, lats)
    X, Y = lonlat_to_local(LON, LAT, lon0, lat0, azimuth_deg)
    return {"bounds": [[round(lat_s, 7), round(lon_w, 7)], [round(lat_n, 7), round(lon_e, 7)]],
            "width": int(nx), "height": int(ny), "pixel_m": round(scale, 2),
            "X": X - x_offset_m, "Y": Y, "x_offset_m": float(x_offset_m),
            # for rotating a layer about the pin in pixel space
            "sx_m": w_m / nx, "sy_m": h_m / ny,
            "pin_rc": ((lat_n - lat0) / (lat_n - lat_s) * ny - 0.5,
                       (lon0 - lon_w) / (lon_e - lon_w) * nx - 0.5)}


#: evenly spaced flow-direction quantiles per parameter draw. Parameter and
#: direction uncertainty are independent, so every draw is combined with every
#: direction -- 15 is enough that the fan is a continuous field, not rays.
N_DIRECTIONS = 15


def direction_offsets(sd_deg: float | None, n: int = N_DIRECTIONS) -> list[float] | None:
    """Flow-direction offsets [deg]: the n evenly spaced quantiles of a normal
    with the measured standard deviation. None / 0 -> no direction spread."""
    if not sd_deg or sd_deg <= 0 or n <= 0:
        return None
    from scipy.stats import norm
    return [float(sd_deg * v) for v in norm.ppf((np.arange(n) + 0.5) / n)]


def _rotate_about_pin(layer: np.ndarray, grid: dict, delta_deg: float) -> np.ndarray:
    """`layer` swung clockwise (in bearing) by `delta_deg` about the pin.

    Output pixel P takes the value the unrotated layer has at P turned back by
    delta about the pin. Pixels are square to within rounding; the separate
    metric sizes sx, sy keep the turn a true rotation on the ground."""
    from scipy.ndimage import affine_transform
    d = math.radians(delta_deg)
    c, s_ = math.cos(d), math.sin(d)
    sx, sy = grid["sx_m"], grid["sy_m"]
    r0, c0 = grid["pin_rc"]
    M = np.array([[c, -(sx / sy) * s_], [(sy / sx) * s_, c]])
    offset = np.array([r0 - M[0, 0] * r0 - M[0, 1] * c0,
                       c0 - M[1, 0] * r0 - M[1, 1] * c0])
    return affine_transform(layer, M, offset=offset, order=1, mode="constant", cval=0.0)


def _plume_on(grid: dict, params) -> np.ndarray:
    """Plume-attributable concentration at every pixel -- the SAME display rules
    as the contours: plume-only (the leach-zone disc is its own layer, bug A
    2026-08-11) and zero up-gradient of the source plane (the Domenico
    half-plane artifact `solve_plume` also masks)."""
    from ml_pipeline.physics.transport import concentration_field
    C = concentration_field(grid["X"], grid["Y"], params, include_disc=False)
    return np.where(grid["X"] > 0.0, C, 0.0)


def concentration_layer(grid: dict, params, *, threshold: float,
                        background: float) -> dict | None:
    """The central run's field, evaluated DIRECTLY at each pixel centre.

    WHY. Two to six flat contour fills throw away the field between the levels.
    The engine's field is analytical, so no interpolation or resampling of the
    solver grid is involved: each pixel is handed to the same
    `concentration_field` the contours and metrics come from. Absolute
    concentration (plume + background), log scale, with the display floor
    `_choose_levels` uses; below it a pixel is transparent, so the floor is
    where the picture stops, not an implied zero.

    Encoding: uint8, 0 = below the floor; 1..255 = log10(concentration) linear
    in [log10_min, log10_max]. None when nothing clears the floor.
    """
    c_abs = _plume_on(grid, params) + background
    floor = max(background * 1.05, threshold * 0.05, 1e-9)
    top = float(np.nanmax(c_abs))
    if not (top > floor):
        return None
    lo, hi = math.log10(floor), math.log10(top)
    t = (np.log10(np.maximum(c_abs, floor)) - lo) / max(hi - lo, 1e-9)
    q = np.where(c_abs > floor, 1 + np.round(np.clip(t, 0.0, 1.0) * 254), 0)
    return {"log10_min": round(lo, 5), "log10_max": round(hi, 5),
            "threshold": float(threshold),
            "encoding": ("uint8, row 0 = north, base64; 0 = below the display "
                         "floor (transparent); 1..255 = log10(absolute "
                         "concentration) linear in [log10_min, log10_max]"),
            "data": _b64_u8(q)}


def _draw_box(p, thr_inc: float) -> tuple[float, float, float, float]:
    """(x0, x1, y0, y1) in the solver frame outside which draw `p` cannot
    exceed `thr_inc`: the same reach and auto-grid `solve_plume` sizes its own
    grid to -- the Tang early-arrival tail taken at the INCREMENTAL threshold's
    fraction of C0, not a fixed level, so a strongly sorbing species' faint tail
    is not cut off."""
    from ml_pipeline.physics.transport import _auto_grid, _tang_reach, MAX_GRID_REACH_M
    level = float(np.clip(thr_inc / max(p.C0, 1e-9), 1e-4, 0.5))
    reach = min(max(p.Xc, _tang_reach(p.t_days, p.Xw, p.sigma, level=level)),
                MAX_GRID_REACH_M)
    X, Y = _auto_grid(reach, p.aL, p.source_width_m, n=8,
                      disc_radius=p.disc_radius_m,
                      disc_center_x=p.disc_center_x_m, aT=p.aT)
    return float(X.min()), float(X.max()), float(Y.min()), float(Y.max())


def exceedance_layer(grid: dict, draws: list, *, thr_inc: float,
                     direction: dict | None = None) -> dict | None:
    """Fraction of Monte-Carlo draws whose plume exceeds the drinking-water
    limit at each pixel.

    The draws are the ones the served `excursion_probability` already scores
    (`ml.predict.mc_param_draws`: same scenario, same common random numbers,
    same seed) -- local K heterogeneity, Kd, beta x4, gradient, dispersivity,
    bleed drift, downtime and aperture over their REGISTERED ranges. So this is
    not a new uncertainty model; it is the existing one drawn in space instead
    of reduced to one number at the ring.

    FLOW DIRECTION (2026-09-25). With `direction` (data_prep/flow_direction.py:
    the measured uncertainty of the long-term flow direction), the draws'
    fraction map is averaged over N_DIRECTIONS evenly spaced direction
    quantiles, each a rotation about the wellfield centre. Rotation is linear,
    so rotating the draw-averaged map equals combining every draw with every
    direction -- the full independent product, at the cost of 15 image
    rotations. Without it, every draw lies on the central bearing, which is
    exactly the frame the served excursion probability is computed in.

    Encoding: uint8 = round(255 * fraction); 0 = no draw exceeds.
    """
    if not draws:
        return None
    from ml_pipeline.physics.transport import concentration_field
    X, Y = grid["X"], grid["Y"]
    hits = np.zeros(X.shape, dtype=np.float64)
    for p in draws:
        # evaluate only inside the draw's own plume box (and down-gradient of
        # the source plane, the contours' mask): outside it the draw is below
        # the threshold by construction, and most of a fanned grid is outside
        x0, x1, y0, y1 = _draw_box(p, thr_inc)
        sel = (X > max(x0, 0.0)) & (X <= x1) & (Y >= y0) & (Y <= y1)
        if sel.any():
            c = concentration_field(X[sel], Y[sel], p, include_disc=False)
            hits[sel] += (c >= thr_inc)
    frac = hits / float(len(draws))
    offs = direction_offsets((direction or {}).get("served_sd_deg"))
    if offs:
        frac = np.mean([_rotate_about_pin(frac, grid, o) for o in offs], axis=0)
    if not np.any(frac > 0.5 / 255):
        return None
    return {"n_draws": len(draws),
            "n_directions": (len(offs) if offs else 1),
            "thr_inc": float(thr_inc),
            "direction_sd_deg": (direction.get("served_sd_deg") if offs else None),
            "direction": (direction if offs else None),
            "encoding": ("uint8, row 0 = north, base64; value/255 = fraction of "
                         "(parameter draw x flow direction) combinations "
                         "exceeding the limit; 0 = none"),
            "data": _b64_u8(np.round(np.clip(frac, 0.0, 1.0) * 255))}


def draws_extent(draws: list, x_extent, y_extent, *, x_offset_m: float = 0.0,
                 max_turn_deg: float = 0.0,
                 thr_inc: float | None = None) -> tuple[tuple, tuple]:
    """Grow the central run's solver box so it covers every draw's plume -- and,
    with direction spread, every draw's plume swung about the wellfield centre.
    Otherwise a long P90 front, or a draw pointing off the central bearing, is
    clipped at the edge of the central picture."""
    from ml_pipeline.physics.transport import _auto_grid, _tang_reach, MAX_GRID_REACH_M
    x0, x1 = float(x_extent[0]), float(x_extent[1])
    y0, y1 = float(y_extent[0]), float(y_extent[1])
    turns = (0.0, -max_turn_deg, max_turn_deg) if max_turn_deg else (0.0,)
    for p in draws:
        if thr_inc is not None:
            bx0, bx1, by0, by1 = _draw_box(p, thr_inc)
        else:
            reach = min(max(p.Xc, _tang_reach(p.t_days, p.Xw, p.sigma, level=1e-2)),
                        MAX_GRID_REACH_M)
            X, Y = _auto_grid(reach, p.aL, p.source_width_m, n=8,
                              disc_radius=p.disc_radius_m,
                              disc_center_x=p.disc_center_x_m, aT=p.aT)
            bx0, bx1, by0, by1 = float(X.min()), float(X.max()), float(Y.min()), float(Y.max())
        for rot in turns:
            d = math.radians(rot)
            c, s_ = math.cos(d), math.sin(d)
            for xd in (bx0, bx1):
                for yd in (by0, by1):
                    xp = xd + x_offset_m                 # draw frame, pin-centred
                    xc = c * xp + s_ * yd - x_offset_m   # back to the central frame
                    yc = -s_ * xp + c * yd
                    x0, x1 = min(x0, xc), max(x1, xc)
                    y0, y1 = min(y0, yc), max(y1, yc)
    return (x0, x1), (y0, y1)


def plume_rasters(params, draws: list, *, x_extent, y_extent, lon0: float,
                  lat0: float, azimuth_deg: float, threshold: float,
                  background: float, x_offset_m: float = 0.0,
                  direction: dict | None = None,
                  max_px: int = RASTER_MAX_PX) -> dict | None:
    """Both layers on one grid: the central concentration field and the
    exceedance probability across the Monte-Carlo draws, each draw also swung
    by the measured flow-direction uncertainty when `direction` is given."""
    offs = direction_offsets((direction or {}).get("served_sd_deg"))
    thr_inc = max(threshold - background, P.INCREMENTAL_FLOOR * threshold)
    if draws:
        x_extent, y_extent = draws_extent(
            draws, x_extent, y_extent, x_offset_m=x_offset_m,
            max_turn_deg=(max(abs(o) for o in offs) if offs else 0.0), thr_inc=thr_inc)
    grid = raster_grid(x_extent, y_extent, lon0=lon0, lat0=lat0,
                       azimuth_deg=azimuth_deg, x_offset_m=x_offset_m, max_px=max_px)
    if grid is None:
        return None
    conc = concentration_layer(grid, params, threshold=threshold, background=background)
    prob = exceedance_layer(grid, draws, thr_inc=thr_inc, direction=direction)
    if conc is None and prob is None:
        return None
    return {"bounds": grid["bounds"], "width": grid["width"], "height": grid["height"],
            "pixel_m": grid["pixel_m"], "concentration": conc, "exceedance": prob}


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
