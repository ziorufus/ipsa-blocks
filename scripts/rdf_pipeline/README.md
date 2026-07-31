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
* risultati del matching degli speaker e delle presidenze;
* tabella di corrispondenza delle legislature;
* ontologia IPSA.

Per la generazione completa deve essere utilizzato `speaker_matches_context.json`, prodotto da `resolve_document_context.py` a partire da `speaker_matches.json`.

Il file contestualizzato conserva i risultati del matching degli speaker e aggiunge i record relativi alle dichiarazioni di presidenza.

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

#### Gestione delle presidenze

Le dichiarazioni di presidenza sono rappresentate dai blocchi con etichetta `B-presidencydeclaration`.

La risoluzione del nome del presidente viene eseguita prima della generazione RDF da:

```text
scripts/matcher/resolve_document_context.py
```

Lo script combina:

```text
predictions_multiclass.json
speaker_matches.json
```

e produce:

```text
speaker_matches_context.json
```

Quando una dichiarazione di presidenza è associata a un solo candidato dotato di URI personale, `generate_rdf.py` aggiunge al blocco funzionale la tripla:

```turtle
<blocco> ipsa:presidenza <URI_della_persona> .
```

I casi ambigui, privi di candidati o privi di un record di matching non ricevono una URI, ma vengono conteggiati nel riepilogo finale della generazione.

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
│   │   ├── speaker_matches.json
│   │   ├── speaker_matches_context.json
│   │   └── rdf/
│   └── senato/
│       ├── predictions_multiclass.json
│       ├── speaker_matches.json
│       ├── speaker_matches_context.json
│       └── rdf/
├── regno_02_full/
│   ├── camera/
│   └── senato/
└── ...
```

## Input

Per la generazione RDF completa sono necessari, per ciascun ramo:

```text
predictions_multiclass.json
speaker_matches_context.json
```

Il file `predictions_multiclass.json` contiene i blocchi classificati dal modello LayoutLMv3.
Il file `speaker_matches_context.json` contiene:
* le associazioni tra gli speaker riconosciuti e le rispettive URI personali;
* le associazioni tra le dichiarazioni di presidenza e le URI dei presidenti;
* gli eventuali casi ambigui o non risolti.

Il file viene prodotto dal passaggio:

```text
speaker_matches.json
        ↓
resolve_document_context.py
        ↓
speaker_matches_context.json
```
Utilizzando direttamente `speaker_matches.json`, le associazioni degli speaker possono essere conservate, ma non sono disponibili i record aggiunti successivamente per le dichiarazioni di presidenza.
È possibile fornire al runner di un singolo regno un file di matching specifico tramite l’opzione:
`--speaker-matches`
Per includere le presidenze, il file indicato deve contenere anche i record relativi ai blocchi B-presidencydeclaration; normalmente si utilizza `speaker_matches_context.json`.


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
  /percorso/regno_02_full/senato/speaker_matches_context.json
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
