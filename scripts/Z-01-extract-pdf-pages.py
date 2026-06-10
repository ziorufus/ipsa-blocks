#!/usr/bin/env python3
import argparse
import csv
import os
import random
from pathlib import Path
from typing import List, Tuple

from pypdf import PdfReader, PdfWriter
from tqdm import tqdm


def find_pdfs(root: Path) -> List[Path]:
    return [p for p in root.rglob("*.pdf") if p.is_file()]


def safe_num_pages(pdf_path: Path) -> int:
    # Reader can raise on corrupted PDFs; treat those as 0 pages
    try:
        r = PdfReader(str(pdf_path))
        return len(r.pages)
    except Exception:
        return 0


def build_global_index(pdf_paths: List[Path]) -> Tuple[List[Tuple[Path, int]], int]:
    """
    Returns:
      - index: list of (pdf_path, page_index) pairs for every page across all PDFs
      - total_pages: total count
    """
    index: List[Tuple[Path, int]] = []
    total = 0

    for p in tqdm(pdf_paths):
        n = safe_num_pages(p)
        if n <= 0:
            continue
        # store page indices 0..n-1
        index.extend((p, i) for i in range(n))
        total += n

    return index, total


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Randomly extract a total of N pages from PDFs under a folder (recursively)."
    )
    ap.add_argument("root", help="Root folder to scan for PDFs")
    ap.add_argument("-n", "--num-pages", type=int, required=True, help="Total pages to extract (e.g., 1000)")
    ap.add_argument("-o", "--output", default="random_pages.pdf", help="Output PDF filename")
    ap.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    ap.add_argument("--manifest", default="random_pages_manifest.csv", help="CSV manifest path (set to '' to disable)")
    ap.add_argument(
        "--allow-duplicates",
        action="store_true",
        help="Allow the same page to be selected multiple times (useful if N > total pages).",
    )
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"Root folder does not exist: {root}")

    if args.num_pages <= 0:
        raise SystemExit("num-pages must be > 0")

    if args.seed is not None:
        random.seed(args.seed)

    pdfs = find_pdfs(root)
    if not pdfs:
        raise SystemExit(f"No PDFs found under: {root}")

    global_index, total_pages = build_global_index(pdfs)
    if total_pages == 0:
        raise SystemExit("Found PDFs, but none could be read (0 total pages).")

    n = args.num_pages

    if not args.allow_duplicates and n > total_pages:
        raise SystemExit(
            f"Requested {n} pages but only {total_pages} pages are available. "
            f"Either lower -n or use --allow-duplicates."
        )

    # Choose page references
    if args.allow_duplicates:
        chosen = [random.choice(global_index) for _ in range(n)]
    else:
        chosen = random.sample(global_index, n)

    # To avoid re-opening PDFs for every page, group selections by file
    selections_by_pdf = {}
    for pdf_path, page_idx in chosen:
        selections_by_pdf.setdefault(pdf_path, []).append(page_idx)

    writer = PdfWriter()
    manifest_rows = []

    # Add pages in the random order selected
    # We'll cache readers to reduce IO
    reader_cache = {}

    for (pdf_path, page_idx) in chosen:
        if pdf_path not in reader_cache:
            reader_cache[pdf_path] = PdfReader(str(pdf_path))
        reader = reader_cache[pdf_path]

        try:
            writer.add_page(reader.pages[page_idx])
        except Exception:
            # Skip unreadable page; you could also choose to error out instead
            continue

        manifest_rows.append({
            "source_pdf": str(pdf_path),
            "source_page_1based": page_idx + 1,
        })

    out_path = Path(args.output).expanduser().resolve()
    with open(out_path, "wb") as f:
        writer.write(f)

    if args.manifest != "":
        man_path = Path(args.manifest).expanduser().resolve()
        with open(man_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["source_pdf", "source_page_1based"])
            w.writeheader()
            w.writerows(manifest_rows)

    print(f"Scanned PDFs: {len(pdfs)}")
    print(f"Total readable pages found: {total_pages}")
    print(f"Pages written: {len(manifest_rows)}")
    print(f"Output PDF: {out_path}")
    if args.manifest != "":
        print(f"Manifest CSV: {Path(args.manifest).expanduser().resolve()}")


if __name__ == "__main__":
    main()
