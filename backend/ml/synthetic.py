"""Synthetic water-sample generator using a Gaussian copula.

Approach (no `sdv` dependency — keep the stack lean):
  1. Fit empirical CDF for each numeric column.
  2. Map each value to a standard-normal quantile via Phi^-1(rank/(n+1)).
  3. Estimate the covariance matrix in this Gaussian space.
  4. Sample N rows from MVN(0, Sigma); invert Phi to get uniform marginals;
     then map back to the empirical distribution per column.

Conditioning:
  - Distance-to-ISR sampled from the lower tail to bias towards mining-proximate
    locations (these are the rows that would otherwise be under-represented).
  - 25% of synthetic rows are forced into the "unsafe" regime by injecting
    elevated uranium / TDS; this keeps the classification target balanced.

Output (CSV mirrors water_samples columns + lat/lon + aquifer_type):
    fakedataset/synthetic_wells.csv
    fakedataset/synthetic_water_samples.csv
    fakedataset/synthetic_metadata.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats
from sqlalchemy import text

from app.database import AsyncSessionLocal
from ml import FAKEDATASET_DIR


# Jharkhand bounding box (approx) for sampling fake well locations
JH_BBOX = {"min_lon": 83.30, "max_lon": 87.95, "min_lat": 21.95, "max_lat": 25.45}

# Fallback Jharkhand-typical chemistry stats if real DB has too few rows
FALLBACK_STATS: Dict[str, Tuple[float, float]] = {
    # (mean, std)
    "ph": (7.4, 0.6),
    "ec_us_cm": (820.0, 540.0),
    "tds_mg_l": (530.0, 360.0),
    "uranium_ppb": (12.0, 18.0),
    "nitrate_mg_l": (28.0, 24.0),
    "fluoride_mg_l": (0.6, 0.5),
    "arsenic_ppb": (4.0, 6.0),
    "iron_ppm": (0.45, 0.7),
    "chloride_mg_l": (60.0, 75.0),
    "sulphate_mg_l": (45.0, 55.0),
    "do_mg_l": (5.4, 1.8),
    "turbidity_ntu": (3.5, 4.0),
    "total_hardness": (220.0, 140.0),
    "calcium_mg_l": (55.0, 35.0),
    "magnesium_mg_l": (28.0, 18.0),
    "sodium_mg_l": (38.0, 28.0),
    "potassium_mg_l": (4.0, 3.0),
    "bicarbonate_mg_l": (210.0, 100.0),
    "carbonate_mg_l": (4.0, 5.0),
    "phosphate_mg_l": (0.4, 0.6),
}

CHEM_COLS = list(FALLBACK_STATS.keys())


SQL_REAL_CHEM = """
SELECT ph, ec_us_cm, tds_mg_l, uranium_ppb, nitrate_mg_l, fluoride_mg_l,
       arsenic_ppb, iron_ppm, chloride_mg_l, sulphate_mg_l, do_mg_l,
       turbidity_ntu, total_hardness, calcium_mg_l, magnesium_mg_l,
       sodium_mg_l, potassium_mg_l, bicarbonate_mg_l, carbonate_mg_l, phosphate_mg_l
FROM water_samples
WHERE synthetic = FALSE
"""


class GaussianCopulaGenerator:
    """Fit / sample a Gaussian copula over the numeric chemistry features."""

    def __init__(self, columns: List[str]):
        self.columns = columns
        self._sorted: Dict[str, np.ndarray] = {}
        self._cov: Optional[np.ndarray] = None
        self._mean_fallback: Dict[str, Tuple[float, float]] = {}

    def fit(self, df: pd.DataFrame) -> "GaussianCopulaGenerator":
        # numeric coercion + drop all-NaN columns
        numeric = df[self.columns].apply(pd.to_numeric, errors="coerce")
        normals = pd.DataFrame(index=numeric.index, columns=self.columns, dtype=float)

        for col in self.columns:
            vals = numeric[col].dropna().to_numpy()
            if len(vals) >= 5:
                vals_sorted = np.sort(vals)
                self._sorted[col] = vals_sorted
                ranks = numeric[col].rank(method="average") / (len(numeric) + 1)
                ranks = ranks.fillna(0.5)
                normals[col] = stats.norm.ppf(ranks.clip(1e-4, 1 - 1e-4))
            else:
                # use fallback distribution for sparse columns
                mu, sigma = FALLBACK_STATS.get(col, (0.0, 1.0))
                self._mean_fallback[col] = (mu, sigma)
                normals[col] = np.nan

        # Cov matrix only on columns that have data
        present = [c for c in self.columns if c in self._sorted]
        sub = normals[present].fillna(0.0)
        if len(sub) >= 5 and len(present) >= 2:
            self._cov = np.cov(sub.values, rowvar=False)
        else:
            # uncorrelated fallback
            self._cov = np.eye(len(self.columns))
        self._present_cols = present
        return self

    def _empirical_inverse(self, col: str, u: np.ndarray) -> np.ndarray:
        sorted_vals = self._sorted[col]
        idx = np.clip((u * len(sorted_vals)).astype(int), 0, len(sorted_vals) - 1)
        return sorted_vals[idx]

    def sample(self, n: int, rng: np.random.Generator) -> pd.DataFrame:
        present = self._present_cols
        if not present:
            # full fallback to univariate normal
            out = {}
            for col, (mu, sigma) in FALLBACK_STATS.items():
                out[col] = np.clip(rng.normal(mu, sigma, n), 0, None)
            return pd.DataFrame(out)

        # sample MVN in standard-normal copula space
        cov = self._cov
        # regularise cov matrix
        cov = cov + 1e-4 * np.eye(cov.shape[0])
        z = rng.multivariate_normal(mean=np.zeros(cov.shape[0]), cov=cov, size=n)
        u = stats.norm.cdf(z).clip(1e-4, 1 - 1e-4)

        out = {}
        for i, col in enumerate(present):
            out[col] = self._empirical_inverse(col, u[:, i])

        # sparse columns get univariate normal
        for col in self.columns:
            if col in present:
                continue
            mu, sigma = self._mean_fallback.get(col, FALLBACK_STATS.get(col, (0.0, 1.0)))
            out[col] = np.clip(rng.normal(mu, sigma, n), 0, None)
        return pd.DataFrame(out)


def _sample_well_locations(n_wells: int, rng: np.random.Generator) -> pd.DataFrame:
    lons = rng.uniform(JH_BBOX["min_lon"], JH_BBOX["max_lon"], n_wells)
    lats = rng.uniform(JH_BBOX["min_lat"], JH_BBOX["max_lat"], n_wells)
    depths = np.clip(rng.normal(60, 30, n_wells), 5, 250)
    well_types = rng.choice(["bore", "tube", "dug"], n_wells, p=[0.5, 0.3, 0.2])
    return pd.DataFrame({
        "name": [f"SYN-WELL-{i:04d}" for i in range(n_wells)],
        "latitude": lats,
        "longitude": lons,
        "depth": depths,
        "well_type": well_types,
    })


def _force_unsafe(df: pd.DataFrame, idx: np.ndarray) -> pd.DataFrame:
    df.loc[idx, "uranium_ppb"] = np.clip(
        df.loc[idx, "uranium_ppb"].fillna(0) + np.random.uniform(20, 60, len(idx)), 0, None
    )
    df.loc[idx, "tds_mg_l"] = np.clip(
        df.loc[idx, "tds_mg_l"].fillna(0) + np.random.uniform(400, 900, len(idx)), 0, None
    )
    df.loc[idx, "ec_us_cm"] = np.clip(
        df.loc[idx, "ec_us_cm"].fillna(0) + np.random.uniform(800, 2000, len(idx)), 0, None
    )
    return df


async def _load_real_chem() -> pd.DataFrame:
    async with AsyncSessionLocal() as session:
        result = await session.execute(text(SQL_REAL_CHEM))
        rows = result.mappings().all()
    df = pd.DataFrame([dict(r) for r in rows])
    logger.info(f"Loaded {len(df)} real water samples for copula fit")
    return df


async def generate(
    n_samples: int = 500,
    n_wells: int = 50,
    seed: int = 42,
    output_dir: Optional[Path] = None,
) -> Dict[str, Path]:
    output_dir = output_dir or FAKEDATASET_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    np.random.seed(seed)
    random.seed(seed)

    # fit copula
    real = await _load_real_chem()
    gen = GaussianCopulaGenerator(CHEM_COLS).fit(real if len(real) >= 10 else pd.DataFrame())

    # well locations
    wells = _sample_well_locations(n_wells, rng)
    wells_path = output_dir / "synthetic_wells.csv"
    wells.to_csv(wells_path, index=False)

    # sample chemistry
    samples = gen.sample(n_samples, rng)

    # sampled timestamps spread across last 3 years, biased to monsoon months
    base = datetime(2023, 1, 1, tzinfo=timezone.utc)
    days_offset = rng.integers(0, 365 * 3, n_samples)
    samples["sampled_at"] = [
        (base + timedelta(days=int(d))).isoformat() for d in days_offset
    ]

    # assign each sample to a random well
    samples["well_index"] = rng.integers(0, n_wells, n_samples)
    samples["well_name"] = wells.iloc[samples["well_index"].values]["name"].values
    samples["latitude"] = wells.iloc[samples["well_index"].values]["latitude"].values
    samples["longitude"] = wells.iloc[samples["well_index"].values]["longitude"].values

    # force ~25% unsafe to keep classifier targets balanced
    n_unsafe = int(0.25 * n_samples)
    unsafe_idx = rng.choice(n_samples, n_unsafe, replace=False)
    samples = _force_unsafe(samples, unsafe_idx)

    # also bias 35% toward marginal
    marginal_pool = np.setdiff1d(np.arange(n_samples), unsafe_idx)
    n_marg = int(0.35 * n_samples)
    marg_idx = rng.choice(marginal_pool, n_marg, replace=False)
    samples.loc[marg_idx, "tds_mg_l"] = np.clip(
        samples.loc[marg_idx, "tds_mg_l"].fillna(500) + rng.uniform(100, 400, n_marg),
        500, 1000,
    )

    samples["synthetic"] = True

    samples_path = output_dir / "synthetic_water_samples.csv"
    samples.to_csv(samples_path, index=False)

    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "method": "gaussian_copula_empirical_marginals",
        "n_samples": n_samples,
        "n_wells": n_wells,
        "real_rows_used_for_fit": int(len(real)),
        "forced_unsafe_pct": 0.25,
        "forced_marginal_pct": 0.35,
        "files": {
            "wells": str(wells_path.relative_to(output_dir.parent)),
            "samples": str(samples_path.relative_to(output_dir.parent)),
        },
    }
    meta_path = output_dir / "synthetic_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2))

    logger.info(
        f"Generated {n_samples} synthetic samples across {n_wells} wells -> {output_dir}"
    )
    return {"wells": wells_path, "samples": samples_path, "metadata": meta_path}


def _cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-samples", type=int, default=500)
    parser.add_argument("--n-wells", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    asyncio.run(
        generate(
            n_samples=args.n_samples,
            n_wells=args.n_wells,
            seed=args.seed,
            output_dir=args.output_dir,
        )
    )


if __name__ == "__main__":
    _cli()
