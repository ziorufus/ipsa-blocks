#!/usr/bin/env bash

set -uo pipefail

# Directory contenente regno_01_full, regno_02_full, ecc.
# Può essere sovrascritta al lancio:
# ROOT=/percorso/dati bash run_rdf_all_regni.sh
ROOT="${ROOT:-/home/claudia/tantospazio}"

# Directory della pipeline RDF.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Interprete Python:
# 1. usa PYTHON_BIN, se specificato;
# 2. usa il virtual environment di Rhodes, se presente;
# 3. usa python3 disponibile nel sistema.
if [[ -n "${PYTHON_BIN:-}" ]]; then
    PY="$PYTHON_BIN"
elif [[ -x "/home/claudia/layoutlm_env/bin/python" ]]; then
    PY="/home/claudia/layoutlm_env/bin/python"
else
    PY="python3"
fi

GENERATOR="$SCRIPT_DIR/scripts/generate_rdf.py"
LEGISLATURES="$SCRIPT_DIR/resources/legislature.tsv"
ONTOLOGY="$SCRIPT_DIR/ontology/ontologia_ipsa_pipeline.ttl"

# DRY_RUN=1: mostra cosa verrebbe generato
# DRY_RUN=0: genera realmente i TTL
DRY_RUN="${DRY_RUN:-1}"

pronti=0
completati=0
input_mancanti=0
falliti=0

echo "============================================================"
echo "GENERAZIONE RDF — REGNI 01–30"
echo "Avvio: $(date)"
echo "DRY_RUN=$DRY_RUN"
echo "============================================================"

for file in \
    "$GENERATOR" \
    "$LEGISLATURES" \
    "$ONTOLOGY"
do
    if [[ ! -s "$file" ]]; then
        echo "ERRORE: file mancante o vuoto: $file"
        exit 1
    fi
done

for numero in $(seq -w 1 30); do
    for ramo in camera senato; do

        nome="regno_${numero} ${ramo}"
        cartella="$ROOT/regno_${numero}_full/${ramo}"

        predictions="$cartella/predictions_multiclass.json"
        matches="$cartella/speaker_matches.json"

        rdf_dir="$cartella/rdf"
        output="$rdf_dir/regno_${numero}_${ramo}.ttl"
        output_tmp="$rdf_dir/.regno_${numero}_${ramo}.tmp.ttl"
        log="$rdf_dir/generate_rdf.log"

        if [[ ! -s "$predictions" ]]; then
            echo "⚠️  PREDIZIONI MANCANTI: $nome"
            input_mancanti=$((input_mancanti + 1))
            continue
        fi

        if [[ ! -s "$matches" ]]; then
            echo "⚠️  MATCH MANCANTI:      $nome"
            input_mancanti=$((input_mancanti + 1))
            continue
        fi

        pronti=$((pronti + 1))

        if [[ "$DRY_RUN" == "1" ]]; then
            if [[ -s "$output" ]]; then
                echo "🔄 DA RIGENERARE: $nome"
            else
                echo "▶️  DA GENERARE:   $nome"
            fi

            echo "    Predictions: $(basename "$predictions")"
            echo "    Matches:     $(basename "$matches")"
            echo "    Output:      $output"
            continue
        fi

        mkdir -p "$rdf_dir"
        rm -f "$output_tmp"

        echo
        echo "------------------------------------------------------------"
        echo "INIZIO:      $nome — $(date)"
        echo "Predictions: $predictions"
        echo "Matches:     $matches"
        echo "Output:      $output"
        echo "Log:         $log"
        echo "------------------------------------------------------------"

        if "$PY" "$GENERATOR" \
            --predictions-json "$predictions" \
            --speaker-matches "$matches" \
            --legislatures "$LEGISLATURES" \
            --ontology "$ONTOLOGY" \
            --output "$output_tmp" \
            > "$log" 2>&1
        then
            if "$PY" - "$output_tmp" <<'PY'
import sys
from pathlib import Path
from rdflib import Graph

path = Path(sys.argv[1])

if not path.is_file() or path.stat().st_size == 0:
    raise SystemExit("TTL mancante o vuoto")

graph = Graph()
graph.parse(path, format="turtle")

print(f"Turtle valido: {len(graph)} triple")
PY
            then
                mv -f "$output_tmp" "$output"
                completati=$((completati + 1))

                echo "✅ COMPLETATO: $nome — $(date)"
                ls -lh "$output"
                tail -n 8 "$log"
            else
                echo "❌ TTL NON VALIDO: $nome"
                rm -f "$output_tmp"
                falliti=$((falliti + 1))
            fi
        else
            echo "❌ GENERAZIONE FALLITA: $nome"
            tail -n 30 "$log"
            rm -f "$output_tmp"
            falliti=$((falliti + 1))
        fi
    done
done

echo
echo "============================================================"
echo "RIEPILOGO RDF"
echo "============================================================"
echo "Rami pronti:          $pronti"
echo "Completati ora:       $completati"
echo "Input mancanti:       $input_mancanti"
echo "Falliti:              $falliti"
echo "Fine: $(date)"
echo "============================================================"

if [[ "$falliti" -gt 0 ]]; then
    exit 1
fi
