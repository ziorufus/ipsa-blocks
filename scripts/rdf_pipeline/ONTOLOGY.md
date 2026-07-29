# Ontologia IPSA

Questo documento descrive il modello concettuale utilizzato dalla pipeline RDF
per rappresentare i resoconti parlamentari elaborati dal progetto IPSA.

Per la struttura della cartella, gli input, gli output e le istruzioni di
esecuzione degli script, si veda [README.md](README.md).

## 1. Scopo

L’ontologia IPSA rappresenta i risultati della pipeline composta da:

1. OCR e segmentazione delle pagine;
2. classificazione multimodale dei blocchi con LayoutLMv3;
3. ricostruzione dei blocchi funzionali;
4. estrazione e matching degli speaker;
5. risoluzione del contesto documentale;
6. generazione delle istanze RDF in formato Turtle.

Il modello distingue tre livelli principali:

- la **pagina sorgente** (`ipsa:Page`);
- il **blocco funzionale** (`ipsa:Block`);
- il **paragrafo OCR** (`ipsa:Paragraph`).

Un blocco funzionale può aggregare più paragrafi OCR e può estendersi su più
pagine.

## 2. Namespace

Il namespace principale è:

```turtle
@prefix ipsa:
    <http://www.semanticweb.org/claudia/ontologies/2026/ipsa/> .
```

L’IRI dell’ontologia è:

```text
http://www.semanticweb.org/claudia/ontologies/2026/ipsa
```

I namespace utilizzati sono:

| Prefisso | Namespace | Uso |
|---|---|---|
| `ipsa:` | `http://www.semanticweb.org/claudia/ontologies/2026/ipsa/` | Classi, proprietà e individui definiti dal progetto IPSA |
| `ocd:` | `http://dati.camera.it/ocd/` | Persone, legislature, sedute e altre risorse dei dati della Camera |
| `semparl:` | `http://ldf.fi/schema/semparl/` | Contenuto, speaker e metadati parlamentari |
| `dct:` | `http://purl.org/dc/terms/` | Metadati generali, in particolare la lingua |
| `rdf:` | `http://www.w3.org/1999/02/22-rdf-syntax-ns#` | Tipizzazione RDF |
| `rdfs:` | `http://www.w3.org/2000/01/rdf-schema#` | Domini, range, etichette e commenti |
| `owl:` | `http://www.w3.org/2002/07/owl#` | Definizione dell’ontologia e delle proprietà |
| `xsd:` | `http://www.w3.org/2001/XMLSchema#` | Tipi di dato |

L’ontologia importa i vocabolari OCD e SEMParl:

```turtle
<http://www.semanticweb.org/claudia/ontologies/2026/ipsa>
    a owl:Ontology ;
    owl:imports ocd: ,
                semparl: .
```

## 3. Modello concettuale

La struttura fondamentale è:

```text
Page
 └── contiene uno o più Paragraph

Block
 ├── appartiene a una o più Page
 ├── ha un FunctionalBlockType
 └── aggrega uno o più Paragraph
```

Le relazioni principali sono:

```text
ipsa:Block ── ipsa:hasParagraph ──> ipsa:Paragraph
ipsa:Block ── ipsa:hasPage ───────> ipsa:Page
ipsa:Paragraph ── ipsa:hasPage ───> ipsa:Page
ipsa:Block ── ipsa:hasBlockType ──> ipsa:FunctionalBlockType
```

`ipsa:Paragraph` e `ipsa:Block` sono classi distinte. Un paragrafo non è una
sottoclasse di blocco: è una risorsa collegata al blocco funzionale tramite
`ipsa:hasParagraph`.

## 4. Classi

### `ipsa:Page`

Rappresenta una pagina fisica elaborata dalla pipeline.

Una pagina conserva:

- il numero progressivo nel dataset;
- il numero della pagina nel documento sorgente;
- l’identificativo del documento;
- il ramo parlamentare;
- il nome dell’immagine utilizzata dal modello;
- il collegamento alla legislatura ufficiale.

### `ipsa:Block`

Rappresenta un’unità funzionale del documento, per esempio:

- un intervento parlamentare;
- un titolo;
- un articolo;
- una descrizione;
- un’intestazione;
- un piè di pagina;
- una dichiarazione di presidenza.

Un blocco può essere composto da più paragrafi OCR consecutivi e può essere
collegato a più pagine quando il contenuto continua nella pagina successiva.

### `ipsa:Paragraph`

Rappresenta un singolo blocco OCR prodotto dalla segmentazione della pagina.

Conserva:

- il testo OCR;
- l’ordine nel blocco funzionale;
- la posizione originaria nella pagina;
- la label completa predetta dal modello;
- la confidenza della predizione;
- la categoria OCR originaria;
- il collegamento alla pagina fisica.

### `ipsa:FunctionalBlockType`

Rappresenta la classe degli individui utilizzati come tipi funzionali dei
blocchi.

### `ocd:legislatura`

Classe esterna del vocabolario OCD utilizzata per rappresentare le legislature
ufficiali.

## 5. Tipi funzionali

I tipi funzionali non sono classi, ma individui della classe
`ipsa:FunctionalBlockType`.

```turtle
ipsa:speech a ipsa:FunctionalBlockType .
ipsa:title a ipsa:FunctionalBlockType .
```

Gli individui previsti sono:

| Individuo | Significato |
|---|---|
| `ipsa:article` | Articolo o parte normativa |
| `ipsa:description` | Descrizione narrativa degli eventi della seduta |
| `ipsa:footer` | Piè di pagina |
| `ipsa:header` | Intestazione della pagina |
| `ipsa:other` | Contenuto non riconducibile agli altri tipi |
| `ipsa:presidencydeclaration` | Dichiarazione o formula della Presidenza |
| `ipsa:speech` | Intervento parlamentare |
| `ipsa:speechnotext` | Segnalazione di un intervento senza testo discorsivo |
| `ipsa:text` | Testo generico |
| `ipsa:title` | Titolo o intestazione funzionale del documento |

Il collegamento tra un blocco e il suo tipo è espresso mediante:

```turtle
ipsa:hasBlockType
```

Esempio:

```turtle
<.../block/...>
    a ipsa:Block ;
    ipsa:hasBlockType ipsa:speech .
```

## 6. Proprietà oggetto

### `ipsa:hasBlockType`

Collega un blocco al suo tipo funzionale.

```text
Dominio: ipsa:Block
Range:   ipsa:FunctionalBlockType
```

### `ipsa:hasPage`

Collega un blocco o un paragrafo alla pagina in cui compare.

```text
Dominio: unione di ipsa:Block e ipsa:Paragraph
Range:   ipsa:Page
```

Il dominio è definito mediante `owl:unionOf`:

```turtle
ipsa:hasPage
    a owl:ObjectProperty ;
    rdfs:domain [
        a owl:Class ;
        owl:unionOf (
            ipsa:Block
            ipsa:Paragraph
        )
    ] ;
    rdfs:range ipsa:Page .
```

Un blocco funzionale può avere più valori `ipsa:hasPage`. Ogni paragrafo è
invece collegato alla pagina fisica in cui si trova.

### `ipsa:hasParagraph`

Collega un blocco funzionale ai paragrafi OCR che lo compongono.

```text
Dominio: ipsa:Block
Range:   ipsa:Paragraph
```

### `ocd:rif_leg`

Collega una pagina alla legislatura ufficiale.

```text
Dominio: ipsa:Page
Range:   ocd:legislatura
```

L’URI della legislatura viene recuperata dalla tabella `legislature.tsv`.

### `semparl:speaker`

Collega un blocco di tipo `speech` o `speechnotext` alla persona identificata
nel dataset OCD.

```text
Dominio: ipsa:Block
Range:   ocd:persona
```

La proprietà viene generata soltanto quando il matching restituisce un unico
candidato dotato di URI.

### `ipsa:presidenza`

Collega un blocco di tipo `presidencydeclaration` alla persona che esercita la
Presidenza in quel punto del documento.

```text
Dominio: ipsa:Block
Range:   ocd:persona
```

La proprietà viene valorizzata quando la dichiarazione di presidenza produce
un unico candidato dotato di URI.

### `ipsa:Author`

Proprietà predisposta per collegare un blocco di tipo `article` o `text`
all’autore identificato.

```text
Dominio: ipsa:Block
Range:   ocd:persona
```

### `ocd:rif_seduta`

Proprietà predisposta per collegare un blocco alla seduta parlamentare di
riferimento.

La pipeline corrente non la valorizza ancora.

## 7. Proprietà dei dati della pagina

### `ipsa:pageNumber`

Numero progressivo della pagina nel dataset elaborato.

```text
Dominio: ipsa:Page
Range:   xsd:integer
```

### `ipsa:sourcePageNumber`

Numero della pagina nel documento sorgente.

```text
Dominio: ipsa:Page
Range:   xsd:integer
```

L’indicizzazione può partire da `0`, in base ai metadati di origine.

### `ipsa:documentID`

Identificativo stabile del documento sorgente.

```text
Dominio: ipsa:Page
Range:   xsd:string
```

### `ipsa:ramo`

Ramo parlamentare di provenienza.

```text
Dominio: ipsa:Page
Range:   xsd:string
```

Valori tipici:

```text
camera
senato
```

### `ipsa:imageFile`

Nome dell’immagine utilizzata come input visuale del modello.

```text
Dominio: ipsa:Page
Range:   xsd:string
```

## 8. Proprietà dei dati del blocco

### `semparl:orderNumber`

Posizione iniziale del blocco funzionale nella pagina in cui ha origine.

```text
Dominio: ipsa:Block
Range:   xsd:integer
```

Il valore corrisponde al `block_seq` del primo paragrafo del gruppo.

### `ipsa:speakerLabel`

Conserva una rappresentazione testuale dello speaker.

```text
Dominio: ipsa:Block
Range:   xsd:string
```

La valorizzazione segue queste regole:

| Esito del matching | `ipsa:speakerLabel` | `semparl:speaker` |
|---|---|---|
| Un solo candidato | Nome e cognome del candidato | URI ufficiale della persona |
| Più candidati | Forma normalizzata estratta dal testo | Non generata |
| Nessun candidato | Forma normalizzata estratta dal testo | Non generata |
| Nessun record di matching | Non generata | Non generata |

Esempio di match univoco:

```turtle
<.../block/...>
    ipsa:speakerLabel "Pier Dionigi Pinelli"@it ;
    semparl:speaker
        <http://dati.camera.it/ocd/persona.rdf/pr201> .
```

Esempio di match ambiguo:

```turtle
<.../block/...>
    ipsa:speakerLabel "Pareto"@it .
```

### `ipsa:presidingRole`

Conserva il ruolo formale ricavato dalla dichiarazione di presidenza.

```text
Dominio: ipsa:Block
Range:   rdf:langString
```

I valori attualmente prodotti sono:

```text
presidente
vice-presidente
```

Esempio:

```turtle
<.../block/presidencydeclaration/...>
    ipsa:presidingRole "vice-presidente"@it .
```

La proprietà può essere presente:

- sul blocco `presidencydeclaration`;
- sul blocco `speech` risolto attraverso il contesto della presidenza.

Il ruolo rimane `vice-presidente` anche quando, nel resoconto, il successivo
turno di parola è introdotto dalla forma funzionale `PRESIDENTE`.

### `ipsa:authorLabel`

Proprietà predisposta per conservare la forma testuale dell’autore quando non
sia disponibile un collegamento univoco a una persona.

```text
Dominio: ipsa:Block
Range:   xsd:string
```

La pipeline corrente non la valorizza ancora.

## 9. Proprietà dei dati del paragrafo

### `semparl:content`

Contiene il testo OCR del paragrafo.

```text
Dominio: ipsa:Paragraph
Range:   xsd:string
```

Nelle istanze italiane viene normalmente utilizzato un literal con tag di
lingua:

```turtle
semparl:content "Testo del paragrafo..."@it .
```

### `ipsa:orderID`

Ordine del paragrafo OCR all’interno del blocco funzionale.

```text
Dominio: ipsa:Paragraph
Range:   xsd:integer
```

Per un blocco formato da `B-speech`, `I-speech`, `I-speech`, i tre paragrafi
ricevono rispettivamente i valori `1`, `2` e `3`.

### `ipsa:sourceBlockSequence`

Posizione originaria del blocco OCR nella pagina sorgente.

```text
Dominio: ipsa:Paragraph
Range:   xsd:integer
```

### `ipsa:predictedLabel`

Etichetta completa assegnata dal modello.

```text
Dominio: ipsa:Paragraph
Range:   xsd:string
```

Conserva sia il tipo funzionale sia il prefisso strutturale:

```text
B-speech
I-speech
H-speech
N-speech
U-speech
B-title
I-article
```

Il tipo funzionale normalizzato viene espresso sul blocco mediante
`ipsa:hasBlockType`.

### `ipsa:predictionConfidence`

Confidenza associata alla classe scelta dal modello.

```text
Dominio: ipsa:Paragraph
Range:   xsd:decimal
```

Esempio:

```turtle
ipsa:predictionConfidence 0.998819 .
```

### `ipsa:ocrCategory`

Categoria originaria assegnata dal sistema OCR.

```text
Dominio: ipsa:Paragraph
Range:   xsd:string
```

Valori possibili dipendono dal sistema OCR e possono includere, per esempio,
`Text`, `Title`, `Page-header` e `Page-footer`.

## 10. Blocchi multipagina

Un `ipsa:Block` può essere collegato a più risorse `ipsa:Page` quando una stessa
unità funzionale continua nella pagina successiva.

I singoli blocchi OCR rimangono rappresentati come risorse
`ipsa:Paragraph`, ciascuna collegata alla propria pagina sorgente.

Esempio concettuale:

```text
ipsa:Block di tipo ipsa:speech
├── Paragraph B-speech della pagina 10
├── Paragraph I-speech della pagina 10
├── Paragraph H-speech della pagina 11
└── Paragraph I-speech della pagina 11
```

In questo caso:

```text
Block ──hasPage──> Page 10
Block ──hasPage──> Page 11
```

La label `H-speech` viene conservata sul paragrafo mediante
`ipsa:predictedLabel`. Le regole operative utilizzate da `generate_rdf.py` per
decidere quando collegare un `H-speech` al blocco precedente sono descritte nel
[README.md](README.md).

## 11. Modellazione degli speaker

Il collegamento a una persona viene espresso sul blocco funzionale, non sui
singoli paragrafi:

```text
ipsa:Block ── semparl:speaker ──> ocd:persona
```

Questa scelta consente a tutti i paragrafi che compongono lo stesso intervento,
anche su più pagine, di condividere lo stesso speaker.

Quando il matching non è univoco, viene conservata soltanto la forma testuale
mediante `ipsa:speakerLabel`.

## 12. Modellazione della presidenza

La dichiarazione di presidenza è rappresentata come un blocco funzionale:

```turtle
<.../block/...>
    a ipsa:Block ;
    ipsa:hasBlockType ipsa:presidencydeclaration ;
    ipsa:presidenza
        <http://dati.camera.it/ocd/persona.rdf/pr...> ;
    ipsa:presidingRole "vice-presidente"@it .
```

`ipsa:presidenza` identifica la persona, mentre `ipsa:presidingRole` conserva il
ruolo formale riportato nella dichiarazione.

I successivi turni introdotti dalla forma `PRESIDENTE` possono essere collegati
alla persona che presiede in quel punto del documento:

```turtle
<.../block/speech/...>
    a ipsa:Block ;
    ipsa:hasBlockType ipsa:speech ;
    semparl:speaker
        <http://dati.camera.it/ocd/persona.rdf/pr...> ;
    ipsa:presidingRole "vice-presidente"@it .
```

In questo caso `PRESIDENTE` è la funzione testuale con cui viene introdotto il
turno, mentre `vice-presidente` rimane il ruolo istituzionale della persona.

## 13. Convenzioni per le URI

Le URI delle istanze includono ramo, legislatura, documento e posizione nel
documento, così da evitare collisioni tra legislature o documenti diversi.

### Pagina

```text
ipsa:page/{ramo}/{legislatura}/{document_id}/{source_page_number}
```

Esempio:

```text
http://www.semanticweb.org/claudia/ontologies/2026/ipsa/page/camera/regno_01/39fd80500eafe62f05cd80ffb9630296/0
```

### Blocco funzionale

```text
ipsa:block/{ramo}/{legislatura}/{document_id}/{start_source_page}/{start_block_seq}
```

Esempio:

```text
http://www.semanticweb.org/claudia/ontologies/2026/ipsa/block/camera/regno_01/39fd80500eafe62f05cd80ffb9630296/0/6
```

### Paragrafo OCR

```text
ipsa:paragraph/{ramo}/{legislatura}/{document_id}/{source_page_number}/{block_seq}
```

Esempio:

```text
http://www.semanticweb.org/claudia/ontologies/2026/ipsa/paragraph/camera/regno_01/39fd80500eafe62f05cd80ffb9630296/0/6
```

## 14. Esempio completo

### Pagina

```turtle
<http://www.semanticweb.org/claudia/ontologies/2026/ipsa/page/camera/regno_01/39fd80500eafe62f05cd80ffb9630296/0>
    a ipsa:Page ;
    ocd:rif_leg
        <http://dati.camera.it/ocd/legislatura.rdf/regno_01> ;
    ipsa:documentID "39fd80500eafe62f05cd80ffb9630296" ;
    ipsa:imageFile "1.png" ;
    ipsa:pageNumber 1 ;
    ipsa:ramo "camera" ;
    ipsa:sourcePageNumber 0 .
```

### Blocco speech

```turtle
<http://www.semanticweb.org/claudia/ontologies/2026/ipsa/block/camera/regno_01/39fd80500eafe62f05cd80ffb9630296/0/6>
    a ipsa:Block ;
    dct:language
        <http://id.loc.gov/vocabulary/iso639-1/it> ;
    semparl:orderNumber 6 ;
    semparl:speaker
        <http://dati.camera.it/ocd/persona.rdf/pr201> ;
    ipsa:hasBlockType ipsa:speech ;
    ipsa:hasPage
        <http://www.semanticweb.org/claudia/ontologies/2026/ipsa/page/camera/regno_01/39fd80500eafe62f05cd80ffb9630296/0> ;
    ipsa:hasParagraph
        <http://www.semanticweb.org/claudia/ontologies/2026/ipsa/paragraph/camera/regno_01/39fd80500eafe62f05cd80ffb9630296/0/6> ;
    ipsa:speakerLabel "Pier Dionigi Pinelli"@it .
```

### Paragrafo OCR

```turtle
<http://www.semanticweb.org/claudia/ontologies/2026/ipsa/paragraph/camera/regno_01/39fd80500eafe62f05cd80ffb9630296/0/6>
    a ipsa:Paragraph ;
    dct:language
        <http://id.loc.gov/vocabulary/iso639-1/it> ;
    semparl:content
        "PINELLI propone che la Camera voglia adottare il capo primo del regolamento..."@it ;
    ipsa:hasPage
        <http://www.semanticweb.org/claudia/ontologies/2026/ipsa/page/camera/regno_01/39fd80500eafe62f05cd80ffb9630296/0> ;
    ipsa:ocrCategory "Text" ;
    ipsa:orderID 1 ;
    ipsa:predictedLabel "B-speech" ;
    ipsa:predictionConfidence 0.998819 ;
    ipsa:sourceBlockSequence 6 .
```

## 15. Proprietà predisposte per estensioni future

L’ontologia contiene alcune proprietà non ancora valorizzate dalla pipeline
corrente:

- `ocd:rif_seduta`;
- `ipsa:Author`;
- `ipsa:authorLabel`;
- `semparl:startDate`;
- `semparl:endDate`.

La loro presenza consente di estendere la pipeline senza modificare il modello
concettuale di base.

## 16. Regole di coerenza

La generazione delle istanze segue queste regole:

- ogni pagina è un’istanza di `ipsa:Page`;
- ogni blocco funzionale è un’istanza di `ipsa:Block`;
- ogni blocco OCR è un’istanza di `ipsa:Paragraph`;
- `ipsa:Paragraph` non è una sottoclasse di `ipsa:Block`;
- ogni blocco deve avere un valore `ipsa:hasBlockType`;
- ogni paragrafo deve essere collegato alla propria pagina;
- un blocco può essere collegato a più pagine;
- `semparl:speaker` e `ipsa:presidenza` vengono generati soltanto per candidati
  univoci dotati di URI;
- le label complete del modello restano conservate mediante
  `ipsa:predictedLabel`.

## 17. Validazione

La sintassi dell’ontologia può essere controllata con `rdflib`:

```bash
python3 - <<'PY'
from rdflib import Graph

path = "scripts/rdf_pipeline/ontologia_ipsa_pipeline.ttl"

graph = Graph()
graph.parse(path, format="turtle")

print("Ontologia valida")
print("Triple:", len(graph))
PY
```

Per verificare che `ipsa:Paragraph` non sia definita come sottoclasse di
`ipsa:Block`:

```bash
python3 - <<'PY'
from rdflib import Graph, Namespace
from rdflib.namespace import RDFS

IPSA = Namespace(
    "http://www.semanticweb.org/claudia/ontologies/2026/ipsa/"
)

graph = Graph()
graph.parse(
    "scripts/rdf_pipeline/ontologia_ipsa_pipeline.ttl",
    format="turtle",
)

print(
    "Paragraph sottoclasse di Block:",
    (IPSA.Paragraph, RDFS.subClassOf, IPSA.Block) in graph,
)
PY
```

Il risultato atteso è:

```text
Paragraph sottoclasse di Block: False
```

Per verificare la dichiarazione di `ipsa:presidingRole`:

```bash
python3 - <<'PY'
from rdflib import Graph, Namespace
from rdflib.namespace import RDF, RDFS, OWL

IPSA = Namespace(
    "http://www.semanticweb.org/claudia/ontologies/2026/ipsa/"
)

graph = Graph()
graph.parse(
    "scripts/rdf_pipeline/ontologia_ipsa_pipeline.ttl",
    format="turtle",
)

assert (
    IPSA.presidingRole,
    RDF.type,
    OWL.DatatypeProperty,
) in graph

assert (
    IPSA.presidingRole,
    RDFS.domain,
    IPSA.Block,
) in graph

assert (
    IPSA.presidingRole,
    RDFS.range,
    RDF.langString,
) in graph

print("presidingRole dichiarata correttamente")
PY
```
