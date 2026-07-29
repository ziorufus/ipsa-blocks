#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Esegue la generazione RDF IPSA per un regno e un ramo."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


# La directory della pipeline viene ricavata dalla posizione dello script.
PIPELINE = Path(__file__).resolve().parent

# Directory contenente regno_01_full, regno_02_full, ecc.
# Può essere sovrascritta tramite IPSA_DATA_ROOT.
BASE_DIR = Path(
    os.environ.get(
        "IPSA_DATA_ROOT",
        "/home/claudia/tantospazio",
    )
).expanduser().resolve()

GENERATOR = PIPELINE / "generate_rdf.py"
ONTOLOGY = PIPELINE / "ontologia_ipsa_pipeline.ttl"
LEGISLATURES = PIPELINE / "legislature.tsv"


def normalize_regno(value: str) -> str:
    match = re.fullmatch(
        r"(?:regno[_-]?)?0*(\d+)",
        value.strip().lower(),
    )

    if not match:
        raise argparse.ArgumentTypeError(
            "Usa un valore come 2, 02 oppure regno_02."
        )

    return f"regno_{int(match.group(1)):02d}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera il file RDF/Turtle di un ramo parlamentare."
    )

    parser.add_argument(
        "--regno",
        required=True,
        type=normalize_regno,
        help="Regno da elaborare: 2, 02 o regno_02.",
    )

    parser.add_argument(
        "--ramo",
        required=True,
        choices=["camera", "senato"],
        help="Ramo parlamentare.",
    )

    parser.add_argument(
        "--speaker-matches",
        type=Path,
        help=(
            "File di matching da usare. Se omesso, viene cercato "
            "speaker_matches.json nella cartella del ramo."
        ),
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Sovrascrive un RDF già esistente.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra il comando senza eseguirlo.",
    )

    return parser.parse_args()


def require_file(path: Path, description: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{description} non trovato: {path}")


def main() -> int:
    args = parse_args()

    try:
        branch_dir = BASE_DIR / f"{args.regno}_full" / args.ramo

        predictions = branch_dir / "predictions_multiclass.json"

        matches = (
            args.speaker_matches
            if args.speaker_matches is not None
            else branch_dir / "speaker_matches.json"
        )

        rdf_dir = branch_dir / "rdf"
        output = rdf_dir / f"{args.regno}_{args.ramo}.ttl"
        log = rdf_dir / f"{args.regno}_{args.ramo}_rdf.log"

        require_file(GENERATOR, "Generatore RDF")
        require_file(ONTOLOGY, "Ontologia IPSA")
        require_file(LEGISLATURES, "Mapping delle legislature")
        require_file(predictions, "Predizioni multiclasse")
        require_file(matches, "Matching degli speaker")

        if output.exists() and not args.overwrite:
            raise FileExistsError(
                f"Output già presente: {output}\n"
                "Usa --overwrite per rigenerarlo."
            )

        command = [
            sys.executable,
            str(GENERATOR),
            "--predictions-json",
            str(predictions),
            "--speaker-matches",
            str(matches),
            "--legislatures",
            str(LEGISLATURES),
            "--ontology",
            str(ONTOLOGY),
            "--output",
            str(output),
        ]

        print("=" * 70)
        print(f"Regno:       {args.regno}")
        print(f"Ramo:        {args.ramo}")
        print(f"Predizioni:  {predictions}")
        print(f"Matching:    {matches}")
        print(f"Output RDF:  {output}")
        print(f"Log:         {log}")
        print("=" * 70)
        print("Comando:")
        print(" ".join(str(part) for part in command))

        if args.dry_run:
            print("\nDry run: nessun file generato.")
            return 0

        rdf_dir.mkdir(parents=True, exist_ok=True)

        with log.open("w", encoding="utf-8") as log_handle:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            if process.stdout is None:
                raise RuntimeError("Impossibile leggere l'output del processo.")

            for line in process.stdout:
                print(line, end="")
                log_handle.write(line)
                log_handle.flush()

            return_code = process.wait()

        if return_code != 0:
            raise RuntimeError(
                f"Generazione RDF fallita. Controlla: {log}"
            )

        print(f"\nRDF generato correttamente: {output}")
        return 0

    except Exception as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
