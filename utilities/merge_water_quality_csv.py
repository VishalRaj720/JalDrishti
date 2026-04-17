"""
Merge Water Quality CSVs
========================
Merges all waterQuality_table*.csv files (already Jharkhand-only) into a
single clean CSV: waterQuality_jharkhand_combined.csv

The merged file adds a 'source_table' column indicating which original table
each row came from so data lineage is preserved.

Usage:
    python merge_water_quality_csv.py
    python merge_water_quality_csv.py --input-dir path/to/csv  --output-dir path/to/out
    python merge_water_quality_csv.py --drop-duplicates
"""

import argparse
import csv
import glob
from pathlib import Path


def load_csv(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    return fieldnames, rows


def merge_csvs(
    csv_dir: Path,
    output_dir: Path,
    pattern: str = "waterQuality_table*.csv",
    drop_duplicates: bool = False,
) -> None:
    files = sorted(csv_dir.glob(pattern))
    if not files:
        print(f"No files matching '{pattern}' found in {csv_dir}")
        return

    print(f"\nMerging {len(files)} file(s) from {csv_dir}")

    all_rows: list[dict] = []
    master_fields: list[str] = []

    for path in files:
        fieldnames, rows = load_csv(path)
        print(f"  {path.name}: {len(rows):>4} rows, {len(fieldnames)} columns")

        # Build master field list preserving order, adding new columns as seen
        for col in fieldnames:
            if col not in master_fields:
                master_fields.append(col)

        for row in rows:
            row["source_table"] = path.stem   # e.g. waterQuality_table36
            all_rows.append(row)

    # Add source_table column at the end of fieldnames
    if "source_table" not in master_fields:
        master_fields.append("source_table")

    total_before = len(all_rows)

    if drop_duplicates:
        # Deduplicate by (S. No., State, District, Location, Year)
        key_cols = ["S. No.", "State", "District", "Location", "Year"]
        seen: set[tuple] = set()
        deduped: list[dict] = []
        for row in all_rows:
            key = tuple(row.get(c, "").strip() for c in key_cols)
            if key not in seen:
                seen.add(key)
                deduped.append(row)
        all_rows = deduped
        print(f"\n  Dropped {total_before - len(all_rows)} duplicate rows.")

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "waterQuality_jharkhand_combined.csv"

    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=master_fields, extrasaction="ignore")
        writer.writeheader()
        for row in all_rows:
            # Fill missing columns with empty string
            writer.writerow({col: row.get(col, "") for col in master_fields})

    print(f"\n  Total rows written : {len(all_rows):,}")
    print(f"  Output             : {out_path}")
    print(f"  Columns            : {len(master_fields)}")
    print(f"  Columns list       : {master_fields}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Merge Jharkhand water quality CSV tables into one combined file."
    )
    parser.add_argument(
        "--input-dir",
        default=None,
        help="Directory containing waterQuality_table*.csv (default: <project>/Datasets/csv)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: <project>/Datasets/jharkhand)",
    )
    parser.add_argument(
        "--drop-duplicates",
        action="store_true",
        help="Remove duplicate rows keyed on (S. No., State, District, Location, Year).",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent

    input_dir = Path(args.input_dir) if args.input_dir else project_root / "Datasets" / "csv"
    output_dir = Path(args.output_dir) if args.output_dir else project_root / "Datasets" / "jharkhand"

    merge_csvs(input_dir, output_dir, drop_duplicates=args.drop_duplicates)


if __name__ == "__main__":
    main()
