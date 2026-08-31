from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from intentfence.constants import (
    ALIGNMENT_TARGETS,
    INPUT_MODES,
    LEGACY_ALIGNMENT_LABELS,
    RISK_LABELS,
    TASK_ALIGNMENT_LABELS,
)

EXPORT_METADATA_SCHEMA_VERSION = 2
EXPORT_FP32_FILENAME = "model.onnx"
EXPORT_INT8_FILENAME = "model.int8.onnx"
EXPORT_TOKENIZER_DIRNAME = "tokenizer"
ONNX_INPUT_NAMES = ("input_ids", "attention_mask")
ONNX_OUTPUT_NAMES = ("risk_logits", "alignment_logits")
ONNX_DYNAMIC_AXES = {
    "input_ids": {"0": "batch", "1": "sequence"},
    "attention_mask": {"0": "batch", "1": "sequence"},
    "risk_logits": {"0": "batch"},
    "alignment_logits": {"0": "batch"},
}
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_REVISION_RE = re.compile(r"[0-9a-f]{40}\Z")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_tree_sha256(path: str | Path) -> str:
    """Hash relative file names and bytes deterministically."""

    root = Path(path)
    if not root.is_dir():
        raise FileNotFoundError(f"artifact directory does not exist: {root}")
    digest = hashlib.sha256()
    files = [item for item in root.rglob("*") if item.is_file()]
    for item in sorted(files, key=lambda value: value.relative_to(root).as_posix()):
        relative = item.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        with item.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _read_json_object(path: Path, *, description: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{description} must be valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{description} must be a JSON object: {path}")
    return payload


def _require_sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _require_revision(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or _REVISION_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a full lowercase 40-character revision")
    return value


def _validate_model_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    if list(payload.get("risk_labels", ())) != list(RISK_LABELS):
        raise ValueError("model metadata risk_labels must match the frozen Task Shield labels")

    alignment_target = payload.get("alignment_target", "legacy_binary")
    if alignment_target not in ALIGNMENT_TARGETS:
        raise ValueError(f"model metadata alignment_target must be one of {ALIGNMENT_TARGETS}")
    expected_alignment = (
        TASK_ALIGNMENT_LABELS
        if alignment_target == "task_alignment"
        else LEGACY_ALIGNMENT_LABELS
    )
    if list(payload.get("alignment_labels", ())) != list(expected_alignment):
        raise ValueError("model metadata alignment_labels do not match alignment_target")

    if payload.get("input_mode") not in INPUT_MODES:
        raise ValueError(f"model metadata input_mode must be one of {INPUT_MODES}")
    max_length = payload.get("max_length")
    if isinstance(max_length, bool) or not isinstance(max_length, int) or max_length <= 0:
        raise ValueError("model metadata max_length must be a positive integer")
    try:
        alignment_loss_weight = float(payload.get("alignment_loss_weight"))
    except (TypeError, ValueError) as exc:
        raise ValueError("model metadata alignment_loss_weight must be numeric") from exc
    if not math.isfinite(alignment_loss_weight) or alignment_loss_weight < 0:
        raise ValueError("model metadata alignment_loss_weight must be finite and non-negative")
    _require_revision(payload.get("model_revision"), field="model metadata model_revision")
    expected_version = "3" if alignment_target == "task_alignment" else "2"
    if str(payload.get("version", expected_version)) != expected_version:
        raise ValueError(
            f"model metadata version must be {expected_version} for {alignment_target}"
        )
    return payload


def validate_model_directory(model_dir: str | Path) -> dict[str, Any]:
    """Validate the immutable files required by an exported model source."""

    source = Path(model_dir)
    if not source.is_dir():
        raise FileNotFoundError(f"model directory does not exist: {source}")
    for name in ("metadata.json", "heads.pt"):
        if not (source / name).is_file():
            raise FileNotFoundError(f"model directory is missing {name}: {source}")
    for name in ("encoder", "tokenizer"):
        if not (source / name).is_dir():
            raise FileNotFoundError(f"model directory is missing {name}/: {source}")
    return _validate_model_metadata(
        _read_json_object(source / "metadata.json", description="model metadata")
    )


def validate_export_inputs(
    model_dir: str | Path,
    output_dir: str | Path,
    *,
    opset: int,
) -> dict[str, Any]:
    """Run export checks before importing/loading a model or creating outputs."""

    if isinstance(opset, bool) or not isinstance(opset, int) or not 11 <= opset <= 20:
        raise ValueError("opset must be an integer in [11, 20]")
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing export directory: {output}")
    return validate_model_directory(model_dir)


def _file_artifact(path: Path, *, expected_name: str) -> dict[str, str]:
    if path.name != expected_name or not path.is_file():
        raise FileNotFoundError(f"missing exported artifact: {path}")
    return {"path": expected_name, "sha256": sha256_file(path)}


def build_export_metadata(
    output_dir: str | Path,
    model_dir: str | Path,
    *,
    model_metadata: dict[str, Any],
    opset: int,
    quantized_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build the hash-bound metadata written beside an ONNX export."""

    output = Path(output_dir)
    source = Path(model_dir)
    if not output.is_dir():
        raise FileNotFoundError(f"export directory does not exist: {output}")
    if isinstance(opset, bool) or not isinstance(opset, int) or not 11 <= opset <= 20:
        raise ValueError("opset must be an integer in [11, 20]")
    source_metadata = validate_model_directory(source)
    _validate_model_metadata(model_metadata)
    for key in (
        "model_revision",
        "risk_labels",
        "alignment_labels",
        "alignment_target",
        "input_mode",
        "max_length",
        "version",
    ):
        if model_metadata.get(key) != source_metadata.get(key):
            raise ValueError(f"model_metadata.{key} does not match source model metadata")
    tokenizer = output / EXPORT_TOKENIZER_DIRNAME
    if not tokenizer.is_dir():
        raise FileNotFoundError(f"export is missing tokenizer/: {output}")
    quantized = Path(quantized_path) if quantized_path is not None else None
    if quantized is not None and quantized.resolve().parent != output.resolve():
        raise ValueError("quantized artifact must be inside the export directory")

    metadata = {
        "schema_version": EXPORT_METADATA_SCHEMA_VERSION,
        "source_model": {
            "path": str(source.resolve()),
            "model_revision": model_metadata["model_revision"],
            "artifact_sha256": artifact_tree_sha256(source),
            "metadata_sha256": sha256_file(source / "metadata.json"),
        },
        "export": {
            "opset": opset,
            "input_names": list(ONNX_INPUT_NAMES),
            "output_names": list(ONNX_OUTPUT_NAMES),
            "dynamic_axes": ONNX_DYNAMIC_AXES,
            "max_length": model_metadata["max_length"],
            "risk_labels": list(model_metadata["risk_labels"]),
            "alignment_labels": list(model_metadata["alignment_labels"]),
            "alignment_target": model_metadata.get("alignment_target", "legacy_binary"),
            "model_metadata_version": str(model_metadata.get("version", "")),
            "quantization": "dynamic_weight_qint8" if quantized is not None else None,
        },
        "artifacts": {
            "tokenizer": {
                "path": EXPORT_TOKENIZER_DIRNAME,
                "tree_sha256": artifact_tree_sha256(tokenizer),
            },
            "fp32": _file_artifact(output / EXPORT_FP32_FILENAME, expected_name=EXPORT_FP32_FILENAME),
            "int8": (
                _file_artifact(quantized, expected_name=EXPORT_INT8_FILENAME)
                if quantized is not None
                else None
            ),
        },
    }
    return metadata


def write_export_metadata(output_dir: str | Path, payload: dict[str, Any]) -> Path:
    destination = Path(output_dir) / "export_metadata.json"
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite export metadata: {destination}")
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def _validate_export_file(
    output: Path,
    value: Any,
    *,
    key: str,
    expected_name: str,
) -> None:
    if not isinstance(value, dict) or value.get("path") != expected_name:
        raise ValueError(f"export metadata artifacts.{key}.path must be {expected_name!r}")
    path = output / expected_name
    _require_sha256(value.get("sha256"), field=f"artifacts.{key}.sha256")
    if not path.is_file():
        raise FileNotFoundError(f"export metadata references missing artifact: {path}")
    if sha256_file(path) != value["sha256"]:
        raise ValueError(f"artifacts.{key}.sha256 does not match {path}")


def validate_export_artifacts(
    output_dir: str | Path,
    *,
    model_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate an exported ONNX directory and return its trusted metadata."""

    output = Path(output_dir)
    if not output.is_dir():
        raise FileNotFoundError(f"export directory does not exist: {output}")
    payload = _read_json_object(
        output / "export_metadata.json", description="export metadata"
    )
    if payload.get("schema_version") != EXPORT_METADATA_SCHEMA_VERSION:
        raise ValueError(
            f"export metadata schema_version must be {EXPORT_METADATA_SCHEMA_VERSION}"
        )

    source = payload.get("source_model")
    if not isinstance(source, dict):
        raise ValueError("export metadata source_model must be an object")
    _require_revision(source.get("model_revision"), field="source_model.model_revision")
    _require_sha256(source.get("artifact_sha256"), field="source_model.artifact_sha256")
    _require_sha256(source.get("metadata_sha256"), field="source_model.metadata_sha256")

    export = payload.get("export")
    if not isinstance(export, dict):
        raise ValueError("export metadata export must be an object")
    opset = export.get("opset")
    if isinstance(opset, bool) or not isinstance(opset, int) or not 11 <= opset <= 20:
        raise ValueError("export metadata opset must be an integer in [11, 20]")
    if tuple(export.get("input_names", ())) != ONNX_INPUT_NAMES:
        raise ValueError("export metadata input_names do not match the exporter contract")
    if tuple(export.get("output_names", ())) != ONNX_OUTPUT_NAMES:
        raise ValueError("export metadata output_names do not match the exporter contract")
    if export.get("dynamic_axes") != ONNX_DYNAMIC_AXES:
        raise ValueError("export metadata dynamic_axes do not match the exporter contract")
    max_length = export.get("max_length")
    if isinstance(max_length, bool) or not isinstance(max_length, int) or max_length <= 0:
        raise ValueError("export metadata max_length must be a positive integer")
    if list(export.get("risk_labels", ())) != list(RISK_LABELS):
        raise ValueError("export metadata risk_labels must match the frozen Task Shield labels")
    alignment_target = export.get("alignment_target")
    if alignment_target not in ALIGNMENT_TARGETS:
        raise ValueError("export metadata alignment_target is invalid")
    expected_alignment = (
        TASK_ALIGNMENT_LABELS
        if alignment_target == "task_alignment"
        else LEGACY_ALIGNMENT_LABELS
    )
    if list(export.get("alignment_labels", ())) != list(expected_alignment):
        raise ValueError("export metadata alignment_labels do not match alignment_target")
    expected_version = "3" if alignment_target == "task_alignment" else "2"
    if str(export.get("model_metadata_version")) != expected_version:
        raise ValueError("export metadata model_metadata_version does not match alignment_target")

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("export metadata artifacts must be an object")
    tokenizer = artifacts.get("tokenizer")
    if not isinstance(tokenizer, dict) or tokenizer.get("path") != EXPORT_TOKENIZER_DIRNAME:
        raise ValueError("export metadata tokenizer path is invalid")
    _require_sha256(tokenizer.get("tree_sha256"), field="artifacts.tokenizer.tree_sha256")
    tokenizer_path = output / EXPORT_TOKENIZER_DIRNAME
    if not tokenizer_path.is_dir():
        raise FileNotFoundError(f"export tokenizer directory does not exist: {tokenizer_path}")
    if artifact_tree_sha256(tokenizer_path) != tokenizer["tree_sha256"]:
        raise ValueError("artifacts.tokenizer.tree_sha256 does not match tokenizer/")
    _validate_export_file(
        output,
        artifacts.get("fp32"),
        key="fp32",
        expected_name=EXPORT_FP32_FILENAME,
    )
    int8 = artifacts.get("int8")
    if int8 is not None:
        if export.get("quantization") != "dynamic_weight_qint8":
            raise ValueError("export metadata quantization does not match the INT8 artifact")
        _validate_export_file(
            output,
            int8,
            key="int8",
            expected_name=EXPORT_INT8_FILENAME,
        )
    elif (output / EXPORT_INT8_FILENAME).exists():
        raise ValueError("model.int8.onnx exists but is not hash-bound in export metadata")
    elif export.get("quantization") is not None:
        raise ValueError("export metadata quantization claims an absent INT8 artifact")
    if model_path is not None:
        requested = Path(model_path).resolve()
        if requested.parent != output.resolve():
            raise ValueError("model_path must be inside the export directory")
        if requested.name == EXPORT_FP32_FILENAME:
            selected = artifacts["fp32"]
        elif requested.name == EXPORT_INT8_FILENAME:
            selected = int8
        else:
            raise ValueError("model_path must be model.onnx or model.int8.onnx")
        if selected is None:
            raise FileNotFoundError(f"requested ONNX variant is not present: {requested.name}")
    return payload
