# Pipeline LayoutLMv3 + BiLSTM

Questa cartella contiene gli script per:

1. preparare gli output DoTS di una legislatura;
2. addestrare e valutare un classificatore multiclasse dei blocchi;
3. applicare un checkpoint addestrato a nuove pagine parlamentari.

Il modello combina LayoutLMv3 con una BiLSTM per classificare i blocchi utilizzando:

* il testo OCR;
* le coordinate dei blocchi;
* l’immagine della pagina.

## Script disponibili

### `prepare_legislature.py`

Prepara un dataset per l’inferenza a partire dagli output DoTS di una legislatura.

Lo script produce:

* `input.json`;
* `manifest.csv`;
* `skipped.csv`;
* una cartella `images/` contenente le immagini associate alle pagine.

Per ogni pagina viene copiato, senza ricodifica, il JPG pulito generato da Ghostscript (`<documento>.pdf.out/page-NNN.jpg`), coerente con le immagini usate per l’addestramento (vedi `build_gold_images.py`). Il nome dell’immagine viene registrato nel campo `image_file` di ogni pagina; le pagine senza JPG pulito finiscono in `skipped.csv`.

Con `--dots-images` lo script usa invece l’immagine di visualizzazione DoTS (`<documento>_page_N.jpg`, con i box dei blocchi disegnati), come nella versione precedente.

Esempio:

```bash
python scripts/layoutlm/prepare_legislature.py \
  /path/to/source/regno_02 \
  senato \
  /path/to/output/regno_02 \
  --legislatura regno_02
```

Nel JSON preparato, il campo `label` viene inizializzato con l’etichetta fittizia `B-text`, necessaria per costruire il dataset di inferenza.

Questa etichetta non rappresenta la previsione del modello.

---

### `train_layoutlmv3_bilstm.py`

Addestra e valuta un modello LayoutLMv3 + BiLSTM su JSON annotati manualmente.

Esempio:

```bash
python scripts/layoutlm/train_layoutlmv3_bilstm.py \
  --train-json /path/to/train.json \
  --test-json /path/to/test.json \
  --image-dir /path/to/images \
  --label2id config/layoutlm/label2id_multiclass.json \
  --output-dir /path/to/experiments \
  --epochs 15 \
  --batch-size 1 \
  --num-workers 0
```

Le immagini possono essere in formato JPG, JPEG o PNG.

Quando nel JSON è presente il campo `image_file`, lo script utilizza il nome dell’immagine specificato in quel campo.

#### Dataset legacy con una pagina mancante

Il dataset utilizzato per il training originale presentava una pagina eliminata dalle immagini, mentre nei JSON era stata conservata la numerazione originale.

Per riprodurre quel particolare allineamento è disponibile l’opzione `--legacy-missing-page`.

Esempio:

```bash
python scripts/layoutlm/train_layoutlmv3_bilstm.py \
  --train-json /path/to/train.json \
  --test-json /path/to/test.json \
  --image-dir /path/to/images \
  --aligned-image-dir /path/to/images_aligned \
  --legacy-missing-page 411 \
  --label2id config/layoutlm/label2id_multiclass.json \
  --output-dir /path/to/experiments \
  --epochs 15 \
  --batch-size 1 \
  --num-workers 0
```

In questa modalità lo script crea collegamenti simbolici nella cartella indicata da `--aligned-image-dir`.

L’opzione `--legacy-missing-page` non deve essere utilizzata per i dataset normali.

---

### `predict_layoutlmv3_bilstm.py`

Applica un checkpoint multiclasse a un dataset preparato con `prepare_legislature.py`.

Esempio:

```bash
python scripts/layoutlm/predict_layoutlmv3_bilstm.py \
  --input-json /path/to/input.json \
  --images-dir /path/to/images \
  --label2id config/layoutlm/label2id_multiclass.json \
  --checkpoint /path/to/model_final.pt \
  --output-json /path/to/predictions_multiclass.json \
  --batch-size 1 \
  --num-workers 0 \
  --device cuda
```

Per eseguire un test rapido su poche pagine:

```bash
python scripts/layoutlm/predict_layoutlmv3_bilstm.py \
  --input-json /path/to/input.json \
  --images-dir /path/to/images \
  --label2id config/layoutlm/label2id_multiclass.json \
  --checkpoint /path/to/model_final.pt \
  --output-json /path/to/predictions_test.json \
  --batch-size 1 \
  --num-workers 0 \
  --device cuda \
  --max-pages 3
```

Il parametro `--device` accetta:

* `auto`;
* `cuda`;
* `cpu`.

## Output della predizione

Ogni blocco conserva i campi originali e riceve inoltre:

* `predicted_label`: classe assegnata dal modello;
* `prediction_confidence`: probabilità associata alla classe scelta;
* `prediction_probabilities`: distribuzione delle probabilità su tutte le classi.

Nei dataset preparati per l’inferenza, il campo originale `label` contiene l’etichetta fittizia `B-text`.

La previsione effettiva deve quindi essere letta dal campo:

```text
predicted_label
```

## Mappatura delle etichette

La mappatura tra etichette e identificativi numerici è contenuta in:

```text
config/layoutlm/label2id_multiclass.json
```

Lo script di predizione verifica che questa mappatura coincida con quella salvata nel checkpoint.

## Checkpoint

I checkpoint non sono inclusi nel repository, perché possono avere dimensioni elevate.

Il checkpoint deve contenere almeno:

* `model_state_dict`;
* `label2id`;
* i parametri dell’architettura salvati nel campo `arguments`.

## Dipendenze

Le dipendenze Python generali sono elencate nel file principale:

```text
requirements.txt
```

L’installazione di PyTorch può variare a seconda del sistema operativo, della GPU e della versione CUDA disponibile.

## Test della pipeline JPEG

La pipeline è stata verificata sul Senato del Regno, legislatura `regno_02`.

Risultati del test:

* 123 pagine;
* 3.395 blocchi;
* immagini in formato JPEG;
* nessuna immagine mancante;
* nessun blocco privo di predizione.

Le versioni dell’ambiente utilizzato per il test sono documentate in:

```text
docs/layoutlm-environment.md
```

## Dati gold del modello multiclasse

La cartella contiene i dati gold utilizzati per l’addestramento e la
valutazione del modello LayoutLMv3 + BiLSTM multiclasse.

### Training set

Il file `new_train.json` contiene il training set definitivo:

- 410 pagine;
- 9.012 blocchi;
- 24 classi;
- SHA-256: `f742f78bf5b83178b14326f7a1855a627ed8b676574f4b7b594b3dd5ba2eead6`.

### Test set

Il file `strat-250-test-bbox.json` contiene il test set definitivo:

- 47 pagine;
- 1.035 blocchi;
- 22 classi presenti;
- SHA-256: `453073e59ee0aa6b53484c32c93b766d18a476d32bae15dade0c0ef8d49a717d`.

Il test set è mantenuto separato dal training set e viene utilizzato per
la valutazione finale del modello.

### Struttura dei dati

Ciascun file contiene una lista di pagine. Ogni pagina comprende un
identificativo nel campo `page` e una lista di blocchi OCR nel campo
`blocks`. Per ogni blocco sono conservati testo, coordinate, categoria
OCR, ordine ed etichetta gold.

Le immagini non sono incorporate nei JSON. Durante l’addestramento
vengono caricate da una directory separata e associate alle pagine
attraverso il loro identificativo.

### File della pipeline

- `prepare_legislature.py`: prepara gli input a partire dagli output DoTS.
- `train_layoutlmv3_bilstm.py`: addestra e valuta il modello.
- `predict_layoutlmv3_bilstm.py`: applica il modello a nuove pagine.
- `new_train.json`: gold del training multiclasse definitivo.
- `strat-250-test-bbox.json`: gold del test multiclasse definitivo.

### Verifica dell’integrità

```bash
shasum -a 256 \
  new_train.json \
  strat-250-test-bbox.json
```

### Immagini delle pagine gold

Le immagini non sono incluse nella cartella. Si ricostruiscono dai JPG
originali di `parlamento/pdf` con `build_gold_images.py`:

```bash
python scripts/layoutlm/build_gold_images.py \
  /path/to/parlamento/pdf \
  /path/to/images_gold
```

Lo script legge le pagine da `new_train.json` e `strat-250-test-bbox.json`
e la loro sorgente da `gold_pages_sources.csv`, poi copia
`<pdf>.out/page-NNN.jpg` in `images_gold/<page>.jpg`. Le immagini hanno lo
stesso identificativo del campo `page`, quindi l'addestramento va lanciato
con `--image-dir /path/to/images_gold` e **senza** `--legacy-missing-page`.

Con `--dots-images` lo script copia invece le immagini di visualizzazione
DoTS (`<id>.out/<id>/<id>_page_N.jpg`, con i box dei blocchi), da usare
insieme a `prepare_legislature.py --dots-images`. Le pagine prive di output
DoTS vengono elencate e lo script termina con errore: attualmente mancano le
24 pagine provenienti dalle cartelle `camera/repubblica_*/_l/`.

`gold_pages_sources.csv` è stato ricostruito così:

- pagine 1–300: `data-orig/gold-resoconti-2-leg.csv` (riga = pagina);
- pagina 301: pagina bianca, lo script genera un'immagine bianca;
- pagine 302–380: `data-orig/silver-resoconti-new.csv` (riga = pagina − 301);
- pagina 381: assente dai manifest, è la pagina 37 di
  `senato/10/1990/317963.pdf`;
- pagine 382–460: `data-orig/silver-resoconti-new.csv` (riga = pagina − 302); la
  riga 109 corrisponde alla pagina 411, eliminata dal gold.

Tutte le corrispondenze sono state verificate confrontando il testo gold con
l'output DoTS (o con il TSV di Tesseract per i documenti senza DoTS).

Le immagini usate nell'addestramento originale (`gold-new.pdf`) contenevano,
dalla pagina 302 in poi, la visualizzazione di DoTS con i box dei blocchi.
