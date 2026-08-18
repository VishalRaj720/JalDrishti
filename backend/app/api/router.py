"""API v1 router factory.

Reference geography (districts, blocks, aquifers, monitoring stations) used to be
served here as generic CRUD. Most of it was never reachable from the portal: the
map reads geography from `/ml/*`, which forwards to the pipeline's own loaders, and
the aggregates a user actually sees come from `/public/risk/*`. Serving the same
tables twice, from two code paths with two sets of guards, meant a district could
read one way through the ML engine and another through SQLAlchemy.

R11 deleted the unreachable half rather than leaving it to rot behind a login:
`/aquifers`, `/blocks`, `/districts/{id}/blocks`, `/monitoring-stations` and the
`/blocks/{id}/monitoring-stations` CRUD tree. Bulk changes to reference geography
go through `/ingest/*`, which checksums the source file and writes a
`dataset_versions` row; row-level changes go through `/datasets/*`, which enforces
the `source` column. Both are auditable. Ad-hoc CRUD was neither.
"""
from fastapi import APIRouter
from app.api.v1 import (
    advisories, auth, citizen, audit, lifecycle, preview, dataset_sync, datasets, model_ops,
    field_observations, ml, public_risk, scenarios, users, districts, isr_points,
    simulations, ingest, monitoring_wells, water_samples,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(audit.router)
api_router.include_router(field_observations.router)
api_router.include_router(dataset_sync.router)
api_router.include_router(datasets.router)
api_router.include_router(model_ops.router)
api_router.include_router(scenarios.router)
api_router.include_router(advisories.router)
api_router.include_router(citizen.router)
api_router.include_router(lifecycle.router)
api_router.include_router(preview.router)
api_router.include_router(ml.router)
api_router.include_router(public_risk.router)
api_router.include_router(users.router)
api_router.include_router(districts.router)
api_router.include_router(isr_points.router)
api_router.include_router(simulations.router)
api_router.include_router(ingest.router)
api_router.include_router(monitoring_wells.router)
api_router.include_router(water_samples.router)
