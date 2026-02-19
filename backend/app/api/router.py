"""API v1 router factory."""
from fastapi import APIRouter
from app.api.v1 import auth, users, districts, blocks, aquifers, isr_points, simulations, ingest

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(districts.router)
api_router.include_router(blocks.router)
api_router.include_router(aquifers.router)
api_router.include_router(isr_points.router)
api_router.include_router(simulations.router)
api_router.include_router(ingest.router)
