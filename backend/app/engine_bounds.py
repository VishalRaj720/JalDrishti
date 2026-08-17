"""Parameter bounds and defaults, read from `ml_pipeline` rather than retyped.

Every range an ISR point or a Studio slider accepts belongs to the engine, not
to the portal. Copying them by hand creates two sources of truth that agree
until the day they do not: widen `restoration_years` in
`ml_pipeline/config/parameters.py` and a hand-typed `le=10` here starts
rejecting values the engine serves happily. Narrow one, and the portal starts
accepting values the engine will refuse — turning a form-validation message into
a 422 from a service the user never heard of.

So this module imports the engine's own constants once and exposes them as a
frozen record. It is also the single place that knows the two shapes the engine
uses which the portal does not: `bleed_fraction` is a FRACTION in the config and
a PERCENT everywhere a human sees it, and several sliders have a UI exploration
bound deliberately wider than the trained envelope.

If the import fails the portal must not silently fall back to invented numbers —
a bound nobody can trace is worse than a crash at startup, because it will be
enforced against real input and blamed on the engine.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _parameters():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from ml_pipeline.config import parameters as P  # noqa: PLC0415
    return P


@dataclass(frozen=True)
class EngineBounds:
    injection_rate_min: float
    injection_rate_max: float
    injection_rate_default: float

    #: PERCENT, not the config's fraction. The engine's own request model does
    #: the same ×100, and every label a user reads says "%".
    bleed_min: float
    bleed_max: float
    bleed_default: float

    operation_years_min: float
    operation_years_max: float
    operation_years_default: float

    #: `restoration_ui_max` is deliberately wider than `restoration_trained_max`.
    #: The analytical engine serves any sweep length correctly; beyond the
    #: trained max the ML band is FLAGGED as extrapolating, not refused. The UI
    #: must offer the wider range and surface the flag — clamping to the trained
    #: max would hide a limitation instead of reporting it.
    restoration_min: float
    restoration_trained_max: float
    restoration_ui_max: float

    #: Same pattern: the evaluation horizon explores past the trained maximum.
    horizon_min: float
    horizon_trained_max: float
    horizon_ui_max: float

    wellfield_width_min: float
    wellfield_width_max: float
    wellfield_width_default: float

    monitor_ring_min: float
    monitor_ring_max: float
    monitor_ring_default: float
    monitor_ring_justify_beyond: float

    ore_depth_min: float
    ore_depth_max: float
    ore_depth_default: float

    ore_thickness_min: float
    ore_thickness_max: float
    ore_thickness_default: float

    gradient_min: float
    gradient_max: float


def _build() -> EngineBounds:
    P = _parameters()
    o = P.OPERATIONAL_RANGES
    v = P.VERTICAL
    return EngineBounds(
        injection_rate_min=o["injection_rate_m3_day"][0],
        injection_rate_max=o["injection_rate_m3_day"][1],
        injection_rate_default=2500.0,

        bleed_min=o["bleed_fraction"][0] * 100,
        bleed_max=o["bleed_fraction"][1] * 100,
        bleed_default=2.0,

        operation_years_min=o["operation_years"][0],
        operation_years_max=o["operation_years"][1],
        operation_years_default=8.0,

        restoration_min=o["restoration_years"][0],
        restoration_trained_max=o["restoration_years"][1],
        restoration_ui_max=P.RESTORATION_SLIDER_MAX_YEARS,

        horizon_min=o["horizon_years"][0],
        horizon_trained_max=o["horizon_years"][1],
        horizon_ui_max=P.HORIZON_SLIDER_MAX_YEARS,

        wellfield_width_min=o["wellfield_width_m"][0],
        wellfield_width_max=o["wellfield_width_m"][1],
        wellfield_width_default=300.0,

        monitor_ring_min=P.MONITOR_RING_RANGE_M[0],
        monitor_ring_max=P.MONITOR_RING_RANGE_M[1],
        monitor_ring_default=P.COMPLIANCE_BUFFER_M,
        monitor_ring_justify_beyond=P.MONITOR_RING_JUSTIFY_BEYOND_M,

        ore_depth_min=v["ore_depth_range_m"][0],
        ore_depth_max=v["ore_depth_range_m"][1],
        ore_depth_default=v["ore_depth_default_m"],

        ore_thickness_min=v["ore_thickness_range_m"][0],
        ore_thickness_max=v["ore_thickness_range_m"][1],
        ore_thickness_default=v["ore_thickness_default_m"],

        gradient_min=o["hydraulic_gradient"][0],
        gradient_max=o["hydraulic_gradient"][1],
    )


#: Built at import. A failure here should stop the app rather than be caught:
#: serving invented bounds would enforce limits nobody can trace to a source.
BOUNDS = _build()


def as_dict() -> dict[str, float]:
    """Flat mapping, for the client so the forms and sliders use these too."""
    return {k: getattr(BOUNDS, k) for k in BOUNDS.__dataclass_fields__}
