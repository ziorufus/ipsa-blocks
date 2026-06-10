#!/usr/bin/env python3
import argparse
import csv
import sys


CONSULTA_LEGISLATURA = "http://dati.camera.it/ocd/legislatura.rdf/consulta_nazionale"
CONSULTA_RIFERIMENTO = "camera"

OUTPUT_FIELDS = [
    "persona",
    "nome",
    "cognome",
    "dataNascita",
    "dataMorte",
    "riferimento",
    "legislatura",
]

CONSULTA_FIELDS = [
    "persona",
    "nome",
    "cognome",
    "dataNascita",
    "dataMorte",
    "valoreConsulta",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Integra l'elenco parlamentari con i membri della Consulta Nazionale."
        )
    )
    parser.add_argument(
        "--persone",
        default="persone-all.tsv",
        help="TSV di input con l'elenco aggiornato dei parlamentari (default: persone-all.tsv)",
    )
    parser.add_argument(
        "--consulta",
        default="consulta.tsv",
        help="TSV di input con i membri della Consulta Nazionale (default: consulta.tsv)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="persone-all-consulta.tsv",
        help="TSV di output (default: persone-all-consulta.tsv)",
    )
    return parser.parse_args()


def read_tsv(path, required_fields):
    with open(path, newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file, delimiter="\t")
        missing = [field for field in required_fields if field not in (reader.fieldnames or [])]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"{path}: colonne mancanti: {joined}")
        return list(reader)


def clean(value):
    return (value or "").strip()


def dedupe_key(row):
    return (
        clean(row.get("persona")),
        clean(row.get("riferimento")),
        clean(row.get("legislatura")),
    )


def output_row(row):
    return {field: clean(row.get(field)) for field in OUTPUT_FIELDS}


def consulta_row(row):
    return {
        "persona": clean(row.get("persona")),
        "nome": clean(row.get("nome")),
        "cognome": clean(row.get("cognome")),
        "dataNascita": clean(row.get("dataNascita")),
        "dataMorte": clean(row.get("dataMorte")),
        "riferimento": CONSULTA_RIFERIMENTO,
        "legislatura": CONSULTA_LEGISLATURA,
    }


def quote_tsv_value(value):
    value = "" if value is None else str(value)
    if value == "":
        return ""
    return '"' + value.replace('"', '""') + '"'


def write_tsv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as output_file:
        output_file.write(
            "\t".join(quote_tsv_value(field) for field in OUTPUT_FIELDS) + "\n"
        )
        for row in rows:
            output_file.write(
                "\t".join(quote_tsv_value(row.get(field, "")) for field in OUTPUT_FIELDS)
                + "\n"
            )


def integrate(persone_rows, consulta_rows):
    normalized_persone = [output_row(row) for row in persone_rows]
    normalized_consulta = [consulta_row(row) for row in consulta_rows]
    output_rows = []
    seen = set()
    original_duplicates = 0
    consulta_duplicates = 0
    added = 0

    for row in normalized_persone:
        key = dedupe_key(row)
        if key in seen:
            original_duplicates += 1
            continue
        seen.add(key)
        output_rows.append(row)

    for row in normalized_consulta:
        key = dedupe_key(row)
        if key in seen:
            consulta_duplicates += 1
            continue
        seen.add(key)
        output_rows.append(row)
        added += 1

    stats = {
        "original_rows": len(persone_rows),
        "consulta_rows": len(consulta_rows),
        "original_duplicates": original_duplicates,
        "consulta_duplicates": consulta_duplicates,
        "duplicates": original_duplicates + consulta_duplicates,
        "added_rows": added,
        "output_rows": len(output_rows),
    }
    return output_rows, stats


def main():
    args = parse_args()

    try:
        persone_rows = read_tsv(args.persone, OUTPUT_FIELDS)
        consulta_rows = read_tsv(args.consulta, CONSULTA_FIELDS)
        output_rows, stats = integrate(persone_rows, consulta_rows)
        write_tsv(args.output, output_rows)
    except (OSError, ValueError) as error:
        print(f"Errore: {error}", file=sys.stderr)
        return 1

    print(f"File scritto: {args.output}")
    print(f"Righe parlamentari lette: {stats['original_rows']}")
    print(f"Righe consulta lette: {stats['consulta_rows']}")
    print(f"Righe consulta aggiunte: {stats['added_rows']}")
    print(f"Duplicati parlamentari saltati: {stats['original_duplicates']}")
    print(f"Duplicati consulta saltati: {stats['consulta_duplicates']}")
    print(f"Duplicati totali saltati: {stats['duplicates']}")
    print(f"Righe totali output: {stats['output_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
