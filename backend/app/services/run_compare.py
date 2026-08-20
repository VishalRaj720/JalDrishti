"""Diff two stored runs, and say **why** they differ.

Two runs can disagree for two very different reasons: the inputs changed, or the
model did. Reporting a delta without attributing it leaves a reviewer unable to
act on it — a 12 % rise in affected area means something quite different if the
site parameters moved than if the artifact bundle did.

WHY THIS IS A SERVICE. The logic lived inside `POST /scenarios/{id}/compare`,
which made it reachable only for runs belonging to a scenario. Runs saved from
the Console carry `scenario_id = NULL`, so comparing two registered ISR sites —
the thing an analyst actually wants — had no route at all, and the scenario route
would have needed a scenario id that does not exist. One implementation, two
routes: `/simulations/compare` for arbitrary runs, `/scenarios/{id}/compare`
kept for the scenario workflow.

COMPARING TWO SITES IS COMPARING TWO OPERATIONS. A registered site *is* the
operation (`RUN_VARIABLE`: only species, time_years and restoration_years vary
per run), so a cross-site diff will always show input differences. That is the
point — it says which parameters differ and what each one did to the outcome.
"""
from __future__ import annotations

from typing import Any


def _flat(m: dict[str, Any] | None) -> dict[str, float]:
    """`{engine: {metric: value}}` -> `{"engine.metric": value}`.

    Flattened rather than compared nested so a metric present under one engine
    and absent under the other is visible as a row rather than lost in a diff of
    two dicts.
    """
    out: dict[str, float] = {}
    for engine, block in (m or {}).items():
        if isinstance(block, dict):
            for k, v in block.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    out[f"{engine}.{k}"] = v
    return out


def diff(a, b) -> dict[str, Any]:
    """Attribute the difference between two completed runs.

    Callers are responsible for having checked both runs are `completed`; an
    incomplete run has no metrics to compare and the caller can give a better
    error than this function can.
    """
    input_keys = set(a.request or {}) | set(b.request or {})
    input_delta = {
        k: {"a": (a.request or {}).get(k), "b": (b.request or {}).get(k)}
        for k in sorted(input_keys)
        if (a.request or {}).get(k) != (b.request or {}).get(k)
    }
    same_model = (a.artifacts_sha == b.artifacts_sha
                  and a.model_card_sha == b.model_card_sha)
    # Code version is part of "did the model change", and was missing from the
    # original check. Two runs can share an artifact bundle and still have been
    # computed by different physics: the analytical engine is CODE, not a
    # pickled model, so a change to transport.py moves every analytical number
    # while artifacts_sha stays identical. Reporting "same model" there would
    # attribute a code-driven delta to the inputs, which is the one thing this
    # function exists to prevent. Observed on real runs: two runs with identical
    # artifacts_sha and model_card_sha, code_version 9d7b60e7 vs 9b881655.
    same_code = a.code_version == b.code_version
    same_engine = same_model and same_code
    same_site = a.isr_point_id == b.isr_point_id

    what_changed = (
        "the MODEL ARTIFACTS changed" if not same_model and same_code else
        "the ENGINE CODE changed" if same_model and not same_code else
        "both the model artifacts and the engine code changed")

    if input_delta and same_engine:
        cause = "inputs differ; same model and code"
    elif not input_delta and not same_engine:
        cause = f"same inputs; {what_changed} between these runs"
    elif input_delta and not same_engine:
        cause = (f"both inputs and the engine differ ({what_changed}) — the "
                 f"metric delta cannot be attributed to either without "
                 f"re-running one of them")
    else:
        cause = "identical inputs, model and code"

    if not same_site:
        # Said explicitly, because the cause line above reads as a warning when
        # comparing one site across time and as a plain fact when comparing two
        # sites. Different operations SHOULD have different inputs.
        cause = (f"two different sites — {cause}. Site parameters are fixed at "
                 f"registration, so these are two distinct hypothetical "
                 f"operations rather than one operation re-run.")

    fa, fb = _flat(a.metrics), _flat(b.metrics)
    metric_delta: dict[str, Any] = {}
    for k in sorted(set(fa) | set(fb)):
        va, vb = fa.get(k), fb.get(k)
        if va is None or vb is None:
            metric_delta[k] = {"a": va, "b": vb, "change_pct": None}
        elif va != vb:
            metric_delta[k] = {
                "a": va, "b": vb,
                # A change from zero has no meaningful percentage — a plume that
                # did not exist and now does is not "infinitely larger".
                "change_pct": (round((vb - va) / va * 100, 2) if va else None),
            }

    return {
        "run_a": str(a.id), "run_b": str(b.id),
        "isr_point_a": str(a.isr_point_id), "isr_point_b": str(b.isr_point_id),
        "same_site": same_site,
        "species": {"a": a.species, "b": b.species},
        "cause": cause,
        "same_model": same_model,
        "same_code": same_code,
        "same_engine": same_engine,
        "model": {
            "a": {"artifacts_sha": a.artifacts_sha, "code_version": a.code_version,
                  "model_card_sha": a.model_card_sha},
            "b": {"artifacts_sha": b.artifacts_sha, "code_version": b.code_version,
                  "model_card_sha": b.model_card_sha},
        },
        "input_delta": input_delta,
        "metric_delta": metric_delta,
        "extrapolation": {"a": a.extrapolation, "b": b.extrapolation},
        "note": (
            "Both runs are hypothetical. No ISR uranium mine operates in "
            "Jharkhand, so this compares two modelled scenarios, not two "
            "operations that exist."),
    }
