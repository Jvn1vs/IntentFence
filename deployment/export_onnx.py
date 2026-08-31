from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from intentfence.deployment import (
    ONNX_INPUT_NAMES,
    ONNX_OUTPUT_NAMES,
    build_export_metadata,
    validate_export_artifacts,
    validate_export_inputs,
    write_export_metadata,
)
from intentfence.modeling import load_multitask_model


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export IntentFence to ONNX and optionally INT8"
    )
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--opset", type=int, default=17)
    parser.add_argument("--quantize", action="store_true")
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate the source and output paths without loading a model or writing files",
    )
    args = parser.parse_args()
    source_metadata = validate_export_inputs(
        args.model_dir,
        args.output_dir,
        opset=args.opset,
    )
    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "passed",
                    "model_dir": str(args.model_dir.resolve()),
                    "output_dir": str(args.output_dir.resolve()),
                    "opset": args.opset,
                    "quantize": args.quantize,
                    "model_revision": source_metadata["model_revision"],
                },
                sort_keys=True,
            )
        )
        return

    try:
        import torch
    except ImportError as exc:
        raise SystemExit("Install intentfence[ml,onnx] before export") from exc

    model, tokenizer, metadata = load_multitask_model(args.model_dir)
    model.eval()
    args.output_dir.mkdir(parents=True)
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
        input_names=list(ONNX_INPUT_NAMES),
        output_names=list(ONNX_OUTPUT_NAMES),
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
    export_metadata = build_export_metadata(
        args.output_dir,
        args.model_dir,
        model_metadata=source_metadata,
        opset=args.opset,
        quantized_path=quantized,
    )
    write_export_metadata(args.output_dir, export_metadata)
    validate_export_artifacts(args.output_dir, model_path=target)
    print(target)


if __name__ == "__main__":
    main()
