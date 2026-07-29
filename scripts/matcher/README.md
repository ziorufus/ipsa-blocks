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
├── assegna_legislature_senatori.py
├── extract_speaker_review.py
├── match_speakers.py
├── nicknames.tsv
├── persone.tsv
├── persone_e_senatori.tsv
├── prepare_speaker_manual_review.py
├── resolve_document_context.py
├── run_matcher_regni_mancanti.sh
├── senatori.tsv
├── senatori_con_legislatura.tsv
└── README.md
```

### Script

* `match_speakers.py`: esegue l’estrazione e il matching degli speaker presenti nei blocchi predetti dal modello.
* `run_matcher_regni_mancanti.sh`: applica automaticamente il matcher ai rami Camera e Senato dei regni da `regno_01` a `regno_30`.
* `assegna_legislature_senatori.py`: associa ai mandati dei senatori le legislature temporalmente compatibili. Produce `senatori_con_legislatura.tsv`, un file con i record da controllare e, facoltativamente, l’anagrafica unificata `persone_e_senatori.tsv`.
* `extract_speaker_review.py`: estrae da `speaker_matches.json` i casi ambigui e non assegnati, li collega ai blocchi di `predictions_multiclass.json` e genera i TSV per la revisione.
* `prepare_speaker_manual_review.py`: combina le occorrenze problematiche con i candidati originali del matcher e produce il TSV finale da compilare manualmente.
* `resolve_document_context.py`: risolve la persona che presiede la seduta a partire dai blocchi B-presidencydeclaration e associa tale persona ai successivi turni PRESIDENTE.


### Anagrafiche

* `persone.tsv`: anagrafica utilizzata per il matching dei deputati della Camera.
* `persone_e_senatori.tsv`: anagrafica combinata utilizzata per il matching degli speaker del Senato.
* `nicknames.tsv`: contiene forme alternative, pseudonimi e varianti dei nomi.
* `senatori.tsv`: anagrafica originale dei senatori.
* `senatori_con_legislatura.tsv`: anagrafica dei senatori integrata con l’informazione sulla legislatura.

## Preparazione dell’anagrafica del Senato

Lo script `assegna_legislature_senatori.py` assegna una o più legislature a ciascun mandato presente in `senatori.tsv`, verificando la sovrapposizione tra l’intervallo temporale del mandato e quello della legislatura.

Lo script richiede:

* `senatori.tsv`;
* un TSV delle legislature con le colonne `legislatura`, `dataInizio` e `dataFine`;
* il percorso di destinazione di `senatori_con_legislatura.tsv`;
* il percorso di un TSV contenente i record non assegnabili automaticamente.

Esempio:

```bash
python3 scripts/matcher/assegna_legislature_senatori.py \
  --senatori scripts/matcher/senatori.tsv \
  --legislature PERCORSO/legislature.tsv \
  --output scripts/matcher/senatori_con_legislatura.tsv \
  --review-output senatori_da_controllare.tsv
```

È possibile creare contemporaneamente l’anagrafica unificata utilizzata per il Senato:

```bash
python3 scripts/matcher/assegna_legislature_senatori.py \
  --senatori scripts/matcher/senatori.tsv \
  --legislature PERCORSO/legislature.tsv \
  --output scripts/matcher/senatori_con_legislatura.tsv \
  --review-output senatori_da_controllare.tsv \
  --persone scripts/matcher/persone.tsv \
  --combined-output scripts/matcher/persone_e_senatori.tsv
```

Il file indicato con `--review-output` contiene i record con date mancanti o non valide e quelli per i quali non è stata individuata alcuna sovrapposizione con una legislatura.

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

## Estrazione dei casi da revisionare

Il matcher conserva in `speaker_matches.json` anche i casi che non possono essere risolti automaticamente.

Sono considerati problematici:

* `unassigned`: nessuna persona candidata;
* `ambiguous`: più persone candidate.

Lo script `extract_speaker_review.py` collega questi risultati ai blocchi originali di `predictions_multiclass.json` e aggiunge il testo precedente, il testo dello speaker e il testo successivo.

Esempio:

```bash
python3 scripts/matcher/extract_speaker_review.py \
  --predictions-json predictions_multiclass.json \
  --speaker-matches speaker_matches.json \
  --occurrences-output speaker_review_occurrences.tsv \
  --aliases-output speaker_review_aliases.tsv
```

Gli output sono:

* `speaker_review_occurrences.tsv`: una riga per ogni occorrenza ambigua o non assegnata, con il contesto del blocco;
* `speaker_review_aliases.tsv`: raggruppamento delle occorrenze per ramo, legislatura e forma normalizzata dello speaker.

È possibile limitare l’estrazione a una sola legislatura:

```bash
python3 scripts/matcher/extract_speaker_review.py \
  --predictions-json predictions_multiclass.json \
  --speaker-matches speaker_matches.json \
  --occurrences-output speaker_review_occurrences.tsv \
  --aliases-output speaker_review_aliases.tsv \
  --legislatura regno_01
```

## Preparazione del file di revisione manuale

Lo script `prepare_speaker_manual_review.py` combina le occorrenze problematiche con i candidati originali presenti in `speaker_matches.json`.

Esempio:

```bash
python3 scripts/matcher/prepare_speaker_manual_review.py \
  --occurrences speaker_review_occurrences.tsv \
  --speaker-matches speaker_matches.json \
  --output speaker_manual_review.tsv
```

Il file `speaker_manual_review.tsv` contiene:

* i dati identificativi del blocco;
* `raw_speaker` e `clean_speaker`;
* il tipo di problema;
* il metodo di matching;
* il nome e l’URI di ciascun candidato;
* il contesto testuale;
* campi vuoti per registrare la decisione manuale.

I principali campi da compilare sono:

* `decision`;
* `scope`;
* `selected_persona`;
* `selected_name`;
* `note`.

Gli script di revisione preparano i dati, ma non modificano automaticamente `speaker_matches.json` o `nicknames.tsv`.

## Aggiornamento di `nicknames.tsv`

Dopo la revisione manuale, i casi inizialmente classificati come `unassigned` e risolti con certezza devono essere registrati in:

```text
scripts/matcher/nicknames.tsv
```

Il file deve contenere le colonne:

```text
persona nickname  legislatura
```

Per ciascun caso risolto devono essere indicati:

* `persona`: URI della persona selezionata;
* `nickname`: forma alternativa o forma OCR da riconoscere;
* `legislatura`: URI della legislatura nella quale la forma è attestata.

In genere, il valore di `nickname` corrisponde a `clean_speaker`, salvo che sia necessario conservare una diversa variante grafica.

Esempio:

```text
http://dati.camera.it/ocd/persona.rdf/pr12345 DE AZEGLIO  http://dati.camera.it/ocd/legislatura.rdf/regno_01
```

La legislatura deve essere sempre specificata: la stessa forma può identificare persone diverse in legislature differenti.

Dopo aver aggiornato `nicknames.tsv`, il matcher deve essere eseguito nuovamente. Poiché `run_matcher_regni_mancanti.sh` non sovrascrive un `speaker_matches.json` già esistente, è possibile eseguire il singolo matcher creando inizialmente un nuovo output:

```bash
python3 scripts/matcher/match_speakers.py \
  predictions_multiclass.json \
  ANAGRAFICA.tsv \
  speaker_matches_revised.json \
  --nicknames-tsv scripts/matcher/nicknames.tsv
```

Dopo aver verificato il nuovo JSON, questo può sostituire il precedente `speaker_matches.json`.

È poi opportuno rigenerare i TSV di revisione per controllare quali casi rimangano ancora ambigui o non assegnati.

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
## Risoluzione della presidenza a livello di documento

Lo script:

```text
resolve_document_context.py
```

completa il matching degli speaker utilizzando informazioni che possono essere ricostruite soltanto considerando l’ordine dei blocchi nell’intero documento.

Deve essere eseguito **dopo** `match_speakers.py` e dopo l’eventuale aggiornamento di `nicknames.tsv`, ma **prima** della generazione RDF.

L’ordine consigliato è:

```text
predictions_multiclass.json
        ↓
match_speakers.py
        ↓
speaker_matches.json
        ↓
eventuale revisione manuale e aggiornamento di nicknames.tsv
        ↓
resolve_document_context.py
        ↓
speaker_matches_context.json
        ↓
generate_rdf.py
```

### Funzioni dello script

Lo script:

* raggruppa le pagine per `ramo`, `legislatura` e `document_id`;
* ordina le pagine e i blocchi secondo la loro posizione nel documento;
* individua i blocchi `B-presidencydeclaration`;
* estrae il nome della persona che presiede;
* distingue il ruolo `presidente` dal ruolo `vice-presidente`;
* associa il nome estratto all’anagrafica della Camera o del Senato;
* mantiene una sola presidenza attiva alla volta;
* sostituisce la presidenza corrente quando incontra una nuova dichiarazione;
* interrompe la propagazione se una nuova dichiarazione non viene risolta in modo univoco;
* associa la persona che presiede ai successivi blocchi `B-speech` il cui testo inizia con `PRESIDENTE` o `IL PRESIDENTE`;
* conserva tutti i record già presenti in `speaker_matches.json`;
* produce un nuovo JSON senza modificare gli input.

Per esempio:

```text
PRESIDENZA DEL VICE-PRESIDENTE MAMIANI
...
PRESIDENTE. La seduta è aperta.
```

viene interpretato come:

```text
persona che presiede: Mamiani
ruolo: vice-presidente
speaker del turno PRESIDENTE: Mamiani
```

Il termine `PRESIDENTE` all’inizio del turno indica la persona che dirige la seduta in quel momento, anche quando la dichiarazione precedente la qualifica formalmente come `vice-presidente`.

I turni che iniziano esplicitamente con `VICE-PRESIDENTE` non vengono risolti mediante questa propagazione e restano affidati al normale matching degli speaker.

### Cambi di presidenza

Nel corso dello stesso documento possono comparire più dichiarazioni:

```text
PRESIDENZA DEL PRESIDENTE FARINI
...
PRESIDENZA DEL VICE-PRESIDENTE MAMIANI
...
PRESIDENZA DEL PRESIDENTE FARINI
```

Ogni nuova dichiarazione sostituisce quella precedente. Se la nuova dichiarazione è ambigua, non contiene un nome estraibile oppure non produce un candidato univoco, la presidenza precedente viene disattivata per evitare attribuzioni errate.

### Input

Lo script richiede:

* `--predictions-json`: il file `predictions_multiclass.json`;
* `--speaker-matches`: il file `speaker_matches.json` prodotto dal matcher;
* `--anagrafica-tsv`: `persone.tsv` per la Camera oppure `persone_e_senatori.tsv` per il Senato;
* `--output`: il nuovo JSON con la presidenza risolta.

Sono inoltre disponibili:

* `--nicknames-tsv`: file opzionale con le varianti onomastiche;
* `--fuzzy-threshold`: soglia del fuzzy matching, con lo stesso valore predefinito utilizzato da `match_speakers.py`.

### Output

È consigliato utilizzare un nome distinto dall’output originale:

```text
speaker_matches_context.json
```

Il file contiene:

* tutti i record originali di `speaker_matches.json`;
* i match relativi ai blocchi `B-presidencydeclaration`;
* i turni `PRESIDENTE` risolti mediante il contesto documentale;
* il campo `presiding_role`, con valore `presidente` oppure `vice-presidente`;
* per i turni propagati, `source_presidency_page` e `source_presidency_block_seq`, che indicano la dichiarazione da cui deriva l’associazione.

Il metodo assegnato ai turni risolti attraverso la presidenza è:

```text
presidency_context
```

### Esempio per la Camera

```bash
python3 scripts/matcher/resolve_document_context.py \
  --predictions-json /percorso/regno_01_full/camera/predictions_multiclass.json \
  --speaker-matches /percorso/regno_01_full/camera/speaker_matches.json \
  --anagrafica-tsv scripts/matcher/persone.tsv \
  --nicknames-tsv scripts/matcher/nicknames.tsv \
  --output /percorso/regno_01_full/camera/speaker_matches_context.json
```

### Esempio per il Senato

```bash
python3 scripts/matcher/resolve_document_context.py \
  --predictions-json /percorso/regno_01_full/senato/predictions_multiclass.json \
  --speaker-matches /percorso/regno_01_full/senato/speaker_matches.json \
  --anagrafica-tsv scripts/matcher/persone_e_senatori.tsv \
  --nicknames-tsv scripts/matcher/nicknames.tsv \
  --output /percorso/regno_01_full/senato/speaker_matches_context.json
```

### Controlli consigliati

Prima di usare il nuovo JSON per la generazione RDF, è opportuno verificare nel riepilogo:

* il numero delle dichiarazioni di presidenza individuate;
* il numero delle presidenze risolte in modo univoco;
* il numero dei turni `PRESIDENTE` risolti;
* il numero dei turni `PRESIDENTE` rimasti senza contesto.

Il file originale `speaker_matches.json` non viene sovrascritto.