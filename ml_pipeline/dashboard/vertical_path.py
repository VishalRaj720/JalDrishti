"""
ml_pipeline.dashboard.vertical_path  --  what the vertical screening is fed
===========================================================================
2026-09-25 (P.VERTICAL_PATH). The shallow-impact screening used to be called
with ONE set of inputs for every species: the ore-depth K and no matrix
storage. So the upward pathway moved water, not solute, and uranium "reached"
the drinking-water aquifer as fast as TDS -- while the horizontal front in the
same response retarded uranium ~270x through the same rock.

This module resolves, for any species, the three things that were missing:

  * `layer2_retention`   the confining rock's sorbing dual-porosity capacity for
                         that species, by the same laws and from the same tables
                         as the horizontal front (so the two directions cannot
                         disagree about one rock);
  * `path_conductivity`  the series (harmonic-mean) K of the column the solute
                         actually climbs, from the NAQUIM K(z) law;
  * `indicator_arrivals` the same screening for the lixiviant indicators NUREG
                         asks licensees to monitor, so a uranium run still says
                         when the injected salts -- which arrive first -- would
                         reach the shallow aquifer.

Every call site builds its screening arguments through `screening_geometry`,
one function, so the run's species and each indicator cannot be screened
against different geometry. Mirrored call sites drifting apart is this
project's most repeated defect.
"""
from __future__ import annotations

import numpy as np

from ml_pipeline.config import parameters as P


def layer2_retention(inputs: dict, payload: dict | None = None) -> dict:
    """Sorbing capacity ratio and transfer rate of the CONFINING rock (Layer 2)
    for `inputs["species"]`.

    Layer 2 is fractured bedrock in both regime interpretations (that is why
    `phi_confining` is fixed at the fractured value), so:
      * fractured pin -- same lithology as the ore rock: the run's own total
        porosity, grain density and species Kd;
      * porous pin    -- the ore aquifer is weathered/sedimentary but the rock
        below the saprolite is not: the fractured REGIME_ARCHETYPE materials and
        the fractured Kd for the species.
    beta = theta_immobile/theta_mobile from THIS layer's porosities (the R17
    rule: beta and the mobile porosity the transport runs on may not disagree).
    A user beta override is honoured on a fractured pin, where it demonstrably
    refers to fractured rock; on a porous pin it has no fractured-rock meaning.
    """
    from ml_pipeline.physics.transport import (effective_capacity_ratio,
                                               matrix_transfer_omega)
    payload = payload or {}
    species = inputs["species"]
    phi = float(P.VERTICAL["phi_confining"])
    fractured_pin = inputs.get("regime") == "fractured"
    if fractured_pin:
        n_total = float(inputs["n_total"])
        rho = float(inputs["grain_density"])
        kd = float(inputs["kd_L_kg"])
        materials = "run's own rock (fractured pin)"
    else:
        arch = P.REGIME_ARCHETYPE["fractured"]
        n_total, rho = float(arch["n_total"]), float(arch["grain_density"])
        kd = float(P.kd_range_for(species, "fractured")[1])
        materials = "fractured-bedrock archetype (porous pin)"

    if not P.VERTICAL_PATH.get("matrix_retention", True):
        return {"beta": 0.0, "beta_eff": 0.0,
                "omega": float(P.DUAL_POROSITY["mass_transfer_omega"]),
                "retardation_asymptotic": 1.0, "basis": "disabled",
                "materials": materials, "phi_mobile": phi, "n_total": n_total,
                "grain_density": rho, "Kd_L_kg": kd}

    if fractured_pin and payload.get("beta") is not None:
        beta, basis = float(payload["beta"]), "user_override"
    else:
        beta, basis = P.beta_from_porosities(n_total, phi), "porosity_derived"
    beta_eff = effective_capacity_ratio(beta, n_total, rho, kd)
    omega = matrix_transfer_omega(phi, n_total, rho, kd)
    return {"beta": round(beta, 3), "beta_eff": float(beta_eff),
            "omega": float(omega),
            "retardation_asymptotic": round(1.0 + beta_eff, 1),
            "basis": basis, "materials": materials,
            "phi_mobile": phi, "n_total": n_total, "grain_density": rho,
            "Kd_L_kg": kd}


def path_conductivity(inputs: dict, hydro: dict, *, ore_depth_m: float,
                      ore_thickness_m: float, layer1_base_m: float) -> dict:
    """Horizontal K of the confining column, for Kv = K * Kv/Kh.

    Uses the pin's reference (shallow, tested) K and fracture base -- the same
    two numbers `resolve` decays to ore depth -- so the path and the ore zone
    rest on one K(z) law. Falls back to the served K, flagged, when there is no
    profile to integrate: a user K override is a statement about the ORE zone
    and is used uniformly, and a disabled K(z) law has nothing to integrate.
    """
    from ml_pipeline.physics.transport import confining_path_conductivity
    k_served = float(inputs["K_m_day"])
    kd = hydro.get("k_depth")
    ore_top = float(ore_depth_m) - float(ore_thickness_m) / 2.0
    if not P.VERTICAL_PATH.get("depth_resolved_K", True):
        return {"K_path_m_day": k_served, "basis": "ore_depth_K (depth_resolved_K off)"}
    if not kd:
        return {"K_path_m_day": k_served,
                "basis": ("served K used uniformly -- no K(z) profile "
                          "(user K override or depth decay disabled)")}
    k_path = confining_path_conductivity(
        float(kd["K_shallow_m_day"]), float(layer1_base_m), ore_top,
        fracture_base_m=float(kd["fracture_base_m"]))
    return {"K_path_m_day": round(float(k_path), 4),
            "K_ore_depth_m_day": round(k_served, 4),
            "K_reference_m_day": round(float(kd["K_shallow_m_day"]), 4),
            "path_top_m": round(float(layer1_base_m), 1),
            "path_bottom_m": round(ore_top, 1),
            "basis": "harmonic mean of K(z) over the column (series flow)"}


def screening_geometry(*, req, inputs: dict, hydro: dict, vparams: dict,
                       flow: dict, timeline: dict | None) -> dict:
    """The species-independent arguments to `shallow_impact_screening`.

    One builder for the run's species AND every indicator: they climb the same
    column under the same gradient, and only the solute differs.
    """
    regime = inputs["regime"]
    path = path_conductivity(inputs, hydro, ore_depth_m=req.ore_depth_m,
                             ore_thickness_m=req.ore_thickness_m,
                             layer1_base_m=vparams["layer1_base_m"])
    wet_default = P.VERTICAL_SEASONAL["water_table_wet_m"]
    dry_default = P.VERTICAL_SEASONAL["water_table_dry_m"]
    kwargs = dict(
        ore_depth_m=req.ore_depth_m, ore_thickness_m=req.ore_thickness_m,
        layer1_base_m=vparams["layer1_base_m"], K_m_day=path["K_path_m_day"],
        # confining Layer-2 porosity is FIXED (fractured bedrock, not the ore
        # regime); the regime enters through vertical anisotropy Kv/Kh instead.
        phi_confining=P.VERTICAL["phi_confining"],
        Kv_Kh_ratio=P.VERTICAL["Kv_Kh_by_regime"].get(regime, 0.01),
        Kv_Kh_band=P.VERTICAL["Kv_Kh_band_by_regime"].get(regime),
        upward_gradient=P.VERTICAL["upward_gradient"],
        t_days=req.time_years * 365.0,
        wellbore_failure_prob=P.VERTICAL["wellbore_failure_prob"],
        # D1: real post-monsoon (shallowest) water table as receptor context
        water_table_m=flow.get("depth_to_water_shallow_m"),
        # 3.7: the wet/dry pair drives the seasonal vertical band. Both must be
        # present for a per-pin band; otherwise the screening falls back to the
        # state-wide CGWB campaign medians (flagged in `seasonal.water_table_source`).
        water_table_wet_m=flow.get("depth_to_water_shallow_m"),
        water_table_dry_m=flow.get("depth_to_water_deep_m"),
        # TIMELINE: this month's interpolated table (None unless a start date was
        # given). Amplitude is the pin's own wet/dry pair; only the monsoon
        # TIMING is state-wide -- see P.water_table_shape for why.
        water_table_now_m=(
            P.water_table_at_month(
                timeline["month"],
                flow.get("depth_to_water_shallow_m", wet_default) or wet_default,
                flow.get("depth_to_water_deep_m", dry_default) or dry_default)
            if timeline else None))
    return {"kwargs": kwargs, "path": path}


def _species_front(payload: dict, species: str) -> tuple[dict, float, float]:
    """(resolved inputs, horizontal front Xc, alpha_L) for `species` at the same
    pin and operation -- the resolve -> features -> params path the served
    analytical answer and the excursion panel both use."""
    from ml_pipeline.dashboard.resolve import resolve_inputs
    from ml_pipeline.ml.predict import features_from_inputs
    from ml_pipeline.physics.transport import params_from_features
    sp_payload = dict(payload)
    sp_payload["species"] = species
    inputs, _hydro = resolve_inputs(sp_payload)
    _X, feat, _Xc = features_from_inputs(**inputs)
    params = params_from_features(
        feat, species_C0=inputs["source_conc_C0"],
        t_days=inputs["time_years"] * 365.0,
        operation_days=inputs["operation_years"] * 365.0,
        restoration_days=float(inputs.get("restoration_years", 0.0) or 0.0) * 365.0,
        residual_fraction=feat.get("_residual_endpoint", 1.0),
        background=float(inputs["background_conc_Cb"]),
        floor_source_at_background=True)
    alpha_L = P.longitudinal_dispersivity(
        max(params.Xc, inputs["wellfield_width_m"], 1.0))
    return inputs, float(params.Xc), float(alpha_L)


def screen_species(payload: dict, species: str, geometry: dict,
                   *, inputs: dict | None = None, Xc_m: float | None = None,
                   alpha_L: float | None = None) -> dict:
    """Full vertical screening for one species on the shared geometry.

    The run's own species passes its already-resolved inputs and front (no
    second resolve); indicators are resolved here. A species with no
    drinking-water limit in this model (chloride) is screened for its ARRIVAL
    only: the threshold is set to infinity, which zeroes every concentration-
    gated term (no index is invented) while leaving the kinematics -- which do
    not depend on the limit -- exact.
    """
    from ml_pipeline.physics.transport import shallow_impact_screening
    if inputs is None or Xc_m is None or alpha_L is None:
        inputs, Xc_m, alpha_L = _species_front(payload, species)
    limit = P.EXCURSION_THRESHOLDS.get(species)
    ret = layer2_retention(inputs, payload)
    C0 = float(inputs["source_conc_C0"])
    Cb = float(inputs["background_conc_Cb"])
    v = shallow_impact_screening(
        C0=C0, background=Cb,
        threshold=(float("inf") if limit is None else limit),
        Xc_m=Xc_m, source_width_m=inputs["wellfield_width_m"], alpha_L=alpha_L,
        alpha_V=alpha_L * P.VERTICAL["alpha_V_ratio"],
        layer2_beta_eff=ret["beta_eff"], layer2_omega=ret["omega"],
        **geometry["kwargs"])
    out = {"species": species, "retention": ret, "screening": v,
           "years_to_breakthrough": v["years_to_vertical_breakthrough"],
           "water_arrival_years": v["water_arrival_years"],
           "layer2_retardation": v["layer2_retardation"],
           "health_limit": limit,
           "source_conc": round(C0, 3), "background": round(Cb, 3)}
    if limit is None:
        out.update({"source_exceeds_limit": None,
                    "shallow_impact_probability": None, "risk_band": None,
                    "note": ("no drinking-water limit is modelled for this "
                             "species; its arrival is reported because it is "
                             "what an overlying monitor well would detect")})
    else:
        thr_inc = max(limit - Cb, P.INCREMENTAL_FLOOR * limit)
        out.update({"source_exceeds_limit": bool(C0 >= thr_inc),
                    "shallow_impact_probability": v["shallow_impact_probability"],
                    "risk_band": v["risk_band"]})
    return out


def front_series(run: dict, indicators: list[dict], *, n: int = 101,
                 horizon_years: float | None = None) -> dict | None:
    """Height of each front above the ore top, year by year -- for animating the
    climb in the 3-D block.

    Uses the SAME kinematics as the headline arrival times (`retarded_clock` at
    the headline pore-water velocity, each species with its own confining-rock
    retention), so an animation built on it arrives exactly when the numbers say
    it does. `water` is beta = 0: the pore water itself. Heights are capped at
    the separation (the front has entered the shallow aquifer).
    """
    from ml_pipeline.physics.transport import retarded_clock
    v = run["screening"]
    v_up = float(v.get("headline_v_up_m_day") or 0.0)
    dz = float(v["separation_m"])
    if v_up <= 0.0 or dz <= 0.0:
        return None
    H = float(horizon_years or P.HORIZON_SLIDER_MAX_YEARS)
    years = np.linspace(0.0, H, n)

    def climb(beta_eff: float, omega: float) -> list[float]:
        return [round(min(v_up * retarded_clock(y * 365.0, beta_eff, omega), dz), 2)
                for y in years]

    fronts = {"water": climb(0.0, P.DUAL_POROSITY["mass_transfer_omega"]),
              run["species"]: climb(run["retention"]["beta_eff"], run["retention"]["omega"])}
    for r in indicators:
        if "status" not in r:
            fronts[r["species"]] = climb(r["retention"]["beta_eff"], r["retention"]["omega"])
    return {"years": [round(float(y), 3) for y in years], "separation_m": dz,
            "v_up_m_day": v_up, "fronts_m_above_ore_top": fronts,
            "basis": ("headline gradient (duty cycle where present); same "
                      "retarded clock as the arrival times")}


def indicator_arrivals(payload: dict, geometry: dict, *, run: dict) -> dict:
    """Vertical arrival of each lixiviant indicator, and the FIRST arrival.

    `run` is `screen_species` for the run's own species.

    WHY THIS IS NOT OPTIONAL. Once the upward pathway retards solute, a uranium
    run's breakthrough moves out by the uranium retardation (centuries at
    Jaduguda). Every downstream consumer keyed on that number -- the
    aquifer-reach and breach-due alerts -- would then go quiet for a uranium
    advisory, while the injected salts from the same wellfield reach the same
    aquifer within years. That is the uranium-only failure R14 removed from the
    citizen map, reappearing one layer down.

    `first_arrival` is the earliest constituent whose SOURCE exceeds its
    drinking-water limit, among the run's species and the indicators, so an
    alert keyed on it cannot be silenced by the choice of display species.
    `first_detectable` is the earliest indicator arrival of any kind -- when an
    overlying monitor well (NUREG/CR-6733 densities, `monitoring` above) would
    first see the excursion, which is earlier than or equal to any breach.
    """
    indicators = []
    for sp in P.VERTICAL_PATH["indicator_species"]:
        if sp == run["species"]:
            continue
        try:
            r = screen_species(payload, sp, geometry)
        except Exception as e:                       # never break the main answer
            indicators.append({"species": sp, "status": f"unavailable: {e}"})
            continue
        indicators.append(r)
    # the climb, from the full retention of every species, BEFORE it is trimmed
    series = front_series(run, indicators)
    for r in indicators:
        if "status" in r:
            continue
        r.pop("screening", None)
        r["retention"] = {k: r["retention"][k] for k in
                          ("beta", "retardation_asymptotic", "basis", "Kd_L_kg")}

    def _entry(r: dict) -> dict:
        return {"species": r["species"], "years": r["years_to_breakthrough"],
                "shallow_impact_probability": r["shallow_impact_probability"],
                "risk_band": r["risk_band"]}

    pool = [run] + [r for r in indicators if "status" not in r]
    breaching = [r for r in pool if r.get("source_exceeds_limit")
                 and r.get("years_to_breakthrough") is not None]
    first = min(breaching, key=lambda r: r["years_to_breakthrough"]) if breaching else None
    detect = [r for r in indicators if "status" not in r
              and r.get("years_to_breakthrough") is not None]
    earliest = (min(detect, key=lambda r: r["years_to_breakthrough"])
                if detect else None)
    return {
        "indicators": indicators,
        "front_series": series,
        "first_arrival": (None if first is None else {
            **_entry(first),
            "basis": ("earliest arrival among the run's species and the "
                      "lixiviant indicators whose source exceeds its "
                      "drinking-water limit")}),
        "first_detectable": (None if earliest is None else {
            "species": earliest["species"],
            "years": earliest["years_to_breakthrough"],
            "basis": ("earliest lixiviant-indicator arrival at the shallow "
                      "aquifer base -- when an overlying monitor well would "
                      "detect a vertical excursion")}),
    }
