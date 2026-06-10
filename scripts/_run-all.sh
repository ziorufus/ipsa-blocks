#!/usr/bin/env bash

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo "### Running A-01-create-gold.py"
python3 A-01-create-gold.py \
  --json ../data-final/gold.json \
  --dots ../dots/ \
  ../data-final/gold.csv \
  ../data-orig/alessio.csv \
  ../data-orig/claudia.csv \
  ../data-orig/samuele.csv

echo "### Running A-02-aggiungi-legislatura.py"
python3 A-02-aggiungi-legislatura.py \
  --json ../data-final/gold.json \
  --csv ../data-orig/gold-resoconti-2-leg.csv \
  --out ../data-final/gold-leg.json

echo "### Running B-01-clean.py"
python3 B-01-clean.py \
  ../data-parl/persone.tsv \
  ../data-final/persone-ok.tsv

echo "### Running B-02-integrate-senato.py"
python3 B-02-integrate-senato.py \
  --persone ../data-final/persone-ok.tsv \
  --legislature ../data-parl/legislature.tsv \
  --senatori ../data-parl/senatori.tsv \
  -o ../data-final/persone+senato.tsv

echo "### Running B-03-integrate-consulta.py"
python3 B-03-integrate-consulta.py \
  --persone ../data-final/persone+senato.tsv \
  --consulta ../data-parl/consulta.tsv \
  -o ../data-final/persone-all.tsv

# python3 C-match_speakers.py \
#   ../data-final/output_con_legislatura.json \
#   ../data-final/persone-all.tsv \
#   matched_speakers.json \
#   --nicknames-tsv nicknames.tsv
