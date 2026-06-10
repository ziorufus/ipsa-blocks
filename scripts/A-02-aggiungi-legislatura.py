#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Aggiunge a ogni pagina di output.json la legislatura/periodo indicata nel CSV.

Input:
- output.json
- regni_percorsi_resoconti2 copia.csv

Output:
- output_con_legislatura.json

La corrispondenza viene fatta tra:
- JSON: campo "page"
- CSV: colonna "Page ID"
Il valore aggiunto al JSON viene preso dalla colonna CSV "periodo"
e salvato nel nuovo campo "legislatura".
"""

import argparse
import json
from pathlib import Path

import pandas as pd


def carica_mappa_legislature(csv_path: Path) -> dict[int, str]:
    df = pd.read_csv(csv_path)

    # Normalizza i nomi delle colonne per evitare problemi di spazi iniziali/finali.
    df.columns = [col.strip() for col in df.columns]

    colonne_richieste = {"Page ID", "periodo"}
    colonne_mancanti = colonne_richieste - set(df.columns)
    if colonne_mancanti:
        raise ValueError(f"Colonne mancanti nel CSV: {', '.join(sorted(colonne_mancanti))}")

    df = df[["Page ID", "periodo"]].dropna(subset=["Page ID", "periodo"]).copy()
    df["Page ID"] = df["Page ID"].astype(int)

    # Verifica che una stessa pagina non sia associata a legislature diverse.
    conflitti = df.groupby("Page ID")["periodo"].nunique()
    pagine_conflitto = conflitti[conflitti > 1]
    if not pagine_conflitto.empty:
        raise ValueError(
            "Alcune pagine hanno più valori diversi in 'periodo': "
            + ", ".join(map(str, pagine_conflitto.index.tolist()))
        )

    return df.drop_duplicates("Page ID").set_index("Page ID")["periodo"].to_dict()


def aggiungi_legislatura(json_path: Path, csv_path: Path, output_path: Path) -> None:
    mappa_legislature = carica_mappa_legislature(csv_path)

    with json_path.open("r", encoding="utf-8") as f:
        dati = json.load(f)

    pagine_senza_legislatura = []

    for pagina in dati:
        page_id = pagina.get("page")
        try:
            page_id_int = int(page_id)
        except (TypeError, ValueError):
            pagine_senza_legislatura.append(page_id)
            pagina["legislatura"] = None
            continue

        legislatura = mappa_legislature.get(page_id_int)
        pagina["legislatura"] = legislatura

        if legislatura is None:
            pagine_senza_legislatura.append(page_id)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=2)

    print(f"File salvato in: {output_path}")
    print(f"Pagine elaborate: {len(dati)}")

    if pagine_senza_legislatura:
        print(
            "Attenzione: non è stata trovata una legislatura per queste pagine: "
            + ", ".join(map(str, pagine_senza_legislatura))
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggiunge il campo 'legislatura' a ogni pagina di un JSON usando un CSV di mapping."
    )
    parser.add_argument("--json", default="output.json", help="Percorso del file JSON di input")
    parser.add_argument("--csv", default="regni_percorsi_resoconti2 copia.csv", help="Percorso del file CSV")
    parser.add_argument("--out", default="output_con_legislatura.json", help="Percorso del JSON di output")
    args = parser.parse_args()

    aggiungi_legislatura(Path(args.json), Path(args.csv), Path(args.out))


if __name__ == "__main__":
    main()
