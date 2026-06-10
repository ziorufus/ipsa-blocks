#!/usr/bin/env python3
"""
Merge and expand parliamentary speech annotation CSVs, then combine with OCR JSON.

Basic usage (CSV only):
    python merge.py output.csv input1.csv [input2.csv ...]

With JSON output:
    python merge.py output.csv input1.csv [input2.csv ...] --json output.json --dots dots/
"""

import sys
import json
import glob
import os
import argparse
import warnings
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore", category=FutureWarning)

HIDDEN_STARTING_LETTER = "H"
INFERRED_STARTING_LETTER = "N"
UNKNOWN_STARTING_LETTER = "U"

B_ONLY = ["title"]


def _is_positive_int(val):
    try:
        return int(float(val)) >= 1
    except (ValueError, TypeError):
        return False


def load_csv(filepath):
    df = pd.read_csv(filepath, header=0, dtype=str)
    # Keep first 10 columns, rename uniformly A-J
    df = df.iloc[:, :10]
    df.columns = list("ABCDEFGHIJ")
    df = df.replace(r"^\s*$", np.nan, regex=True)
    # Drop rows where column F is not a positive integer
    df = df[df["F"].apply(_is_positive_int)].reset_index(drop=True)
    return df


def fill_column_a(df):
    """Forward-fill page number."""
    df["A"] = df["A"].ffill()
    return df


def fill_column_b(df):
    """Fill empty B cells with progressive integers, resetting on each new page."""
    result = []
    last_a = None
    last_b = None
    for _, row in df.iterrows():
        curr_a = row["A"]
        raw_b = row["B"]

        if curr_a != last_a:
            last_b = None  # reset counter on new page
            last_a = curr_a

        if pd.isna(raw_b):
            last_b = (last_b or 0) + 1
            result.append(last_b)
        else:
            try:
                last_b = int(float(raw_b))
            except (ValueError, TypeError):
                last_b = (last_b or 0) + 1
            result.append(last_b)

    df["B"] = result
    return df


def merge_and_sort(dfs):
    combined = pd.concat(dfs, ignore_index=True)
    combined["_a"] = pd.to_numeric(combined["A"], errors="coerce")
    combined["_b"] = pd.to_numeric(combined["B"], errors="coerce")
    combined = combined.sort_values(["_a", "_b"]).drop(columns=["_a", "_b"])
    return combined.reset_index(drop=True)


def _int_val(val):
    """Return integer from a cell value, or 0 if missing/non-numeric."""
    if pd.isna(val):
        return 0
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def _iob_letter(d_value):
    """Return B, H, or I for original rows based on the D column value."""
    if pd.notna(d_value) and str(d_value).strip().lower().startswith("[hidden]"):
        return HIDDEN_STARTING_LETTER
    if pd.notna(d_value) and str(d_value).strip().lower().startswith("[inferred]"):
        return INFERRED_STARTING_LETTER
    if pd.notna(d_value) and str(d_value).strip().lower().startswith("[unknown]"):
        return UNKNOWN_STARTING_LETTER
    return "B"


def add_headers_and_footers(df):
    """
    For each page's first block (B==1):
      - if G is set, prepend G rows with B=0, C='header'
      - if H is set, append H rows with B=999, C='footer' after all page rows
    Added rows are flagged _orig=False; original rows get _orig=True.
    """
    page_meta = {}
    for _, row in df.iterrows():
        try:
            b = int(float(row["B"]))
        except (ValueError, TypeError):
            continue
        if b == 1:
            page = row["A"]
            if page not in page_meta:
                page_meta[page] = {
                    "header_count": _int_val(row["G"]),
                    "footer_count": _int_val(row["H"]),
                }

    def make_row(page, b_val, c_val, is_first=False):
        return {col: np.nan for col in df.columns} | {
            "A": page, "B": b_val, "C": c_val, "_orig": is_first,
        }

    df = df.copy()
    df["_orig"] = True

    pages_in_order = list(dict.fromkeys(df["A"].tolist()))
    page_groups = {page: grp for page, grp in df.groupby("A", sort=False)}

    rows = []
    for page in pages_in_order:
        meta = page_meta.get(page, {"header_count": 0, "footer_count": 0})

        for i in range(meta["header_count"]):
            rows.append(make_row(page, 0, "header", is_first=(i == 0)))

        rows.extend(page_groups[page].to_dict("records"))

        for i in range(meta["footer_count"]):
            rows.append(make_row(page, 999, "footer", is_first=(i == 0)))

    return pd.DataFrame(rows, columns=[*df.columns])


def expand_blocks(df):
    """
    Apply IOB labeling to column C and expand rows based on column F.

    Original rows  → {letter}-{type}  (letter = B, H, or I based on column D)
    Added rows     → I-{type}         (header/footer rows, F-expansion rows)
    """
    cols = [c for c in df.columns if c != "_orig"]
    rows = []

    for _, row in df.iterrows():
        c_label = str(row["C"]) if pd.notna(row["C"]) else ""
        is_orig = bool(row.get("_orig", True))

        if c_label in B_ONLY:
            letter = "B"
        else:
            letter = _iob_letter(row["D"]) if is_orig else "I"
        row_dict = row.to_dict()
        row_dict["C"] = f"{letter}-{c_label}"
        rows.append(row_dict)

        n = _int_val(row["F"])
        if n > 1:
            extra = {col: np.nan for col in cols}
            expansion_prefix = "B" if c_label in B_ONLY else "I"
            extra.update({"A": row["A"], "B": row["B"], "C": f"{expansion_prefix}-{c_label}"})
            for _ in range(n - 1):
                rows.append(extra.copy())

    return pd.DataFrame(rows, columns=cols)


def generate_json(df, dots_dir, output_json):
    """Combine CSV annotation data with OCR JSON files into a single JSON output."""
    pages = sorted(df["A"].dropna().unique(), key=lambda x: int(x))
    result = []
    skipped = 0

    for page in pages:
        page_int = int(page)
        json_page = page_int - 1  # JSON files are 0-indexed

        matches = glob.glob(os.path.join(dots_dir, f"*_page_{json_page}.json"))
        if not matches:
            print(f"WARNING: page {page_int}: no JSON file found for page index {json_page}, skipping")
            skipped += 1
            continue

        with open(matches[0], encoding="utf-8") as f:
            ocr_blocks = json.load(f)

        csv_rows = df[df["A"] == page].reset_index(drop=True)

        if len(csv_rows) != len(ocr_blocks):
            print(
                f"WARNING: page {page_int}: CSV has {len(csv_rows)} rows "
                f"but OCR has {len(ocr_blocks)} blocks, skipping"
            )
            skipped += 1
            continue

        blocks = []
        for i, (_, row) in enumerate(csv_rows.iterrows()):
            ocr = ocr_blocks[i]
            blocks.append({
                "bbox": ocr.get("bbox", []),
                "label": str(row["C"]) if pd.notna(row["C"]) else "",
                "ocr_category": ocr.get("category", ""),
                "block_seq": str(int(float(row["B"]))) if pd.notna(row["B"]) else "",
                "text": ocr.get("text", ""),
                "author": str(row["D"]) if pd.notna(row["D"]) else "",
                "authorURL": ""
            })

        result.append({"page": page_int, "blocks": blocks})

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Saved JSON with {len(result)} pages to {output_json} ({skipped} skipped)")


def main():
    parser = argparse.ArgumentParser(description="Merge annotation CSVs and optionally combine with OCR JSON.")
    parser.add_argument("output_csv", help="Output CSV file path")
    parser.add_argument("inputs", nargs="+", help="Input CSV files")
    parser.add_argument("--json", dest="output_json", help="Output JSON file path")
    parser.add_argument("--dots", dest="dots_dir", help="Directory containing OCR JSON files")
    args = parser.parse_args()

    if args.output_json and not args.dots_dir:
        parser.error("--json requires --dots")
    if args.dots_dir and not args.output_json:
        parser.error("--dots requires --json")

    dfs = []
    for f in args.inputs:
        df = load_csv(f)
        df = fill_column_a(df)
        df = fill_column_b(df)
        dfs.append(df)

    df = merge_and_sort(dfs)
    df = add_headers_and_footers(df)
    df = expand_blocks(df)

    out = df[["A", "B", "C", "D"]].copy()
    out["A"] = pd.to_numeric(out["A"], errors="coerce").astype("Int64")
    out["B"] = pd.to_numeric(out["B"], errors="coerce").astype("Int64")
    out.to_csv(args.output_csv, index=False)
    print(f"Saved {len(out)} rows to {args.output_csv}")
    print(f"Column A range: {out['A'].min()} – {out['A'].max()}")

    if args.output_json:
        generate_json(out, args.dots_dir, args.output_json)


if __name__ == "__main__":
    main()
