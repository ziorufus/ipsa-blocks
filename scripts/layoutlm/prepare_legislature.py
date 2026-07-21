#!/usr/bin/env python3

import argparse
import csv
import json
import re
import shutil
from pathlib import Path



PAGE_RE = re.compile(
    r"^(?P<document_id>.+)_page_(?P<page_number>\d+)\.json$"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Prepara un dataset per la predizione LayoutLMv3 "
            "a partire dagli output DoTS di una legislatura."
        )
    )

    parser.add_argument(
        "source_dir",
        type=Path,
        help="Cartella della legislatura contenente gli output DoTS.",
    )

    parser.add_argument(
        "ramo",
        choices=["camera", "senato"],
        help="Ramo del Parlamento.",
    )

    parser.add_argument(
        "output_dir",
        type=Path,
        help="Cartella in cui salvare JSON, manifest e immagini.",
    )

    parser.add_argument(
        "--legislatura",
        default="regno_01",
        help="Identificativo normalizzato della legislatura.",
    )

    return parser.parse_args()


def find_image(page_json):
    """
    Cerca l'immagine corrispondente al JSON nella stessa cartella.
    """

    stem = page_json.with_suffix("")

    for extension in [".jpg", ".jpeg", ".png"]:
        candidate = stem.with_suffix(extension)

        if candidate.exists():
            return candidate

    return None


def copy_image(source_image, destination):
    """
    Copia l'immagine DoTS senza ricodificarla.

    Il formato originale viene conservato: JPG/JPEG rimangono JPEG
    e gli eventuali PNG rimangono PNG.
    """

    shutil.copy2(source_image, destination)


def load_blocks(page_json):
    """
    Legge la lista dei blocchi DoTS.

    Alcuni file contengono una lista JSON normale.
    Altri contengono la stessa lista serializzata dentro una stringa JSON.
    """

    with page_json.open(encoding="utf-8") as file:
        blocks = json.load(file)

    if isinstance(blocks, str):
        blocks = json.loads(blocks)

    return blocks


def main():
    args = parse_args()

    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()
    images_dir = output_dir / "images"

    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    source_pages = []

    for page_json in source_dir.rglob("*_page_*.json"):

        # Esclude cartelle duplicate o incomplete con suffisso .pdf.out.
        if any(
            parent.name.endswith(".pdf.out")
            for parent in page_json.parents
        ):
            continue

        match = PAGE_RE.match(page_json.name)

        if not match:
            continue

        document_id = match.group("document_id")
        page_source_number = int(match.group("page_number"))

        source_pages.append(
            (
                str(page_json.parent),
                document_id,
                page_source_number,
                page_json,
            )
        )

    source_pages.sort(
        key=lambda item: (
            item[0],
            item[2],
        )
    )

    pages = []
    manifest = []
    skipped = []

    for (
        _parent,
        document_id,
        page_source_number,
        page_json,
    ) in source_pages:

        image_path = find_image(page_json)

        if image_path is None:
            skipped.append(
                [
                    document_id,
                    page_source_number,
                    str(page_json),
                    "immagine mancante",
                ]
            )
            continue

        try:
            blocks = load_blocks(page_json)

        except Exception as error:
            skipped.append(
                [
                    document_id,
                    page_source_number,
                    str(page_json),
                    f"errore lettura JSON: {error}",
                ]
            )
            continue

        if not isinstance(blocks, list):
            skipped.append(
                [
                    document_id,
                    page_source_number,
                    str(page_json),
                    (
                        "il contenuto finale non è una lista "
                        f"ma {type(blocks).__name__}"
                    ),
                ]
            )
            continue

        converted_blocks = []

        for block_seq, block in enumerate(blocks):

            if not isinstance(block, dict):
                continue

            converted_blocks.append(
                {
                    "bbox": block.get("bbox", []),
                    "ocr_category": block.get("category", ""),
                    "category": block.get("category", ""),
                    "block_seq": block_seq,
                    "text": block.get("text", ""),
                    # Etichetta fittizia necessaria per costruire
                    # il dataset di predizione.
                    "label": "B-text",
                }
            )

        # L'identificativo interno viene assegnato solo alle pagine
        # effettivamente inserite, evitando buchi nella numerazione.
        internal_page_id = len(pages) + 1

        image_extension = image_path.suffix.lower()

        # Uniforma soltanto il nome dell'estensione:
        # .jpeg e .jpg indicano entrambi un'immagine JPEG.
        if image_extension == ".jpeg":
            image_extension = ".jpg"

        image_name = (
            f"{internal_page_id}{image_extension}"
        )
        output_image = images_dir / image_name

        try:
            copy_image(
                image_path,
                output_image,
            )

        except Exception as error:
            skipped.append(
                [
                    document_id,
                    page_source_number,
                    str(page_json),
                    f"errore copia immagine: {error}",
                ]
            )
            continue

        pages.append(
            {
                "page": internal_page_id,
                "ramo": args.ramo,
                "legislatura": args.legislatura,
                "document_id": document_id,
                "page_source_number": page_source_number,
                "image_file": image_name,
                "blocks": converted_blocks,
            }
        )

        manifest.append(
            [
                internal_page_id,
                args.ramo,
                args.legislatura,
                document_id,
                page_source_number,
                image_name,
                len(converted_blocks),
                str(page_json),
                str(image_path),
            ]
        )

    input_json = output_dir / "input.json"

    with input_json.open("w", encoding="utf-8") as file:
        json.dump(
            pages,
            file,
            ensure_ascii=False,
        )

    manifest_path = output_dir / "manifest.csv"

    with manifest_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.writer(file)

        writer.writerow(
            [
                "page",
                "ramo",
                "legislatura",
                "document_id",
                "page_source_number",
                "image_file",
                "block_count",
                "source_json",
                "source_image",
            ]
        )

        writer.writerows(manifest)

    skipped_path = output_dir / "skipped.csv"

    with skipped_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.writer(file)

        writer.writerow(
            [
                "document_id",
                "page_source_number",
                "source_json",
                "reason",
            ]
        )

        writer.writerows(skipped)

    total_blocks = sum(
        len(page["blocks"])
        for page in pages
    )

    print()
    print("Ramo:", args.ramo)
    print("Legislatura:", args.legislatura)
    print("JSON individuati:", len(source_pages))
    print("Pagine inserite:", len(pages))
    print("Pagine saltate:", len(skipped))
    print("Blocchi complessivi:", total_blocks)
    print("Input:", input_json)
    print("Immagini:", images_dir)
    print("Manifest:", manifest_path)
    print("Skipped:", skipped_path)


if __name__ == "__main__":
    main()
