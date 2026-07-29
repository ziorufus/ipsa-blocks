#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Estrae i casi di speaker ambigui o non assegnati da speaker_matches.json
e li arricchisce con metadati e contesto da predictions_multiclass.json.

Produce:
1. un TSV con una riga per ogni occorrenza problematica;
2. un TSV aggregato per speaker normalizzato, utile per la revisione manuale.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Estrae gli speaker ambigui e non assegnati e prepara "
            "le tabelle per la revisione manuale."
        )
    )
    parser.add_argument(
        "--predictions-json",
        required=True,
        type=Path,
        help="JSON prodotto dalla classificazione LayoutLMv3 + BiLSTM.",
    )
    parser.add_argument(
        "--speaker-matches",
        required=True,
        type=Path,
        help="JSON prodotto dal matching degli speaker.",
    )
    parser.add_argument(
        "--occurrences-output",
        required=True,
        type=Path,
        help="TSV di output con una riga per occorrenza problematica.",
    )
    parser.add_argument(
        "--aliases-output",
        required=True,
        type=Path,
        help="TSV aggregato per speaker normalizzato.",
    )
    parser.add_argument(
        "--legislatura",
        default=None,
        help="Filtra una legislatura, per esempio regno_01.",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"File non trovato: {path}")

    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def clean_text(value: Any) -> str:
    """Riduce spazi, tab e ritorni a capo a singoli spazi."""
    return " ".join(str(value or "").split())


def candidate_name(candidate: dict[str, Any]) -> str:
    nome = clean_text(candidate.get("nome"))
    cognome = clean_text(
        candidate.get("cognome")
        or candidate.get("cognome_main")
    )
    return " ".join(part for part in (nome, cognome) if part)


def join_values(values: list[str]) -> str:
    return " | ".join(value for value in values if value)


def build_block_index(
    pages: list[dict[str, Any]],
) -> dict[tuple[int, int], dict[str, Any]]:
    """
    Indicizza i blocchi tramite (page, block_seq) e conserva
    il contesto precedente e successivo nella stessa pagina.
    """
    index: dict[tuple[int, int], dict[str, Any]] = {}

    for page in pages:
        page_number = int(page["page"])
        blocks = page.get("blocks") or []

        for position, block in enumerate(blocks):
            block_seq = int(block["block_seq"])
            previous_block = blocks[position - 1] if position > 0 else {}
            next_block = (
                blocks[position + 1]
                if position + 1 < len(blocks)
                else {}
            )

            key = (page_number, block_seq)

            if key in index:
                raise ValueError(
                    "Chiave duplicata nelle predizioni: "
                    f"page={page_number}, block_seq={block_seq}"
                )

            index[key] = {
                "ramo": clean_text(page.get("ramo")),
                "legislatura": clean_text(page.get("legislatura")),
                "document_id": clean_text(page.get("document_id")),
                "page": page_number,
                "page_source_number": page.get("page_source_number", ""),
                "image_file": clean_text(page.get("image_file")),
                "block_seq": block_seq,
                "predicted_label": clean_text(
                    block.get("predicted_label")
                ),
                "speaker_text": clean_text(block.get("text")),
                "prediction_confidence": block.get(
                    "prediction_confidence",
                    "",
                ),
                "previous_label": clean_text(
                    previous_block.get("predicted_label")
                ),
                "previous_text": clean_text(
                    previous_block.get("text")
                ),
                "next_label": clean_text(
                    next_block.get("predicted_label")
                ),
                "next_text": clean_text(next_block.get("text")),
            }

    return index


def classify_problem(candidates: list[dict[str, Any]]) -> str | None:
    if len(candidates) == 0:
        return "unassigned"
    if len(candidates) > 1:
        return "ambiguous"
    return None


def write_tsv(
    path: Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            quoting=csv.QUOTE_MINIMAL,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()

    pages = load_json(args.predictions_json)
    matches = load_json(args.speaker_matches)

    if not isinstance(pages, list):
        raise TypeError("Il JSON delle predizioni deve contenere una lista.")
    if not isinstance(matches, list):
        raise TypeError("Il JSON dei match deve contenere una lista.")

    block_index = build_block_index(pages)
    occurrence_rows: list[dict[str, Any]] = []
    missing_blocks: list[tuple[int, int]] = []

    for match in matches:
        match_legislatura = clean_text(match.get("legislatura"))

        if (
            args.legislatura
            and match_legislatura != args.legislatura
        ):
            continue

        candidates = match.get("candidates") or []
        problem_status = classify_problem(candidates)

        # I record con un solo candidato sono già risolti.
        if problem_status is None:
            continue

        page_number = int(match["page"])
        block_seq = int(match["block_seq"])
        key = (page_number, block_seq)
        block_data = block_index.get(key)

        if block_data is None:
            missing_blocks.append(key)
            continue

        candidate_names = sorted(
            {
                candidate_name(candidate)
                for candidate in candidates
                if candidate_name(candidate)
            }
        )
        candidate_uris = sorted(
            {
                clean_text(candidate.get("persona"))
                for candidate in candidates
                if clean_text(candidate.get("persona"))
            }
        )

        row = {
            **block_data,
            "problem_status": problem_status,
            "match_method": clean_text(match.get("method")),
            "matched_flag": str(bool(match.get("matched"))).lower(),
            "raw_speaker": clean_text(match.get("raw_speaker")),
            "clean_speaker": clean_text(match.get("clean_speaker")),
            "candidate_count": len(candidates),
            "candidate_names": join_values(candidate_names),
            "candidate_uris": join_values(candidate_uris),
            # Colonne da compilare nella revisione manuale.
            "manual_persona": "",
            "manual_decision": "",
            "manual_note": "",
        }
        occurrence_rows.append(row)

    occurrence_rows.sort(
        key=lambda row: (
            row["legislatura"],
            row["page"],
            row["block_seq"],
        )
    )

    occurrence_fields = [
        "ramo",
        "legislatura",
        "document_id",
        "page",
        "page_source_number",
        "image_file",
        "block_seq",
        "problem_status",
        "match_method",
        "matched_flag",
        "raw_speaker",
        "clean_speaker",
        "candidate_count",
        "candidate_names",
        "candidate_uris",
        "previous_label",
        "previous_text",
        "predicted_label",
        "prediction_confidence",
        "speaker_text",
        "next_label",
        "next_text",
        "manual_persona",
        "manual_decision",
        "manual_note",
    ]

    write_tsv(
        args.occurrences_output,
        occurrence_rows,
        occurrence_fields,
    )

    # Aggregazione per ramo + legislatura + clean_speaker.
    grouped: dict[
        tuple[str, str, str],
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in occurrence_rows:
        group_key = (
            row["ramo"],
            row["legislatura"],
            row["clean_speaker"] or row["raw_speaker"],
        )
        grouped[group_key].append(row)

    alias_rows: list[dict[str, Any]] = []

    for (ramo, legislatura, speaker), rows in grouped.items():
        statuses = sorted(
            {str(row["problem_status"]) for row in rows}
        )
        methods = sorted(
            {str(row["match_method"]) for row in rows}
        )
        candidate_names = sorted(
            {
                value.strip()
                for row in rows
                for value in str(row["candidate_names"]).split("|")
                if value.strip()
            }
        )
        candidate_uris = sorted(
            {
                value.strip()
                for row in rows
                for value in str(row["candidate_uris"]).split("|")
                if value.strip()
            }
        )
        pages_values = sorted({int(row["page"]) for row in rows})

        sample_texts: list[str] = []
        for row in rows:
            text = str(row["speaker_text"])
            if text and text not in sample_texts:
                sample_texts.append(text[:300])
            if len(sample_texts) == 3:
                break

        alias_rows.append(
            {
                "ramo": ramo,
                "legislatura": legislatura,
                "clean_speaker": speaker,
                "occurrences": len(rows),
                "problem_statuses": join_values(statuses),
                "match_methods": join_values(methods),
                "candidate_names": join_values(candidate_names),
                "candidate_uris": join_values(candidate_uris),
                "sample_pages": ", ".join(
                    str(page) for page in pages_values[:20]
                ),
                "sample_text_1": (
                    sample_texts[0]
                    if len(sample_texts) > 0
                    else ""
                ),
                "sample_text_2": (
                    sample_texts[1]
                    if len(sample_texts) > 1
                    else ""
                ),
                "sample_text_3": (
                    sample_texts[2]
                    if len(sample_texts) > 2
                    else ""
                ),
                # Colonne da compilare nella revisione per alias.
                "resolved_persona": "",
                "decision": "",
                "note": "",
            }
        )

    alias_rows.sort(
        key=lambda row: (
            -int(row["occurrences"]),
            row["clean_speaker"],
        )
    )

    alias_fields = [
        "ramo",
        "legislatura",
        "clean_speaker",
        "occurrences",
        "problem_statuses",
        "match_methods",
        "candidate_names",
        "candidate_uris",
        "sample_pages",
        "sample_text_1",
        "sample_text_2",
        "sample_text_3",
        "resolved_persona",
        "decision",
        "note",
    ]

    write_tsv(
        args.aliases_output,
        alias_rows,
        alias_fields,
    )

    status_counts = Counter(
        row["problem_status"] for row in occurrence_rows
    )

    print("Estrazione completata")
    print(f"- occorrenze problematiche: {len(occurrence_rows)}")
    print(f"- ambigue: {status_counts.get('ambiguous', 0)}")
    print(f"- non assegnate: {status_counts.get('unassigned', 0)}")
    print(f"- speaker normalizzati distinti: {len(alias_rows)}")
    print(f"- blocchi non trovati nelle predizioni: {len(missing_blocks)}")
    print(f"- file occorrenze: {args.occurrences_output}")
    print(f"- file aggregato: {args.aliases_output}")

    if missing_blocks:
        print("- prime chiavi mancanti:", missing_blocks[:10])


if __name__ == "__main__":
    main()
