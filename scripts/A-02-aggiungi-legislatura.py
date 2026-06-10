#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import csv
import sys
from pathlib import Path


def carica_legislature(csv_path: Path) -> list[str]:
    """Restituisce la lista di legislature indicizzata 1-based (indice 0 inutilizzato)."""
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "legislatura" not in reader.fieldnames:
            raise ValueError(f"Colonna 'legislatura' non trovata nel CSV. Colonne presenti: {reader.fieldnames}")
        righe = [None] + [row["legislatura"].strip() for row in reader]
    return righe


def aggiungi_legislatura(json_path: Path, csv_path: Path, output_path: Path) -> None:
    legislature = carica_legislature(csv_path)
    max_pagina_csv = len(legislature) - 1  # indice 0 inutilizzato

    with json_path.open(encoding="utf-8") as f:
        dati = json.load(f)

    max_pagina_json = max(item["page"] for item in dati)
    if max_pagina_csv < max_pagina_json:
        print(
            f"Errore: il CSV ha {max_pagina_csv} righe ma il JSON contiene pagine fino a {max_pagina_json}.",
            file=sys.stderr,
        )
        sys.exit(1)

    risultato = []
    for item in dati:
        pagina = item["page"]
        legislatura = legislature[pagina]
        risultato.append({"page": pagina, "legislatura": legislatura, "blocks": item["blocks"]})

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(risultato, f, ensure_ascii=False, indent=2)

    print(f"Pagine elaborate: {len(risultato)}")
    print(f"File salvato in: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggiunge il campo 'legislatura' a ogni elemento del JSON usando la riga corrispondente nel CSV."
    )
    parser.add_argument("--json", required=True, help="JSON di input (formato gold.json)")
    parser.add_argument("--csv", required=True, help="CSV con colonna 'legislatura' (una riga per pagina)")
    parser.add_argument("--out", required=True, help="JSON di output")
    args = parser.parse_args()

    aggiungi_legislatura(Path(args.json), Path(args.csv), Path(args.out))


if __name__ == "__main__":
    main()
