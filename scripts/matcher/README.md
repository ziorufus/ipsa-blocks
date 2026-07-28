# Speaker Matching Pipeline

Questa cartella contiene la pipeline sviluppata per associare gli speaker individuati nei resoconti parlamentari alle rispettive persone presenti nelle anagrafiche della Camera e del Senato.

La pipeline lavora sugli output prodotti dal modello LayoutLMv3 multiclasse e genera, per ogni ramo parlamentare, un file JSON contenente i risultati del matching.

Il precedente matcher del repository rimane separato e invariato nel file:

```text
scripts/C-match_speakers.py
```

## Struttura della cartella

```text
scripts/matcher/
├── match_speakers.py
├── nicknames.tsv
├── persone.tsv
├── persone_e_senatori.tsv
├── run_matcher_regni_mancanti.sh
├── senatori.tsv
├── senatori_con_legislatura.tsv
└── README.md
```

### Script

* `match_speakers.py`: esegue l’estrazione e il matching degli speaker presenti nei blocchi predetti dal modello.
* `run_matcher_regni_mancanti.sh`: applica automaticamente il matcher ai rami Camera e Senato dei regni da `regno_01` a `regno_30`.

### Anagrafiche

* `persone.tsv`: anagrafica utilizzata per il matching dei deputati della Camera.
* `persone_e_senatori.tsv`: anagrafica combinata utilizzata per il matching degli speaker del Senato.
* `nicknames.tsv`: contiene forme alternative, pseudonimi e varianti dei nomi.
* `senatori.tsv`: anagrafica originale dei senatori.
* `senatori_con_legislatura.tsv`: anagrafica dei senatori integrata con l’informazione sulla legislatura.

## Input

Il matcher utilizza come input il file prodotto dalla predizione multiclasse:

```text
predictions_multiclass.json
```

Lo script multiplo si aspetta una struttura delle directory di questo tipo:

```text
ROOT/
├── regno_01_full/
│   ├── camera/
│   │   └── predictions_multiclass.json
│   └── senato/
│       └── predictions_multiclass.json
├── regno_02_full/
│   ├── camera/
│   └── senato/
└── ...
```

Per ciascun regno vengono controllati entrambi i rami:

```text
regno_XX_full/camera/predictions_multiclass.json
regno_XX_full/senato/predictions_multiclass.json
```

## Output

Per ciascun input elaborato viene prodotto:

```text
speaker_matches.json
```

Nella stessa cartella viene inoltre creato il file di log:

```text
matching.log
```

Durante l’elaborazione il risultato viene inizialmente scritto in:

```text
.speaker_matches.json.tmp
```

Il file temporaneo viene rinominato in `speaker_matches.json` soltanto dopo aver verificato che:

* il file esista e non sia vuoto;
* il contenuto sia un JSON valido;
* il livello principale del JSON contenga una lista.

## Esecuzione del singolo matcher

La sintassi generale è:

```bash
python3 scripts/matcher/match_speakers.py \
  INPUT_JSON \
  ANAGRAFICA_TSV \
  OUTPUT_JSON \
  --nicknames-tsv scripts/matcher/nicknames.tsv
```

Esempio per la Camera:

```bash
python3 scripts/matcher/match_speakers.py \
  /percorso/regno_01_full/camera/predictions_multiclass.json \
  scripts/matcher/persone.tsv \
  /percorso/regno_01_full/camera/speaker_matches.json \
  --nicknames-tsv scripts/matcher/nicknames.tsv
```

Esempio per il Senato:

```bash
python3 scripts/matcher/match_speakers.py \
  /percorso/regno_01_full/senato/predictions_multiclass.json \
  scripts/matcher/persone_e_senatori.tsv \
  /percorso/regno_01_full/senato/speaker_matches.json \
  --nicknames-tsv scripts/matcher/nicknames.tsv
```

## Esecuzione sui regni 01–30

Lo script:

```text
run_matcher_regni_mancanti.sh
```

controlla i rami Camera e Senato dei regni da `regno_01` a `regno_30`.

Lo script:

* ignora i rami per i quali manca `predictions_multiclass.json`;
* non sovrascrive un file `speaker_matches.json` già presente e non vuoto;
* utilizza `persone.tsv` per la Camera;
* utilizza `persone_e_senatori.tsv` per il Senato;
* utilizza `nicknames.tsv` per entrambi i rami;
* verifica la validità dell’output prima di salvarlo definitivamente;
* produce un riepilogo finale delle elaborazioni.

## Simulazione

Per impostazione predefinita lo script utilizza:

```bash
DRY_RUN=1
```

In questa modalità mostra quali regni sarebbero elaborati senza eseguire realmente il matcher:

```bash
bash scripts/matcher/run_matcher_regni_mancanti.sh
```

La stessa modalità può essere indicata esplicitamente:

```bash
DRY_RUN=1 \
bash scripts/matcher/run_matcher_regni_mancanti.sh
```

## Esecuzione reale

Per eseguire realmente il matching:

```bash
DRY_RUN=0 \
bash scripts/matcher/run_matcher_regni_mancanti.sh
```

## Configurazione della directory dei dati

Su Rhodes, la directory predefinita contenente le cartelle dei regni è:

```text
/home/claudia/tantospazio
```

È possibile utilizzare una directory diversa impostando la variabile `ROOT`:

```bash
ROOT=/percorso/dei/dati \
DRY_RUN=1 \
bash scripts/matcher/run_matcher_regni_mancanti.sh
```

Per eseguire realmente il matcher su una directory diversa:

```bash
ROOT=/percorso/dei/dati \
DRY_RUN=0 \
bash scripts/matcher/run_matcher_regni_mancanti.sh
```

## Configurazione di Python

Lo script seleziona l’interprete Python nel seguente ordine:

1. usa il percorso specificato nella variabile `PYTHON_BIN`;
2. usa `/home/claudia/layoutlm_env/bin/python`, se presente;
3. usa il comando `python3` disponibile nel sistema.

È possibile specificare manualmente l’interprete:

```bash
ROOT=/percorso/dei/dati \
PYTHON_BIN=/percorso/venv/bin/python \
DRY_RUN=0 \
bash scripts/matcher/run_matcher_regni_mancanti.sh
```

## Esecuzione su Rhodes

Sul server Rhodes, la simulazione può essere avviata con:

```bash
cd /home/claudia/tantospazio/speaker_pipeline

DRY_RUN=1 \
bash run_matcher_regni_mancanti.sh
```

Per avviare l’elaborazione reale:

```bash
cd /home/claudia/tantospazio/speaker_pipeline

DRY_RUN=0 \
bash run_matcher_regni_mancanti.sh
```

## Controllo della sintassi

Per controllare la sintassi dello script Python:

```bash
python3 -m py_compile scripts/matcher/match_speakers.py
```

Per controllare la sintassi dello script Bash:

```bash
bash -n scripts/matcher/run_matcher_regni_mancanti.sh
```
