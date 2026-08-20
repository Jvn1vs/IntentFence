from __future__ import annotations

__version__ = "0.1.0"

RISK_LABELS: tuple[str, ...] = (
    "benign",
    "instruction_hijacking",
    "data_exfiltration",
    "privilege_escalation",
    "tool_manipulation",
)

RISK_TO_ID = {label: index for index, label in enumerate(RISK_LABELS)}
ID_TO_RISK = dict(enumerate(RISK_LABELS))

SPLIT_NAMES: tuple[str, ...] = (
    "train",
    "validation",
    "calibration",
    "test_a",
    "test_b",
    "test_c",
    "test_d",
)

INPUT_MODES: tuple[str, ...] = ("text", "context", "action")
