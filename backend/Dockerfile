# JalDrishti API image.
#
# BUILD FROM THE REPOSITORY ROOT, NOT FROM backend/:
#
#     docker build -f backend/Dockerfile -t jaldrishti-api .
#
# AUDIT 2026-08-24. This file used to be built with `context: ./backend`, which
# produced an image that could not run the product. `ml_pipeline_adapter.py`
# computes `REPO_ROOT = Path(__file__).resolve().parents[3]` and inserts it on
# `sys.path` so the engine is importable in-process. With only `backend/` copied
# to `/app`, that expression resolves to `/` — `ml_pipeline` was not there,
# `Datasets/` was not there, and every simulation would have failed with
# "ml_pipeline is not importable". The layout below preserves the three-deep
# relationship the adapter depends on:
#
#     /app/backend/app/services/ml_pipeline_adapter.py   ->  parents[3] == /app
#     /app/ml_pipeline/...                                    (the engine)
#     /app/Datasets/...                                       (what it reads)
#
# `.dockerignore` at the repo root keeps the ~1.1 GB of build-time rasters out;
# only the ~43 MB the engine actually reads at runtime is copied.

FROM python:3.12-slim

# System deps for psycopg2 and geopandas/pyogrio.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements first, so a source change does not invalidate the pip layer.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# The engine, the data it reads, and the API.
COPY ml_pipeline/ ml_pipeline/
COPY Datasets/ Datasets/
COPY backend/ backend/

WORKDIR /app/backend

EXPOSE 8000

# ONE worker by default, deliberately.
#
# This was `--workers 4`. Simulations run as in-process background tasks, so a
# worker solving transport is not serving requests — but each worker also loads
# its own copy of the ~12 MB artifact bundle plus numpy/xgboost, and four of
# them will OOM a small instance long before they help. Raise it only after
# measuring, and only on an instance with the memory for it.
#
# `--proxy-headers` with `--forwarded-allow-ips` is REQUIRED behind a gateway:
# without it every anonymous caller shares one rate-limit bucket keyed on the
# proxy's address. Narrow the allow-list to your gateway if you know it.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
