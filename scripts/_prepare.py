from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from intentfence.schema import IntentSample, iter_json_objects, write_jsonl


def _dig(record: dict[str, Any], key: str) -> Any:
    current: Any = record
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def first_text(record: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _dig(record, key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (dict, list)) and value:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return ""


def stable_id(source: str, record: dict[str, Any], index: int) -> str:
    existing = first_text(record, ("sample_id", "id", "case_id", "task_id"))
    if existing:
        safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in existing)
        return f"{source.casefold()}_{safe}"
    digest = hashlib.sha256(
        json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    return f"{source.casefold()}_{index:06d}_{digest}"


def risk_from_record(record: dict[str, Any], default: str) -> str:
    raw = first_text(record, ("risk_label", "attack_type", "attack_category", "category", "label"))
    normalized = raw.casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "benign": "benign",
        "clean": "benign",
        "legit": "benign",
        "safe": "benign",
        "instruction_hijacking": "instruction_hijacking",
        "prompt_injection": "instruction_hijacking",
        "indirect_prompt_injection": "instruction_hijacking",
        "data_exfiltration": "data_exfiltration",
        "data_stealing": "data_exfiltration",
        "direct_harm": "tool_manipulation",
        "privilege_escalation": "privilege_escalation",
        "tool_manipulation": "tool_manipulation",
    }
    if normalized in aliases:
        return aliases[normalized]
    truthy = record.get("injected", record.get("is_attack", record.get("attack")))
    if truthy is False or truthy == 0:
        return "benign"
    return default


def convert_file(
    input_path: Path,
    output_path: Path,
    *,
    source: str,
    default_risk: str,
    force_benign: bool = False,
    allow_missing_action: bool = False,
) -> dict[str, Any]:
    converted: list[IntentSample] = []
    skipped: list[dict[str, Any]] = []
    for index, record in enumerate(iter_json_objects(input_path), start=1):
        user_goal = first_text(
            record,
            (
                "user_goal",
                "user_task",
                "user_instruction",
                "user_query",
                "query",
                "question",
                "task.instruction",
            ),
        )
        content = first_text(
            record,
            (
                "untrusted_content",
                "tool_response",
                "tool_output",
                "injected_content",
                "attack_instruction",
                "content",
                "context",
                "document",
                "email",
                "response",
            ),
        )
        action = first_text(
            record,
            (
                "proposed_action",
                "tool_call",
                "action",
                "assistant_action",
                "attacker_tool",
                "target_action",
            ),
        )
        missing = [
            name
            for name, value in (("user_goal", user_goal), ("untrusted_content", content))
            if not value
        ]
        if not action and not allow_missing_action:
            missing.append("proposed_action")
        if missing:
            skipped.append({"record_index": index, "missing": missing})
            continue
        if not action:
            action = "NO_ACTION_PROVIDED"
        risk = "benign" if force_benign else risk_from_record(record, default_risk)
        sample_id = stable_id(source, record, index)
        template = first_text(record, ("template_group", "attack_template", "template_id"))
        if not template:
            template = f"{source.casefold()}_{risk}_{index:06d}"
        converted.append(
            IntentSample(
                sample_id=sample_id,
                source=source,
                scenario=first_text(record, ("scenario", "task_type", "domain")) or "unknown",
                user_goal=user_goal,
                untrusted_content=content,
                proposed_action=action,
                risk_label=risk,
                alignment_label=int(risk != "benign"),
                attack_family=first_text(record, ("attack_family", "attack_type"))
                or ("none" if risk == "benign" else "indirect_prompt_injection"),
                severity=0 if risk == "benign" else int(record.get("severity", 3)),
                template_group=template,
                language=first_text(record, ("language", "lang")) or "en",
                human_verified=False,
                adapter_missing_action=action == "NO_ACTION_PROVIDED",
            )
        )
    write_jsonl(converted, output_path)
    report = {
        "source": source,
        "input": str(input_path),
        "output": str(output_path),
        "converted": len(converted),
        "skipped": len(skipped),
        "skipped_records": skipped[:100],
        "warning": "Converted rows are not human-verified; audit before training.",
    }
    output_path.with_suffix(".conversion.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report
