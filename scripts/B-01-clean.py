#!/usr/bin/env python3
import argparse
import csv
import sys


FIELDS = [
    "persona",
    "nome",
    "cognome",
    "dataNascita",
    "dataMorte",
    "riferimento",
    "legislatura",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Rimuove da un file nel formato persone.tsv le righe senza riferimento."
        )
    )
    parser.add_argument("input", help="TSV di input nel formato persone.tsv")
    parser.add_argument("output", help="TSV di output ripulito")
    return parser.parse_args()


def clean(value):
    return (value or "").strip()


def read_tsv(path):
    with open(path, newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file, delimiter="\t")
        missing = [field for field in FIELDS if field not in (reader.fieldnames or [])]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"{path}: colonne mancanti: {joined}")
        return [{field: clean(row.get(field)) for field in FIELDS} for row in reader]


def quote_tsv_value(value):
    value = "" if value is None else str(value)
    if value == "":
        return ""
    return '"' + value.replace('"', '""') + '"'


def write_tsv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as output_file:
        output_file.write("\t".join(quote_tsv_value(field) for field in FIELDS) + "\n")
        for row in rows:
            output_file.write(
                "\t".join(quote_tsv_value(row.get(field, "")) for field in FIELDS)
                + "\n"
            )


def main():
    args = parse_args()

    try:
        rows = read_tsv(args.input)
        cleaned_rows = [row for row in rows if clean(row.get("riferimento"))]
        write_tsv(args.output, cleaned_rows)
    except (OSError, ValueError) as error:
        print(f"Errore: {error}", file=sys.stderr)
        return 1

    removed = len(rows) - len(cleaned_rows)
    print(f"File scritto: {args.output}")
    print(f"Righe lette: {len(rows)}")
    print(f"Righe rimosse senza riferimento: {removed}")
    print(f"Righe totali output: {len(cleaned_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
