"""
PDF to CSV extractor for selectable-text PDFs (no OCR required).
Uses pdfplumber for table detection and pdfminer for raw text fallback.

Usage:
    python pdf_to_csv.py input.pdf
    python pdf_to_csv.py input.pdf --output result.csv
    python pdf_to_csv.py input.pdf --pages 1,3,5
    python pdf_to_csv.py input.pdf --all-text   # extract all text as CSV rows
"""

import sys
import csv
import argparse
from pathlib import Path


def extract_tables_pdfplumber(pdf_path: str, pages: list[int] | None = None) -> list[list[list[str]]]:
    """Extract tables from PDF using pdfplumber. Returns list of tables (each table is list of rows)."""
    try:
        import pdfplumber
    except ImportError:
        print("Installing pdfplumber...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pdfplumber"])
        import pdfplumber

    all_tables = []
    with pdfplumber.open(pdf_path) as pdf:
        target_pages = pdf.pages
        if pages:
            target_pages = [pdf.pages[i - 1] for i in pages if 0 < i <= len(pdf.pages)]

        for page in target_pages:
            tables = page.extract_tables()
            for table in tables:
                # Clean None values and strip whitespace
                cleaned = [
                    [cell.strip() if cell else "" for cell in row]
                    for row in table
                    if any(cell for cell in row)  # skip fully empty rows
                ]
                if cleaned:
                    all_tables.append(cleaned)

    return all_tables


def extract_text_as_rows(pdf_path: str, pages: list[int] | None = None) -> list[list[str]]:
    """Fallback: extract all text lines as CSV rows (useful when no tables found)."""
    try:
        import pdfplumber
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pdfplumber"])
        import pdfplumber

    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        target_pages = pdf.pages
        if pages:
            target_pages = [pdf.pages[i - 1] for i in pages if 0 < i <= len(pdf.pages)]

        for page_num, page in enumerate(target_pages, 1):
            words = page.extract_words()
            if not words:
                continue

            # Group words into lines by their vertical position (top coordinate)
            lines: dict[float, list[str]] = {}
            for word in words:
                top = round(word["top"], 1)
                lines.setdefault(top, []).append(word["text"])

            for top in sorted(lines.keys()):
                rows.append(lines[top])

    return rows


def save_to_csv(data: list[list[str]], output_path: str) -> int:
    """Write rows to CSV file. Returns number of rows written."""
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerows(data)
    return len(data)


def main():
    parser = argparse.ArgumentParser(description="Extract tables from a selectable-text PDF to CSV.")
    parser.add_argument("pdf", help="Path to input PDF file")
    parser.add_argument("-o", "--output", help="Output CSV file path (default: <pdf_name>.csv)")
    parser.add_argument(
        "--pages",
        help="Comma-separated page numbers to extract (e.g. 1,2,5). Default: all pages.",
    )
    parser.add_argument(
        "--all-text",
        action="store_true",
        help="Extract all text as rows (fallback when no tables detected)",
    )
    parser.add_argument(
        "--table-index",
        type=int,
        default=None,
        help="If multiple tables found, export only this table (1-based index)",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"Error: File not found — {pdf_path}")
        sys.exit(1)

    output_path = args.output or pdf_path.with_suffix(".csv").name

    pages = None
    if args.pages:
        try:
            pages = [int(p.strip()) for p in args.pages.split(",")]
        except ValueError:
            print("Error: --pages must be comma-separated integers, e.g. 1,2,5")
            sys.exit(1)

    print(f"Reading: {pdf_path}")

    if args.all_text:
        rows = extract_text_as_rows(str(pdf_path), pages)
        if not rows:
            print("No text found in the PDF.")
            sys.exit(1)
        count = save_to_csv(rows, output_path)
        print(f"Saved {count} rows -> {output_path}")
        return

    # Table extraction mode
    tables = extract_tables_pdfplumber(str(pdf_path), pages)

    if not tables:
        print("No tables detected. Trying text extraction fallback...")
        rows = extract_text_as_rows(str(pdf_path), pages)
        if not rows:
            print("No content found in the PDF.")
            sys.exit(1)
        count = save_to_csv(rows, output_path)
        print(f"No tables found — saved {count} text rows -> {output_path}")
        return

    print(f"Found {len(tables)} table(s).")

    if args.table_index is not None:
        idx = args.table_index - 1
        if idx < 0 or idx >= len(tables):
            print(f"Error: --table-index {args.table_index} is out of range (found {len(tables)} tables).")
            sys.exit(1)
        tables_to_export = [(args.table_index, tables[idx])]
    elif len(tables) == 1:
        tables_to_export = [(1, tables[0])]
    else:
        tables_to_export = list(enumerate(tables, 1))

    if len(tables_to_export) == 1:
        _, table = tables_to_export[0]
        count = save_to_csv(table, output_path)
        print(f"Saved table with {count} rows -> {output_path}")
    else:
        # Multiple tables: save each to a separate file
        base = Path(output_path).stem
        ext = Path(output_path).suffix or ".csv"
        for i, table in tables_to_export:
            out = f"{base}_table{i}{ext}"
            count = save_to_csv(table, out)
            print(f"  Table {i}: {count} rows -> {out}")


if __name__ == "__main__":
    main()
