import os
import csv

file_csv = "./parlamento/gold-resoconti-2.csv"
output = "destinazioni_link.txt"

with open(file_csv, newline="", encoding="utf-8") as f, open(output, "w", encoding="utf-8") as out:
    reader = csv.DictReader(f)

    for riga in reader:
        percorso = riga["source_pdf"]

        if os.path.islink(percorso):
            destinazione = os.readlink(percorso)
            out.write(f"{percorso} -> {destinazione}\n")
        else:
            out.write(f"{percorso} NON è un link simbolico\n")