#!/usr/bin/env python3
import argparse
import csv
import sys


OUTPUT_FIELDS = [
    "persona",
    "nome",
    "cognome",
    "dataNascita",
    "dataMorte",
    "riferimento",
    "legislatura",
]

LEGISLATURE_FIELDS = ["legislatura", "dataInizio", "dataFine"]
SENATOR_FIELDS = [
    "persona",
    "nome",
    "cognome",
    "dataNascita",
    "dataMorte",
    "dataInizioMandato",
    "dataFineMandato",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Integra persone.tsv con le legislature del Regno in cui i senatori "
            "erano in carica."
        )
    )
    parser.add_argument(
        "--persone",
        default="persone.tsv",
        help="TSV di input con le persone (default: persone.tsv)",
    )
    parser.add_argument(
        "--legislature",
        default="legislature.tsv",
        help="TSV di input con le legislature (default: legislature.tsv)",
    )
    parser.add_argument(
        "--senatori",
        default="senatori.tsv",
        help="TSV di input con i senatori (default: senatori.tsv)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="persone-integrate-senato.tsv",
        help="TSV di output (default: persone-integrate-senato.tsv)",
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


def is_yyyymmdd(value):
    value = clean(value)
    return len(value) == 8 and value.isdigit()


def overlaps(first_start, first_end, second_start, second_end):
    return first_start <= second_end and second_start <= first_end


def regno_legislatures(rows):
    legislatures = []
    for row in rows:
        legislatura = clean(row.get("legislatura"))
        start = clean(row.get("dataInizio"))
        end = clean(row.get("dataFine"))

        if "regno_" not in legislatura:
            continue
        if not is_yyyymmdd(start) or not is_yyyymmdd(end):
            continue

        legislatures.append(
            {
                "legislatura": legislatura,
                "dataInizio": start,
                "dataFine": end,
            }
        )

    return sorted(legislatures, key=lambda row: row["dataInizio"])


def output_row_from_person(row):
    return {field: clean(row.get(field)) for field in OUTPUT_FIELDS}


def senator_row(senator, legislatura):
    return {
        "persona": clean(senator.get("persona")),
        "nome": clean(senator.get("nome")),
        "cognome": clean(senator.get("cognome")),
        "dataNascita": clean(senator.get("dataNascita")),
        "dataMorte": clean(senator.get("dataMorte")),
        "riferimento": "senato",
        "legislatura": legislatura,
    }


def dedupe_key(row):
    return (
        clean(row.get("persona")),
        clean(row.get("riferimento")),
        clean(row.get("legislatura")),
    )


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


def integrate(persone_rows, legislature_rows, senator_rows):
    output_rows = [output_row_from_person(row) for row in persone_rows]
    legislatures = regno_legislatures(legislature_rows)
    seen = {
        dedupe_key(row)
        for row in output_rows
        if clean(row.get("persona"))
        and clean(row.get("riferimento"))
        and clean(row.get("legislatura"))
    }

    added = 0
    duplicate = 0
    missing_mandate_dates = 0
    invalid_mandate_dates = 0

    for senator in senator_rows:
        mandate_start = clean(senator.get("dataInizioMandato"))
        mandate_end = clean(senator.get("dataFineMandato"))

        if not mandate_start or not mandate_end:
            missing_mandate_dates += 1
            continue
        if not is_yyyymmdd(mandate_start) or not is_yyyymmdd(mandate_end):
            invalid_mandate_dates += 1
            continue

        for legislature in legislatures:
            if not overlaps(
                mandate_start,
                mandate_end,
                legislature["dataInizio"],
                legislature["dataFine"],
            ):
                continue

            row = senator_row(senator, legislature["legislatura"])
            key = dedupe_key(row)
            if key in seen:
                duplicate += 1
                continue

            output_rows.append(row)
            seen.add(key)
            added += 1

    stats = {
        "original_rows": len(persone_rows),
        "regno_legislatures": len(legislatures),
        "senator_rows": len(senator_rows),
        "added_rows": added,
        "skipped_duplicates": duplicate,
        "skipped_missing_mandate_dates": missing_mandate_dates,
        "skipped_invalid_mandate_dates": invalid_mandate_dates,
        "output_rows": len(output_rows),
    }
    return output_rows, stats


def main():
    args = parse_args()

    try:
        persone_rows = read_tsv(args.persone, OUTPUT_FIELDS)
        legislature_rows = read_tsv(args.legislature, LEGISLATURE_FIELDS)
        senator_rows = read_tsv(args.senatori, SENATOR_FIELDS)
        output_rows, stats = integrate(persone_rows, legislature_rows, senator_rows)
        write_tsv(args.output, output_rows)
    except (OSError, ValueError) as error:
        print(f"Errore: {error}", file=sys.stderr)
        return 1

    print(f"File scritto: {args.output}")
    print(f"Righe originali: {stats['original_rows']}")
    print(f"Legislature del Regno considerate: {stats['regno_legislatures']}")
    print(f"Righe senatori lette: {stats['senator_rows']}")
    print(f"Righe aggiunte: {stats['added_rows']}")
    print(f"Duplicati saltati: {stats['skipped_duplicates']}")
    print(
        "Senatori saltati per date mandato mancanti: "
        f"{stats['skipped_missing_mandate_dates']}"
    )
    print(
        "Senatori saltati per date mandato non valide: "
        f"{stats['skipped_invalid_mandate_dates']}"
    )
    print(f"Righe totali output: {stats['output_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
