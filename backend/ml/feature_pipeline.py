"""Build the training feature matrix from PostgreSQL/PostGIS.

Run:
    cd backend
    python -m ml.feature_pipeline                     # default output path
    python -m ml.feature_pipeline --include-synthetic # include synthetic samples

Outputs:
    backend/ml/artifacts/feature_matrix.csv
    backend/ml/artifacts/feature_metadata.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy import text

from app.database import AsyncSessionLocal
from ml import ARTIFACTS_DIR
from ml.features import FeatureBuilder, feature_schema


# Single SQL pulls every input the FeatureBuilder needs.
# Distance to nearest ISR is computed via PostGIS LATERAL join on geography casts.
RAW_SQL = """
SELECT
    ws.id::text                      AS sample_id,
    ws.well_id::text                 AS well_id,
    ws.sampled_at                    AS sampled_at,
    ws.tds_mg_l                      AS tds_mg_l,
    ws.ec_us_cm                      AS ec_us_cm,
    ws.uranium_ppb                   AS uranium_ppb,
    ws.synthetic                     AS synthetic,

    mw.depth                         AS well_depth,
    mw.latitude                      AS well_lat,
    mw.longitude                     AS well_lon,

    a.type::text                     AS aquifer_type,
    a.porosity                       AS porosity,
    a.hydraulic_conductivity         AS hydraulic_conductivity,
    a.transmissivity                 AS transmissivity,
    a.specific_yield                 AS specific_yield,
    a.storage_coefficient            AS storage_coefficient,
    a.dtw_decadal_avg                AS dtw_decadal_avg,
    a.min_depth                      AS aquifer_min_depth,
    a.max_depth                      AS aquifer_max_depth,

    isr_near.distance_km             AS distance_to_nearest_isr_km,
    isr_near.injection_rate          AS nearest_isr_injection_rate

FROM water_samples ws
JOIN monitoring_wells mw ON mw.id = ws.well_id

LEFT JOIN LATERAL (
    SELECT a.*
    FROM aquifers a
    WHERE a.geometry IS NOT NULL
      AND ST_Intersects(a.geometry, mw.location)
    LIMIT 1
) a ON TRUE

LEFT JOIN LATERAL (
    SELECT
        ip.injection_rate                                        AS injection_rate,
        ST_Distance(mw.location::geography, ip.location::geography) / 1000.0 AS distance_km
    FROM isr_points ip
    WHERE ip.location IS NOT NULL
    ORDER BY mw.location::geography <-> ip.location::geography
    LIMIT 1
) isr_near ON TRUE

WHERE (:include_synthetic OR ws.synthetic = FALSE)
ORDER BY ws.sampled_at;
"""


async def fetch_raw(include_synthetic: bool = True) -> pd.DataFrame:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(RAW_SQL), {"include_synthetic": include_synthetic}
        )
        rows = result.mappings().all()
    df = pd.DataFrame([dict(r) for r in rows])
    logger.info(f"Pulled {len(df)} water samples from DB (include_synthetic={include_synthetic})")
    return df


async def build_feature_matrix(
    output_csv: Optional[Path] = None,
    output_meta: Optional[Path] = None,
    include_synthetic: bool = True,
) -> pd.DataFrame:
    output_csv = output_csv or (ARTIFACTS_DIR / "feature_matrix.csv")
    output_meta = output_meta or (ARTIFACTS_DIR / "feature_metadata.json")

    raw = await fetch_raw(include_synthetic=include_synthetic)
    if raw.empty:
        raise RuntimeError("No water samples found. Run scripts.seed_month3_data first.")

    X, y_reg, y_clf, meta = FeatureBuilder.split_xy(raw)
    if X.empty:
        raise RuntimeError("Feature matrix is empty after target derivation. Check water-sample chemistry coverage.")

    matrix = X.copy()
    matrix["__target_tds__"] = y_reg.values
    matrix["__target_class__"] = y_clf.values
    matrix["__sample_id__"] = meta["sample_id"].values
    matrix["__well_id__"] = meta["well_id"].values
    matrix["__sampled_at__"] = meta["sampled_at"].values
    # tag synthetic rows for downstream filtering
    matrix["__synthetic__"] = raw.set_index("sample_id").reindex(meta["sample_id"]).get(
        "synthetic", pd.Series(False, index=meta.index)
    ).fillna(False).values

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(output_csv, index=False)

    metadata = {
        "row_count": int(len(matrix)),
        "real_count": int((~matrix["__synthetic__"]).sum()),
        "synthetic_count": int(matrix["__synthetic__"].sum()),
        "class_distribution": y_clf.value_counts().to_dict(),
        "tds_summary": {
            "mean": float(y_reg.mean()),
            "std": float(y_reg.std()),
            "min": float(y_reg.min()),
            "max": float(y_reg.max()),
        },
        **feature_schema(),
    }
    output_meta.write_text(json.dumps(metadata, indent=2, default=str))

    logger.info(
        f"Feature matrix written to {output_csv} "
        f"(rows={metadata['row_count']}, real={metadata['real_count']}, synthetic={metadata['synthetic_count']})"
    )
    return matrix


def _cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exclude-synthetic", action="store_true")
    parser.add_argument("--output-csv", type=Path, default=None)
    parser.add_argument("--output-meta", type=Path, default=None)
    args = parser.parse_args()

    asyncio.run(
        build_feature_matrix(
            output_csv=args.output_csv,
            output_meta=args.output_meta,
            include_synthetic=not args.exclude_synthetic,
        )
    )


if __name__ == "__main__":
    _cli()
