from __future__ import annotations

import argparse
import contextlib
import json
import os
import tempfile
from pathlib import Path

import numpy as np

from intentfence.calibration import (
    calibration_bundle_marker_path,
    validate_calibration_export_authorization,
)
from intentfence.constants import RISK_LABELS, RISK_TO_ID, TASK_ALIGNMENT_TO_ID
from intentfence.deployment import validate_model_directory
from intentfence.modeling import load_multitask_model
from intentfence.run_manifest import artifact_tree_sha256, sha256_file
from intentfence.schema import read_jsonl
from intentfence.text import build_model_text


def _publish_no_overwrite(staged: Path, destination: Path) -> None:
    """Publish one staged file without replacing a concurrently-created output."""

    os.link(staged, destination)
    staged.unlink()


def _write_export_bundle(
    output: Path,
    metadata_path: Path,
    *,
    arrays: dict[str, np.ndarray],
    metadata: dict[str, object],
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    marker_path = calibration_bundle_marker_path(output)
    published: list[Path] = []
    try:
        with tempfile.TemporaryDirectory(
            prefix=".intentfence-calibration-export-", dir=output.parent
        ) as temporary_directory:
            staging = Path(temporary_directory)
            staged_output = staging / output.name
            staged_metadata = staging / metadata_path.name
            staged_marker = staging / marker_path.name
            np.savez_compressed(staged_output, **arrays)
            metadata["logits_sha256"] = sha256_file(staged_output)
            staged_metadata.write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            metadata_sha256 = sha256_file(staged_metadata)
            _publish_no_overwrite(staged_output, output)
            published.append(output)
            _publish_no_overwrite(staged_metadata, metadata_path)
            published.append(metadata_path)
            staged_marker.write_text(
                json.dumps(
                    {
                        "format_version": 1,
                        "logits_path": str(output.resolve()),
                        "metadata_path": str(metadata_path.resolve()),
                        "logits_sha256": metadata["logits_sha256"],
                        "metadata_sha256": metadata_sha256,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            _publish_no_overwrite(staged_marker, marker_path)
            published.append(marker_path)
    except Exception:
        for path in published:
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Export frozen model logits for calibration")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--authorization-file",
        type=Path,
        help="project-owner authorization for exporting this exact frozen model/input pair",
    )
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
    marker_path = calibration_bundle_marker_path(args.output)
    if args.output.exists() or metadata_path.exists() or marker_path.exists():
        raise SystemExit(
            f"refusing to overwrite existing logits outputs: "
            f"{[str(path) for path in (args.output, metadata_path, marker_path) if path.exists()]}"
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
    model_dir = args.model_dir.resolve()
    input_path = args.input.resolve()
    input_sha256 = sha256_file(args.input)
    try:
        model_artifact_sha256 = artifact_tree_sha256(model_dir)
        model_metadata = validate_model_directory(model_dir)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise SystemExit(f"calibration model preflight failed: {exc}") from exc
    if args.authorization_file is None:
        raise SystemExit(
            "calibration export authorization is required for real logits export; "
            "use --preflight-only for a read-only check"
        )
    try:
        authorization = validate_calibration_export_authorization(
            args.authorization_file,
            model_dir=model_dir,
            model_artifact_sha256=model_artifact_sha256,
            model_revision=model_metadata["model_revision"],
            input_path=input_path,
            input_sha256=input_sha256,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise SystemExit(f"calibration export authorization failed: {exc}") from exc
    try:
        import torch
        from torch.utils.data import DataLoader, Dataset
    except ImportError as exc:
        raise SystemExit("Install intentfence[ml] to export logits") from exc

    model, tokenizer, metadata = load_multitask_model(model_dir, map_location=args.device)
    if metadata.model_revision != model_metadata["model_revision"]:
        raise SystemExit("calibration model metadata changed during export preflight")
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

    risk_logits_array = np.concatenate(risk_logits)
    alignment_logits_array = np.concatenate(alignment_logits)
    risk_labels_array = np.concatenate(risk_labels)
    alignment_labels_array = np.concatenate(alignment_labels)
    try:
        if artifact_tree_sha256(model_dir) != model_artifact_sha256:
            raise ValueError("model artifact changed during logits export")
        _write_export_bundle(
            args.output,
            metadata_path,
            arrays={
                "risk_logits": risk_logits_array,
                "alignment_logits": alignment_logits_array,
                "risk_labels": risk_labels_array,
                "alignment_labels": alignment_labels_array,
            },
            metadata={
                "format_version": 3,
                "model_dir": str(model_dir),
                "model_artifact_sha256": model_artifact_sha256,
                "model_revision": model_metadata["model_revision"],
                "input": str(input_path),
                "input_sha256": input_sha256,
                "split": "calibration",
                "samples": len(samples),
                "sample_ids": [sample.sample_id for sample in samples],
                "template_groups": [sample.template_group for sample in samples],
                "risk_labels": list(RISK_LABELS),
                "risk_logits_shape": [len(samples), len(RISK_TO_ID)],
                "alignment_logits_shape": [len(samples), int(alignment_logits_array.shape[1])],
                "input_mode": metadata.input_mode,
                "max_length": metadata.max_length,
                "alignment_target": metadata.alignment_target,
                "alignment_labels": list(metadata.alignment_labels),
                "authorized_by_project_owner": authorization["approved_by_project_owner"],
            },
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"calibration logits publication failed: {exc}") from exc
    print(f"Wrote logits for {len(samples)} samples to {args.output}")


if __name__ == "__main__":
    main()
