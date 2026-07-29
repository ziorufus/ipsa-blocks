# RDF Generation Pipeline

Questa cartella contiene la pipeline per convertire le predizioni dei blocchi parlamentari e i risultati del matching degli speaker in RDF/Turtle, utilizzando l’ontologia IPSA.

## Struttura

```text
scripts/rdf_pipeline/
├── generate_rdf.py
├── legislature.tsv
├── ontologia_ipsa_pipeline.ttl
├── run_rdf_all_regni.sh
├── run_rdf_regno.py
└── README.md
```

## File principali

### `generate_rdf.py`

Genera il file RDF/Turtle a partire da:

* predizioni multiclasse dei blocchi;
* risultati del matching degli speaker;
* tabella di corrispondenza delle legislature;
* ontologia IPSA.

#### Ricostruzione degli `H-speech`

La risoluzione degli `H-speech` viene eseguita direttamente da
`generate_rdf.py` durante la ricostruzione dei blocchi funzionali.

Un blocco `H-speech` viene collegato allo speech della pagina precedente
quando:

* appartiene allo stesso documento;
* la pagina sorgente è immediatamente successiva;
* prima dell’`H-speech` compaiono soltanto header o footer;
* l’ultimo blocco di contenuto della pagina precedente è di tipo `speech`.

In questo caso, i paragrafi delle due pagine vengono aggregati nello stesso
`ipsa:Block`, che mantiene lo speaker associato al precedente `B-speech`.

Se queste condizioni non sono soddisfatte, l’`H-speech` apre un blocco
autonomo e viene segnalato nel riepilogo come `H-speech` orfano.

### `run_rdf_regno.py`

Esegue la generazione RDF per un singolo regno e un singolo ramo parlamentare.

Lo script individua automaticamente:

* `generate_rdf.py`;
* l’ontologia IPSA;
* il file `legislature.tsv`.

La directory contenente i dati dei regni può essere configurata tramite la variabile d’ambiente `IPSA_DATA_ROOT`.

### `run_rdf_all_regni.sh`

Esegue la generazione RDF per Camera e Senato nei regni da `regno_01` a `regno_30`.

Per impostazione predefinita viene eseguito in modalità simulazione (`DRY_RUN=1`).

### `ontologia_ipsa_pipeline.ttl`

Contiene l’ontologia IPSA utilizzata per rappresentare pagine, blocchi,
paragrafi, speaker e presidenze.

Per la descrizione dettagliata del modello concettuale, delle classi e delle
proprietà, si veda [ONTOLOGY.md](ONTOLOGY.md).

### `legislature.tsv`

Contiene il mapping tra gli identificativi normalizzati delle legislature e le relative URI.

## Struttura dei dati attesa

La directory dei dati deve contenere cartelle organizzate nel seguente modo:

```text
DATA_ROOT/
├── regno_01_full/
│   ├── camera/
│   │   ├── predictions_multiclass.json
│   │   └── speaker_matches.json
│   └── senato/
│       ├── predictions_multiclass.json
│       └── speaker_matches.json
├── regno_02_full/
│   ├── camera/
│   └── senato/
└── ...
```

## Input

Per ciascun ramo sono necessari:

```text
predictions_multiclass.json
speaker_matches.json
```

Il file delle predizioni contiene i blocchi classificati dal modello LayoutLMv3.

Il file dei match contiene le associazioni tra gli speaker riconosciuti e le rispettive URI personali.

È possibile fornire al runner di un singolo regno un file di matching alternativo tramite l’opzione:

```text
--speaker-matches
```

Questo è utile, per esempio, quando per il Senato viene usato:

```text
speaker_matches_combinati.json
```

## Output

Per ogni ramo viene creata una cartella:

```text
rdf/
```

contenente il file Turtle:

```text
regno_XX_camera.ttl
regno_XX_senato.ttl
```

Il runner per il singolo regno produce inoltre un log con nome:

```text
regno_XX_camera_rdf.log
regno_XX_senato_rdf.log
```

Il launcher generale utilizza invece:

```text
generate_rdf.log
```

## Generazione di un singolo regno

La sintassi generale è:

```bash
python3 scripts/rdf_pipeline/run_rdf_regno.py \
  --regno NUMERO \
  --ramo camera|senato
```

Il regno può essere indicato in uno dei seguenti modi:

```text
2
02
regno_02
```

### Esempio per la Camera

```bash
IPSA_DATA_ROOT=/percorso/dei/dati \
python3 scripts/rdf_pipeline/run_rdf_regno.py \
  --regno 02 \
  --ramo camera
```

### Esempio per il Senato

```bash
IPSA_DATA_ROOT=/percorso/dei/dati \
python3 scripts/rdf_pipeline/run_rdf_regno.py \
  --regno 02 \
  --ramo senato
```

### File di matching alternativo

```bash
IPSA_DATA_ROOT=/percorso/dei/dati \
python3 scripts/rdf_pipeline/run_rdf_regno.py \
  --regno 02 \
  --ramo senato \
  --speaker-matches \
  /percorso/regno_02_full/senato/speaker_matches_combinati.json
```

## Simulazione

Per mostrare il comando senza generare alcun file:

```bash
IPSA_DATA_ROOT=/percorso/dei/dati \
python3 scripts/rdf_pipeline/run_rdf_regno.py \
  --regno 02 \
  --ramo camera \
  --dry-run
```

## Sovrascrittura dell’output

Per impostazione predefinita, il runner non sovrascrive un file TTL già esistente.

Per rigenerarlo:

```bash
IPSA_DATA_ROOT=/percorso/dei/dati \
python3 scripts/rdf_pipeline/run_rdf_regno.py \
  --regno 02 \
  --ramo camera \
  --overwrite
```

## Generazione per tutti i regni

Il launcher generale controlla Camera e Senato per i regni da `regno_01` a `regno_30`.

### Simulazione

```bash
ROOT=/percorso/dei/dati \
DRY_RUN=1 \
bash scripts/rdf_pipeline/run_rdf_all_regni.sh
```

La simulazione indica:

* gli input mancanti;
* i rami pronti;
* i file RDF da generare o rigenerare.

### Esecuzione reale

```bash
ROOT=/percorso/dei/dati \
DRY_RUN=0 \
bash scripts/rdf_pipeline/run_rdf_all_regni.sh
```

## Configurazione di Python

Il launcher Bash seleziona l’interprete Python nel seguente ordine:

1. usa il valore di `PYTHON_BIN`, se specificato;
2. usa `/home/claudia/layoutlm_env/bin/python`, se presente;
3. usa il comando `python3` disponibile nel sistema.

Esempio:

```bash
ROOT=/percorso/dei/dati \
PYTHON_BIN=/percorso/venv/bin/python \
DRY_RUN=0 \
bash scripts/rdf_pipeline/run_rdf_all_regni.sh
```

## Esecuzione su Rhodes

Su Rhodes, la directory predefinita dei dati è:

```text
/home/claudia/tantospazio
```

Per il singolo regno:

```bash
/home/claudia/layoutlm_env/bin/python \
  scripts/rdf_pipeline/run_rdf_regno.py \
  --regno 02 \
  --ramo camera
```

Per tutti i regni, inizialmente in modalità simulazione:

```bash
DRY_RUN=1 \
bash scripts/rdf_pipeline/run_rdf_all_regni.sh
```

Per eseguire realmente la generazione:

```bash
DRY_RUN=0 \
bash scripts/rdf_pipeline/run_rdf_all_regni.sh
```

## Controlli di sintassi

Per controllare gli script Python:

```bash
python3 -m py_compile \
  scripts/rdf_pipeline/generate_rdf.py \
  scripts/rdf_pipeline/run_rdf_regno.py
```

Per controllare il launcher Bash:

```bash
bash -n scripts/rdf_pipeline/run_rdf_all_regni.sh
```

## Validazione RDF

Il launcher generale verifica ogni file generato caricandolo con `rdflib.Graph`.

Il file temporaneo viene sostituito al TTL definitivo soltanto quando:

* esiste;
* non è vuoto;
* è sintatticamente valido in formato Turtle.

Gli output RDF generati non sono inclusi nella pipeline sorgente e devono essere conservati nelle cartelle `rdf/` dei rispettivi regni.
