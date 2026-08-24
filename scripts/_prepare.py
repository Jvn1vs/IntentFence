from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from intentfence.schema import IntentSample, iter_json_objects, write_jsonl

ActionProvenance = Literal[
    "missing",
    "benchmark_target",
    "protocol_wrapper",
    "source_field",
]


@dataclass(frozen=True)
class AdapterProfile:
    """Strict field contract for one pinned upstream representation."""

    profile_id: str
    source: str
    required_fields: tuple[str, ...]
    user_goal_fields: tuple[str, ...]
    content_fields: tuple[str, ...]
    action_fields: tuple[str, ...] = ()
    scenario_fields: tuple[str, ...] = ()
    template_fields: tuple[str, ...] = ()
    attack_family_fields: tuple[str, ...] = ()
    risk_label: str = "instruction_hijacking"
    severity: int = 3
    constant_user_goal: str = ""
    constant_action: str = ""
    action_provenance: ActionProvenance = "missing"
    label_provenance: str = "protocol_constant"


PROFILES = {
    "bipia_generated_v1": AdapterProfile(
        profile_id="bipia_generated_v1",
        source="BIPIA",
        required_fields=(
            "question",
            "context",
            "attack_name",
            "attack_str",
            "task_name",
            "position",
        ),
        user_goal_fields=("question",),
        content_fields=("context",),
        scenario_fields=("task_name",),
        template_fields=("attack_name",),
        attack_family_fields=("attack_name",),
        risk_label="instruction_hijacking",
        action_provenance="missing",
        label_provenance="official_builder_generated_attack",
    ),
    "bipia_clean_v1": AdapterProfile(
        profile_id="bipia_clean_v1",
        source="BIPIA",
        required_fields=("question", "context"),
        user_goal_fields=("question",),
        content_fields=("context",),
        risk_label="benign",
        severity=0,
        action_provenance="missing",
        label_provenance="official_clean_context",
    ),
    "injecagent_direct_harm_v1": AdapterProfile(
        profile_id="injecagent_direct_harm_v1",
        source="InjecAgent",
        required_fields=(
            "User Instruction",
            "Tool Response",
            "User Tool",
            "Attacker Tools",
            "Attacker Instruction",
            "Attack Type",
        ),
        user_goal_fields=("User Instruction",),
        content_fields=("Tool Response",),
        action_fields=("Attacker Tools", "Attacker Instruction"),
        scenario_fields=("User Tool",),
        template_fields=("User Tool", "Attacker Tools"),
        attack_family_fields=("Attack Type",),
        risk_label="tool_manipulation",
        action_provenance="benchmark_target",
        label_provenance="source_filename_direct_harm",
    ),
    "injecagent_data_stealing_v1": AdapterProfile(
        profile_id="injecagent_data_stealing_v1",
        source="InjecAgent",
        required_fields=(
            "User Instruction",
            "Tool Response",
            "User Tool",
            "Attacker Tools",
            "Attacker Instruction",
        ),
        user_goal_fields=("User Instruction",),
        content_fields=("Tool Response",),
        action_fields=("Attacker Tools", "Attacker Instruction"),
        scenario_fields=("User Tool",),
        template_fields=("User Tool", "Attacker Tools"),
        attack_family_fields=("Attack Type",),
        risk_label="data_exfiltration",
        action_provenance="benchmark_target",
        label_provenance="source_filename_data_stealing",
    ),
    "notinject_v1": AdapterProfile(
        profile_id="notinject_v1",
        source="NotInject",
        required_fields=("prompt", "word_list", "category"),
        user_goal_fields=(),
        content_fields=("prompt",),
        scenario_fields=("category",),
        risk_label="benign",
        severity=0,
        constant_user_goal="Respond to the user's benign request without taking external actions.",
        constant_action="return_text_response()",
        action_provenance="protocol_wrapper",
        label_provenance="official_notinject_all_benign",
    ),
}


def _dig(record: dict[str, Any], key: str) -> Any:
    current: Any = record
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _serialize(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _first(record: dict[str, Any], fields: tuple[str, ...]) -> str:
    for field in fields:
        value = _serialize(_dig(record, field))
        if value:
            return value
    return ""


def _combine(record: dict[str, Any], fields: tuple[str, ...]) -> str:
    values = {field: _dig(record, field) for field in fields if _dig(record, field) is not None}
    if not values:
        return ""
    if len(values) == 1:
        return _serialize(next(iter(values.values())))
    return json.dumps(values, ensure_ascii=False, sort_keys=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(source: str, record: dict[str, Any], index: int) -> str:
    for field in ("sample_id", "id", "case_id", "task_id"):
        existing = _serialize(_dig(record, field))
        if existing:
            safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in existing)
            return f"{source.casefold()}_{safe}"
    digest = hashlib.sha256(
        json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"{source.casefold()}_{index:06d}_{digest}"


def _template_group(profile: AdapterProfile, record: dict[str, Any], sample_id: str) -> str:
    if profile.profile_id == "notinject_v1":
        category = _first(record, ("category",)) or "unknown"
        words = _dig(record, "word_list")
        trigger_count = len(words) if isinstance(words, list) else 0
        raw = f"notinject_{category}_{trigger_count}_trigger_words"
    else:
        raw = _combine(record, profile.template_fields) or sample_id
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{profile.source.casefold()}_{digest}"


def convert_records(
    input_path: Path,
    *,
    profile_name: str,
    scenario_override: str | None = None,
    split_override: str | None = None,
) -> tuple[list[IntentSample], list[dict[str, Any]], int]:
    """Replay one pinned adapter without writing conversion artifacts."""
    if profile_name not in PROFILES:
        raise ValueError(f"Unknown adapter profile: {profile_name}")
    profile = PROFILES[profile_name]
    converted: list[IntentSample] = []
    skipped: list[dict[str, Any]] = []
    records = list(iter_json_objects(input_path))

    for index, record in enumerate(records, start=1):
        missing = [field for field in profile.required_fields if _dig(record, field) is None]
        if missing:
            skipped.append({"record_index": index, "missing": missing})
            continue

        user_goal = profile.constant_user_goal or _first(record, profile.user_goal_fields)
        content = _first(record, profile.content_fields)
        action = profile.constant_action or _combine(record, profile.action_fields)
        sample_id = stable_id(profile.source, record, index)
        scenario = scenario_override or _first(record, profile.scenario_fields) or "unknown"
        attack_family = _first(record, profile.attack_family_fields)
        if not attack_family:
            attack_family = (
                "none" if profile.risk_label == "benign" else "indirect_prompt_injection"
            )

        converted.append(
            IntentSample(
                sample_id=sample_id,
                source=profile.source,
                source_record_id=sample_id,
                scenario=scenario,
                user_goal=user_goal,
                untrusted_content=content,
                proposed_action=action,
                risk_label=profile.risk_label,
                alignment_label=int(profile.risk_label != "benign"),
                attack_family=attack_family,
                severity=profile.severity,
                template_group=_template_group(profile, record, sample_id),
                split=split_override,
                language="en",
                human_verified=False,
                adapter_profile=profile.profile_id,
                adapter_missing_action=not bool(action),
                action_provenance=profile.action_provenance,
                label_provenance=profile.label_provenance,
                field_provenance={
                    "user_goal": list(profile.user_goal_fields),
                    "untrusted_content": list(profile.content_fields),
                    "proposed_action": list(profile.action_fields),
                },
            )
        )

    return converted, skipped, len(records)


def convert_file(
    input_path: Path,
    output_path: Path,
    *,
    profile_name: str,
    allow_skips: bool = False,
    scenario_override: str | None = None,
    split_override: str | None = None,
) -> dict[str, Any]:
    """Convert with a pinned, source-specific contract; never guess labels or fields."""
    report_path = output_path.with_suffix(".conversion.json")
    existing = [path for path in (output_path, report_path) if path.exists()]
    if existing:
        rendered = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite conversion output or report: {rendered}")
    if profile_name not in PROFILES:
        raise ValueError(f"Unknown adapter profile: {profile_name}")
    profile = PROFILES[profile_name]
    converted, skipped, records_read = convert_records(
        input_path,
        profile_name=profile_name,
        scenario_override=scenario_override,
        split_override=split_override,
    )

    report = {
        "schema_version": 1,
        "adapter_profile": profile.profile_id,
        "source": profile.source,
        "input": str(input_path),
        "input_sha256": _sha256(input_path),
        "output": str(output_path),
        "split": split_override,
        "records_read": records_read,
        "converted": len(converted),
        "skipped": len(skipped),
        "skipped_records": skipped[:100],
        "risk_labels": dict(sorted(Counter(row.risk_label for row in converted).items())),
        "action_provenance": dict(
            sorted(Counter(row.action_provenance for row in converted).items())
        ),
        "human_verified": 0,
        "warning": "Conversion is unverified and cannot be used for claims before user audit.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)

    if skipped and not allow_skips:
        report["status"] = "failed_strict_field_validation"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise ValueError(
            f"{len(skipped)} records violate {profile.profile_id}; inspect {report_path} "
            "or rerun with --allow-skips after manual review"
        )

    write_jsonl(converted, output_path)
    report["output_sha256"] = _sha256(output_path)
    report["status"] = "converted_unverified"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
