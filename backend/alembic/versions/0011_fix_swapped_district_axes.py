"""Fix transposed district/block geometry, and the attribution that depended on it.

THE BUG. `districts.geometry` and `blocks.geometry` were stored as (lat, lon)
instead of (lon, lat). The source files are the cause —
`District_Boundary_JH.geojson` and `Sub_District_Boundary_JH.geojson` violate
RFC 7946 §3.1.1, while `Aquifers_Jharkhand.geojson` does not — and the ingestion
passed the coordinates through unexamined. `app/services/ingestion.py` now
detects and corrects the order on load; this migration repairs what is already
stored.

HOW IT WENT UNNOTICED. Nothing errored. The polygons simply sat at
(23.98, 85.68) instead of (85.68, 23.98) — a valid point, just in the wrong
hemisphere-ish place. The visible symptoms were silent and easy to misread:

  * every spatial join against a district or block returned nothing, so
    `ST_Within` in `_find_block_for_point` always fell through to its
    "nearest block" fallback;
  * that fallback then assigned **all 397 monitoring wells to a single block**,
    because from a transposed polygon set the nearest centroid is the same one
    for every real Jharkhand coordinate;
  * a district-level map or aggregate built on that attribution would have shown
    the entire state's groundwater data under one district.

The last point is why this is fixed before the citizen risk surface is built on
top of it: the wrong answer would have been public-facing and confidently wrong.

BOTH STEPS ARE GUARDED so this is idempotent and safe to re-run: the flip only
applies to rows whose bounds actually look transposed, and the re-attribution
only runs where a containing block now exists.
"""
from alembic import op
import sqlalchemy as sa

revision = '0011_fix_swapped_district_axes'
down_revision = '0010_field_observations'
branch_labels = None
depends_on = None

# Jharkhand: longitude 83.3..87.9, latitude 21.9..25.4. The bands are disjoint,
# so "x looks like a latitude AND y looks like a longitude" is a reliable test
# rather than a guess.
_LOOKS_SWAPPED = """
    ST_XMin({col}) BETWEEN 19 AND 28 AND ST_XMax({col}) BETWEEN 19 AND 28
AND ST_YMin({col}) BETWEEN 80 AND 90 AND ST_YMax({col}) BETWEEN 80 AND 90
"""


def upgrade() -> None:
    conn = op.get_bind()
    for table in ("districts", "blocks"):
        cond = _LOOKS_SWAPPED.format(col="geometry")
        n = conn.execute(sa.text(
            f"SELECT count(*) FROM {table} WHERE geometry IS NOT NULL AND ({cond})"
        )).scalar()
        if n:
            conn.execute(sa.text(
                f"UPDATE {table} SET geometry = ST_FlipCoordinates(geometry) "
                f"WHERE geometry IS NOT NULL AND ({cond})"))
            print(f"  flipped {n} {table} geometries to (lon, lat)")
        else:
            print(f"  {table}: nothing transposed")

    # Re-attribute wells now that containment works. Only rows that genuinely
    # fall inside a block are touched; anything outside keeps what it had rather
    # than being guessed at by a nearest-neighbour fallback, which is what
    # produced the single-block result in the first place.
    moved = conn.execute(sa.text("""
        UPDATE monitoring_wells w
        SET block_id = b.id
        FROM blocks b
        WHERE b.geometry IS NOT NULL
          AND ST_Within(w.location::geometry, b.geometry)
          AND (w.block_id IS DISTINCT FROM b.id)
    """)).rowcount
    print(f"  re-attributed {moved} monitoring_wells to their containing block")

    moved_st = conn.execute(sa.text("""
        UPDATE monitoring_stations s
        SET block_id = b.id
        FROM blocks b
        WHERE b.geometry IS NOT NULL
          AND ST_Within(
                ST_SetSRID(ST_MakePoint(s.longitude, s.latitude), 4326), b.geometry)
          AND (s.block_id IS DISTINCT FROM b.id)
    """)).rowcount
    print(f"  re-attributed {moved_st} monitoring_stations to their containing block")


def downgrade() -> None:
    # Restoring the transposition would put the database back into a state where
    # every spatial join silently returns nothing. The flip is therefore
    # one-way; the block attribution is left as corrected.
    print("  0011 is not reversible: re-transposing geometry would restore a "
          "silent data-correctness bug. No action taken.")
