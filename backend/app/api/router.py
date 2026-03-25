"""API v1 router factory."""
from fastapi import APIRouter
from app.api.v1 import auth, users, districts, blocks, global_blocks, aquifers, isr_points, simulations, ingest, monitoring_stations, global_monitoring

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(districts.router)
api_router.include_router(blocks.router)
api_router.include_router(global_blocks.router)
api_router.include_router(aquifers.router)
api_router.include_router(isr_points.router)
api_router.include_router(simulations.router)
api_router.include_router(ingest.router)
api_router.include_router(monitoring_stations.router)
api_router.include_router(global_monitoring.router)
