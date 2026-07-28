#!/usr/bin/env bash

set -uo pipefail

# Cartella in cui si trovano regno_01_full, regno_02_full, ecc.
# Può essere sovrascritta al lancio:
# ROOT=/percorso/dati bash run_matcher_regni_mancanti.sh
ROOT="${ROOT:-/home/claudia/tantospazio}"

# Cartella che contiene questo script, il matcher e le anagrafiche.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Interprete Python:
# 1. usa PYTHON_BIN, se specificato;
# 2. altrimenti usa il virtual environment di Rhodes, se presente;
# 3. infine usa python3 disponibile nel sistema.
if [[ -n "${PYTHON_BIN:-}" ]]; then
    PY="$PYTHON_BIN"
elif [[ -x "/home/claudia/layoutlm_env/bin/python" ]]; then
    PY="/home/claudia/layoutlm_env/bin/python"
else
    PY="python3"
fi

MATCHER="$SCRIPT_DIR/match_speakers.py"

PERSONE_CAMERA="$SCRIPT_DIR/persone.tsv"
PERSONE_SENATO="$SCRIPT_DIR/persone_e_senatori.tsv"
NICKNAMES="$SCRIPT_DIR/nicknames.tsv"

# DRY_RUN=1: mostra cosa verrebbe eseguito
# DRY_RUN=0: esegue realmente il matcher
DRY_RUN="${DRY_RUN:-1}"

da_eseguire=0
completati=0
gia_presenti=0
input_mancanti=0
falliti=0

echo "============================================================"
echo "MATCHING SPEAKER — REGNI 01–30"
echo "Avvio: $(date)"
echo "DRY_RUN=$DRY_RUN"
echo "============================================================"

for file in \
    "$MATCHER" \
    "$PERSONE_CAMERA" \
    "$PERSONE_SENATO" \
    "$NICKNAMES"
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

        input="$cartella/predictions_multiclass.json"
        output="$cartella/speaker_matches.json"
        output_tmp="$cartella/.speaker_matches.json.tmp"
        log="$cartella/matching.log"

        if [[ "$ramo" == "camera" ]]; then
            ANAGRAFICA="$PERSONE_CAMERA"
        else
            ANAGRAFICA="$PERSONE_SENATO"
        fi

        if [[ ! -s "$input" ]]; then
            echo "⚠️  INPUT MANCANTE: $nome"
            input_mancanti=$((input_mancanti + 1))
            continue
        fi

        if [[ -s "$output" ]]; then
            echo "✅ GIÀ PRESENTE:   $nome"
            gia_presenti=$((gia_presenti + 1))
            continue
        fi

        da_eseguire=$((da_eseguire + 1))

        if [[ "$DRY_RUN" == "1" ]]; then
            echo "▶️  DA ESEGUIRE:    $nome"
            echo "    Anagrafica:     $(basename "$ANAGRAFICA")"
            echo "    Nickname:       $(basename "$NICKNAMES")"
            continue
        fi

        echo
        echo "------------------------------------------------------------"
        echo "INIZIO:      $nome — $(date)"
        echo "Input:       $input"
        echo "Anagrafica:  $ANAGRAFICA"
        echo "Nickname:    $NICKNAMES"
        echo "Output:      $output"
        echo "Log:         $log"
        echo "------------------------------------------------------------"

        rm -f "$output_tmp"

        if "$PY" "$MATCHER" \
            "$input" \
            "$ANAGRAFICA" \
            "$output_tmp" \
            --nicknames-tsv "$NICKNAMES" \
            > "$log" 2>&1
        then
            if "$PY" - "$output_tmp" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])

if not path.is_file() or path.stat().st_size == 0:
    raise SystemExit("Output mancante o vuoto")

with path.open(encoding="utf-8") as handle:
    data = json.load(handle)

if not isinstance(data, list):
    raise SystemExit("L'output JSON non contiene una lista")

print(f"JSON valido: {len(data)} record")
PY
            then
                mv "$output_tmp" "$output"
                completati=$((completati + 1))

                echo "✅ COMPLETATO: $nome — $(date)"
                ls -lh "$output"
                tail -n 8 "$log"
            else
                echo "❌ OUTPUT NON VALIDO: $nome"
                rm -f "$output_tmp"
                falliti=$((falliti + 1))
            fi
        else
            echo "❌ MATCHER FALLITO: $nome"
            tail -n 20 "$log"
            rm -f "$output_tmp"
            falliti=$((falliti + 1))
        fi
    done
done

echo
echo "============================================================"
echo "RIEPILOGO"
echo "============================================================"
echo "Da eseguire individuati: $da_eseguire"
echo "Completati ora:          $completati"
echo "Già presenti:            $gia_presenti"
echo "Input mancanti:          $input_mancanti"
echo "Falliti:                 $falliti"
echo "Fine: $(date)"
echo "============================================================"

if [[ "$falliti" -gt 0 ]]; then
    exit 1
fi
