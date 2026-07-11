"""
ml_pipeline.data_prep.strike_field  (Phase-2 D2 -- fracture-strike field)
========================================================================
Offline prep that turns the GSI/NRSC structural lineaments into a coarse grid of
(dominant fracture strike, orientation dispersion) so Module 3 (E1) can decide,
per pin, between:
  * a SINGLE dominant set (low dispersion) -> anisotropic plume that channels /
    elongates along strike, and
  * a MULTIDIRECTIONAL crisscross network (high dispersion) -> isotropic, radial
    spread -- the user's "multidirectional cracks disperse radially" requirement,
    driven by a measured quantity instead of a manual toggle.

Product (per ~5 km cell, same grid as flow_field), artifacts/strike_field.npz:
  * res_x, res_y      the AXIAL mean-resultant vector (doubled-angle), so a single
                      bilinear interpolation carries BOTH the mean strike (its
                      direction) and the dispersion (its length R). |R|->1 aligned,
                      |R|->0 dispersed.
  * n_segments        support count (confidence; low -> regional fallback)
  * in_jh             inside the dissolved state boundary

METHOD (each choice deliberate)
  Axial stats:  strikes are UNDIRECTED (10 deg == 190 deg). All circular means /
                variances use the doubled-angle method (theta -> 2*theta, vector-
                average, halve back). Plain angle averaging is wrong here.
  Weighting:    by segment LENGTH x Gaussian(distance). Length is legitimate
                orientation information (a long shear zone outweighs a short
                joint); it is NOT a density proxy. We deliberately use ORIENTATION
                only and never fracture COUNT/INTENSITY, because the lineaments
                came from a point-sampled WMS GetFeatureInfo harvest -- orientation
                statistics are robust to that undersampling, intensity is not.
  Structural:   only the ~870 STRUCTURAL lineaments (Des starts "Structural
                Lineaments-": Joint/Fracture, Shear Zone, Fault, Dyke, Axial trace
                of fold). Geomorphic (drainage/ridge-parallel) lines are dropped --
                they track topography, not the rock's fracture fabric.

Build:   myvenv/Scripts/python.exe -m ml_pipeline.data_prep.strike_field
Runtime: load_strike_field()/strike_at() read only the small committed .npz.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

import numpy as np

from ml_pipeline.config import parameters as P

REPO_ROOT = Path(__file__).resolve().parents[2]
LINEAMENTS = REPO_ROOT / "Datasets" / "jharkhand_lineaments.geojson"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
STRIKE_NPZ = ARTIFACT_DIR / "strike_field.npz"
STRIKE_META = ARTIFACT_DIR / "strike_field_meta.json"

M_PER_DEG = 111_320.0
GRID_KM = 5.0
RADIUS_KM = 30.0          # lineaments are sparse -> wider search than the flow field
MIN_SEGMENTS = 20
SIGMA_KM = 15.0

# V -> transverse anisotropy ratio (alpha_T/alpha_L), FRACTURED regime. Re-anchored
# (Stage D) so the FIELD-MEDIAN V reproduces the current fractured value 0.02 and V
# only PERTURBS around it -- anchoring to the theoretical V=0/1 extremes mapped the
# real field (V in [0.36,0.78]) to 0.19-0.39 and would have fattened every fractured
# plume 10-20x. Multiplicative/log form stays positive; clipped to a physical band.
# [Gelhar et al. 1992: aT/aL ~ 0.01-0.1]
ANISO_BASE = 0.02          # aT/aL at the field-median V
ANISO_V_MED = 0.63         # field-median circular variance
ANISO_V_SCALE = 0.20       # e-fold of V-deviation
ANISO_CLIP = (0.01, 0.10)  # aligned floor .. dispersed ceiling


def anisotropy_from_variance(v: float) -> float:
    """alpha_T/alpha_L (FRACTURED) from orientation dispersion V. Median V -> 0.02;
    aligned (low V) -> more channeled; dispersed (high V) -> rounder (<= porous)."""
    v = float(np.clip(v, 0.0, 1.0))
    aniso = ANISO_BASE * np.exp((v - ANISO_V_MED) / ANISO_V_SCALE)
    return float(np.clip(aniso, *ANISO_CLIP))


# Flux-rotation permeability anisotropy lambda(V)=K_strike/K_across, FRACTURED only,
# for the DISPLAY-ONLY tensor rotation of the plume azimuth toward strike.
LAMBDA_K = 5.0             # lambda = 1 + LAMBDA_K*(1-V)
LAMBDA_CLIP = (1.0, 6.0)


def anisotropy_lambda(v: float, fractured: bool = True) -> float:
    """Permeability anisotropy K_parallel/K_across from dispersion V (fractured)."""
    if not fractured:
        return 1.0
    v = float(np.clip(v, 0.0, 1.0))
    return float(np.clip(1.0 + LAMBDA_K * (1.0 - v), *LAMBDA_CLIP))


def flux_azimuth(flow_az_deg: float, strike_deg: float, v: float,
                 fractured: bool = True) -> float:
    """DISPLAY-only tensor rotation: in anisotropic fractured rock the Darcy flux
    deviates from -grad(h) TOWARD the high-K fracture strike. Returns the rotated
    plume-travel bearing (deg). Vector form (singularity-free, undirected-strike-
    safe): shrink the across-strike component of the flow unit vector by 1/lambda.
    Labels are UNCHANGED (the solve stays flow-aligned) -- this only orients the map."""
    lam = anisotropy_lambda(v, fractured)
    if lam <= 1.0 + 1e-9:
        return float(flow_az_deg % 360.0)
    ts = np.radians(strike_deg)
    es = np.array([np.sin(ts), np.cos(ts)])            # along strike (E, N)
    ep = np.array([np.cos(ts), -np.sin(ts)])           # across strike
    tf = np.radians(flow_az_deg)
    f = np.array([np.sin(tf), np.cos(tf)])
    fp = f.dot(es) * es + (f.dot(ep) / lam) * ep
    return float(np.degrees(np.arctan2(fp[0], fp[1])) % 360.0)


# --------------------------------------------------------------------------- #
# Load structural lineaments -> segment table (midpoint, strike, length)
# --------------------------------------------------------------------------- #
def _load_segments():
    import json as _json
    fc = _json.loads(LINEAMENTS.read_text(encoding="utf-8"))
    classes = {}
    mlon, mlat, strike, length = [], [], [], []
    for f in fc.get("features", []):
        props = f.get("properties", {})
        des = str(props.get("Des") or props.get("Description") or "")
        if not des.startswith("Structural Lineaments"):
            continue
        classes[des] = classes.get(des, 0) + 1
        g = f.get("geometry")
        if not g:
            continue
        lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        for ln in lines:
            arr = np.asarray(ln, dtype=float)
            if len(arr) < 2:
                continue
            for (x0, y0), (x1, y1) in zip(arr[:-1], arr[1:]):
                lat_mid = 0.5 * (y0 + y1)
                dE = (x1 - x0) * M_PER_DEG * np.cos(np.radians(lat_mid))
                dN = (y1 - y0) * M_PER_DEG
                L = np.hypot(dE, dN)
                if L < 1.0:
                    continue
                th = np.degrees(np.arctan2(dE, dN)) % 180.0     # axial strike [0,180)
                mlon.append(0.5 * (x0 + x1)); mlat.append(lat_mid)
                strike.append(th); length.append(L)
    return (np.array(mlon), np.array(mlat), np.array(strike),
            np.array(length), classes)


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build_strike_field() -> dict:
    from ml_pipeline.data_prep.boundary import in_jharkhand
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    mlon, mlat, strike, length, classes = _load_segments()
    phi = 2.0 * np.radians(strike)                     # doubled angle
    cos2, sin2 = np.cos(phi), np.sin(phi)

    B = P.JHARKHAND_BOUNDS
    dlat = GRID_KM * 1000.0 / M_PER_DEG
    mid_lat = 0.5 * (B["lat_min"] + B["lat_max"])
    dlon = GRID_KM * 1000.0 / (M_PER_DEG * np.cos(np.radians(mid_lat)))
    lat_c = np.arange(B["lat_min"], B["lat_max"] + dlat, dlat)
    lon_c = np.arange(B["lon_min"], B["lon_max"] + dlon, dlon)
    H, W = len(lat_c), len(lon_c)

    radius_m, sigma_m = RADIUS_KM * 1000.0, SIGMA_KM * 1000.0
    res_x = np.zeros((H, W)); res_y = np.zeros((H, W))
    n_seg = np.zeros((H, W), dtype=np.int32); in_jh = np.zeros((H, W), dtype=bool)

    # global fallback resultant (whole-state) for under-supported cells
    wg = length
    gX = np.sum(wg * cos2) / np.sum(wg); gY = np.sum(wg * sin2) / np.sum(wg)

    for j, lat0 in enumerate(lat_c):
        cos_lat = np.cos(np.radians(lat0))
        for i, lon0 in enumerate(lon_c):
            in_jh[j, i] = in_jharkhand(lon0, lat0)
            dE = (mlon - lon0) * M_PER_DEG * cos_lat
            dN = (mlat - lat0) * M_PER_DEG
            d = np.hypot(dE, dN)
            near = d <= radius_m
            k = int(near.sum())
            n_seg[j, i] = k
            if k >= MIN_SEGMENTS:
                w = length[near] * np.exp(-(d[near] / sigma_m) ** 2)
                wsum = w.sum()
                if wsum > 1e-9:
                    res_x[j, i] = np.sum(w * cos2[near]) / wsum
                    res_y[j, i] = np.sum(w * sin2[near]) / wsum
                    continue
            res_x[j, i], res_y[j, i] = gX, gY          # regional fallback

    R = np.hypot(res_x, res_y)
    mean_strike = (np.degrees(np.arctan2(res_y, res_x)) / 2.0) % 180.0
    V = 1.0 - R
    np.savez_compressed(STRIKE_NPZ, lon_c=lon_c, lat_c=lat_c, res_x=res_x,
                        res_y=res_y, n_segments=n_seg, in_jh=in_jh)
    meta = {
        "grid_km": GRID_KM, "radius_km": RADIUS_KM, "min_segments": MIN_SEGMENTS,
        "sigma_km": SIGMA_KM, "n_segments_total": int(len(strike)),
        "structural_classes": classes, "grid_shape": [H, W],
        "cells_in_jh": int(in_jh.sum()),
        "supported_cells": int(((n_seg >= MIN_SEGMENTS) & in_jh).sum()),
        "global_mean_strike_deg": round(float((np.degrees(np.arctan2(gY, gX)) / 2) % 180), 1),
        "global_V": round(float(1.0 - np.hypot(gX, gY)), 3),
        "mean_strike_pctiles": [round(float(np.percentile(mean_strike[in_jh], q)), 1) for q in (25, 50, 75)],
        "V_pctiles": [round(float(np.percentile(V[in_jh], q)), 3) for q in (10, 50, 90)],
    }
    STRIKE_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


# --------------------------------------------------------------------------- #
# Runtime
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=1)
def load_strike_field() -> dict:
    z = np.load(STRIKE_NPZ)
    return {k: z[k] for k in z.files}


def strike_at(lon: float, lat: float) -> dict:
    """Bilinear-sampled fracture strike + dispersion at a pin. Direction and
    dispersion both ride the interpolated axial resultant vector (seam-safe)."""
    sf = load_strike_field()
    lon_c, lat_c = sf["lon_c"], sf["lat_c"]
    lon = float(np.clip(lon, lon_c[0], lon_c[-1]))
    lat = float(np.clip(lat, lat_c[0], lat_c[-1]))
    i = int(np.clip(np.searchsorted(lon_c, lon) - 1, 0, len(lon_c) - 2))
    j = int(np.clip(np.searchsorted(lat_c, lat) - 1, 0, len(lat_c) - 2))
    tx = (lon - lon_c[i]) / (lon_c[i + 1] - lon_c[i])
    ty = (lat - lat_c[j]) / (lat_c[j + 1] - lat_c[j])
    w = np.array([(1 - tx) * (1 - ty), tx * (1 - ty), (1 - tx) * ty, tx * ty])

    def corners(A):
        return np.array([A[j, i], A[j, i + 1], A[j + 1, i], A[j + 1, i + 1]], dtype=float)

    # validity-weighted: don't drag a border pin toward out-of-Jharkhand cells
    valid = (corners(sf["in_jh"].astype(float)) > 0.5).astype(float)

    def bilin(A):
        vals = corners(A)
        m = w * valid
        s = m.sum()
        return float(np.sum(vals * m) / s) if s > 1e-12 else float(np.sum(vals * w) / w.sum())

    rx, ry = bilin(sf["res_x"]), bilin(sf["res_y"])
    R = float(np.hypot(rx, ry))
    strike = float((np.degrees(np.arctan2(ry, rx)) / 2.0) % 180.0)
    V = float(np.clip(1.0 - R, 0.0, 1.0))
    disp = "aligned" if V < 0.4 else ("dispersed" if V > 0.65 else "intermediate")
    return {
        "mean_strike_deg": round(strike, 1),
        "circular_variance": round(V, 3),
        "dispersion": disp,
        "aniso_ratio": round(anisotropy_from_variance(V), 3),
    }


def _render_png(sf, meta):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    lon_c, lat_c = sf["lon_c"], sf["lat_c"]
    R = np.hypot(sf["res_x"], sf["res_y"]); V = 1.0 - R
    strike = (np.degrees(np.arctan2(sf["res_y"], sf["res_x"])) / 2.0) % 180.0
    step = max(1, len(lon_c) // 40)
    fig, ax = plt.subplots(figsize=(8, 6))
    for j in range(0, len(lat_c), step):
        for i in range(0, len(lon_c), step):
            if not sf["in_jh"][j, i]:
                continue
            th = np.radians(strike[j, i]); ln = 0.06
            dE, dN = np.sin(th) * ln, np.cos(th) * ln   # axial tick (both ways)
            col = plt.cm.plasma(float(np.clip(V[j, i], 0, 1)))
            ax.plot([lon_c[i] - dE, lon_c[i] + dE], [lat_c[j] - dN, lat_c[j] + dN],
                    color=col, lw=1.3)
    ax.set_title("Fracture strike (tick=mean strike, colour=dispersion V: dark=aligned, bright=dispersed)")
    ax.set_xlabel("lon"); ax.set_ylabel("lat"); ax.set_aspect("equal")
    fig.savefig(ARTIFACT_DIR / "strike_field.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    print("building strike field (reads lineaments geojson)...")
    meta = build_strike_field()
    print(json.dumps(meta, indent=2))
    sf = load_strike_field()
    _render_png(sf, meta)
    print("\nspot checks:")
    for name, lon, lat in [("Jaduguda(Sbm shear)", 86.347, 22.652),
                           ("Jamshedpur", 86.20, 22.80), ("Ranchi", 85.33, 23.36),
                           ("Dhanbad", 86.43, 23.80)]:
        print(f"  {name:20s} {strike_at(lon, lat)}")
    print(f"\nwrote {STRIKE_NPZ} ({STRIKE_NPZ.stat().st_size/1e3:.0f} KB)")
