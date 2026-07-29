#!/usr/bin/env python3
# coding: utf-8

"""
Prepara un TSV per la revisione manuale delle attribuzioni degli speaker.

Il file combina:
- i casi problematici estratti da speaker_review_occurrences.tsv;
- i candidati originali di speaker_matches.json, mantenendo corretta
  l'associazione nome <-> URI.

Non modifica nicknames.tsv e non modifica speaker_matches.json.
"""

import argparse
import csv
import json
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Prepara il file TSV per la revisione manuale degli speaker."
    )
    parser.add_argument(
        "--occurrences",
        required=True,
        help="TSV dei casi problematici prodotto da extract_speaker_review.py.",
    )
    parser.add_argument(
        "--speaker-matches",
        required=True,
        help="JSON corrente con i risultati del matching.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="TSV di revisione manuale da creare.",
    )
    return parser.parse_args()


def row_key(row):
    """Chiave stabile per collegare occorrenze e risultati del matcher."""
    return (
        str(row.get("page", "")).strip(),
        str(row.get("block_seq", "")).strip(),
    )


def candidate_label(candidate):
    nome = str(candidate.get("nome", "") or "").strip()
    cognome = str(candidate.get("cognome", "") or "").strip()
    return " ".join(part for part in (nome, cognome) if part).strip()


def main():
    args = parse_args()

    occurrences_path = Path(args.occurrences)
    matches_path = Path(args.speaker_matches)
    output_path = Path(args.output)

    with matches_path.open(encoding="utf-8") as file:
        matches = json.load(file)

    matches_by_key = {}
    duplicate_keys = set()

    for match in matches:
        key = row_key(match)
        if key in matches_by_key:
            duplicate_keys.add(key)
        matches_by_key[key] = match

    if duplicate_keys:
        examples = ", ".join(
            f"page={page}, block={block}"
            for page, block in sorted(duplicate_keys)[:10]
        )
        raise ValueError(
            "Chiavi duplicate in speaker_matches.json. "
            f"Esempi: {examples}"
        )

    with occurrences_path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")
        occurrence_rows = list(reader)

    if not reader.fieldnames:
        raise ValueError(f"Intestazione mancante: {occurrences_path}")

    max_candidates = 0
    missing_matches = []
    prepared = []

    for occurrence in occurrence_rows:
        key = row_key(occurrence)
        match = matches_by_key.get(key)

        if match is None:
            missing_matches.append(key)
            candidates = []
            method = occurrence.get("match_method", "")
        else:
            candidates = match.get("candidates") or []
            method = match.get("method", "")

        max_candidates = max(max_candidates, len(candidates))

        status = (
            occurrence.get("problem_status")
            or occurrence.get("status")
            or occurrence.get("problem_statuses")
            or ("ambiguous" if len(candidates) > 1 else "unassigned")
        )

        base = {
            "ramo": occurrence.get("ramo", ""),
            "legislatura": occurrence.get("legislatura", ""),
            "document_id": occurrence.get("document_id", ""),
            "page": occurrence.get("page", ""),
            "block_seq": occurrence.get("block_seq", ""),
            "raw_speaker": occurrence.get("raw_speaker", ""),
            "clean_speaker": occurrence.get("clean_speaker", ""),
            "problem_status": status,
            "match_method": method,
            "previous_text": occurrence.get("previous_text", ""),
            "speaker_text": (
                occurrence.get("speaker_text")
                or occurrence.get("text")
                or ""
            ),
            "next_text": occurrence.get("next_text", ""),
            # Campi da compilare manualmente
            "decision": "",
            "scope": "",
            "selected_persona": "",
            "selected_name": "",
            "note": "",
        }

        for index, candidate in enumerate(candidates, start=1):
            base[f"candidate_{index}_name"] = candidate_label(candidate)
            base[f"candidate_{index}_persona"] = candidate.get("persona", "")

        prepared.append(base)

    candidate_fields = []
    for index in range(1, max_candidates + 1):
        candidate_fields.extend(
            [
                f"candidate_{index}_name",
                f"candidate_{index}_persona",
            ]
        )

    fieldnames = [
        "ramo",
        "legislatura",
        "document_id",
        "page",
        "block_seq",
        "raw_speaker",
        "clean_speaker",
        "problem_status",
        "match_method",
        *candidate_fields,
        "decision",
        "scope",
        "selected_persona",
        "selected_name",
        "note",
        "previous_text",
        "speaker_text",
        "next_text",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            delimiter="\t",
            quoting=csv.QUOTE_MINIMAL,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(prepared)

    ambiguous = sum(
        1 for row in prepared if row["problem_status"] == "ambiguous"
    )
    unassigned = sum(
        1 for row in prepared if row["problem_status"] == "unassigned"
    )

    print("Preparazione completata")
    print(f"- righe di revisione: {len(prepared)}")
    print(f"- ambigue: {ambiguous}")
    print(f"- non assegnate: {unassigned}")
    print(f"- numero massimo di candidati: {max_candidates}")
    print(f"- match mancanti: {len(missing_matches)}")
    print(f"- output: {output_path}")

    if missing_matches:
        print("\nPrime chiavi senza corrispondenza:")
        for page, block in missing_matches[:10]:
            print(f"- page={page}, block_seq={block}")


if __name__ == "__main__":
    main()
