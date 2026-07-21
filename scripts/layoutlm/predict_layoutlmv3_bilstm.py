#!/usr/bin/env python3
# coding: utf-8

import argparse
import copy
import json
from collections import defaultdict
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from train_layoutlmv3_bilstm import (
    IPSABlockWindowDataset,
    LayoutLMv3BiLSTMForBlockClassification,
    block_window_collate_fn,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Inferenza multiclasse sui blocchi IPSA con LayoutLMv3 e BiLSTM."
    )
    parser.add_argument("--input-json", required=True)
    parser.add_argument("--images-dir", required=True)
    parser.add_argument("--label2id", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    parser.add_argument("--max-pages", type=int, default=None)
    return parser.parse_args()


def checkpoint_argument(arguments, name, default):
    if not isinstance(arguments, dict):
        return default
    value = arguments.get(name, default)
    return default if value is None else value


def load_checkpoint(path, device):
    try:
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    except TypeError:
        checkpoint = torch.load(path, map_location="cpu")

    if "model_state_dict" not in checkpoint:
        raise KeyError("Il checkpoint non contiene model_state_dict")

    label2id = checkpoint.get("label2id")
    if not isinstance(label2id, dict) or not label2id:
        raise ValueError("Il checkpoint non contiene label2id")

    label2id = {str(label): int(idx) for label, idx in label2id.items()}
    id2label = {idx: label for label, idx in label2id.items()}

    arguments = checkpoint.get("arguments", {})
    state_dict = checkpoint["model_state_dict"]
    class_weights = state_dict.get("class_weights")

    model = LayoutLMv3BiLSTMForBlockClassification(
        num_labels=len(label2id),
        class_weights=class_weights,
        lstm_hidden_size=int(checkpoint_argument(arguments, "lstm_hidden_size", 256)),
        lstm_layers=int(checkpoint_argument(arguments, "lstm_layers", 1)),
        dropout=float(checkpoint_argument(arguments, "dropout", 0.1)),
        freeze_layoutlmv3=bool(
            checkpoint_argument(arguments, "freeze_layoutlmv3", False)
        ),
    )

    missing, unexpected = model.load_state_dict(state_dict, strict=False)
    real_missing = [key for key in missing if key != "class_weights"]

    if real_missing or unexpected:
        raise RuntimeError(
            "Checkpoint incompatibile:\n"
            f"chiavi mancanti: {real_missing}\n"
            f"chiavi inattese: {unexpected}"
        )

    model.to(device)
    model.eval()

    configuration = {
        "max_length": int(checkpoint_argument(arguments, "max_length", 512)),
        "stride_blocks": int(checkpoint_argument(arguments, "stride_blocks", 0)),
    }

    return model, label2id, id2label, configuration


def main():
    args = parse_args()

    if args.device == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA non disponibile")
        device = torch.device("cuda")
    elif args.device == "cpu":
        device = torch.device("cpu")
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    print("Dispositivo:", device)

    model, checkpoint_label2id, id2label, configuration = load_checkpoint(
        Path(args.checkpoint), device
    )

    with open(args.label2id, encoding="utf-8") as f:
        file_label2id = {str(k): int(v) for k, v in json.load(f).items()}

    if file_label2id != checkpoint_label2id:
        raise ValueError(
            "Il label2id fornito non coincide con quello salvato nel checkpoint.\n"
            f"File: {file_label2id}\nCheckpoint: {checkpoint_label2id}"
        )

    input_json = Path(args.input_json)
    dataset_input = input_json
    temporary_subset = None

    if args.max_pages is not None:
        with input_json.open(encoding="utf-8") as f:
            subset_pages = json.load(f)[: args.max_pages]

        temporary_subset = Path(args.output_json).with_suffix(".subset.tmp.json")
        temporary_subset.write_text(
            json.dumps(subset_pages, ensure_ascii=False), encoding="utf-8"
        )
        dataset_input = temporary_subset

    try:
        dataset = IPSABlockWindowDataset(
            pages_path=str(dataset_input),
            image_dir=args.images_dir,
            label2id_path=args.label2id,
            max_length=configuration["max_length"],
            stride_blocks=configuration["stride_blocks"],
        )

        loader = DataLoader(
            dataset,
            batch_size=args.batch_size,
            shuffle=False,
            num_workers=args.num_workers,
            collate_fn=block_window_collate_fn,
            pin_memory=(device.type == "cuda"),
        )

        print("Pagine:", len(dataset.pages))
        print("Finestre:", len(dataset))
        print("Label:", checkpoint_label2id)

        accumulated = defaultdict(list)

        with torch.inference_mode():
            for batch_number, batch in enumerate(loader, start=1):
                output = model(
                    input_ids=batch["input_ids"].to(device),
                    attention_mask=batch["attention_mask"].to(device),
                    bbox=batch["bbox"].to(device),
                    pixel_values=batch["pixel_values"].to(device),
                    block_ids=batch["block_ids"].to(device),
                )

                probabilities = torch.softmax(output["logits"], dim=-1).cpu()
                mask = output["mask"].cpu()

                for sample_idx in range(probabilities.size(0)):
                    page_id = batch["page_id"][sample_idx]
                    original_indices = batch["original_block_indices"][sample_idx]
                    valid_blocks = int(mask[sample_idx].sum().item())

                    for compact_idx in range(valid_blocks):
                        original_idx = int(original_indices[compact_idx].item())
                        if original_idx < 0:
                            continue

                        accumulated[(page_id, original_idx)].append(
                            probabilities[sample_idx, compact_idx].tolist()
                        )

                if batch_number % 25 == 0:
                    print(f"Finestre elaborate: {batch_number}/{len(loader)}")

        output_pages = copy.deepcopy(dataset.pages)
        page_position = {
            page["page"]: idx for idx, page in enumerate(output_pages)
        }

        predicted_count = 0

        for (page_id, block_idx), vectors in accumulated.items():
            mean_probabilities = [
                sum(values) / len(values) for values in zip(*vectors)
            ]
            predicted_id = max(
                range(len(mean_probabilities)),
                key=mean_probabilities.__getitem__,
            )
            predicted_label = id2label[predicted_id]

            block = output_pages[page_position[page_id]]["blocks"][block_idx]
            block["predicted_label"] = predicted_label
            block["prediction_confidence"] = round(
                float(mean_probabilities[predicted_id]), 6
            )
            block["prediction_probabilities"] = {
                id2label[idx]: round(float(probability), 6)
                for idx, probability in enumerate(mean_probabilities)
            }
            predicted_count += 1

        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(output_pages, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        total_blocks = sum(len(page.get("blocks", [])) for page in output_pages)
        print(f"Blocchi predetti: {predicted_count}/{total_blocks}")
        print("Output:", output_path)

    finally:
        if temporary_subset is not None:
            temporary_subset.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
