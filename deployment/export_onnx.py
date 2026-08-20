from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from intentfence.modeling import load_multitask_model


def main() -> None:
    parser = argparse.ArgumentParser(description="Export IntentFence to ONNX and optionally INT8")
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--opset", type=int, default=17)
    parser.add_argument("--quantize", action="store_true")
    args = parser.parse_args()
    try:
        import torch
    except ImportError as exc:
        raise SystemExit("Install intentfence[ml,onnx] before export") from exc

    model, tokenizer, metadata = load_multitask_model(args.model_dir)
    model.eval()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer.save_pretrained(args.output_dir / "tokenizer")
    sample = tokenizer(
        "Summarize the page [SEP] This is a public article. [SEP] return_summary()",
        return_tensors="pt",
        truncation=True,
        max_length=metadata.max_length,
    )

    class ExportWrapper(torch.nn.Module):
        def __init__(self, wrapped: Any) -> None:
            super().__init__()
            self.wrapped = wrapped

        def forward(self, input_ids: Any, attention_mask: Any) -> tuple[Any, Any]:
            output = self.wrapped(input_ids=input_ids, attention_mask=attention_mask)
            return output["risk_logits"], output["alignment_logits"]

    target = args.output_dir / "model.onnx"
    torch.onnx.export(
        ExportWrapper(model),
        (sample["input_ids"], sample["attention_mask"]),
        target,
        input_names=["input_ids", "attention_mask"],
        output_names=["risk_logits", "alignment_logits"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "sequence"},
            "attention_mask": {0: "batch", 1: "sequence"},
            "risk_logits": {0: "batch"},
            "alignment_logits": {0: "batch"},
        },
        opset_version=args.opset,
        do_constant_folding=True,
    )
    quantized = None
    if args.quantize:
        try:
            from onnxruntime.quantization import QuantType, quantize_dynamic
        except ImportError as exc:
            raise SystemExit("Install intentfence[onnx] to quantize the exported model") from exc
        quantized = args.output_dir / "model.int8.onnx"
        quantize_dynamic(str(target), str(quantized), weight_type=QuantType.QInt8)
    (args.output_dir / "export_metadata.json").write_text(
        json.dumps(
            {
                "source_model": str(args.model_dir.resolve()),
                "onnx": str(target.name),
                "quantized": quantized.name if quantized else None,
                "opset": args.opset,
                "max_length": metadata.max_length,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
