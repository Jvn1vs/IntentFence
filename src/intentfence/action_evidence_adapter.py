"""Derived evidence identities for offline pilot observations, not dataset admission."""
from __future__ import annotations

from copy import deepcopy

from pydantic import Field

from intentfence.offline_actions import StrictModel, Text, digest


class EvidenceOrigin(StrictModel):
    source_file: Text
    source_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_index: int = Field(ge=0)
    observation_index: int = Field(ge=0)
    case_id: Text
    implementation_hashes: dict[str, str] = Field(min_length=1)


def adapt(observation: dict, origin: EvidenceOrigin) -> dict:
    observation = deepcopy(observation)
    origin = EvidenceOrigin.model_validate(origin.model_dump())
    if observation.get("executed") is not False or observation.get("external_side_effects") is not False:
        raise ValueError("only nonexecuted offline observations are accepted")
    for key in ["risk_label", "task_alignment_label", "split"]:
        if observation.get(key) is not None:
            raise ValueError("unexpected applied label or split")
    if observation.get("human_verified", False) is not False or observation.get("training_ready", False) is not False:
        raise ValueError("unsupported evidence promotion")
    policy = observation.get("action_policy_id") or observation.get("policy")
    if not isinstance(policy, str) or not policy.strip():
        raise ValueError("missing source policy")
    for value in origin.implementation_hashes.values():
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("invalid implementation digest")
    fields = observation.get("field_provenance") or observation.get("resolved_field_provenance")
    if not isinstance(fields, dict) or not fields:
        raise ValueError("missing field provenance")
    action = observation.get("candidate_action")
    if not isinstance(action, dict) or not action.get("tool") or not isinstance(action.get("arguments"), dict):
        raise ValueError("missing structured action")
    identity = {"origin": origin.model_dump(), "original_observation_sha256": digest(observation)}
    return {
        "schema_version": 1, **identity,
        "action_observation_id": "derived-evidence-v1:" + digest(identity),
        "original_action_observation_id": observation.get("action_observation_id"),
        "action_policy_id": "prepared-policy-v1:" + digest({"name": policy, "implementation_hashes": origin.implementation_hashes}),
        "original_policy_name": policy, "proposed_action": action,
        "field_provenance": fields, "original_observation": observation,
        "identity_scope": "adapter_assigned_receipt_not_new_runtime_observation",
        "action_provenance": "sandbox_policy_output", "model_generated": False,
        "risk_label": None, "task_alignment_label": None, "split": None,
        "human_verified": False, "training_ready": False,
    }
