"""Append quarantined offline evidence without altering a frozen register."""

from __future__ import annotations

from copy import deepcopy

from intentfence.action_evidence_adapter import EvidenceOrigin, adapt


def extend_register(
    base: dict, record: dict, *, source_file: str, source_sha256: str,
    implementation_hashes: dict[str, str],
) -> dict:
    """Return a new register; IDs are receipts, never a training admission."""
    if (base.get("training_ready") is not False
            or base.get("route_b_admission_verified") is not False):
        raise ValueError("base register must remain quarantined")
    old_entries = base.get("entries")
    if not isinstance(old_entries, list) or len(old_entries) != base.get("observations"):
        raise ValueError("invalid base observation count")
    keys = set()
    ids = set()
    for entry in old_entries:
        if (entry.get("training_ready") is not False
                or entry.get("human_verified") is not False
                or any(entry.get(name) is not None for name in (
                    "risk_label", "task_alignment_label", "split"
                ))):
            raise ValueError("base entry has applied label or approval")
        key, identity = entry.get("key"), entry.get("action_observation_id")
        if not isinstance(key, str) or not isinstance(identity, str):
            raise ValueError("base entry missing identity")
        if key in keys or identity in ids:
            raise ValueError("duplicate base identity")
        keys.add(key)
        ids.add(identity)
    if (record.get("training_ready") is not False
            or record.get("human_verified") is not False
            or any(record.get(name) is not None for name in (
                "risk_label", "task_alignment_labels", "split"
            ))):
        raise ValueError("new record has applied label or approval")
    observations = record.get("observations")
    if not isinstance(observations, list) or len(observations) != 2:
        raise ValueError("new record must contain one action contrast")
    prefix = observations[0].get("prefix_sha256")
    if (not isinstance(prefix, str) or len(prefix) != 64
            or any(c not in "0123456789abcdef" for c in prefix)
            or prefix != observations[1].get("prefix_sha256")
            or observations[0].get("candidate_action")
            == observations[1].get("candidate_action")):
        raise ValueError("actions are not a same-prefix contrast")
    if {observation.get("policy") for observation in observations} != {
        "goal_bounded", "content_following"
    }:
        raise ValueError("missing contrasted policies")
    if any(observation.get("action_provenance") != "sandbox_policy_output"
           or observation.get("model_generated") is not False
           for observation in observations):
        raise ValueError("new actions lack honest offline provenance")
    case_id = record["source_binding"]["case_id"]
    added = []
    for index, observation in enumerate(observations):
        key = f"{case_id}:{index}"
        if key in keys:
            raise ValueError("duplicate observation key")
        origin = EvidenceOrigin(
            source_file=source_file,
            source_file_sha256=source_sha256,
            record_index=0,
            observation_index=index,
            case_id=case_id,
            implementation_hashes=implementation_hashes,
        )
        entry = adapt(observation, origin)
        if entry["action_observation_id"] in ids:
            raise ValueError("duplicate observation identity")
        entry["key"] = key
        added.append(entry)
        keys.add(key)
        ids.add(entry["action_observation_id"])
    result = deepcopy(base)
    result["entries"].extend(added)
    result["observations"] = len(result["entries"])
    result["schema_version"] = 3
    result["training_ready"] = False
    result["route_b_admission_verified"] = False
    return result
