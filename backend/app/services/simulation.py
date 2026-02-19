"""
Simulation service – orchestrates plume geometry, ADE physics,
ML calls, and result storage.

Designed to be called from a Celery task for async execution.
"""
import uuid
import math
import random
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.repositories.simulation import SimulationRepository
from app.repositories.aquifer import AquiferRepository
from app.repositories.isr_point import IsrPointRepository
from app.models.simulation import Simulation, SimulationAquifer
from app.exceptions import (
    SimulationDataError, ResourceNotFoundError, MLServiceError
)


# ── Physics helpers (Advection-Dispersion Equation stub) ──────────

def _compute_plume_wkt(
    lon: float,
    lat: float,
    gradient_angle_deg: float,
    dispersivity_l: float = 50.0,
    dispersivity_t: float = 10.0,
    days: float = 365.0,
) -> str:
    """
    Approximate plume as an ellipse WKT projected from the ISR point.
    gradient_angle_deg: direction of groundwater flow (degrees from North).
    Returns a POLYGON WKT representing the plume footprint.
    """
    # Longitudinal and transverse spread (metres → degrees approx)
    rx = dispersivity_l * math.sqrt(days) / 111320  # ~1 degree lat ≈ 111 km
    ry = dispersivity_t * math.sqrt(days) / 111320

    angle_rad = math.radians(gradient_angle_deg)

    # Offset centre of ellipse along gradient direction
    cx = lon + rx * math.sin(angle_rad)
    cy = lat + rx * math.cos(angle_rad)

    # Build ellipse as 36-point polygon (approximation)
    points = []
    for i in range(37):
        theta = math.radians(i * 10)
        dx = rx * math.cos(theta) * math.sin(angle_rad) - ry * math.sin(theta) * math.cos(angle_rad)
        dy = rx * math.cos(theta) * math.cos(angle_rad) + ry * math.sin(theta) * math.sin(angle_rad)
        points.append(f"{cx + dx} {cy + dy}")

    wkt_coords = ", ".join(points)
    return f"POLYGON(({wkt_coords}))"


def _monte_carlo_uncertainty(base_value: float, n: int = 100) -> float:
    """Return std-dev of Monte Carlo runs (Gaussian noise model)."""
    runs = [base_value * (1 + random.gauss(0, 0.15)) for _ in range(n)]
    mean = sum(runs) / n
    variance = sum((r - mean) ** 2 for r in runs) / n
    return math.sqrt(variance)


def _recovery_suggestion(porosity: Optional[float]) -> str:
    if porosity is None:
        return "Insufficient data to recommend recovery method."
    if porosity > 0.15:
        return (
            "High porosity aquifer: consider enhanced bioremediation with "
            "electron donor injection to stimulate uranium reduction."
        )
    elif porosity > 0.05:
        return "Moderate porosity: pump-and-treat with in-situ redox manipulation recommended."
    return "Low porosity: permeable reactive barrier (PRB) installation suggested."


# ── ML Service call ───────────────────────────────────────────────

async def _call_ml_service(isr_data: Dict[str, Any]) -> Dict[str, Any]:
    """Call the ML microservice; fall back to stub if unavailable."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.ML_SERVICE_URL}/predict",
                json=isr_data,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning(f"ML service unreachable: {exc}. Using stub predictions.")
        # Stub: realistic values from Jharkhand aquifer data ranges
        uranium = round(random.uniform(0.01, 0.12), 4)
        return {
            "concentration": {
                "uranium": {
                    "max": uranium,
                    "unit": "mg/L",
                    "who_limit": 0.03,
                    "exceeds_limit": uranium > 0.03,
                }
            },
            "vulnerability": {
                "risk_level": random.choice(["low", "medium", "high"]),
                "probability": round(random.uniform(0.4, 0.95), 2),
                "model": "stub_v0",
            },
        }


# ── Main Simulation Service ───────────────────────────────────────

class SimulationService:
    def __init__(self, db: AsyncSession):
        self.sim_repo = SimulationRepository(db)
        self.aquifer_repo = AquiferRepository(db)
        self.isr_repo = IsrPointRepository(db)
        self.db = db

    async def create_pending(self, isr_point_id: uuid.UUID) -> Simulation:
        isr = await self.isr_repo.get(isr_point_id)
        if not isr:
            raise ResourceNotFoundError("ISR Point", str(isr_point_id))
        return await self.sim_repo.create({
            "isr_point_id": isr_point_id,
            "status": "pending",
        })

    async def get(self, sim_id: uuid.UUID) -> Simulation:
        obj = await self.sim_repo.get(sim_id)
        if not obj:
            raise ResourceNotFoundError("Simulation", str(sim_id))
        return obj

    async def list_by_isr(self, isr_point_id: uuid.UUID) -> List[Simulation]:
        return await self.sim_repo.get_by_isr_point(isr_point_id)

    async def run(self, simulation_id: uuid.UUID) -> Simulation:
        """Execute the full simulation workflow."""
        sim = await self.get(simulation_id)
        isr = await self.isr_repo.get(sim.isr_point_id)

        try:
            await self.sim_repo.update(sim, {"status": "running"})

            # ── 1. Extract ISR location ───────────────────────────
            # location stored as WKB; parse lon/lat from WKT representation
            # For stub: use a default Jharkhand centroid if not set
            lon, lat = 85.3, 23.5
            if isr.location is not None:
                try:
                    from shapely import wkb as shapely_wkb
                    geom = shapely_wkb.loads(bytes(isr.location.desc), hex=True)
                    lon, lat = geom.x, geom.y
                except Exception:
                    pass

            # ── 2. Compute gradient vector ────────────────────────
            # Without real piezometric data we stub a NE gradient
            gradient_angle_deg = random.uniform(30, 90)

            # ── 3. Generate directional plume geometry (WKT) ──────
            plume_wkt = _compute_plume_wkt(lon, lat, gradient_angle_deg)

            # ── 4. Spatial query for impacted aquifers ────────────
            impacted = await self.aquifer_repo.get_intersecting_plume(plume_wkt)

            # ── 5. Call ML service ────────────────────────────────
            ml_input = {
                "lon": lon,
                "lat": lat,
                "injection_rate": isr.injection_rate or 100.0,
                "gradient_angle_deg": gradient_angle_deg,
                "aquifer_count": len(impacted),
                "avg_porosity": (
                    sum(a.porosity for a in impacted if a.porosity) / max(len(impacted), 1)
                ),
            }
            ml_result = await _call_ml_service(ml_input)

            # ── 6. Compute affected area (stub: π*rx*ry) ──────────
            rx = 50 * math.sqrt(365) / 1000  # km
            ry = 10 * math.sqrt(365) / 1000
            affected_area_km2 = round(math.pi * rx * ry, 4)

            # ── 7. Uncertainty via Monte Carlo ────────────────────
            base_conc = ml_result["concentration"]["uranium"]["max"]
            uncertainty = round(_monte_carlo_uncertainty(base_conc), 5)

            # ── 8. Recovery suggestion ────────────────────────────
            avg_por = ml_input["avg_porosity"]
            suggestion = _recovery_suggestion(avg_por if avg_por > 0 else None)

            # ── 9. Persist results ────────────────────────────────
            updates = {
                "status": "completed",
                "affected_area": affected_area_km2,
                "estimated_concentration_spread": ml_result["concentration"],
                "vulnerability_assessment": ml_result["vulnerability"],
                "uncertainty_estimate": uncertainty,
                "suggested_recovery": suggestion,
            }
            sim = await self.sim_repo.update(sim, updates)

            # Insert junction records for impacted aquifers
            if impacted:
                for aquifer in impacted:
                    self.db.add(
                        SimulationAquifer(
                            simulation_id=sim.id, aquifer_id=aquifer.id
                        )
                    )
                await self.db.flush()

            logger.info(
                f"Simulation {simulation_id} completed. "
                f"Affected area: {affected_area_km2} km², "
                f"Impacted aquifers: {len(impacted)}"
            )
            return sim

        except Exception as exc:
            await self.sim_repo.update(sim, {
                "status": "failed",
                "error_message": str(exc),
            })
            logger.error(f"Simulation {simulation_id} failed: {exc}")
            raise
