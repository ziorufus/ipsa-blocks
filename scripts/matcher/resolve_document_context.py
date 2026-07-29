#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Risoluzione document-level prima della generazione RDF.

Lo script:
- identifica la persona nominata nei blocchi B-presidencydeclaration;
- propaga la presidenza ai turni B-speech che iniziano con PRESIDENTE;
- conserva tutti i risultati già presenti in speaker_matches.json;
- produce un nuovo JSON di matching, senza modificare gli input.

Gli H-speech non ricevono un record separato: vengono ricongiunti allo speech
precedente da generate_rdf.py, ereditandone così lo speaker.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from match_speakers import (
    DEFAULT_FUZZY_THRESHOLD,
    detect_leg_col,
    load_nicknames_tsv,
    load_tsv,
    match_name_to_parl,
)


PRESIDENT_SPEECH_RE = re.compile(
    r"^\s*(?:[*_]+\s*)?(?:IL\s+)?PRESIDENTE\b",
    re.IGNORECASE,
)

ROLE_RE = re.compile(
    r"\b(?:VICE[-\s]?PRESIDENTE|PRESIDENTE)\b",
    re.IGNORECASE,
)

HONORIFIC_RE = re.compile(
    r"^(?:(?:IL|L['’])\s+)?(?:COMMENDATORE|COMM\.?|ONOREVOLE|"
    r"SENATORE|DEPUTATO|CONTE|MARCHESE|AVVOCATO|AVV\.?|PROFESSORE|PROF\.?)\s+",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Risolvi presidenza e turni PRESIDENTE prima della generazione RDF."
        )
    )
    parser.add_argument(
        "--predictions-json",
        required=True,
        type=Path,
        help="JSON con le predizioni multiclasse.",
    )
    parser.add_argument(
        "--speaker-matches",
        required=True,
        type=Path,
        help="JSON prodotto da match_speakers.py.",
    )
    parser.add_argument(
        "--anagrafica-tsv",
        required=True,
        type=Path,
        help="persone.tsv oppure persone_e_senatori.tsv.",
    )
    parser.add_argument(
        "--nicknames-tsv",
        type=Path,
        help="TSV opzionale con persona, nickname e legislatura.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Nuovo JSON con i match document-level.",
    )
    parser.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=DEFAULT_FUZZY_THRESHOLD,
        help=(
            "Soglia minima del fuzzy matching "
            f"(default: {DEFAULT_FUZZY_THRESHOLD})."
        ),
    )
    args = parser.parse_args()

    if not 0 <= args.fuzzy_threshold <= 1:
        parser.error("--fuzzy-threshold deve essere compreso tra 0 e 1.")

    return args


def load_json_list(path: Path, label: str) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
        raise ValueError(f"{label} deve contenere una lista di oggetti JSON: {path}")

    return data


def safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def page_sort_key(page: dict[str, Any]) -> tuple[int, int]:
    source_page = safe_int(page.get("page_source_number"))
    page_number = safe_int(page.get("page"))
    return (
        source_page if source_page is not None else 10**12,
        page_number if page_number is not None else 10**12,
    )


def block_sort_key(block: dict[str, Any]) -> int:
    value = safe_int(block.get("block_seq"))
    return value if value is not None else 10**12


def extract_president_name(text: Any) -> str | None:
    """Estrae la parte onomastica da una dichiarazione di presidenza."""
    value = str(text or "")
    value = re.sub(r"[*_]+", " ", value)
    value = " ".join(value.split()).strip(" .,:;–—-")

    role_matches = list(ROLE_RE.finditer(value))
    if len(role_matches) != 1:
        # Una dichiarazione con zero o più ruoli non viene risolta
        # automaticamente.
        return None

    name = value[role_matches[0].end():].strip(" .,:;–—-")

    previous = None
    while name and name != previous:
        previous = name
        name = HONORIFIC_RE.sub("", name).strip(" .,:;–—-")

    return name or None


def extract_presiding_role(text: Any) -> str | None:
    """Restituisce presidente oppure vice-presidente."""
    value = str(text or "")
    value = re.sub(r"[*_]+", " ", value)
    value = " ".join(value.split()).strip(" .,:;–—-")

    role_matches = list(ROLE_RE.finditer(value))
    if len(role_matches) != 1:
        return None

    role = role_matches[0].group(0).upper()
    role = re.sub(r"[-\s]+", "-", role)

    if role == "VICE-PRESIDENTE":
        return "vice-presidente"

    return "presidente"


def is_president_speech(text: Any) -> bool:
    return bool(PRESIDENT_SPEECH_RE.match(str(text or "")))


def candidate_count(record: dict[str, Any] | None) -> int:
    if not record:
        return 0
    return len(record.get("candidates") or [])


def main() -> int:
    args = parse_args()

    pages = load_json_list(args.predictions_json, "Predizioni")
    original_matches = load_json_list(args.speaker_matches, "Speaker matches")

    leg_col = detect_leg_col(args.anagrafica_tsv)
    parl_by_leg, index = load_tsv(args.anagrafica_tsv, leg_col)

    nicknames_by_leg = None
    if args.nicknames_tsv is not None:
        nicknames_by_leg = load_nicknames_tsv(
            args.nicknames_tsv,
            parl_by_leg,
        )

    matches_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for record in original_matches:
        page_number = safe_int(record.get("page"))
        block_seq = safe_int(record.get("block_seq"))
        if page_number is None or block_seq is None:
            continue
        key = (page_number, block_seq)
        if key in matches_by_key:
            raise ValueError(
                f"Match duplicato: page={page_number}, block_seq={block_seq}"
            )
        matches_by_key[key] = dict(record)

    documents: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for page in pages:
        key = (
            str(page.get("ramo") or ""),
            str(page.get("legislatura") or ""),
            str(page.get("document_id") or ""),
        )
        documents[key].append(page)

    declarations = 0
    declarations_unique = 0
    president_speeches_resolved = 0
    president_speeches_without_context = 0

    for (_ramo, legislature, _document_id), document_pages in documents.items():
        document_pages.sort(key=page_sort_key)
        current_presidency: dict[str, Any] | None = None

        for page in document_pages:
            page_number = safe_int(page.get("page"))
            if page_number is None:
                raise ValueError(f"Numero pagina non valido: {page.get('page')!r}")

            for block in sorted(page.get("blocks") or [], key=block_sort_key):
                block_seq = safe_int(block.get("block_seq"))
                if block_seq is None:
                    raise ValueError(
                        f"block_seq non valido a pagina {page_number}: "
                        f"{block.get('block_seq')!r}"
                    )

                predicted_label = str(block.get("predicted_label") or "").strip()
                key = (page_number, block_seq)

                if predicted_label == "B-presidencydeclaration":
                    declarations += 1
                    text = str(block.get("text") or "")
                    name = extract_president_name(text)
                    role = extract_presiding_role(text)

                    if name is None:
                        record = {
                            "page": page_number,
                            "block_seq": block_seq,
                            "legislatura": legislature,
                            "raw_speaker": text,
                            "clean_speaker": "",
                            "matched": False,
                            "method": "presidency_name_not_extracted",
                            "candidates": [],
                            "record_type": "presidencydeclaration",
                            "presiding_role": role,
                        }
                    else:
                        result = match_name_to_parl(
                            name,
                            legislature,
                            parl_by_leg,
                            index,
                            args.fuzzy_threshold,
                            nicknames_by_leg,
                        )
                        record = {
                            "page": page_number,
                            "block_seq": block_seq,
                            "legislatura": legislature,
                            "raw_speaker": text,
                            "clean_speaker": name,
                            "matched": result["matched"],
                            "method": f"presidency_{result['method']}",
                            "candidates": result["candidates"],
                            "record_type": "presidencydeclaration",
                            "presiding_role": role,
                        }

                    matches_by_key[key] = record

                    if candidate_count(record) == 1:
                        current_presidency = record
                        declarations_unique += 1
                    else:
                        # Una nuova dichiarazione non risolta interrompe la
                        # propagazione della presidenza precedente.
                        current_presidency = None

                    continue

                if predicted_label == "B-speech" and is_president_speech(
                    block.get("text")
                ):
                    existing = matches_by_key.get(key)
                    if existing is not None and candidate_count(existing) == 1:
                        continue

                    if current_presidency is None:
                        president_speeches_without_context += 1
                        continue

                    matches_by_key[key] = {
                        "page": page_number,
                        "block_seq": block_seq,
                        "legislatura": legislature,
                        "raw_speaker": "PRESIDENTE",
                        "clean_speaker": "PRESIDENTE",
                        "matched": True,
                        "method": "presidency_context",
                        "candidates": list(current_presidency["candidates"]),
                        "record_type": "speech",
                        "presiding_role": current_presidency.get(
                            "presiding_role"
                        ),
                        "source_presidency_page": current_presidency["page"],
                        "source_presidency_block_seq": current_presidency["block_seq"],
                    }
                    president_speeches_resolved += 1

    output_records = [
        matches_by_key[key]
        for key in sorted(matches_by_key)
    ]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(output_records, handle, ensure_ascii=False, indent=2)

    print("Risoluzione document-level completata")
    print(f"- match originali: {len(original_matches)}")
    print(f"- dichiarazioni di presidenza: {declarations}")
    print(f"- presidenze univoche: {declarations_unique}")
    print(f"- turni PRESIDENTE risolti: {president_speeches_resolved}")
    print(
        "- turni PRESIDENTE senza contesto: "
        f"{president_speeches_without_context}"
    )
    print(f"- record finali: {len(output_records)}")
    print(f"- output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
