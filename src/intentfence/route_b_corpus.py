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


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_mock_corpus_spec(path: str | Path) -> dict[str, Any]:
    source = Path(path).resolve()
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"mock corpus specification must be a mapping: {source}")
    extends = payload.pop("extends", None)
    if extends is None:
        resolved = payload
        sources: list[dict[str, str]] = []
    else:
        parent = (source.parent / str(extends)).resolve()
        if parent == source:
            raise ValueError("mock corpus specification cannot extend itself")
        base = load_mock_corpus_spec(parent)
        sources = list(base.pop("_resolved_spec_sources", []))
        resolved = _deep_merge(base, payload)
    sources.append({"path": str(source), "sha256": file_sha256(source)})
    resolved["_resolved_spec_sources"] = sources
    return resolved


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
    def prepared(spec: Mapping[str, Any], fallback: str) -> tuple[Mapping[str, Any], str]:
        return (
            {key: value for key, value in spec.items() if key != "template_id"},
            str(spec.get("template_id", fallback)),
        )

    if alignment == "aligned":
        return prepared(archetype["aligned_action"], f"{archetype['id']}:aligned")
    if alignment == "unrelated":
        return prepared(global_actions["unrelated"], "global:unrelated")
    if alignment == "ambiguous":
        return prepared(global_actions["ambiguous"], "global:ambiguous")
    if risk == "benign":
        return prepared(global_actions["benign_malicious"], "global:benign_malicious")
    if risk == "instruction_hijacking":
        return prepared(archetype["hijack_action"], f"{archetype['id']}:hijack")
    if risk == "data_exfiltration":
        return prepared(global_actions["exfiltration"], "global:exfiltration")
    if risk == "privilege_escalation":
        return prepared(global_actions["privilege"], "global:privilege")
    return prepared(archetype["manipulation_action"], f"{archetype['id']}:manipulation")


def _content_for(
    risk: str,
    role: str,
    archetype: Mapping[str, Any],
    risk_content: Mapping[str, Any],
    risk_content_by_role: Mapping[str, Any],
    context: Mapping[str, Any],
) -> tuple[str, str]:
    if risk == "benign":
        return str(_format_value(archetype["benign_content"], context)), "benign"
    benign = str(_format_value(archetype["benign_content"], context))
    expanded = dict(context)
    expanded["benign_content"] = benign
    role_content = risk_content_by_role.get(role, {})
    selected = role_content.get(risk, risk_content.get(risk))
    if selected is None:
        if risk == "instruction_hijacking":
            return str(_format_value(archetype["hijack_content"], context)), "hijack"
        if risk == "tool_manipulation":
            return (
                str(_format_value(archetype["manipulation_content"], context)),
                "manipulation",
            )
        raise ValueError(f"{role}/{risk}: missing Risk content template")
    if isinstance(selected, Mapping):
        text = selected.get("text")
        if text is None:
            raise ValueError(f"{role}/{risk}: role risk content mapping requires text")
        template_id = str(selected.get("template_id", risk))
    else:
        text = selected
        template_id = risk
    return str(_format_value(text, expanded)), str(_format_value(template_id, expanded))


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
    risk_content_by_role = spec.get("risk_content_by_role", {})
    archetype_overrides = spec.get("scenario_archetype_overrides", {})
    if not isinstance(roles, dict) or set(roles) != set(ROLE_CODES):
        raise ValueError("roles must define exactly train/validation/calibration/test_a")
    if not isinstance(archetypes, list) or len(archetypes) < 7:
        raise ValueError("at least seven mock scenario archetypes are required")
    if not isinstance(global_actions, dict) or not isinstance(risk_content, dict):
        raise ValueError("global_actions and risk_content mappings are required")
    if not isinstance(risk_content_by_role, Mapping):
        raise ValueError("risk_content_by_role must be a mapping when provided")
    if not isinstance(archetype_overrides, Mapping):
        raise ValueError("scenario_archetype_overrides must be a mapping when provided")

    data_version = str(spec["data_version"])
    source = str(spec["source"])
    policy_id = str(spec["action_policy_id"])
    cases_per_group = int(spec["cases_per_template_group"])
    records: dict[str, list[IntentSample]] = {role: [] for role in ROLE_CODES}
    traces: list[dict[str, Any]] = []
    archetype_lookup = {str(item["id"]): item for item in archetypes}
    unknown_override_ids = sorted(set(map(str, archetype_overrides)) - set(archetype_lookup))
    if unknown_override_ids:
        raise ValueError(
            f"scenario_archetype_overrides contains unknown IDs={unknown_override_ids}"
        )
    if any(not isinstance(value, Mapping) for value in archetype_overrides.values()):
        raise ValueError("scenario_archetype_overrides values must be mappings")
    semantic_isolation = bool(spec.get("semantic_template_isolation", False))
    configured_archetype_roles: dict[str, str] = {}

    for role, role_code in ROLE_CODES.items():
        role_spec = roles[role]
        group_count = int(role_spec["template_groups"])
        style = str(role_spec["style"])
        if group_count <= 0:
            raise ValueError(f"{role}: template_groups must be positive")
        role_archetype_ids = role_spec.get("archetype_ids")
        if role_archetype_ids is None:
            role_archetypes = archetypes
        else:
            if not isinstance(role_archetype_ids, list) or not role_archetype_ids:
                raise ValueError(f"{role}: archetype_ids must be a non-empty list")
            unknown = sorted(set(map(str, role_archetype_ids)) - set(archetype_lookup))
            if unknown:
                raise ValueError(f"{role}: unknown archetype_ids={unknown}")
            role_archetypes = [archetype_lookup[str(item)] for item in role_archetype_ids]
            if semantic_isolation:
                for archetype_id in map(str, role_archetype_ids):
                    previous = configured_archetype_roles.setdefault(archetype_id, role)
                    if previous != role:
                        raise ValueError(
                            f"semantic template isolation requires disjoint role archetypes; "
                            f"{archetype_id!r} is assigned to {previous} and {role}"
                        )
        for group_index in range(group_count):
            archetype = role_archetypes[group_index % len(role_archetypes)]
            archetype_id = str(archetype["id"])
            archetype = _deep_merge(
                archetype, archetype_overrides.get(archetype_id, {})
            )
            template_group = (
                f"{data_version}:{archetype_id}:g{group_index:03d}"
                if semantic_isolation
                else f"{data_version}:{role}:{archetype_id}:g{group_index:03d}"
            )
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
                    "style_token": str(role_spec.get("style_token", role)),
                    "ticket_id": f"T-{namespace}-{serial}",
                    "unique_token": f"MARK-{namespace}-{serial}",
                }
                user_goal = str(_format_value(archetype["user_goal"], context))
                for risk in RISK_LABELS:
                    untrusted_content, attack_template = _content_for(
                        risk,
                        role,
                        archetype,
                        risk_content,
                        risk_content_by_role,
                        context,
                    )
                    attack_family, severity = RISK_METADATA[risk]
                    pair_group = f"{base_id}:{risk}"
                    for alignment in TASK_ALIGNMENT_LABELS:
                        action_spec, action_template = _action_for(
                            alignment, risk, archetype, global_actions
                        )
                        action_template = str(_format_value(action_template, context))
                        resolved_action = _format_value(action_spec, context)
                        if semantic_isolation and spec.get(
                            "inject_role_action_scope_argument", False
                        ):
                            resolved_action = deepcopy(dict(resolved_action))
                            arguments = dict(resolved_action.get("arguments", {}))
                            arguments["workflow_scope"] = context["style_token"]
                            resolved_action["arguments"] = arguments
                            provenance = dict(
                                resolved_action.get("field_provenance", {})
                            )
                            provenance["workflow_scope"] = ["fixture_constant"]
                            resolved_action["field_provenance"] = provenance
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
                                adapter_profile=(
                                    "route_b_project_mock_v3_candidate"
                                    if semantic_isolation
                                    else "route_b_project_mock_v2_candidate"
                                ),
                                adapter_missing_action=False,
                                action_provenance="sandbox_policy_output",
                                action_observation_id=trace["action_observation_id"],
                                action_policy_id=policy_id,
                                label_provenance=(
                                    "deterministic_route_b_protocol_draft3_pending_human_audit"
                                    if semantic_isolation
                                    else "deterministic_route_b_protocol_draft2_pending_human_audit"
                                ),
                                field_provenance=resolved_action.get("field_provenance", {}),
                                data_version=data_version,
                                scenario_family=(
                                    f"{data_version}:{archetype_id}:family"
                                    if semantic_isolation
                                    else f"{data_version}:{role}:{archetype_id}:family-{group_index:03d}"
                                ),
                                goal_template=(
                                    f"{archetype_id}:goal"
                                    if semantic_isolation
                                    else f"{role}:{archetype_id}:goal"
                                ),
                                attack_template=(
                                    f"{archetype_id}:{attack_template}"
                                    if semantic_isolation
                                    else f"{role}:{archetype_id}:{attack_template}"
                                ),
                                action_template=(
                                    f"{action_template}:{alignment}"
                                    if semantic_isolation
                                    else f"{role}:{action_template}:{alignment}"
                                ),
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
                    "resolved_sources": list(spec.get("_resolved_spec_sources", [])),
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


def _repository_root_for_manifest(manifest_path: Path) -> Path:
    resolved = manifest_path.resolve()
    for candidate in (resolved.parent, *resolved.parents):
        if (candidate / "src").is_dir() and (candidate / "configs").is_dir():
            return candidate
    return Path.cwd().resolve()


def _resolve_recorded_path(recorded_path: str | Path, *, repository_root: Path) -> Path:
    direct = Path(recorded_path)
    if direct.is_file():
        return direct
    parts = tuple(
        part for part in str(recorded_path).replace("\\", "/").split("/") if part not in {"", "."}
    )
    project_name = repository_root.name.casefold()
    for index, part in enumerate(parts):
        if part.casefold() == project_name:
            relocated = repository_root.joinpath(*parts[index + 1 :])
            if relocated.is_file():
                return relocated
    return direct


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
    repository_root = _repository_root_for_manifest(path)
    spec = payload.get("spec")
    if isinstance(spec, dict) and spec.get("path"):
        spec_path = _resolve_recorded_path(spec["path"], repository_root=repository_root)
        if not spec_path.is_file():
            errors.append(f"missing corpus specification: {spec_path}")
        elif file_sha256(spec_path) != spec.get("sha256"):
            errors.append("corpus specification hash mismatch")
        for source in spec.get("resolved_sources", []):
            source_path = _resolve_recorded_path(
                str(source.get("path", "")), repository_root=repository_root
            )
            if not source_path.is_file():
                errors.append(f"missing inherited corpus specification: {source_path}")
            elif file_sha256(source_path) != source.get("sha256"):
                errors.append(f"inherited corpus specification hash mismatch: {source_path}")
    return errors
