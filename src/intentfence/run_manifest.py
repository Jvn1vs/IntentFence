from __future__ import annotations

import ctypes
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

import yaml


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_tree_sha256(path: str | Path) -> str:
    """Hash a directory's relative file names and bytes deterministically."""

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


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _git_value(repository_root: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _system_memory_bytes() -> int | None:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total_physical)
        return None
    try:
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, ValueError):
        return None


def _accelerator_details() -> dict[str, Any]:
    try:
        import torch
    except ImportError:
        return {"cuda_available": False, "cuda_version": None, "devices": []}
    available = torch.cuda.is_available()
    devices = []
    if available:
        for index in range(torch.cuda.device_count()):
            properties = torch.cuda.get_device_properties(index)
            devices.append(
                {
                    "index": index,
                    "name": properties.name,
                    "total_memory_bytes": properties.total_memory,
                }
            )
    return {
        "cuda_available": available,
        "cuda_version": torch.version.cuda,
        "cudnn_version": torch.backends.cudnn.version() if available else None,
        "devices": devices,
    }


def build_run_manifest(
    *,
    repository_root: Path,
    config_path: Path,
    train_path: Path,
    validation_path: Path,
    checkpoint_dir: Path,
    started_at: str,
    ended_at: str,
    duration_seconds: float,
    cost_usd: float,
    cost_cny: float | None = None,
    stage: str | None = None,
    authorization_path: Path | None = None,
) -> dict[str, Any]:
    if cost_usd < 0:
        raise ValueError("cost_usd cannot be negative")
    if cost_cny is not None and cost_cny < 0:
        raise ValueError("cost_cny cannot be negative")
    if authorization_path is not None and not authorization_path.is_file():
        raise FileNotFoundError(f"training authorization file does not exist: {authorization_path}")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    checkpoint_files = {
        str(path.relative_to(checkpoint_dir)).replace("\\", "/"): {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(checkpoint_dir.rglob("*"))
        if path.is_file()
    }
    git_status = _git_value(repository_root, "status", "--porcelain")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": "completed",
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": duration_seconds,
        "cost_usd": cost_usd,
        "executor": "project_owner",
        "claim_scope": "engineering_smoke_not_research_result",
        "git": {
            "commit": _git_value(repository_root, "rev-parse", "HEAD"),
            "dirty": bool(git_status),
        },
        "configuration": {
            "path": str(config_path),
            "sha256": sha256_file(config_path),
            "run_name": config.get("run_name"),
            "model_name": config.get("model_name"),
            "model_revision": config.get("model_revision"),
            "input_mode": config.get("input_mode"),
            "seed": config.get("seed"),
        },
        "data": {
            "train": {"path": str(train_path), "sha256": sha256_file(train_path)},
            "validation": {
                "path": str(validation_path),
                "sha256": sha256_file(validation_path),
            },
        },
        "environment": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER"),
            "system_memory_bytes": _system_memory_bytes(),
            "accelerator": _accelerator_details(),
            "packages": {
                name: _package_version(name)
                for name in ("torch", "transformers", "sentencepiece", "numpy")
            },
        },
        "checkpoint_files": checkpoint_files,
    }
    if cost_cny is not None:
        payload["actual_cost_cny"] = cost_cny
    if stage is not None:
        payload["stage"] = stage
    if authorization_path is not None:
        payload["training_authorization"] = {
            "path": str(authorization_path),
            "sha256": sha256_file(authorization_path),
        }
    return payload


def write_run_manifest(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
