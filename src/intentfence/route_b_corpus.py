from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from intentfence.constants import RISK_LABELS, TASK_ALIGNMENT_LABELS
from intentfence.data import file_sha256
from intentfence.mock_runtime import capture_candidate_action
from intentfence.schema import IntentSample, read_jsonl, write_jsonl

RISK_METADATA = {
    "benign": ("none", 0),
    "instruction_hijacking": ("instruction_override", 2),
    "data_exfiltration": ("unauthorized_transfer", 4),
    "privilege_escalation": ("unauthorized_permission_change", 4),
    "tool_manipulation": ("parameter_or_operation_substitution", 3),
}
ROLE_CODES = {"train": "TR", "validation": "VA", "calibration": "CA", "test_a": "TA"}


def load_mock_corpus_spec(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"mock corpus specification must be a mapping: {source}")
    return payload


def _format_value(value: Any, context: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        return value.format_map(context)
    if isinstance(value, list):
        return [_format_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: _format_value(item, context) for key, item in value.items()}
    return value


def _action_for(
    alignment: str,
    risk: str,
    archetype: Mapping[str, Any],
    global_actions: Mapping[str, Any],
) -> tuple[Mapping[str, Any], str]:
    if alignment == "aligned":
        return archetype["aligned_action"], f"{archetype['id']}:aligned"
    if alignment == "unrelated":
        return global_actions["unrelated"], "global:unrelated"
    if alignment == "ambiguous":
        return global_actions["ambiguous"], "global:ambiguous"
    if risk == "benign":
        return global_actions["benign_malicious"], "global:benign_malicious"
    if risk == "instruction_hijacking":
        return archetype["hijack_action"], f"{archetype['id']}:hijack"
    if risk == "data_exfiltration":
        return global_actions["exfiltration"], "global:exfiltration"
    if risk == "privilege_escalation":
        return global_actions["privilege"], "global:privilege"
    return archetype["manipulation_action"], f"{archetype['id']}:manipulation"


def _content_for(
    risk: str,
    archetype: Mapping[str, Any],
    risk_content: Mapping[str, Any],
    context: Mapping[str, Any],
) -> tuple[str, str]:
    if risk == "benign":
        return str(_format_value(archetype["benign_content"], context)), "benign"
    if risk == "instruction_hijacking":
        return str(_format_value(archetype["hijack_content"], context)), "hijack"
    if risk == "tool_manipulation":
        return str(_format_value(archetype["manipulation_content"], context)), "manipulation"
    benign = str(_format_value(archetype["benign_content"], context))
    expanded = dict(context)
    expanded["benign_content"] = benign
    return str(_format_value(risk_content[risk], expanded)), risk


def build_formal_mock_records(
    spec: Mapping[str, Any],
) -> tuple[dict[str, list[IntentSample]], list[dict[str, Any]]]:
    if spec.get("status") != "construction_authorized_not_training_authorized":
        raise ValueError("formal mock corpus construction is not authorized by this specification")
    if int(spec.get("cases_per_template_group", 0)) <= 0:
        raise ValueError("cases_per_template_group must be positive")
    roles = spec.get("roles")
    archetypes = spec.get("scenario_archetypes")
    global_actions = spec.get("global_actions")
    risk_content = spec.get("risk_content")
    if not isinstance(roles, dict) or set(roles) != set(ROLE_CODES):
        raise ValueError("roles must define exactly train/validation/calibration/test_a")
    if not isinstance(archetypes, list) or len(archetypes) < 7:
        raise ValueError("at least seven mock scenario archetypes are required")
    if not isinstance(global_actions, dict) or not isinstance(risk_content, dict):
        raise ValueError("global_actions and risk_content mappings are required")

    data_version = str(spec["data_version"])
    source = str(spec["source"])
    policy_id = str(spec["action_policy_id"])
    cases_per_group = int(spec["cases_per_template_group"])
    records: dict[str, list[IntentSample]] = {role: [] for role in ROLE_CODES}
    traces: list[dict[str, Any]] = []

    for role, role_code in ROLE_CODES.items():
        role_spec = roles[role]
        group_count = int(role_spec["template_groups"])
        style = str(role_spec["style"])
        if group_count <= 0:
            raise ValueError(f"{role}: template_groups must be positive")
        for group_index in range(group_count):
            archetype = archetypes[group_index % len(archetypes)]
            archetype_id = str(archetype["id"])
            template_group = f"{data_version}:{role}:{archetype_id}:g{group_index:03d}"
            for case_index in range(cases_per_group):
                serial_number = group_index * cases_per_group + case_index
                serial = f"{serial_number:04d}"
                base_id = f"{data_version}-{role_code.lower()}-{group_index:03d}-{case_index}"
                namespace = hashlib.sha256(
                    f"{spec['seed']}:{base_id}".encode()
                ).hexdigest()[:10]
                context = {
                    "approved_recipient": (
                        f"reviewer-{namespace}-{serial}@example.test"
                    ),
                    "object_id": f"OBJ-{namespace}-{serial}",
                    "private_asset": f"restricted-{namespace}-{serial}.csv",
                    "role": role,
                    "role_code": namespace,
                    "serial": serial,
                    "style": style,
                    "ticket_id": f"T-{namespace}-{serial}",
                    "unique_token": f"MARK-{namespace}-{serial}",
                }
                user_goal = str(_format_value(archetype["user_goal"], context))
                for risk in RISK_LABELS:
                    untrusted_content, attack_template = _content_for(
                        risk, archetype, risk_content, context
                    )
                    attack_family, severity = RISK_METADATA[risk]
                    pair_group = f"{base_id}:{risk}"
                    for alignment in TASK_ALIGNMENT_LABELS:
                        action_spec, action_template = _action_for(
                            alignment, risk, archetype, global_actions
                        )
                        resolved_action = _format_value(action_spec, context)
                        action, trace = capture_candidate_action(
                            case_id=pair_group,
                            policy_id=policy_id,
                            tool=str(resolved_action["tool"]),
                            arguments=resolved_action.get("arguments", {}),
                            field_provenance=resolved_action.get("field_provenance", {}),
                        )
                        sample_id = f"{pair_group}:{alignment}"
                        records[role].append(
                            IntentSample(
                                sample_id=sample_id,
                                source=source,
                                scenario=str(archetype["scenario"]),
                                user_goal=user_goal,
                                untrusted_content=untrusted_content,
                                proposed_action=action,
                                risk_label=risk,
                                alignment_label=int(risk != "benign"),
                                task_alignment_label=alignment,
                                attack_family=attack_family,
                                severity=severity,
                                template_group=template_group,
                                split=role,
                                human_verified=False,
                                source_record_id=pair_group,
                                adapter_profile="route_b_project_mock_v2_candidate",
                                adapter_missing_action=False,
                                action_provenance="sandbox_policy_output",
                                action_observation_id=trace["action_observation_id"],
                                action_policy_id=policy_id,
                                label_provenance=(
                                    "deterministic_route_b_protocol_draft2_pending_human_audit"
                                ),
                                field_provenance=resolved_action.get("field_provenance", {}),
                                data_version=data_version,
                                scenario_family=(
                                    f"{data_version}:{role}:{archetype_id}:family-{group_index:03d}"
                                ),
                                goal_template=f"{role}:{archetype_id}:goal",
                                attack_template=f"{role}:{archetype_id}:{attack_template}",
                                action_template=f"{role}:{action_template}:{alignment}",
                                action_pair_group=pair_group,
                                secondary_risks=[],
                            )
                        )
                        trace.update(
                            {
                                "sample_id": sample_id,
                                "split": role,
                                "data_version": data_version,
                            }
                        )
                        traces.append(trace)
    return records, traces


def _sealed_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(payload))
    serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    result["sha256"] = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return result


def write_formal_mock_corpus(
    spec: Mapping[str, Any],
    output_dir: str | Path,
    *,
    spec_path: str | Path | None = None,
) -> dict[str, Any]:
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite Route B corpus directory: {destination}")
    destination.mkdir(parents=True)
    records, traces = build_formal_mock_records(spec)
    split_evidence: dict[str, Any] = {}
    for role, rows in records.items():
        path = destination / f"{role}.jsonl"
        write_jsonl(rows, path)
        split_evidence[role] = {
            "path": path.name,
            "rows": len(rows),
            "sha256": file_sha256(path),
            "risk_labels": dict(sorted(Counter(row.risk_label for row in rows).items())),
            "task_alignment_labels": dict(
                sorted(Counter(row.task_alignment_label for row in rows).items())
            ),
            "template_groups": len({row.template_group for row in rows}),
            "base_cases": len({row.action_pair_group for row in rows}) // 5,
        }
    trace_path = destination / "action_traces.jsonl"
    trace_path.write_text(
        "".join(json.dumps(trace, ensure_ascii=False, sort_keys=True) + "\n" for trace in traces),
        encoding="utf-8",
    )
    manifest = _sealed_payload(
        {
            "schema_version": 1,
            "status": "candidate_pending_independent_human_audit_not_training_authorized",
            "data_version": spec["data_version"],
            "prepared_at": spec["prepared_at"],
            "source": spec["source"],
            "generator": {
                "callable": "intentfence.route_b_corpus.write_formal_mock_corpus",
                "source_sha256": file_sha256(Path(__file__)),
                "mock_runtime_sha256": file_sha256(Path(__file__).with_name("mock_runtime.py")),
            },
            "runtime": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "pydantic": importlib.metadata.version("pydantic"),
                "pyyaml": importlib.metadata.version("PyYAML"),
            },
            "spec": (
                {
                    "path": str(Path(spec_path).resolve()),
                    "sha256": file_sha256(spec_path),
                }
                if spec_path is not None
                else None
            ),
            "splits": split_evidence,
            "traces": {
                "path": trace_path.name,
                "rows": len(traces),
                "sha256": file_sha256(trace_path),
                "executed": False,
                "external_side_effects": False,
            },
            "formal_training_authorized": False,
        }
    )
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"manifest": manifest, "manifest_path": str(manifest_path)}


def validate_formal_mock_manifest(manifest_path: str | Path) -> list[str]:
    path = Path(manifest_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    claimed_hash = payload.pop("sha256", None)
    serialized = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    actual_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    if claimed_hash != actual_hash:
        errors.append("manifest self-hash mismatch")
    if payload.get("formal_training_authorized") is not False:
        errors.append("candidate manifest must keep formal_training_authorized=false")
    base = path.parent
    for role, evidence in payload.get("splits", {}).items():
        split_path = base / evidence["path"]
        if not split_path.is_file():
            errors.append(f"missing split file: {role}/{split_path}")
            continue
        if file_sha256(split_path) != evidence.get("sha256"):
            errors.append(f"split hash mismatch: {role}")
        try:
            rows = read_jsonl(split_path)
        except ValueError as exc:
            errors.append(f"invalid split file {role}: {exc}")
            continue
        if len(rows) != evidence.get("rows"):
            errors.append(f"split row count mismatch: {role}")
        if any(row.split != role for row in rows):
            errors.append(f"split declaration mismatch: {role}")
        risks = dict(sorted(Counter(row.risk_label for row in rows).items()))
        alignments = dict(sorted(Counter(row.task_alignment_label for row in rows).items()))
        if risks != evidence.get("risk_labels"):
            errors.append(f"split Risk counts mismatch: {role}")
        if alignments != evidence.get("task_alignment_labels"):
            errors.append(f"split Alignment counts mismatch: {role}")
    trace_evidence = payload.get("traces", {})
    trace_path = base / str(trace_evidence.get("path", ""))
    if not trace_path.is_file():
        errors.append(f"missing action trace file: {trace_path}")
    else:
        if file_sha256(trace_path) != trace_evidence.get("sha256"):
            errors.append("action trace hash mismatch")
        trace_count = 0
        with trace_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                trace_count += 1
                trace = json.loads(line)
                if trace.get("executed") is not False:
                    errors.append(f"trace {line_number} does not declare executed=false")
                if trace.get("external_side_effects") is not False:
                    errors.append(
                        f"trace {line_number} does not declare external_side_effects=false"
                    )
        if trace_count != trace_evidence.get("rows"):
            errors.append("action trace row count mismatch")
    spec = payload.get("spec")
    if isinstance(spec, dict) and spec.get("path"):
        spec_path = Path(spec["path"])
        if not spec_path.is_file():
            errors.append(f"missing corpus specification: {spec_path}")
        elif file_sha256(spec_path) != spec.get("sha256"):
            errors.append("corpus specification hash mismatch")
    return errors
