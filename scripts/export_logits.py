from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from intentfence.constants import RISK_LABELS, RISK_TO_ID, TASK_ALIGNMENT_TO_ID
from intentfence.modeling import load_multitask_model
from intentfence.run_manifest import sha256_file
from intentfence.schema import read_jsonl
from intentfence.text import build_model_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Export frozen model logits for calibration")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="validate the explicit calibration split without loading a model or writing files",
    )
    args = parser.parse_args()
    if args.output.suffix.lower() != ".npz":
        raise SystemExit("--output must use the .npz suffix")
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be positive")
    metadata_path = args.output.with_suffix(".json")
    if args.output.exists() or metadata_path.exists():
        raise SystemExit(
            f"refusing to overwrite existing logits outputs: {[str(path) for path in (args.output, metadata_path) if path.exists()]}"
        )
    try:
        samples = read_jsonl(args.input)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"calibration input preflight failed: {exc}") from exc
    if not samples:
        raise SystemExit("calibration input preflight failed: input contains no samples")
    wrong_split = [sample.sample_id for sample in samples if sample.split != "calibration"]
    if wrong_split:
        raise SystemExit(
            "calibration input preflight failed: every sample must have split='calibration'; "
            f"first invalid ids={wrong_split[:5]}"
        )
    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "preflight_passed",
                    "split": "calibration",
                    "samples": len(samples),
                    "input": str(args.input.resolve()),
                    "input_sha256": sha256_file(args.input),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    if args.model_dir is None:
        raise SystemExit("--model-dir is required unless --preflight-only is used")
    try:
        import torch
        from torch.utils.data import DataLoader, Dataset
    except ImportError as exc:
        raise SystemExit("Install intentfence[ml] to export logits") from exc

    model, tokenizer, metadata = load_multitask_model(args.model_dir, map_location=args.device)
    model.to(args.device).eval()

    class CalibrationDataset(Dataset):
        def __len__(self) -> int:
            return len(samples)

        def __getitem__(self, index: int):
            sample = samples[index]
            text = build_model_text(
                sample, metadata.input_mode, tokenizer.sep_token or "[SEP]"
            )
            encoded = tokenizer(
                text,
                truncation=True,
                max_length=metadata.max_length,
                padding="max_length",
                return_tensors="pt",
            )
            item = {key: value.squeeze(0) for key, value in encoded.items()}
            item["risk_label"] = torch.tensor(RISK_TO_ID[sample.risk_label])
            alignment_id = (
                TASK_ALIGNMENT_TO_ID[str(sample.task_alignment_label)]
                if metadata.alignment_target == "task_alignment"
                else sample.alignment_label
            )
            item["alignment_label"] = torch.tensor(alignment_id)
            return item

    risk_logits, alignment_logits, risk_labels, alignment_labels = [], [], [], []
    with torch.inference_mode():
        for batch in DataLoader(CalibrationDataset(), batch_size=args.batch_size, shuffle=False):
            risk_labels.append(batch.pop("risk_label").numpy())
            alignment_labels.append(batch.pop("alignment_label").numpy())
            output = model(**{key: value.to(args.device) for key, value in batch.items()})
            risk_logits.append(output["risk_logits"].cpu().numpy())
            alignment_logits.append(output["alignment_logits"].cpu().numpy())

    args.output.parent.mkdir(parents=True, exist_ok=True)
    risk_logits_array = np.concatenate(risk_logits)
    alignment_logits_array = np.concatenate(alignment_logits)
    risk_labels_array = np.concatenate(risk_labels)
    alignment_labels_array = np.concatenate(alignment_labels)
    np.savez_compressed(
        args.output,
        risk_logits=risk_logits_array,
        alignment_logits=alignment_logits_array,
        risk_labels=risk_labels_array,
        alignment_labels=alignment_labels_array,
    )
    metadata_path.write_text(
        json.dumps(
            {
                "format_version": 2,
                "model_dir": str(args.model_dir.resolve()),
                "input": str(args.input.resolve()),
                "input_sha256": sha256_file(args.input),
                "split": "calibration",
                "samples": len(samples),
                "risk_labels": list(RISK_LABELS),
                "risk_logits_shape": [len(samples), len(RISK_TO_ID)],
                "alignment_logits_shape": [len(samples), int(alignment_logits_array.shape[1])],
                "input_mode": metadata.input_mode,
                "max_length": metadata.max_length,
                "alignment_target": metadata.alignment_target,
                "alignment_labels": list(metadata.alignment_labels),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote logits for {len(samples)} samples to {args.output}")


if __name__ == "__main__":
    main()
