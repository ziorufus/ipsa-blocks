#!/usr/bin/env python3
"""A-03-stratify.py — Stratified train/test split for IPSA-GOLD JSON data.

Usage:
    python A-03-stratify.py input.json output_prefix [--train-ratio 0.5]

Outputs:
    <output_prefix>-train.json       train pages with labels
    <output_prefix>-test.json        test pages with labels
    <output_prefix>-test-hidden.json test pages with empty labels
"""

import argparse
import json
import sys

import numpy as np
from skmultilearn.model_selection import IterativeStratification


def load_data(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_label_matrix(pages: list) -> tuple[np.ndarray, list[str]]:
    """Return a (pages × labels) count matrix and the sorted label list.

    Using per-page label counts (not binary presence) so IterativeStratification
    balances the total occurrence of each label across folds, not just presence.
    """
    all_labels = sorted({
        block["label"]
        for page in pages
        for block in page.get("blocks", [])
        if block.get("label")
    })
    label_index = {lbl: i for i, lbl in enumerate(all_labels)}
    matrix = np.zeros((len(pages), len(all_labels)), dtype=float)
    for i, page in enumerate(pages):
        for block in page.get("blocks", []):
            lbl = block.get("label", "")
            if lbl in label_index:
                matrix[i, label_index[lbl]] += 1.0
    return matrix, all_labels


def format_page(page: dict, include_labels: bool) -> dict:
    blocks = [
        {"text": block.get("text", ""), "label": block.get("label", "") if include_labels else ""}
        for block in page.get("blocks", [])
    ]
    return {"page": page["page"], "blocks": blocks}


def label_counts(pages: list, all_labels: list[str]) -> dict[str, int]:
    counts = {lbl: 0 for lbl in all_labels}
    for page in pages:
        for block in page.get("blocks", []):
            lbl = block.get("label", "")
            if lbl in counts:
                counts[lbl] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stratified train/test split for IPSA-GOLD JSON",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", help="Input JSON file")
    parser.add_argument(
        "output_prefix",
        help="Output prefix; files will be <prefix>-train.json, -test.json, -test-hidden.json",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.5,
        metavar="RATIO",
        help="Fraction of pages assigned to training set",
    )
    args = parser.parse_args()

    if not (0.0 < args.train_ratio < 1.0):
        sys.exit("Error: --train-ratio must be strictly between 0 and 1")

    test_ratio = 1.0 - args.train_ratio

    pages = load_data(args.input)
    print(f"Loaded {len(pages)} pages from {args.input!r}")

    Y, all_labels = build_label_matrix(pages)
    print(f"Found {len(all_labels)} unique labels: {all_labels}")

    X_dummy = np.arange(len(pages)).reshape(-1, 1)

    # IterativeStratification fills folds in reverse order relative to
    # sample_distribution_per_fold, so we pass [test_ratio, train_ratio] to
    # get fold 0 ≈ train_ratio and fold 1 ≈ test_ratio.
    stratifier = IterativeStratification(
        n_splits=2,
        order=2,
        sample_distribution_per_fold=[test_ratio, args.train_ratio],
    )
    train_idx, test_idx = next(stratifier.split(X_dummy, Y))

    train_pages = [pages[i] for i in train_idx]
    test_pages = [pages[i] for i in test_idx]

    print(f"\nSplit: {len(train_pages)} train / {len(test_pages)} test "
          f"({len(train_pages)/len(pages):.1%} / {len(test_pages)/len(pages):.1%})")

    train_counts = label_counts(train_pages, all_labels)
    test_counts = label_counts(test_pages, all_labels)
    total_counts = label_counts(pages, all_labels)

    print(f"\n{'Label':<28} {'Total':>7}  {'Train':>7} {'Train%':>7}  {'Test':>7} {'Test%':>7}")
    print("-" * 68)
    for lbl in all_labels:
        tot = total_counts[lbl]
        tr = train_counts[lbl]
        te = test_counts[lbl]
        tr_pct = tr / tot * 100 if tot else 0
        te_pct = te / tot * 100 if tot else 0
        print(f"  {lbl:<26} {tot:>7}  {tr:>7} {tr_pct:>6.1f}%  {te:>7} {te_pct:>6.1f}%")

    outputs = [
        (f"{args.output_prefix}-train.json",       train_pages, True),
        (f"{args.output_prefix}-test.json",         test_pages,  True),
        (f"{args.output_prefix}-test-hidden.json",  test_pages,  False),
    ]
    print()
    for path, page_list, with_labels in outputs:
        data = [format_page(p, include_labels=with_labels) for p in page_list]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Saved {path}")


if __name__ == "__main__":
    main()
