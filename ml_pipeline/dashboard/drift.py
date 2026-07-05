"""
ml_pipeline.dashboard.drift
=========================
Lightweight in-process drift monitor for the ISR surrogate.

Every /api/predict serves BOTH engines: the analytical Domenico physics (the
"teacher") and the ML surrogate (the fast imitator). The relative disagreement
between their P50s is a free, per-request signal of surrogate health -- when it
rises, the surrogate is being queried in regions where it no longer tracks the
physics it was trained to reproduce (concept/covariate drift, or simply
extrapolation beyond training support).

We keep a bounded rolling window per metric (no persistence -- a dashboard
process signal, not an audit log), expose the running median / p90, and raise a
`drifting` flag when the median relative disagreement exceeds a threshold. The
threshold is deliberately generous (default 25%): the surrogate's honest
held-out P50 error is single-digit-percent, so a sustained 25% median gap means
something real (out-of-envelope inputs, or a stale model vs a changed physics).

Thread-safe (FastAPI's default threadpool runs sync handlers concurrently).
"""
from __future__ import annotations

import os
import threading
from collections import deque
from statistics import median

# metrics compared between analytical P50 and ML P50
_METRICS = ("area_ha", "migration_m", "compliance_conc")
_EPS = 1e-6
_WINDOW = int(os.environ.get("ML_PIPELINE_DRIFT_WINDOW", "500"))
# median relative disagreement above this (per metric) => drifting
_THRESHOLD = float(os.environ.get("ML_PIPELINE_DRIFT_THRESHOLD", "0.25"))
# don't judge drift until the window has at least this many samples
_MIN_SAMPLES = int(os.environ.get("ML_PIPELINE_DRIFT_MIN_SAMPLES", "20"))


def _rel(ana: float, ml: float) -> float:
    """Symmetric relative disagreement in [0, 2]; robust near zero."""
    denom = max(abs(ana), abs(ml), _EPS)
    return abs(ana - ml) / denom


class DriftMonitor:
    def __init__(self, window: int = _WINDOW, threshold: float = _THRESHOLD):
        self._w = {m: deque(maxlen=window) for m in _METRICS}
        self._pex = deque(maxlen=window)          # |P_ex_ana - P_ex_ml| (absolute)
        self._threshold = threshold
        self._n_total = 0
        self._n_extrapolation = 0
        self._n_offscale = 0
        self._lock = threading.Lock()

    def record(self, analytical: dict, ml: dict | None, *,
               extrapolation: list | None = None, off_scale: bool = False) -> dict:
        """Record one request's analytical-vs-ML disagreement; returns this
        request's per-metric relative disagreement (for the response payload)."""
        this = {}
        with self._lock:
            self._n_total += 1
            if extrapolation:
                self._n_extrapolation += 1
            if off_scale:
                self._n_offscale += 1
            if ml is None:
                return {"ml_available": False}
            for m in _METRICS:
                a = float(analytical[m]["p50"] if isinstance(analytical[m], dict)
                          else analytical[m])
                v = float(ml[m]["p50"] if isinstance(ml[m], dict) else ml[m])
                r = _rel(a, v)
                self._w[m].append(r)
                this[m] = round(r, 4)
            pe = abs(float(analytical.get("excursion_probability", 0.0))
                     - float(ml.get("excursion_probability", 0.0)))
            self._pex.append(pe)
            this["excursion_probability_abs"] = round(pe, 4)
        return this

    def status(self) -> dict:
        with self._lock:
            per_metric = {}
            any_drift = False
            for m in _METRICS:
                w = list(self._w[m])
                n = len(w)
                med = float(median(w)) if w else 0.0
                p90 = float(sorted(w)[int(0.9 * (n - 1))]) if n else 0.0
                drifting = bool(n >= _MIN_SAMPLES and med > self._threshold)
                any_drift = any_drift or drifting
                per_metric[m] = {"n": n, "median_rel": round(med, 4),
                                 "p90_rel": round(p90, 4), "drifting": drifting}
            pex = list(self._pex)
            pex_med = round(float(median(pex)), 4) if pex else 0.0
            return {
                "n_requests": self._n_total,
                "threshold_rel": self._threshold,
                "min_samples": _MIN_SAMPLES,
                "per_metric": per_metric,
                "excursion_probability_median_abs": pex_med,
                "extrapolation_rate": round(self._n_extrapolation / max(self._n_total, 1), 3),
                "off_scale_rate": round(self._n_offscale / max(self._n_total, 1), 3),
                "drifting": any_drift,
            }

    def reset(self) -> None:
        with self._lock:
            for m in _METRICS:
                self._w[m].clear()
            self._pex.clear()
            self._n_total = self._n_extrapolation = self._n_offscale = 0


# process-wide singleton
MONITOR = DriftMonitor()
