from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
from typing import Any

from intentfence.modeling import load_multitask_model


def _require_torch() -> Any:
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("Install the ml extra before verifying a checkpoint") from exc
    return torch


def _predict_once(model_dir: Path, text: str) -> tuple[Any, Any, dict[str, Any]]:
    torch = _require_torch()
    model, tokenizer, metadata = load_multitask_model(model_dir)
    model.eval()
    encoded = tokenizer(
        text,
        truncation=True,
        max_length=metadata.max_length,
        padding="max_length",
        return_tensors="pt",
    )
    with torch.inference_mode():
        output = model(**encoded)
    risk_logits = output["risk_logits"].detach().cpu().clone()
    alignment_logits = output["alignment_logits"].detach().cpu().clone()
    details = {
        "metadata_version": metadata.version,
        "model_name": metadata.model_name,
        "model_revision": metadata.model_revision,
        "input_mode": metadata.input_mode,
        "risk_shape": list(risk_logits.shape),
        "alignment_shape": list(alignment_logits.shape),
    }
    del model, tokenizer, encoded, output
    gc.collect()
    return risk_logits, alignment_logits, details


def verify_checkpoint(model_dir: Path) -> dict[str, Any]:
    torch = _require_torch()
    probe = "User task: summarize the document. External content: ordinary fixture text."
    first_risk, first_alignment, details = _predict_once(model_dir, probe)
    second_risk, second_alignment, second_details = _predict_once(model_dir, probe)
    if details != second_details:
        raise RuntimeError("checkpoint metadata changed between reloads")
    if details["risk_shape"] != [1, 5] or details["alignment_shape"] != [1, 2]:
        raise RuntimeError(f"unexpected output shapes: {details}")
    torch.testing.assert_close(first_risk, second_risk, rtol=0.0, atol=0.0)
    torch.testing.assert_close(first_alignment, second_alignment, rtol=0.0, atol=0.0)
    return {"status": "checkpoint_reload_passed", **details}


def main() -> None:
    parser = argparse.ArgumentParser(description="Reload and compare an IntentFence checkpoint")
    parser.add_argument("--model-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_checkpoint(args.model_dir), sort_keys=True))


if __name__ == "__main__":
    main()
