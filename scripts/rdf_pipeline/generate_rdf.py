#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera RDF/Turtle dagli output della pipeline IPSA.

Input:
- JSON con le predizioni multiclasse dei blocchi;
- JSON con il matching degli speaker;
- TSV o CSV con le URI ufficiali delle legislature;
- ontologia IPSA in Turtle.

Lo script ricostruisce blocchi funzionali B/I, conserva ogni blocco OCR come
Paragraph e collega gli speaker soltanto quando il matching è univoco.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, urlparse

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, RDF, RDFS, XSD


BASE = Namespace("http://www.semanticweb.org/claudia/ontologies/2026/ipsa/")
OCD = Namespace("http://dati.camera.it/ocd/")
SEMPARL = Namespace("http://ldf.fi/schema/semparl/")
OWL = Namespace("http://www.w3.org/2002/07/owl#")
ITALIAN_LANGUAGE = URIRef("http://id.loc.gov/vocabulary/iso639-1/it")

BLOCK_TYPE_NAMES = {
    "article",
    "description",
    "footer",
    "header",
    "other",
    "presidencydeclaration",
    "speech",
    "speechnotext",
    "text",
    "title",
}

PAGE_MATTER_TYPES = {"header", "footer"}
SPEAKER_BLOCK_TYPES = {"speech", "speechnotext"}
SPEAKER_START_LABELS = {"B-speech", "B-speechnotext"}


@dataclass
class FunctionalGroup:
    """Blocco funzionale composto da uno o più blocchi OCR."""

    ramo: str
    legislatura: str
    document_id: str
    functional_type: str
    start_page: int
    start_source_page: int
    start_block_seq: int
    start_label: str
    paragraphs: list[dict[str, Any]] = field(default_factory=list)
    pages: set[int] = field(default_factory=set)
    orphan_i: bool = False
    speaker_match: dict[str, Any] | None = None


@dataclass
class Stats:
    pages: int = 0
    source_blocks: int = 0
    functional_blocks: int = 0
    paragraphs: int = 0
    cross_page_continuations: int = 0
    hidden_speech_resolved: int = 0
    orphan_h_speech: int = 0
    orphan_i: Counter[str] = field(default_factory=Counter)
    unknown_labels: Counter[str] = field(default_factory=Counter)
    missing_legislatures: set[str] = field(default_factory=set)
    speaker_unique: int = 0
    speaker_ambiguous: int = 0
    speaker_no_candidate: int = 0
    speaker_no_record: int = 0
    speaker_unique_without_uri: int = 0
    presidency_unique: int = 0
    presidency_ambiguous: int = 0
    presidency_no_candidate: int = 0
    presidency_no_record: int = 0
    presidency_unique_without_uri: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Genera istanze RDF IPSA dalle predizioni LayoutLMv3 e dal "
            "matching degli speaker."
        )
    )
    parser.add_argument(
        "--predictions-json",
        required=True,
        type=Path,
        help="JSON prodotto dallo script di predizione multiclasse.",
    )
    parser.add_argument(
        "--speaker-matches",
        required=True,
        type=Path,
        help="JSON prodotto dallo script di matching degli speaker.",
    )
    parser.add_argument(
        "--legislatures",
        required=True,
        type=Path,
        help="TSV o CSV contenente le URI ufficiali delle legislature.",
    )
    parser.add_argument(
        "--ontology",
        required=True,
        type=Path,
        help="Ontologia IPSA in formato Turtle.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="File Turtle di output.",
    )
    return parser.parse_args()


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} non trovato: {path}")


def load_json_list(path: Path, label: str) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, list):
        raise ValueError(f"{label} deve contenere una lista JSON: {path}")

    if not all(isinstance(item, dict) for item in data):
        raise ValueError(f"{label} contiene elementi che non sono oggetti JSON.")

    return data


def safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def clean_cell(value: Any) -> str:
    return str(value or "").strip().strip('"').strip()


def legislature_key_from_uri(uri: str) -> str:
    parsed = urlparse(uri)
    return parsed.path.rstrip("/").split("/")[-1]


def detect_delimiter(path: Path) -> str:
    """Rileva il separatore di una tabella TSV/CSV."""

    with path.open(encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(8192)

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="\t,;")
        return dialect.delimiter
    except csv.Error:
        return "\t" if path.suffix.lower() == ".tsv" else ","


def load_legislature_map(path: Path) -> dict[str, URIRef]:
    """Carica key JSON -> URI ufficiale da una tabella TSV o CSV."""

    result: dict[str, URIRef] = {}
    delimiter = detect_delimiter(path)

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)

        if not reader.fieldnames:
            raise ValueError(f"Tabella delle legislature senza intestazione: {path}")

        normalized_headers = {
            clean_cell(header).lower(): header
            for header in reader.fieldnames
            if header is not None
        }
        uri_column = normalized_headers.get("legislatura")

        for row in reader:
            if uri_column is not None:
                official_uri = clean_cell(row.get(uri_column))
            else:
                official_uri = next(
                    (
                        clean_cell(cell)
                        for cell in row.values()
                        if clean_cell(cell).startswith(("http://", "https://"))
                    ),
                    "",
                )

            if not official_uri.startswith(("http://", "https://")):
                continue

            key = legislature_key_from_uri(official_uri)
            if key:
                result[key] = URIRef(official_uri)

    if not result:
        raise ValueError(
            f"Nessuna URI di legislatura trovata nella tabella: {path}"
        )

    return result


def split_label(label: Any) -> tuple[str, str]:
    normalized = str(label or "").strip()

    if "-" not in normalized:
        return "", normalized.lower()

    prefix, functional_type = normalized.split("-", 1)
    return prefix.upper(), functional_type.lower()


def normalize_functional_type(label: Any, stats: Stats) -> str:
    _prefix, functional_type = split_label(label)

    if functional_type in BLOCK_TYPE_NAMES:
        return functional_type

    stats.unknown_labels[str(label or "<vuota>")] += 1
    return "other"


def safe_segment(value: Any, fallback: str) -> str:
    text = str(value or "").strip() or fallback
    return quote(text, safe="")


def page_resource(page: dict[str, Any]) -> URIRef:
    ramo = safe_segment(page.get("ramo"), "ramo-sconosciuto")
    legislatura = safe_segment(
        page.get("legislatura"), "legislatura-sconosciuta"
    )
    document_id = safe_segment(
        page.get("document_id"), "documento-sconosciuto"
    )
    source_page = safe_int(page.get("page_source_number"))
    source_page_segment = str(
        source_page if source_page is not None else page.get("page", "x")
    )
    return BASE[
        f"page/{ramo}/{legislatura}/{document_id}/{source_page_segment}"
    ]


def block_resource(group: FunctionalGroup) -> URIRef:
    ramo = safe_segment(group.ramo, "ramo-sconosciuto")
    legislatura = safe_segment(
        group.legislatura, "legislatura-sconosciuta"
    )
    document_id = safe_segment(
        group.document_id, "documento-sconosciuto"
    )
    return BASE[
        "block/"
        f"{ramo}/{legislatura}/{document_id}/"
        f"{group.start_source_page}/{group.start_block_seq}"
    ]


def paragraph_resource(
    page: dict[str, Any], block_seq: int
) -> URIRef:
    ramo = safe_segment(page.get("ramo"), "ramo-sconosciuto")
    legislatura = safe_segment(
        page.get("legislatura"), "legislatura-sconosciuta"
    )
    document_id = safe_segment(
        page.get("document_id"), "documento-sconosciuto"
    )
    source_page = safe_int(page.get("page_source_number"))
    source_page_segment = str(
        source_page if source_page is not None else page.get("page", "x")
    )
    return BASE[
        "paragraph/"
        f"{ramo}/{legislatura}/{document_id}/"
        f"{source_page_segment}/{block_seq}"
    ]


def page_sort_key(page: dict[str, Any]) -> tuple[int, int]:
    source_page = safe_int(page.get("page_source_number"))
    global_page = safe_int(page.get("page"))
    return (
        source_page if source_page is not None else 10**12,
        global_page if global_page is not None else 10**12,
    )


def block_sort_key(block: dict[str, Any]) -> int:
    value = safe_int(block.get("block_seq"))
    return value if value is not None else 10**12


def build_match_lookup(
    matches: Iterable[dict[str, Any]],
) -> dict[tuple[int, int], dict[str, Any]]:
    lookup: dict[tuple[int, int], dict[str, Any]] = {}

    for item in matches:
        page = safe_int(item.get("page"))
        block_seq = safe_int(item.get("block_seq"))

        if page is None or block_seq is None:
            continue

        key = (page, block_seq)
        if key in lookup:
            raise ValueError(
                "Record duplicato in speaker_matches per "
                f"page={page}, block_seq={block_seq}."
            )
        lookup[key] = item

    return lookup


def reconstruct_groups(
    pages: list[dict[str, Any]],
    match_lookup: dict[tuple[int, int], dict[str, Any]],
    stats: Stats,
) -> list[FunctionalGroup]:
    documents: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)

    for page in pages:
        document_key = (
            str(page.get("ramo") or ""),
            str(page.get("legislatura") or ""),
            str(page.get("document_id") or ""),
        )
        documents[document_key].append(page)

    groups: list[FunctionalGroup] = []

    for (ramo, legislatura, document_id), document_pages in documents.items():
        document_pages.sort(key=page_sort_key)
        previous_page_last_content_group: FunctionalGroup | None = None
        previous_source_page: int | None = None

        for page in document_pages:
            page_number = safe_int(page.get("page"))
            source_page = safe_int(page.get("page_source_number"))

            if page_number is None:
                raise ValueError(
                    f"Numero pagina non valido: {page.get('page')!r}"
                )
            if source_page is None:
                raise ValueError(
                    "page_source_number non valido a pagina "
                    f"{page_number}: {page.get('page_source_number')!r}"
                )

            blocks = sorted(page.get("blocks", []), key=block_sort_key)
            current_group: FunctionalGroup | None = None
            last_content_group_on_page: FunctionalGroup | None = None
            only_page_matter_so_far = True

            for block in blocks:
                stats.source_blocks += 1
                block_seq = safe_int(block.get("block_seq"))
                if block_seq is None:
                    raise ValueError(
                        f"block_seq non valido a pagina {page_number}: "
                        f"{block.get('block_seq')!r}"
                    )

                predicted_label = str(
                    block.get("predicted_label") or ""
                ).strip()
                prefix, _raw_type = split_label(predicted_label)
                functional_type = normalize_functional_type(
                    predicted_label, stats
                )

                pages_are_adjacent = (
                    previous_source_page is not None
                    and source_page == previous_source_page + 1
                )

                continuing_current = (
                    prefix == "I"
                    and current_group is not None
                    and current_group.functional_type == functional_type
                )

                continuing_hidden_speech = (
                    prefix == "H"
                    and functional_type in SPEAKER_BLOCK_TYPES
                    and only_page_matter_so_far
                    and pages_are_adjacent
                    and previous_page_last_content_group is not None
                    and previous_page_last_content_group.functional_type
                    == functional_type
                )

                continuing_previous_page = (
                    prefix == "I"
                    and not continuing_current
                    and only_page_matter_so_far
                    and pages_are_adjacent
                    and previous_page_last_content_group is not None
                    and previous_page_last_content_group.functional_type
                    == functional_type
                )

                if continuing_current:
                    group = current_group
                elif continuing_hidden_speech:
                    group = previous_page_last_content_group
                    current_group = group
                    stats.hidden_speech_resolved += 1
                    stats.cross_page_continuations += 1
                elif continuing_previous_page:
                    group = previous_page_last_content_group
                    current_group = group
                    stats.cross_page_continuations += 1
                else:
                    orphan = prefix == "I"
                    if orphan:
                        stats.orphan_i[predicted_label or "<vuota>"] += 1
                    if (
                        prefix == "H"
                        and functional_type in SPEAKER_BLOCK_TYPES
                    ):
                        stats.orphan_h_speech += 1

                    speaker_match = None
                    if predicted_label in (
                        SPEAKER_START_LABELS
                        | {"B-presidencydeclaration"}
                    ):
                        speaker_match = match_lookup.get(
                            (page_number, block_seq)
                        )

                    group = FunctionalGroup(
                        ramo=ramo,
                        legislatura=legislatura,
                        document_id=document_id,
                        functional_type=functional_type,
                        start_page=page_number,
                        start_source_page=source_page,
                        start_block_seq=block_seq,
                        start_label=predicted_label,
                        orphan_i=orphan,
                        speaker_match=speaker_match,
                    )
                    groups.append(group)
                    current_group = group

                group.paragraphs.append(
                    {
                        "page_obj": page,
                        "block": block,
                    }
                )
                group.pages.add(page_number)

                if functional_type not in PAGE_MATTER_TYPES:
                    only_page_matter_so_far = False
                    last_content_group_on_page = group

            previous_page_last_content_group = last_content_group_on_page
            previous_source_page = source_page

    stats.functional_blocks = len(groups)
    stats.paragraphs = stats.source_blocks
    return groups


def bind_namespaces(graph: Graph) -> None:
    graph.bind("ipsa", BASE)
    graph.bind("ocd", OCD)
    graph.bind("semparl", SEMPARL)
    graph.bind("dct", DCTERMS)
    graph.bind("owl", OWL)
    graph.bind("rdfs", RDFS)
    graph.bind("xsd", XSD)


def add_page_triples(
    graph: Graph,
    page: dict[str, Any],
    legislature_map: dict[str, URIRef],
    stats: Stats,
) -> URIRef:
    page_number = safe_int(page.get("page"))
    source_page = safe_int(page.get("page_source_number"))

    if page_number is None or source_page is None:
        raise ValueError(f"Metadati pagina non validi: {page!r}")

    uri = page_resource(page)
    graph.add((uri, RDF.type, BASE["Page"]))
    graph.add(
        (uri, BASE["pageNumber"], Literal(page_number, datatype=XSD.integer))
    )
    graph.add(
        (
            uri,
            BASE["sourcePageNumber"],
            Literal(source_page, datatype=XSD.integer),
        )
    )

    ramo = str(page.get("ramo") or "").strip()
    legislatura = str(page.get("legislatura") or "").strip()
    document_id = str(page.get("document_id") or "").strip()
    image_file = str(page.get("image_file") or "").strip()

    if ramo:
        graph.add((uri, BASE["ramo"], Literal(ramo)))
    if document_id:
        graph.add((uri, BASE["documentID"], Literal(document_id)))
    if image_file:
        graph.add((uri, BASE["imageFile"], Literal(image_file)))

    legislature_uri = legislature_map.get(legislatura)
    if legislature_uri is not None:
        graph.add((uri, OCD["rif_leg"], legislature_uri))
    else:
        stats.missing_legislatures.add(legislatura or "<vuota>")

    return uri


def display_person_name(candidate: dict[str, Any]) -> str:
    nome = str(candidate.get("nome") or "").strip()
    cognome = str(candidate.get("cognome") or "").strip()
    if not cognome:
        cognome = str(candidate.get("cognome_main") or "").strip()

    return " ".join(part for part in (nome, cognome) if part).title()


def add_speaker_triples(
    graph: Graph,
    block_uri: URIRef,
    match: dict[str, Any] | None,
    stats: Stats,
) -> None:
    if match is None:
        stats.speaker_no_record += 1
        return

    candidates = match.get("candidates") or []

    if len(candidates) == 1:
        candidate = candidates[0]
        full_name = display_person_name(candidate)
        person_uri = str(candidate.get("persona") or "").strip()

        if full_name:
            graph.add(
                (
                    block_uri,
                    BASE["speakerLabel"],
                    Literal(full_name, lang="it"),
                )
            )

        if person_uri:
            graph.add(
                (block_uri, SEMPARL["speaker"], URIRef(person_uri))
            )
            stats.speaker_unique += 1
        else:
            stats.speaker_unique_without_uri += 1
        return

    unresolved_label = str(
        match.get("clean_speaker") or match.get("raw_speaker") or ""
    ).strip()

    if unresolved_label:
        graph.add(
            (
                block_uri,
                BASE["speakerLabel"],
                Literal(unresolved_label, lang="it"),
            )
        )

    if len(candidates) > 1:
        stats.speaker_ambiguous += 1
    else:
        stats.speaker_no_candidate += 1


def add_presidency_triples(
    graph: Graph,
    block_uri: URIRef,
    match: dict[str, Any] | None,
    stats: Stats,
) -> None:
    """Collega la dichiarazione di presidenza solo a una persona univoca."""
    if match is None:
        stats.presidency_no_record += 1
        return

    candidates = match.get("candidates") or []

    if len(candidates) == 1:
        candidate = candidates[0]
        person_uri = str(candidate.get("persona") or "").strip()

        if person_uri:
            graph.add(
                (block_uri, BASE["presidenza"], URIRef(person_uri))
            )
            stats.presidency_unique += 1
        else:
            stats.presidency_unique_without_uri += 1
        return

    if len(candidates) > 1:
        stats.presidency_ambiguous += 1
    else:
        stats.presidency_no_candidate += 1


def decimal_literal(value: Any) -> Literal | None:
    if value is None or value == "":
        return None

    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None

    return Literal(decimal_value, datatype=XSD.decimal)


def add_group_triples(
    graph: Graph,
    group: FunctionalGroup,
    page_uri_by_number: dict[int, URIRef],
    stats: Stats,
) -> None:
    block_uri = block_resource(group)
    graph.add((block_uri, RDF.type, BASE["Block"]))
    graph.add(
        (
            block_uri,
            BASE["hasBlockType"],
            BASE[group.functional_type],
        )
    )
    graph.add((block_uri, DCTERMS.language, ITALIAN_LANGUAGE))
    graph.add(
        (
            block_uri,
            SEMPARL["orderNumber"],
            Literal(group.start_block_seq, datatype=XSD.integer),
        )
    )

    for page_number in sorted(group.pages):
        page_uri = page_uri_by_number[page_number]
        graph.add((block_uri, BASE["hasPage"], page_uri))

    if group.start_label in SPEAKER_START_LABELS:
        add_speaker_triples(
            graph, block_uri, group.speaker_match, stats
        )
    elif group.start_label == "B-presidencydeclaration":
        add_presidency_triples(
            graph, block_uri, group.speaker_match, stats
        )

    for order, paragraph_record in enumerate(group.paragraphs, start=1):
        page = paragraph_record["page_obj"]
        block = paragraph_record["block"]
        block_seq = safe_int(block.get("block_seq"))
        page_number = safe_int(page.get("page"))

        if block_seq is None or page_number is None:
            raise ValueError("Paragrafo con identificatori non validi.")

        paragraph_uri = paragraph_resource(page, block_seq)
        page_uri = page_uri_by_number[page_number]

        graph.add((paragraph_uri, RDF.type, BASE["Paragraph"]))
        graph.add(
            (
                paragraph_uri,
                BASE["orderID"],
                Literal(order, datatype=XSD.integer),
            )
        )
        graph.add(
            (
                paragraph_uri,
                BASE["sourceBlockSequence"],
                Literal(block_seq, datatype=XSD.integer),
            )
        )
        graph.add((paragraph_uri, BASE["hasPage"], page_uri))
        graph.add((paragraph_uri, DCTERMS.language, ITALIAN_LANGUAGE))

        text = str(block.get("text") or "").strip()
        if text:
            graph.add(
                (
                    paragraph_uri,
                    SEMPARL["content"],
                    Literal(text, lang="it"),
                )
            )

        predicted_label = str(
            block.get("predicted_label") or ""
        ).strip()
        if predicted_label:
            graph.add(
                (
                    paragraph_uri,
                    BASE["predictedLabel"],
                    Literal(predicted_label),
                )
            )

        confidence = decimal_literal(
            block.get("prediction_confidence")
        )
        if confidence is not None:
            graph.add(
                (
                    paragraph_uri,
                    BASE["predictionConfidence"],
                    confidence,
                )
            )

        ocr_category = str(
            block.get("ocr_category")
            or block.get("category")
            or ""
        ).strip()
        if ocr_category:
            graph.add(
                (
                    paragraph_uri,
                    BASE["ocrCategory"],
                    Literal(ocr_category),
                )
            )

        graph.add((block_uri, BASE["hasParagraph"], paragraph_uri))


def print_summary(stats: Stats, graph: Graph, output: Path) -> None:
    print(f"Creato file: {output}")
    print("Riepilogo")
    print(f"- pagine: {stats.pages}")
    print(f"- blocchi OCR/paragrafi: {stats.source_blocks}")
    print(f"- blocchi funzionali: {stats.functional_blocks}")
    print(
        "- continuazioni tra pagine collegate: "
        f"{stats.cross_page_continuations}"
    )
    print(f"- H-speech/H-speechnotext risolti: {stats.hidden_speech_resolved}")
    print(f"- H-speech/H-speechnotext orfani: {stats.orphan_h_speech}")
    print(f"- I-* orfani: {sum(stats.orphan_i.values())}")

    for label, count in stats.orphan_i.most_common():
        print(f"  - {label}: {count}")

    print(f"- speaker con URI univoca: {stats.speaker_unique}")
    print(f"- speaker ambigui: {stats.speaker_ambiguous}")
    print(f"- speaker senza candidato: {stats.speaker_no_candidate}")
    print(f"- B-speech/B-speechnotext senza record di matching: {stats.speaker_no_record}")
    print(f"- presidenze con URI univoca: {stats.presidency_unique}")
    print(f"- presidenze ambigue: {stats.presidency_ambiguous}")
    print(f"- presidenze senza candidato: {stats.presidency_no_candidate}")
    print(f"- dichiarazioni senza record: {stats.presidency_no_record}")

    if stats.speaker_unique_without_uri:
        print(
            "- speaker con candidato unico ma URI mancante: "
            f"{stats.speaker_unique_without_uri}"
        )

    if stats.presidency_unique_without_uri:
        print(
            "- presidenze con candidato unico ma URI mancante: "
            f"{stats.presidency_unique_without_uri}"
        )

    if stats.unknown_labels:
        print("- label funzionali ricondotte a other:")
        for label, count in stats.unknown_labels.most_common():
            print(f"  - {label}: {count}")

    if stats.missing_legislatures:
        print(
            "- legislature mancanti nel mapping: "
            + ", ".join(sorted(stats.missing_legislatures))
        )

    print(f"- triple complessive, ontologia inclusa: {len(graph)}")


def main() -> int:
    args = parse_args()

    try:
        require_file(args.predictions_json, "JSON delle predizioni")
        require_file(args.speaker_matches, "JSON degli speaker")
        require_file(args.legislatures, "Tabella TSV/CSV delle legislature")
        require_file(args.ontology, "Ontologia")

        pages = load_json_list(args.predictions_json, "Predizioni")
        matches = load_json_list(args.speaker_matches, "Speaker matches")
        legislature_map = load_legislature_map(args.legislatures)
        match_lookup = build_match_lookup(matches)

        stats = Stats(pages=len(pages))
        groups = reconstruct_groups(pages, match_lookup, stats)

        graph = Graph()
        bind_namespaces(graph)
        graph.parse(args.ontology, format="turtle")

        page_uri_by_number: dict[int, URIRef] = {}
        for page in pages:
            page_number = safe_int(page.get("page"))
            if page_number is None:
                raise ValueError(
                    f"Numero pagina non valido: {page.get('page')!r}"
                )
            if page_number in page_uri_by_number:
                raise ValueError(
                    f"Numero pagina duplicato nel dataset: {page_number}"
                )
            page_uri_by_number[page_number] = add_page_triples(
                graph, page, legislature_map, stats
            )

        for group in groups:
            add_group_triples(graph, group, page_uri_by_number, stats)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        graph.serialize(destination=args.output, format="turtle")
        print_summary(stats, graph, args.output)
        return 0

    except Exception as exc:  # messaggio leggibile per uso da terminale
        print(f"Errore: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
