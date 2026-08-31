from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

MOCK_TOOLS = frozenset(
    {
        "calendar.create_event",
        "database.read_records",
        "file.copy",
        "message.send",
        "permission.grant",
        "storage.share",
        "ticket.update",
        "workflow.request_authorization",
        "workspace.return_result",
    }
)


def capture_candidate_action(
    *,
    case_id: str,
    policy_id: str,
    tool: str,
    arguments: Mapping[str, Any],
    field_provenance: Mapping[str, list[str]],
) -> tuple[str, dict[str, Any]]:
    """Capture an action proposal without executing a tool or external side effect."""

    if not case_id.strip() or not policy_id.strip():
        raise ValueError("case_id and policy_id must be non-empty")
    if tool not in MOCK_TOOLS:
        raise ValueError(f"tool is not in the offline mock allowlist: {tool}")
    payload = {"arguments": dict(arguments), "tool": tool}
    canonical_action = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest_input = json.dumps(
        {
            "action": payload,
            "case_id": case_id,
            "field_provenance": field_provenance,
            "policy_id": policy_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    observation_id = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
    trace = {
        "schema_version": 1,
        "action_observation_id": observation_id,
        "case_id": case_id,
        "action_policy_id": policy_id,
        "candidate_action": payload,
        "field_provenance": dict(field_provenance),
        "runtime": "offline_mock_capture",
        "executed": False,
        "external_side_effects": False,
    }
    return canonical_action, trace
