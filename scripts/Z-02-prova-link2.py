import os
import csv
import argparse


def main(file_csv, output):
    with open(file_csv, newline="", encoding="utf-8") as f, open(output, "w", encoding="utf-8") as out:
        reader = csv.DictReader(f)

        for riga in reader:
            percorso = riga["source_pdf"]

            if os.path.islink(percorso):
                destinazione = os.readlink(percorso)
                out.write(f"{percorso} -> {destinazione}\n")
            else:
                out.write(f"{percorso} NON è un link simbolico\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verifica se i PDF indicati nel CSV sono link simbolici."
    )
    parser.add_argument(
        "file_csv",
        help="Percorso del CSV da leggere.",
    )
    parser.add_argument(
        "output",
        help="Percorso del file di output.",
    )
    args = parser.parse_args()

    main(args.file_csv, args.output)
