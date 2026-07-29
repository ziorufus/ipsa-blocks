#!/usr/bin/env python3
# coding: utf-8

"""
Assegna una o più legislature a ciascun mandato presente in senatori.tsv
in base alla sovrapposizione tra:
- intervallo del mandato: dataInizioMandato - dataFineMandato
- intervallo della legislatura: dataInizio - dataFine

Può inoltre creare un TSV unificato, adatto al matcher, combinando
persone.tsv e i senatori con legislatura assegnata.

Le date devono essere nel formato YYYYMMDD.
"""

import argparse
import csv
from pathlib import Path


DATE_MAX = "99991231"
REQUIRED_SENATORS = {
    "persona",
    "nome",
    "cognome",
    "datainiziomandato",
    "datafinemandato",
}
REQUIRED_LEGISLATURES = {
    "legislatura",
    "datainizio",
    "datafine",
}
REQUIRED_PEOPLE = {
    "persona",
    "nome",
    "cognome",
    "legislatura",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Assegna ai senatori le legislature sovrapposte al loro mandato."
        )
    )
    parser.add_argument("--senatori", required=True, help="Input senatori.tsv")
    parser.add_argument(
        "--legislature",
        required=True,
        help="Input legislature.tsv con dataInizio e dataFine",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output senatori_con_legislatura.tsv",
    )
    parser.add_argument(
        "--review-output",
        required=True,
        help="Output TSV dei record non assegnabili automaticamente",
    )
    parser.add_argument(
        "--persone",
        help="Input opzionale persone.tsv da unire ai senatori",
    )
    parser.add_argument(
        "--combined-output",
        help=(
            "Output opzionale persona/nome/cognome/legislatura "
            "per il matcher"
        ),
    )
    args = parser.parse_args()

    if bool(args.persone) != bool(args.combined_output):
        parser.error(
            "--persone e --combined-output devono essere usati insieme."
        )

    return args


def normalise_header(fieldnames):
    return {
        field.strip().lower(): field
        for field in (fieldnames or [])
    }


def require_columns(path, fieldnames, required):
    header = normalise_header(fieldnames)
    missing = required - set(header)

    if missing:
        raise ValueError(
            f"Colonne mancanti in {path}: "
            + ", ".join(sorted(missing))
        )

    return header


def valid_date(value):
    return (
        value == ""
        or (len(value) == 8 and value.isdigit())
    )


def read_tsv(path):
    with Path(path).open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file, delimiter="\t")
        fieldnames = reader.fieldnames
        rows = list(reader)

    if not fieldnames:
        raise ValueError(f"Intestazione assente: {path}")

    return fieldnames, rows


def write_tsv(path, fieldnames, rows):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            delimiter="\t",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def intervals_overlap(start_a, end_a, start_b, end_b):
    """True se gli intervalli chiusi [a] e [b] si sovrappongono."""
    return start_a <= end_b and end_a >= start_b


def main():
    args = parse_args()

    senators_fields, senators_rows = read_tsv(args.senatori)
    senators_header = require_columns(
        args.senatori,
        senators_fields,
        REQUIRED_SENATORS,
    )

    legislature_fields, legislature_rows = read_tsv(args.legislature)
    legislature_header = require_columns(
        args.legislature,
        legislature_fields,
        REQUIRED_LEGISLATURES,
    )

    legislatures = []

    for row_number, row in enumerate(legislature_rows, start=2):
        uri = row[legislature_header["legislatura"]].strip()
        start = row[legislature_header["datainizio"]].strip()
        end = row[legislature_header["datafine"]].strip()

        if not uri or not valid_date(start) or not valid_date(end):
            raise ValueError(
                f"Legislatura non valida alla riga {row_number}: "
                f"{uri!r}, {start!r}, {end!r}"
            )

        if not start or not end or end < start:
            raise ValueError(
                f"Intervallo legislatura non valido alla riga "
                f"{row_number}: {uri}"
            )

        legislatures.append(
            {
                "legislatura": uri,
                "start": start,
                "end": end,
            }
        )

    output_fields = list(senators_fields)

    if "legislatura" not in {
        field.strip().lower()
        for field in output_fields
    }:
        output_fields.append("legislatura")

    output_rows = []
    review_rows = []
    seen_assignments = set()

    review_fields = list(senators_fields) + ["review_reason"]

    for row_number, row in enumerate(senators_rows, start=2):
        persona = row[senators_header["persona"]].strip()
        start = row[senators_header["datainiziomandato"]].strip()
        end_raw = row[senators_header["datafinemandato"]].strip()

        if not valid_date(start) or not valid_date(end_raw):
            review = dict(row)
            review["review_reason"] = "invalid_date_format"
            review_rows.append(review)
            continue

        if not start:
            review = dict(row)
            review["review_reason"] = "missing_start_date"
            review_rows.append(review)
            continue

        end = end_raw or DATE_MAX

        if end < start:
            review = dict(row)
            review["review_reason"] = "end_before_start"
            review_rows.append(review)
            continue

        matches = [
            leg["legislatura"]
            for leg in legislatures
            if intervals_overlap(
                start,
                end,
                leg["start"],
                leg["end"],
            )
        ]

        if not matches:
            review = dict(row)
            review["review_reason"] = "no_legislature_overlap"
            review_rows.append(review)
            continue

        for legislature_uri in matches:
            key = (persona, legislature_uri)

            # Lo stesso senatore può comparire in più righe di mandato.
            # Per il matcher basta una sola riga persona-legislatura.
            if key in seen_assignments:
                continue

            seen_assignments.add(key)
            output = dict(row)
            output["legislatura"] = legislature_uri
            output_rows.append(output)

    write_tsv(
        args.output,
        output_fields,
        output_rows,
    )
    write_tsv(
        args.review_output,
        review_fields,
        review_rows,
    )

    print(f"Righe di senatori in input : {len(senators_rows)}")
    print(f"Assegnazioni univoche      : {len(output_rows)}")
    print(f"Record da controllare      : {len(review_rows)}")
    print(f"Output                     : {args.output}")
    print(f"Review                     : {args.review_output}")

    if args.persone:
        people_fields, people_rows = read_tsv(args.persone)
        people_header = require_columns(
            args.persone,
            people_fields,
            REQUIRED_PEOPLE,
        )

        combined_rows = []
        combined_seen = set()

        def add_combined(persona, nome, cognome, legislature_uri):
            key = (persona, legislature_uri)

            if not persona or not legislature_uri or key in combined_seen:
                return

            combined_seen.add(key)
            combined_rows.append(
                {
                    "persona": persona,
                    "nome": nome,
                    "cognome": cognome,
                    "legislatura": legislature_uri,
                }
            )

        for row in people_rows:
            add_combined(
                row[people_header["persona"]].strip(),
                row[people_header["nome"]].strip(),
                row[people_header["cognome"]].strip(),
                row[people_header["legislatura"]].strip(),
            )

        for row in output_rows:
            add_combined(
                row[senators_header["persona"]].strip(),
                row[senators_header["nome"]].strip(),
                row[senators_header["cognome"]].strip(),
                row["legislatura"].strip(),
            )

        write_tsv(
            args.combined_output,
            ["persona", "nome", "cognome", "legislatura"],
            combined_rows,
        )

        print(
            f"Righe nel file combinato   : {len(combined_rows)}"
        )
        print(
            f"File combinato             : "
            f"{args.combined_output}"
        )


if __name__ == "__main__":
    main()
