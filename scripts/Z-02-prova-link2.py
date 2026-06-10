import os
import csv
import re
import argparse


def estrai_ramo_e_legislatura(percorso):
    if "camera" in percorso:
        ramo = "camera"
        m = re.search(r"regno_(\d{2})", percorso)
        if m:
            return ramo, f"regno_{m.group(1)}"
        m = re.search(r"repubblica_(\d{2})", percorso)
        if m:
            return ramo, f"repubblica_{m.group(1)}"
        if re.search(r"consulta_nazionale", percorso):
            return ramo, "consulta_nazionale"
        if re.search(r"costituente", percorso):
            return ramo, "costituente"
        return ramo, None
    elif "senato" in percorso:
        ramo = "senato"
        m = re.search(r"regno_(\d{1,2})", percorso)
        if m:
            return ramo, f"regno_{m.group(1).zfill(2)}"
        return ramo, None
    return None, None


def main(file_csv, output):
    with open(file_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames) + ["ramo", "legislatura"]

        with open(output, "w", newline="", encoding="utf-8") as out:
            writer = csv.DictWriter(out, fieldnames=fieldnames)
            writer.writeheader()

            for riga in reader:
                percorso = riga["source_pdf"]

                if os.path.islink(percorso):
                    destinazione = os.readlink(percorso)
                else:
                    destinazione = percorso

                ramo, legislatura = estrai_ramo_e_legislatura(destinazione)
                riga["ramo"] = ramo or ""
                riga["legislatura"] = legislatura or ""
                writer.writerow(riga)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Risolve i link simbolici dei PDF e aggiunge ramo e legislatura al CSV."
    )
    parser.add_argument(
        "file_csv",
        help="Percorso del CSV da leggere.",
    )
    parser.add_argument(
        "output",
        help="Percorso del file CSV di output.",
    )
    args = parser.parse_args()

    main(args.file_csv, args.output)
