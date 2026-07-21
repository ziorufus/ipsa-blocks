#!/usr/bin/env python3
# coding: utf-8

"""
Training e valutazione di LayoutLMv3 + BiLSTM
per la classificazione multiclasse dei blocchi IPSA.

Script derivato dal notebook, ripulito dalle celle specifiche
di Jupyter, Colab, conversione PDF e debug esplorativo.
"""

import json
import torch
from pathlib import Path
from PIL import Image
from torch.utils.data import Dataset
from transformers import LayoutLMv3Processor

class IPSABlockWindowDataset(Dataset):
    """
    Dataset LayoutLMv3 per classificazione a livello di blocco.

    Miglioramenti rispetto al campionamento fisso/proporzionale:
    - crea finestre di blocchi, non finestre arbitrarie di token;
    - non forza ogni blocco a 8/15 token;
    - conserva tutti i blocchi distribuiti su più esempi;
    - mantiene mapping token -> block_id -> label;
    - ignora automaticamente blocchi vuoti o interamente fuori finestra.
    """

    def __init__(
        self,
        pages_path,
        image_dir,
        label2id_path,
        max_length=512,
        stride_blocks=0
    ):
        with open(pages_path, encoding="utf-8") as f:
            self.pages = json.load(f)

        with open(label2id_path, encoding="utf-8") as f:
            self.label2id = json.load(f)

        self.image_dir = Path(image_dir)
        self.max_length = max_length
        self.max_text_tokens = max_length - 2
        self.stride_blocks = stride_blocks

        self.processor = LayoutLMv3Processor.from_pretrained(
            "microsoft/layoutlmv3-base",
            apply_ocr=False
        )

        self.examples = []
        self._build_index()

    def normalize_box(self, box, width, height):
        x0, y0, x1, y1 = box

        norm = [
            int(1000 * x0 / width),
            int(1000 * y0 / height),
            int(1000 * x1 / width),
            int(1000 * y1 / height),
        ]
        norm = [max(0, min(1000, v)) for v in norm]

        if norm[2] < norm[0]:
            norm[0], norm[2] = norm[2], norm[0]
        if norm[3] < norm[1]:
            norm[1], norm[3] = norm[3], norm[1]

        return norm

    def token_len_words(self, words):
        if not words:
            return 0

        dummy_boxes = [[0, 0, 0, 0]] * len(words)

        encoded = self.processor.tokenizer(
            text=words,
            boxes=dummy_boxes,
            add_special_tokens=False,
            truncation=False
        )

        return len(encoded["input_ids"])

    def block_words(self, block):
        return (block.get("text") or "").split()

    def _build_index(self):
        """
        Costruisce finestre di blocchi. Ogni finestra contiene il massimo numero
        di blocchi consecutivi che entra nel budget di 510 token testuali.
        """
        for page_idx, page in enumerate(self.pages):
            blocks = page.get("blocks", [])
            start = 0

            while start < len(blocks):
                end = start
                used = 0
                added = 0

                while end < len(blocks):
                    words = self.block_words(blocks[end])
                    n_tok = self.token_len_words(words)

                    if n_tok == 0:
                        end += 1
                        continue

                    # Se un singolo blocco è troppo lungo, lo troncheremo in __getitem__.
                    if added > 0 and used + n_tok > self.max_text_tokens:
                        break

                    used += min(n_tok, self.max_text_tokens)
                    end += 1
                    added += 1

                    if used >= self.max_text_tokens:
                        break

                if added == 0:
                    start += 1
                    continue

                self.examples.append({
                    "page_idx": page_idx,
                    "start": start,
                    "end": end
                })

                if self.stride_blocks and end < len(blocks):
                    start = max(start + 1, end - self.stride_blocks)
                else:
                    start = end

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        ex = self.examples[idx]
        page = self.pages[ex["page_idx"]]
        page_id = page["page"]

        image_name = page.get("image_file")

        if image_name:
            image_path = self.image_dir / image_name
        else:
            # Compatibilità con vecchi JSON privi di image_file.
            image_path = None

            for extension in (".png", ".jpg", ".jpeg"):
                candidate = self.image_dir / f"{page_id}{extension}"

                if candidate.exists():
                    image_path = candidate
                    break

            if image_path is None:
                raise FileNotFoundError(
                    f"Nessuna immagine trovata per la pagina {page_id} "
                    f"nella cartella {self.image_dir}"
                )

        if not image_path.exists():
            raise FileNotFoundError(
                f"Immagine indicata nel JSON non trovata: {image_path}"
            )

        image = Image.open(image_path).convert("RGB")
        page_bbox_width  = max(b["bbox"][2] for b in page["blocks"])
        page_bbox_height = max(b["bbox"][3] for b in page["blocks"])

        words = []
        boxes = []
        word_block_ids = []
        block_labels = []
        original_block_indices = []

        compact_block_id = 0
        used_tokens = 0

        for original_idx in range(ex["start"], ex["end"]):
            block = page["blocks"][original_idx]
            bw = self.block_words(block)
            if not bw:
                continue

            remaining = self.max_text_tokens - used_tokens
            if remaining <= 0:
                break

            # Se il blocco singolo è troppo lungo, lo tronchiamo a livello di parole
            # ma manteniamo comunque una label per quel blocco.

            selected = []
            selected_tok = 0
            for word in bw:
                n = self.token_len_words([word])
                if selected and selected_tok + n > remaining:
                    break
                selected.append(word)
                selected_tok += n
                if selected_tok >= remaining:
                    break

            if not selected:
                continue

            #norm_box = self.normalize_box(block["bbox"], width, height)
            norm_box = self.normalize_box(block["bbox"], page_bbox_width, page_bbox_height)

            words.extend(selected)
            boxes.extend([norm_box] * len(selected))
            word_block_ids.extend([compact_block_id] * len(selected))
            block_labels.append(self.label2id[block["label"]])
            original_block_indices.append(original_idx)

            compact_block_id += 1
            used_tokens += selected_tok

        if len(words) == 0:
            raise ValueError(f"Nessuna parola nella finestra {idx}, pagina {page_id}")

        if len(words) != len(boxes):
            raise ValueError(
                f"Mismatch words/boxes nella pagina {page_id}: "
                f"{len(words)} words vs {len(boxes)} boxes"
            )

        encoding = self.processor(
            images=image,
            text=words,
            boxes=boxes,
            truncation=True,
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt"
        )

        word_ids = encoding.word_ids(batch_index=0)
        token_block_ids = [
            -1 if word_id is None else word_block_ids[word_id]
            for word_id in word_ids
        ]

        encoding = {k: v.squeeze(0) for k, v in encoding.items()}
        encoding["block_ids"] = torch.tensor(token_block_ids, dtype=torch.long)
        encoding["block_labels"] = torch.tensor(block_labels, dtype=torch.long)
        encoding["page_id"] = page_id
        encoding["original_block_indices"] = torch.tensor(original_block_indices, dtype=torch.long)

        return encoding


# ## 5. Collate function
#

# In[2]:


def block_window_collate_fn(batch):
    """
    Collate custom perché block_labels e original_block_indices hanno lunghezza variabile.
    I tensori LayoutLMv3 restano [batch, 512]; le label di blocco vengono padded con -100.
    """
    fixed_keys = ["input_ids", "attention_mask", "bbox", "pixel_values", "block_ids"]
    collated = {k: torch.stack([item[k] for item in batch]) for k in fixed_keys}

    max_blocks = max(item["block_labels"].numel() for item in batch)

    padded_labels = torch.full((len(batch), max_blocks), -100, dtype=torch.long)
    padded_original_indices = torch.full((len(batch), max_blocks), -1, dtype=torch.long)

    page_ids = []

    for i, item in enumerate(batch):
        n = item["block_labels"].numel()
        padded_labels[i, :n] = item["block_labels"]
        padded_original_indices[i, :n] = item["original_block_indices"]
        page_ids.append(item["page_id"])

    collated["block_labels"] = padded_labels
    collated["original_block_indices"] = padded_original_indices
    collated["page_id"] = page_ids

    return collated


import torch
import torch.nn as nn
from transformers import LayoutLMv3Model

class LayoutLMv3BiLSTMForBlockClassification(nn.Module):
    """
    Variante CRF-like con BiLSTM sopra gli embedding dei blocchi.

    Pipeline:
    1. LayoutLMv3 produce embedding contestualizzati per token.
    2. Per ogni blocco si fa mean pooling dei token che hanno lo stesso block_id.
    3. La sequenza di embedding dei blocchi entra in una BiLSTM.
    4. Un classificatore lineare assegna una label a ogni blocco.
    """

    def __init__(
        self,
        num_labels,
        class_weights=None,
        lstm_hidden_size=256,
        lstm_layers=1,
        dropout=0.1,
        freeze_layoutlmv3=False
    ):
        super().__init__()
        self.layoutlmv3 = LayoutLMv3Model.from_pretrained("microsoft/layoutlmv3-base")
        hidden = self.layoutlmv3.config.hidden_size

        if freeze_layoutlmv3:
            for p in self.layoutlmv3.parameters():
                p.requires_grad = False

        self.bilstm = nn.LSTM(
            input_size=hidden,
            hidden_size=lstm_hidden_size,
            num_layers=lstm_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if lstm_layers > 1 else 0.0
        )

        self.classifier = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(lstm_hidden_size * 2, num_labels)
        )

        if class_weights is not None:
            self.register_buffer("class_weights", class_weights.float())
        else:
            self.class_weights = None

    def _pool_blocks_one_sample(self, token_embeddings, block_ids):
        """Restituisce una sequenza [num_blocks, hidden] in ordine di block_id."""
        valid_block_ids = sorted(b for b in block_ids.unique().tolist() if b >= 0)
        pooled = []
        for b in valid_block_ids:
            mask = block_ids == b
            pooled.append(token_embeddings[mask].mean(dim=0))
        if not pooled:
            return token_embeddings.new_zeros((0, token_embeddings.size(-1)))
        return torch.stack(pooled, dim=0)

    def forward(self, input_ids, attention_mask, bbox, pixel_values, block_ids, block_labels=None, **kwargs):
        outputs = self.layoutlmv3(
            input_ids=input_ids,
            attention_mask=attention_mask,
            bbox=bbox,
            pixel_values=pixel_values
        )

        # LayoutLMv3 concatena token testuali e patch visuali: teniamo solo i token testuali.
        token_embeddings = outputs.last_hidden_state[:, :input_ids.size(1), :]

        block_sequences = []
        lengths = []
        for i in range(token_embeddings.size(0)):
            seq = self._pool_blocks_one_sample(token_embeddings[i], block_ids[i])
            block_sequences.append(seq)
            lengths.append(seq.size(0))

        max_blocks = max(lengths) if lengths else 0
        if max_blocks == 0:
            return {"loss": None, "logits": None}

        batch_size = token_embeddings.size(0)
        hidden = token_embeddings.size(-1)
        padded = token_embeddings.new_zeros((batch_size, max_blocks, hidden))
        mask = torch.zeros((batch_size, max_blocks), dtype=torch.bool, device=token_embeddings.device)

        for i, seq in enumerate(block_sequences):
            n = seq.size(0)
            if n > 0:
                padded[i, :n] = seq
                mask[i, :n] = True

        # pack_padded_sequence evita che la BiLSTM impari dai padding.
        lengths_tensor = torch.tensor(lengths, dtype=torch.long, device="cpu")
        packed = nn.utils.rnn.pack_padded_sequence(
            padded,
            lengths_tensor,
            batch_first=True,
            enforce_sorted=False
        )
        packed_out, _ = self.bilstm(packed)
        lstm_out, _ = nn.utils.rnn.pad_packed_sequence(
            packed_out,
            batch_first=True,
            total_length=max_blocks
        )

        logits = self.classifier(lstm_out)  # [batch, max_blocks, num_labels]

        loss = None
        if block_labels is not None:
            # block_labels è già padded con -100 dalla collate_fn.
            labels = block_labels[:, :max_blocks].to(logits.device)
            active = (labels != -100) & mask
            loss_fn = nn.CrossEntropyLoss(weight=self.class_weights, ignore_index=-100)
            loss = loss_fn(
                logits.reshape(-1, logits.size(-1)),
                labels.masked_fill(~active, -100).reshape(-1)
            )

        return {"loss": loss, "logits": logits, "mask": mask}


def prepare_legacy_aligned_images(
    train_json: Path,
    test_json: Path,
    source_dir: Path,
    aligned_dir: Path,
    missing_page: int,
) -> None:
    """
    Crea collegamenti simbolici per un dataset legacy nel quale una pagina
    è stata eliminata dalle immagini, ma la numerazione originale è rimasta
    nei JSON.

    Questa funzione non viene usata per i dataset normali. Si attiva soltanto
    passando --legacy-missing-page.

    Sono supportate immagini PNG, JPG e JPEG. La cartella sorgente non viene
    mai modificata.
    """

    for json_path in (train_json, test_json):
        if not json_path.is_file():
            raise FileNotFoundError(
                f"File JSON non trovato: {json_path}"
            )

    if not source_dir.is_dir():
        raise FileNotFoundError(
            f"Cartella delle immagini non trovata: {source_dir}"
        )

    page_ids = set()

    for json_path in (train_json, test_json):
        with json_path.open(encoding="utf-8") as file:
            pages = json.load(file)

        page_ids.update(
            int(page["page"])
            for page in pages
        )

    if missing_page in page_ids:
        raise ValueError(
            f"La pagina {missing_page} è presente nei JSON, "
            "ma è stata indicata come pagina eliminata."
        )

    aligned_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    created = 0
    already_correct = 0
    missing_images = []

    for page_id in sorted(page_ids):
        source_id = (
            page_id
            if page_id < missing_page
            else page_id - 1
        )

        source_path = None

        for extension in (".png", ".jpg", ".jpeg"):
            candidate = source_dir / f"{source_id}{extension}"

            if candidate.is_file():
                source_path = candidate
                break

        if source_path is None:
            missing_images.append(
                (page_id, source_id)
            )
            continue

        target_extension = source_path.suffix.lower()

        if target_extension == ".jpeg":
            target_extension = ".jpg"

        target_path = (
            aligned_dir
            / f"{page_id}{target_extension}"
        )

        expected_source = source_path.resolve()

        if target_path.is_symlink():
            if target_path.resolve() == expected_source:
                already_correct += 1
                continue

            target_path.unlink()

        elif target_path.exists():
            raise FileExistsError(
                f"{target_path} esiste ma non è un collegamento "
                "simbolico. Non verrà cancellato automaticamente."
            )

        target_path.symlink_to(expected_source)
        created += 1

    if missing_images:
        details = ", ".join(
            f"pagina JSON {page_id} -> immagine sorgente {source_id}"
            for page_id, source_id in missing_images
        )

        raise FileNotFoundError(
            f"Immagini necessarie non trovate: {details}"
        )

    print("\nAllineamento legacy completato")
    print("Pagine richieste:", len(page_ids))
    print("Nuovi collegamenti:", created)
    print("Collegamenti già corretti:", already_correct)

    if page_ids:
        first_page = min(page_ids)
        last_page = max(page_ids)

        print("Prima pagina allineata:", first_page)
        print("Ultima pagina allineata:", last_page)


def parse_args():
    """Legge i parametri passati allo script da terminale."""
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Training e valutazione di LayoutLMv3 + BiLSTM "
            "per la classificazione multiclasse dei blocchi."
        )
    )

    # File e cartelle
    parser.add_argument(
        "--train-json",
        type=Path,
        default=Path("new_train.json"),
        help="File JSON di training.",
    )
    parser.add_argument(
        "--test-json",
        type=Path,
        default=Path("strat-250-test-bbox.json"),
        help="File JSON di test.",
    )
    parser.add_argument(
        "--image-dir",
        type=Path,
        default=Path("images"),
        help="Cartella contenente le immagini originali (JPG, JPEG o PNG).",
    )
    parser.add_argument(
        "--aligned-image-dir",
        type=Path,
        default=Path("images_aligned"),
        help=(
            "Cartella dei collegamenti simbolici usata soltanto "
            "con --legacy-missing-page."
        ),
    )
    parser.add_argument(
        "--legacy-missing-page",
        type=int,
        default=None,
        help=(
            "Attiva l'allineamento legacy quando una pagina è assente "
            "dalle immagini ma la numerazione originale è conservata "
            "nei JSON. Esempio: --legacy-missing-page 411."
        ),
    )
    parser.add_argument(
        "--label2id",
        type=Path,
        default=Path("label2id_multiclass.json"),
        help="File JSON con la mappatura label -> id.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments"),
        help="Cartella principale in cui salvare esperimenti e risultati.",
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default=None,
        help="Nome dell'esperimento. Default: bilstm_<epoche>epochs.",
    )

    # Training
    parser.add_argument(
        "--epochs",
        type=int,
        default=5,
        help="Numero di epoche.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Batch size.",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=2e-5,
        help="Learning rate dell'optimizer AdamW.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed per la riproducibilità.",
    )

    # Dataset
    parser.add_argument(
        "--max-length",
        type=int,
        default=512,
        help="Lunghezza massima della sequenza.",
    )
    parser.add_argument(
        "--stride-blocks",
        type=int,
        default=0,
        help="Numero di blocchi sovrapposti tra finestre consecutive.",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=0,
        help="Processi usati dai DataLoader. Sul server è prudente iniziare da 0.",
    )

    # BiLSTM
    parser.add_argument(
        "--lstm-hidden-size",
        type=int,
        default=256,
        help="Dimensione dello stato nascosto della BiLSTM.",
    )
    parser.add_argument(
        "--lstm-layers",
        type=int,
        default=1,
        help="Numero di livelli della BiLSTM.",
    )
    parser.add_argument(
        "--dropout",
        type=float,
        default=0.1,
        help="Dropout del classificatore.",
    )
    parser.add_argument(
        "--freeze-layoutlmv3",
        action="store_true",
        help="Congela i pesi di LayoutLMv3.",
    )

    # Debug
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="Limita i batch di training per test rapidi.",
    )
    parser.add_argument(
        "--max-test-batches",
        type=int,
        default=None,
        help="Limita i batch di valutazione per test rapidi.",
    )

    return parser.parse_args()


def set_seed(seed: int) -> None:
    """Imposta i seed principali per rendere gli esperimenti riproducibili."""
    import random

    random.seed(seed)
    torch.manual_seed(seed)

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def validate_configuration(args) -> None:
    """Controlla parametri, file e cartelle prima di caricare il modello."""
    required_files = [
        args.train_json,
        args.test_json,
        args.label2id,
    ]

    for path in required_files:
        if not path.is_file():
            raise FileNotFoundError(f"File richiesto non trovato: {path}")

    if not args.image_dir.is_dir():
        raise FileNotFoundError(
            f"Cartella delle immagini non trovata: {args.image_dir}"
        )

    if args.epochs < 1:
        raise ValueError("--epochs deve essere almeno 1.")

    if args.batch_size < 1:
        raise ValueError("--batch-size deve essere almeno 1.")

    if args.learning_rate <= 0:
        raise ValueError("--learning-rate deve essere maggiore di zero.")

    if args.max_length < 3:
        raise ValueError("--max-length deve essere almeno 3.")

    if args.stride_blocks < 0:
        raise ValueError("--stride-blocks non può essere negativo.")

    if args.num_workers < 0:
        raise ValueError("--num-workers non può essere negativo.")


def prepare_run(args):
    """
    Prepara nome, cartella dell'esperimento e device.

    Restituisce:
        run_name, run_dir, device
    """
    run_name = args.run_name or f"bilstm_{args.epochs}epochs"
    run_dir = args.output_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )

    print("\nConfigurazione esperimento")
    print("Nome:", run_name)
    print("Cartella risultati:", run_dir.resolve())
    print("Epoche:", args.epochs)
    print("Batch size:", args.batch_size)
    print("Learning rate:", args.learning_rate)
    print("Seed:", args.seed)
    print("Device:", device)

    if device.type == "cuda":
        print("GPU:", torch.cuda.get_device_name(0))

    return run_name, run_dir, device


def build_data_components(args):
    """
    Carica label e dati, quindi costruisce dataset, DataLoader
    e pesi di classe.
    """
    import math
    from collections import Counter
    from torch.utils.data import DataLoader

    with args.label2id.open(encoding="utf-8") as file:
        label2id = json.load(file)

    if not label2id:
        raise ValueError(
            f"Il file delle etichette è vuoto: {args.label2id}"
        )

    # Controlla che gli ID siano consecutivi: 0, 1, 2, ...
    label_ids = sorted(int(value) for value in label2id.values())
    expected_ids = list(range(len(label2id)))

    if label_ids != expected_ids:
        raise ValueError(
            "Gli ID delle etichette non sono consecutivi a partire da 0."
        )

    id2label = {
        int(label_id): label
        for label, label_id in label2id.items()
    }

    with args.train_json.open(encoding="utf-8") as file:
        train_pages = json.load(file)

    with args.test_json.open(encoding="utf-8") as file:
        test_pages = json.load(file)

    train_labels = {
        block["label"]
        for page in train_pages
        for block in page.get("blocks", [])
    }

    test_labels = {
        block["label"]
        for page in test_pages
        for block in page.get("blocks", [])
    }

    unknown_train = sorted(train_labels - set(label2id))
    unknown_test = sorted(test_labels - set(label2id))

    if unknown_train:
        raise ValueError(
            f"Label del train assenti da label2id: {unknown_train}"
        )

    if unknown_test:
        raise ValueError(
            f"Label del test assenti da label2id: {unknown_test}"
        )

    dataset_image_dir = (
        args.aligned_image_dir
        if args.legacy_missing_page is not None
        else args.image_dir
    )

    train_dataset = IPSABlockWindowDataset(
        pages_path=args.train_json,
        image_dir=dataset_image_dir,
        label2id_path=args.label2id,
        max_length=args.max_length,
        stride_blocks=args.stride_blocks,
    )

    test_dataset = IPSABlockWindowDataset(
        pages_path=args.test_json,
        image_dir=dataset_image_dir,
        label2id_path=args.label2id,
        max_length=args.max_length,
        stride_blocks=args.stride_blocks,
    )

    generator = torch.Generator()
    generator.manual_seed(args.seed)

    loader_options = {
        "batch_size": args.batch_size,
        "num_workers": args.num_workers,
        "collate_fn": block_window_collate_fn,
        "pin_memory": torch.cuda.is_available(),
    }

    train_loader = DataLoader(
        train_dataset,
        shuffle=True,
        generator=generator,
        **loader_options,
    )

    test_loader = DataLoader(
        test_dataset,
        shuffle=False,
        **loader_options,
    )

    label_counter = Counter(
        block["label"]
        for page in train_pages
        for block in page.get("blocks", [])
    )

    num_labels = len(label2id)
    class_weights = torch.ones(num_labels, dtype=torch.float)

    for label, label_id in label2id.items():
        frequency = label_counter.get(label, 0)

        if frequency == 0:
            raise ValueError(
                f"La label {label!r} non ha esempi nel training set."
            )

        class_weights[int(label_id)] = 1.0 / math.sqrt(frequency)

    class_weights = class_weights / class_weights.mean()

    print("\nDataset")
    print("Pagine train:", len(train_pages))
    print("Pagine test:", len(test_pages))
    print("Finestre train:", len(train_dataset))
    print("Finestre test:", len(test_dataset))
    print("Numero classi:", num_labels)
    print("Pesi di classe:", class_weights.tolist())

    return {
        "label2id": label2id,
        "id2label": id2label,
        "train_dataset": train_dataset,
        "test_dataset": test_dataset,
        "train_loader": train_loader,
        "test_loader": test_loader,
        "class_weights": class_weights,
    }


def build_model_and_optimizer(args, class_weights, device):
    """Inizializza il modello e l'optimizer."""
    model = LayoutLMv3BiLSTMForBlockClassification(
        num_labels=len(class_weights),
        class_weights=class_weights,
        lstm_hidden_size=args.lstm_hidden_size,
        lstm_layers=args.lstm_layers,
        dropout=args.dropout,
        freeze_layoutlmv3=args.freeze_layoutlmv3,
    ).to(device)

    trainable_parameters = [
        parameter
        for parameter in model.parameters()
        if parameter.requires_grad
    ]

    optimizer = torch.optim.AdamW(
        trainable_parameters,
        lr=args.learning_rate,
    )

    total_parameters = sum(
        parameter.numel()
        for parameter in model.parameters()
    )

    trainable_count = sum(
        parameter.numel()
        for parameter in trainable_parameters
    )

    print("\nModello")
    print("Parametri totali:", f"{total_parameters:,}")
    print("Parametri addestrabili:", f"{trainable_count:,}")
    print("LayoutLMv3 congelato:", args.freeze_layoutlmv3)

    return model, optimizer


def serializable_arguments(args) -> dict:
    """Converte i parametri argparse in valori salvabili nel checkpoint."""
    result = {}

    for key, value in vars(args).items():
        if isinstance(value, Path):
            result[key] = str(value)
        else:
            result[key] = value

    return result


def save_training_checkpoint(
    model,
    optimizer,
    epoch,
    history,
    args,
    run_dir,
) -> None:
    """
    Salva lo stato più recente del training.

    Il checkpoint viene sovrascritto a ogni epoca, evitando di creare
    numerosi file di grandi dimensioni.
    """
    checkpoint_path = run_dir / "checkpoint_latest.pt"
    temporary_path = run_dir / "checkpoint_latest.tmp"

    checkpoint = {
        "epoch": epoch,
        "model_state_dict": model.state_dict(),
        "history": history,
        "arguments": serializable_arguments(args),
    }

    torch.save(checkpoint, temporary_path)
    temporary_path.replace(checkpoint_path)

    history_path = run_dir / "training_history.json"
    history_temporary = run_dir / "training_history.tmp"

    with history_temporary.open("w", encoding="utf-8") as file:
        json.dump(history, file, indent=2)

    history_temporary.replace(history_path)

    print("Checkpoint salvato:", checkpoint_path)


def train_model(
    model,
    optimizer,
    train_loader,
    device,
    args,
    run_dir,
):
    """Esegue il training e restituisce la loss media di ogni epoca."""
    import time
    from tqdm import tqdm

    history = []

    for epoch_index in range(args.epochs):
        epoch_number = epoch_index + 1

        model.train()
        total_loss = 0.0
        completed_steps = 0
        start_time = time.perf_counter()

        progress_bar = tqdm(
            train_loader,
            desc=f"Epoch {epoch_number}/{args.epochs}",
            unit="batch",
        )

        for step, batch in enumerate(progress_bar):
            if (
                args.max_batches is not None
                and step >= args.max_batches
            ):
                break

            # Metadati non utilizzati nel forward del modello.
            batch.pop("page_id", None)
            batch.pop("original_block_indices", None)

            batch = {
                key: value.to(device, non_blocking=True)
                for key, value in batch.items()
            }

            optimizer.zero_grad(set_to_none=True)

            outputs = model(**batch)
            loss = outputs["loss"]

            if loss is None:
                continue

            loss.backward()

            torch.nn.utils.clip_grad_norm_(
                model.parameters(),
                max_norm=1.0,
            )

            optimizer.step()

            loss_value = float(loss.item())
            total_loss += loss_value
            completed_steps += 1

            progress_bar.set_postfix(
                loss=f"{loss_value:.4f}"
            )

        if completed_steps == 0:
            raise RuntimeError(
                "Nessun batch valido è stato completato durante il training."
            )

        average_loss = total_loss / completed_steps
        elapsed_seconds = time.perf_counter() - start_time

        epoch_result = {
            "epoch": epoch_number,
            "average_loss": average_loss,
            "completed_steps": completed_steps,
            "elapsed_seconds": elapsed_seconds,
        }

        history.append(epoch_result)

        print(
            f"\nEpoch {epoch_number}/{args.epochs} completata"
            f" | loss media: {average_loss:.4f}"
            f" | batch: {completed_steps}"
            f" | durata: {elapsed_seconds / 60:.2f} minuti"
        )

        save_training_checkpoint(
            model=model,
            optimizer=optimizer,
            epoch=epoch_number,
            history=history,
            args=args,
            run_dir=run_dir,
        )

    return history


def evaluate_model(
    model,
    test_loader,
    device,
    label2id,
    args,
    run_dir,
):
    """Valuta il modello e salva metriche e classification report."""
    from sklearn.metrics import (
        accuracy_score,
        classification_report,
        f1_score,
    )
    from tqdm import tqdm

    model.eval()

    all_predictions = []
    all_gold = []

    with torch.no_grad():
        progress_bar = tqdm(
            test_loader,
            desc="Valutazione",
            unit="batch",
        )

        for step, batch in enumerate(progress_bar):
            if (
                args.max_test_batches is not None
                and step >= args.max_test_batches
            ):
                break

            batch.pop("page_id", None)
            batch.pop("original_block_indices", None)

            # Conserviamo le label su CPU per il calcolo delle metriche.
            gold_padded = batch["block_labels"].clone()

            batch = {
                key: value.to(device, non_blocking=True)
                for key, value in batch.items()
            }

            outputs = model(**batch)

            if outputs["logits"] is None:
                continue

            logits = outputs["logits"].detach().cpu()
            mask = outputs["mask"].detach().cpu()
            predictions_padded = logits.argmax(dim=-1)

            for sample_index in range(predictions_padded.size(0)):
                current_mask = mask[sample_index]

                current_gold = gold_padded[
                    sample_index,
                    :current_mask.size(0),
                ]

                active = current_mask & (current_gold != -100)

                all_predictions.extend(
                    predictions_padded[sample_index, active].tolist()
                )
                all_gold.extend(
                    current_gold[active].tolist()
                )

    if not all_gold:
        raise RuntimeError(
            "La valutazione non ha prodotto esempi validi."
        )

    id2label = {
        int(label_id): label
        for label, label_id in label2id.items()
    }

    all_label_ids = list(range(len(id2label)))
    target_names = [
        id2label[label_id]
        for label_id in all_label_ids
    ]

    accuracy = accuracy_score(
        all_gold,
        all_predictions,
    )

    # Macro F1 sulle classi effettivamente presenti nel test.
    macro_f1_present = f1_score(
        all_gold,
        all_predictions,
        average="macro",
        zero_division=0,
    )

    # Macro F1 su tutte le classi definite nel vocabolario.
    macro_f1_all = f1_score(
        all_gold,
        all_predictions,
        labels=all_label_ids,
        average="macro",
        zero_division=0,
    )

    weighted_f1 = f1_score(
        all_gold,
        all_predictions,
        labels=all_label_ids,
        average="weighted",
        zero_division=0,
    )

    report_text = classification_report(
        all_gold,
        all_predictions,
        labels=all_label_ids,
        target_names=target_names,
        zero_division=0,
        digits=3,
    )

    report_dict = classification_report(
        all_gold,
        all_predictions,
        labels=all_label_ids,
        target_names=target_names,
        zero_division=0,
        output_dict=True,
    )

    metrics = {
        "accuracy": float(accuracy),
        "macro_f1_present_classes": float(macro_f1_present),
        "macro_f1_all_classes": float(macro_f1_all),
        "weighted_f1": float(weighted_f1),
        "evaluated_blocks": len(all_gold),
        "classification_report": report_dict,
    }

    metrics_path = run_dir / "metrics.json"
    metrics_temporary = run_dir / "metrics.tmp"

    with metrics_temporary.open("w", encoding="utf-8") as file:
        json.dump(metrics, file, indent=2)

    metrics_temporary.replace(metrics_path)

    report_path = run_dir / "classification_report.txt"

    with report_path.open("w", encoding="utf-8") as file:
        file.write(f"Accuracy: {accuracy:.6f}\n")
        file.write(
            f"Macro F1, classi presenti: "
            f"{macro_f1_present:.6f}\n"
        )
        file.write(
            f"Macro F1, tutte le classi: "
            f"{macro_f1_all:.6f}\n"
        )
        file.write(f"Weighted F1: {weighted_f1:.6f}\n\n")
        file.write(report_text)

    print("\nRisultati valutazione")
    print("Accuracy:", accuracy)
    print("Macro F1, classi presenti:", macro_f1_present)
    print("Macro F1, tutte le classi:", macro_f1_all)
    print("Weighted F1:", weighted_f1)
    print()
    print(report_text)
    print("Metriche salvate in:", metrics_path)
    print("Report salvato in:", report_path)

    return metrics


def save_final_model(
    model,
    history,
    metrics,
    label2id,
    args,
    run_dir,
) -> None:
    """Salva i pesi finali e le informazioni necessarie al riutilizzo."""
    final_path = run_dir / "model_final.pt"
    temporary_path = run_dir / "model_final.tmp"

    artifact = {
        "model_state_dict": model.state_dict(),
        "history": history,
        "metrics": metrics,
        "label2id": label2id,
        "arguments": serializable_arguments(args),
    }

    torch.save(artifact, temporary_path)
    temporary_path.replace(final_path)

    print("Modello finale salvato in:", final_path)

    # Il checkpoint serve in caso di interruzione durante il training.
    # Dopo il salvataggio finale non è più necessario.
    checkpoint_path = run_dir / "checkpoint_latest.pt"

    if checkpoint_path.exists():
        checkpoint_path.unlink()
        print(
            "Checkpoint intermedio eliminato dopo il salvataggio finale:",
            checkpoint_path,
        )


def main() -> None:
    """Punto di ingresso dello script."""
    import time

    args = parse_args()

    validate_configuration(args)
    set_seed(args.seed)

    run_name, run_dir, device = prepare_run(args)

    # Salva subito la configurazione dell'esperimento.
    configuration_path = run_dir / "configuration.json"

    with configuration_path.open("w", encoding="utf-8") as file:
        json.dump(
            serializable_arguments(args),
            file,
            indent=2,
        )

    print("Configurazione salvata in:", configuration_path)

    # I nuovi dataset usano direttamente image_file e --image-dir.
    # L'allineamento simbolico viene eseguito solo per dataset legacy.
    if args.legacy_missing_page is not None:
        prepare_legacy_aligned_images(
            train_json=args.train_json,
            test_json=args.test_json,
            source_dir=args.image_dir,
            aligned_dir=args.aligned_image_dir,
            missing_page=args.legacy_missing_page,
        )

    data = build_data_components(args)

    model, optimizer = build_model_and_optimizer(
        args=args,
        class_weights=data["class_weights"],
        device=device,
    )

    start_time = time.perf_counter()

    history = train_model(
        model=model,
        optimizer=optimizer,
        train_loader=data["train_loader"],
        device=device,
        args=args,
        run_dir=run_dir,
    )

    metrics = evaluate_model(
        model=model,
        test_loader=data["test_loader"],
        device=device,
        label2id=data["label2id"],
        args=args,
        run_dir=run_dir,
    )

    save_final_model(
        model=model,
        history=history,
        metrics=metrics,
        label2id=data["label2id"],
        args=args,
        run_dir=run_dir,
    )

    elapsed_seconds = time.perf_counter() - start_time

    print("\nEsperimento completato")
    print("Nome:", run_name)
    print("Cartella:", run_dir.resolve())
    print(
        "Durata complessiva:",
        f"{elapsed_seconds / 60:.2f} minuti",
    )


if __name__ == "__main__":
    main()
