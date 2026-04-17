# Month 3 — Data Foundation & Schema Extension

**Status:** ✅ Complete (all 4 phases)
**Scope:** Data infrastructure + ingestion + schema correctness. **No ML, no simulation, no frontend.**
**Branch / worktree:** `gifted-payne-1c4a22`

---

## 1. What Month 3 Was Meant to Deliver

Per the 8-month roadmap, Month 3 hardens the data layer so later months (ML, simulation, dashboards) have trustworthy inputs:

| Requirement | Delivered |
|---|---|
| District & sub-district boundaries ingested | ✅ 25 districts, 275 blocks |
| Aquifer polygons with hydro-parameters | ✅ 24 aquifers, literature-filled where missing |
| Groundwater-level time-series | ✅ 29 stations, 419 readings |
| Water-quality sampling points | ✅ 397 monitoring wells |
| Water-quality chemistry samples | ✅ 397 samples |
| ≥ 50 wells target | ✅ 397 (8×) |
| ≥ 200 samples target | ✅ 397 (2×) |
| Data-quality report | ✅ `backend/reports/data_quality_report.json` |
| APIs to read / ingest | ✅ 11 new endpoints |
| Redis cache on bbox wells | ✅ 30-min TTL, pattern invalidation |

---

## 2. Six Data Decisions Honored

The six user decisions from the planning step are reflected end-to-end:

| # | Decision | Where it lives |
|---|---|---|
| 1 | District/sub-district GeoJSON used for spatial mapping | `ingest_geojson_districts`, `ingest_geojson_subdistricts`; `_find_block_for_point` (ST_Within → nearest fallback) |
| 2 | TDS = 0.65 × EC with `tds_derived=true` | `ingestion.TDS_FROM_EC_FACTOR`; flag in `water_samples.tds_derived` |
| 3 | Uranium is nullable, no dependent logic | `water_samples.uranium_ppb Optional`; no downstream ML logic keyed on it |
| 4 | Range-strings → midpoint; literature fill with `*_source` tags | `_parse_range_midpoint`, `hydro_literature.LITERATURE_HYDRO_PROPS`, `aquifers.{porosity,hydraulic_conductivity,transmissivity}_source` |
| 5 | Data infrastructure only, no ML | Confirmed: 0 ML code added in Month 3 |
| 6 | Decisions reflected in schema + ingestion + API | All three layers updated consistently |

---

## 3. Phased Implementation

### Phase 1 — Schema + ORM Models
**Migration:** `backend/alembic/versions/0004_month3_schema.py`

New tables:
- `data_sources` — content-addressed provenance (SHA-256 checksum), UNIQUE(name, checksum)
- `monitoring_wells` — water-quality sampling points; POINT/4326 geom with GIST index; UNIQUE(lat, lon)
- `water_samples` — chemistry measurements; FK CASCADE to wells; composite index (well_id, sampled_at)
- `contamination_events` — reserved for Month 6 simulations
- `spatial_analysis_results` — UNIQUE(simulation_id, aquifer_id)
- `piezometric_heads` — reserved for Month 4

New columns on `aquifers`:
- `porosity_source`, `hydraulic_conductivity_source`, `transmissivity_source` — provenance tags: `"original" | "derived" | "literature"`

ORM models under `backend/app/models/`:
- `data_source.py`, `monitoring_well.py`, `water_sample.py`,
- `contamination_event.py`, `spatial_analysis_result.py`, `piezometric_head.py`

### Phase 2 — Ingestion Core
**Service:** `backend/app/services/ingestion.py` (rewritten)
**Helper:** `backend/app/services/hydro_literature.py` (new)

Pure helpers:
- `_safe_float` — tolerant scalar-to-float
- `_parse_range_midpoint` — regex-extracts numbers from `"26 - 176"`, `"2-3%"`, etc.
- `_normalise_aquifer_type` — fuzzy-matches label → one of 12 rock types → fallback `gneiss`
- `_jharkhand_bbox_ok` — sanity check (lon 83.3–87.9, lat 21.9–25.6)
- `_checksum` — SHA-256

Async spatial helpers:
- `_find_block_for_point` — `ST_Within` primary, `ST_Distance` nearest fallback
- `_find_block_for_polygon_wkt` — `ST_Intersects` ranked by `ST_Area(ST_Intersection)`, nearest fallback

Provenance:
- `_register_source` — returns `(uuid, is_new)` → enables idempotent re-runs

Five ingestion methods (all go through `_register_source`):

| Method | Idempotency | Notes |
|---|---|---|
| `ingest_geojson_districts` | Upsert by name | Accepts `District`, `name`, `NAME`, `district` keys |
| `ingest_geojson_subdistricts` | Upsert by (Sub_District, parent District) | |
| `ingest_geojson_aquifers` | Checksum early-exit | Parses ranges, fills porosity/HC from literature |
| `ingest_json_groundwater_levels` | Dedup station by (name,lat,lon); readings by timestamp | |
| `ingest_csv_water_quality` | Checksum early-exit; wells deduped by UNIQUE(lat,lon) | Applies TDS = 0.65 × EC; `sampled_at = Jan 1 of Year` |

Hydro-literature defaults (12 rock types, sourced from Freeze & Cherry 1979 + CGWB Jharkhand):

| Rock type | Porosity | Hydraulic K (m/day) |
|---|---|---|
| alluvium | 0.30 | 5.00 |
| sandstone | 0.20 | 0.50 |
| laterite | 0.20 | 1.20 |
| limestone | 0.15 | 1.00 |
| basalt | 0.08 | 0.30 |
| schist | 0.04 | 0.08 |
| gneiss (fallback) | 0.04 | 0.10 |
| basement_gneissic_complex | 0.04 | 0.08 |
| granite | 0.03 | 0.05 |
| intrusive | 0.03 | 0.05 |
| charnockite | 0.03 | 0.05 |
| quartzite | 0.02 | 0.02 |

### Phase 3 — Seed Script & Data-Quality Report
**Script:** `backend/scripts/seed_month3_data.py`

```bash
cd backend
python -m scripts.seed_month3_data
# or with explicit paths:
python -m scripts.seed_month3_data \
    --datasets-dir ../Datasets \
    --report-path reports/data_quality_report.json
```

Behavior:
- 5 sequential stages in single transaction (rollback on exception)
- Idempotent — safe to re-run (checksum-gated stages early-exit)
- Exit codes: `0` ok · `1` ingest error · `2` missing dataset · `3` target not met

Actual run output (current seed):
```
{
  "row_counts": {
    "districts": 25, "blocks": 275, "aquifers": 24,
    "monitoring_stations": 29, "groundwater_level_readings": 419,
    "monitoring_wells": 397, "water_samples": 397
  },
  "targets": { "wells_met": true, "samples_met": true },
  "tds": { "derived_count": 393, "factor_used": 0.65 },
  "uranium": { "records_with_value": 342, "who_exceedance_count": 0, "who_threshold_ppb": 30 },
  "spatial_checks": { "wells_outside_jharkhand_bbox": 0, "wells_without_block": 0 },
  "aquifer_provenance": {
    "porosity_source": { "literature": 23, "null": 1 },
    "hydraulic_conductivity_source": { "literature": 23, "null": 1 },
    "transmissivity_source": { "derived": 20, "null": 4 }
  }
}
```

Notable data-quality signals:
- **Arsenic & iron null rate = 100 %** — both columns absent from CSV; flagged for Month 4 external sourcing.
- **Uranium exceedances = 0** — no sample crosses WHO 30 ppb in current dataset.
- **TDS derivation rate = 99 %** — nearly all TDS values computed from EC, not measured.
- **Spatial mapping 100 %** — every well placed inside Jharkhand + a block assigned.

### Phase 4 — APIs
**New routers:** `app/api/v1/monitoring_wells.py`, `app/api/v1/water_samples.py`
**Extended:** `app/api/v1/ingest.py` (old broken `ingest_xlsx_aquifers` reference removed)

| Method | Path | Auth | Cache |
|---|---|---|---|
| GET | `/api/v1/monitoring-wells?bbox=minlon,minlat,maxlon,maxlat&limit=1000` | any_role | **Redis 30 min** |
| GET | `/api/v1/monitoring-wells/{id}` | any_role | — |
| POST | `/api/v1/monitoring-wells` | analyst_or_admin | Invalidates bbox cache |
| GET | `/api/v1/water-samples?well_id=&from=&to=&skip=&limit=` | any_role | — |
| POST | `/api/v1/water-samples/bulk` | analyst_or_admin | — |
| POST | `/api/v1/ingest/districts/geojson` | analyst_or_admin | — |
| POST | `/api/v1/ingest/subdistricts/geojson` | analyst_or_admin | — |
| POST | `/api/v1/ingest/aquifers/geojson` | analyst_or_admin | — |
| POST | `/api/v1/ingest/groundwater-levels/json` | analyst_or_admin | — |
| POST | `/api/v1/ingest/water-quality/csv` | analyst_or_admin | — |
| GET | `/api/v1/ingest/data-quality-report` | any_role | — |

**Redis cache design (bbox wells only — per the "Redis ONLY for bbox" rule):**
- Key: `wells:bbox:<min_lon,min_lat,max_lon,max_lat>:<limit>` — coords rounded to 4 dp (~11 m) to prevent key explosion.
- TTL: 1800 s.
- Invalidation: `wells:bbox:*` pattern wipe on `POST /monitoring-wells`.

**Bbox SQL:** `ST_Intersects(location, ST_MakeEnvelope(...))` — hits the GIST index on `monitoring_wells.location`.

**Well creation geometry:** EWKT literal `SRID=4326;POINT(lon lat)` → geoalchemy2 parses directly, no raw SQL needed.

---

## 4. File Inventory

### Created
```
backend/
├── alembic/versions/0004_month3_schema.py
├── app/
│   ├── models/
│   │   ├── data_source.py
│   │   ├── monitoring_well.py
│   │   ├── water_sample.py
│   │   ├── contamination_event.py
│   │   ├── spatial_analysis_result.py
│   │   └── piezometric_head.py
│   ├── repositories/
│   │   ├── data_source.py
│   │   ├── monitoring_well.py
│   │   └── water_sample.py
│   ├── schemas/
│   │   ├── monitoring_well.py
│   │   └── water_sample.py
│   ├── services/
│   │   ├── hydro_literature.py
│   │   ├── monitoring_well.py
│   │   └── water_sample.py
│   └── api/v1/
│       ├── monitoring_wells.py
│       └── water_samples.py
├── scripts/
│   └── seed_month3_data.py
└── reports/
    └── data_quality_report.json  (generated)
```

### Modified
- `backend/app/models/aquifer.py` — added `porosity_source`, `hydraulic_conductivity_source`, `transmissivity_source`
- `backend/app/models/__init__.py` — registered 6 new models
- `backend/app/services/ingestion.py` — full rewrite (5 methods, helpers, idempotency)
- `backend/app/api/v1/ingest.py` — removed broken xlsx ref, added 5 new endpoints
- `backend/app/api/router.py` — registered two new routers

---

## 5. Operational Runbook

### Fresh setup
```bash
cd backend
pip install -r requirements.txt
alembic upgrade head        # should reach 0004_month3_schema
python -m scripts.seed_month3_data
uvicorn app.main:app --reload
```

### Re-seed after dataset change
```bash
python -m scripts.seed_month3_data     # idempotent; checksum-gated early-exit
```

### Smoke-test APIs
```bash
# Get token (seeded analyst)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"analyst@jaldrishti.local","password":"analyst123"}'

# Bbox wells (first = DB hit, second = Redis hit)
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/monitoring-wells?bbox=85,23,86,24"

# Data-quality report
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/ingest/data-quality-report
```

---

## 6. Known Gaps / Carry-overs to Month 4

1. **Arsenic and iron data are absent** (100 % null in sample CSV). Need external source.
2. **Water-quality temporal resolution is year-only** (`sampled_at = Jan 1`). CSV lacks true sample dates.
3. **Uranium coverage is 86 %** (342/397 with values, 0 exceeding WHO).
4. **Aquifer hydro-params are literature-filled for 23/24 rows** — replacement with field-measured values deferred.
5. **Piezometric heads & contamination events tables exist but are unpopulated** — wired for Month 4 / Month 6 use.
6. **No frontend consumption yet** — APIs ready but UI integration is a Month 5+ task.

---

## 7. Design Principles Applied

- **Phased delivery** — each phase committed before the next began; no phase was skipped or combined.
- **No over-engineering** — no caching, no imputation, no ML code added outside the explicit scope.
- **Idempotency via content addressing** — SHA-256 checksums in `data_sources` prevent duplicate loads.
- **Spatial mapping never fails** — point→block uses `ST_Within` primary with `ST_Distance` fallback, so `block_id` is always filled when ≥ 1 block exists.
- **Literature fill is tagged** — any value not from the source dataset is marked in a `*_source` column so downstream models can weight accordingly.
- **Redis used surgically** — applied only where the read pattern is cacheable (bbox reads), not sprayed across all endpoints.

---

*Generated at end of Month 3. Awaiting user confirmation before Step 6 (handover / next-month kickoff).*
