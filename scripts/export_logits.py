from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from intentfence.constants import RISK_TO_ID
from intentfence.modeling import load_multitask_model
from intentfence.schema import read_jsonl
from intentfence.text import build_model_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Export frozen model logits for calibration")
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    try:
        import torch
        from torch.utils.data import DataLoader, Dataset
    except ImportError as exc:
        raise SystemExit("Install intentfence[ml] to export logits") from exc

    model, tokenizer, metadata = load_multitask_model(args.model_dir, map_location=args.device)
    model.to(args.device).eval()
    samples = read_jsonl(args.input)

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
            item["alignment_label"] = torch.tensor(sample.alignment_label)
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
    np.savez_compressed(
        args.output,
        risk_logits=np.concatenate(risk_logits),
        alignment_logits=np.concatenate(alignment_logits),
        risk_labels=np.concatenate(risk_labels),
        alignment_labels=np.concatenate(alignment_labels),
    )
    args.output.with_suffix(".json").write_text(
        json.dumps(
            {
                "model_dir": str(args.model_dir.resolve()),
                "input": str(args.input.resolve()),
                "samples": len(samples),
                "input_mode": metadata.input_mode,
                "max_length": metadata.max_length,
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
