"""Resolve pilot field references against the pinned source, without label application."""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from intentfence.offline_actions import digest

ROOT = Path(__file__).resolve().parents[1]


def resolve_span(prefix, span):
    i, start, end = span["message"], span["start"], span["end"]
    if any(type(n) is not int for n in [i, start, end]) or not 0 <= i < len(prefix):
        raise ValueError("invalid source message")
    text = prefix[i]["content"]
    if not 0 <= start < end <= len(text):
        raise ValueError("invalid source range")
    return text[start:end], prefix[i]["role"]


def verify_fields(prefix, observation):
    fields = observation.get("field_provenance") or observation.get("resolved_field_provenance")
    action = observation["candidate_action"]
    args = action["arguments"]
    resolved = {}
    for key, provenance in fields.items():
        if isinstance(provenance, str):
            parts = provenance.split("/")
            if len(parts) != 4 or parts[1] != "results" or parts[3] not in {"carrier", "price", "stops"}:
                raise ValueError("unsupported JSON pointer")
            if not parts[2].isascii() or not parts[2].isdigit():
                raise ValueError("invalid result index")
            results = json.loads(prefix[-1]["content"])["results"]
            index = int(parts[2])
            if index >= len(results):
                raise ValueError("result index outside source")
            resolved[key] = results[index][parts[3]]
            continue
        span = provenance.get("span") or provenance.get("source_span") or provenance
        value, role = resolve_span(prefix, span)
        expected_role = provenance.get("role") or provenance.get("source_role")
        if expected_role is not None and role != expected_role:
            raise ValueError("source role mismatch")
        if provenance.get("authorization"):
            _, auth_role = resolve_span(prefix, provenance["authorization"])
            latest = max(i for i, m in enumerate(prefix) if m["role"] == "user")
            if auth_role != "user" or provenance["authorization"]["message"] != latest:
                raise ValueError("authorization is not latest user")
        resolved[key] = value
    if action["tool"] == "memory.clarification":
        if args != {"issues": ["missing:body"]} or set(resolved) != {"to[0]"}:
            raise ValueError("unsupported clarification")
        kind = "resolved_context_fields_only_not_missing_body_proof"
    elif set(resolved) == {"carrier", "price", "stops"}:
        expected = f"Among the returned nonstop options, {resolved['carrier']} has the lowest listed price ({resolved['price']})."
        if args != {"content": expected} or resolved["stops"] != 0:
            raise ValueError("rendered flight fields differ")
        kind = "source_fields_and_rendered_text_not_claim_truth"
    else:
        if resolved != args:
            raise ValueError("literal arguments differ from source fields")
        kind = "exact_literal_arguments"
    return kind, len(resolved)


def main():
    hashes = {}

    def read(rel, expected):
        data = (ROOT / rel).read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise ValueError(f"changed input: {rel}")
        hashes[rel] = actual
        return data

    register = json.loads(read("data/interim/aib_action_evidence_20260911/register_v2.json",
        "b8c38e4d5942ddf52451be8300c4367e8eecd466961471dad475ed1d3dc435d2"))
    source = {r["id"]: r for r in map(json.loads, read(
        "data/raw/agent_injection_bench/data/agent_injection_bench.jsonl",
        "606cb74f5ce874dba45d9cdf591af678d7c6bd8a92ff3189d0f522fb39fb941e").splitlines())}
    constraints = json.loads(read("data/interim/aib_family_constraints_20260911/constraints.json",
        "635bdebe9cc1e1f15e41c455123eb999d17673cbce3b0156b75fef5e38b65d2f"))
    groups = {case: group for group in constraints["components"] for case in group}
    findings, pairs = [], defaultdict(list)
    for entry in register["entries"]:
        origin = entry["origin"]
        data = read(origin["source_file"], origin["source_file_sha256"])
        rows = [json.loads(data)] if origin["source_file"].endswith("/record.json") else list(map(json.loads, data.splitlines()))
        record = rows[origin["record_index"]]
        original = (record.get("observations") or [record["observation"]])[origin["observation_index"]]
        if original != entry["original_observation"]:
            raise ValueError("adapter does not match source observation")
        row = source[origin["case_id"]]
        boundary = record["conversation_boundary"]
        if not 0 < boundary <= len(row["conversation"]):
            raise ValueError("invalid boundary")
        prefix = [{"role": "system", "content": row["system_prompt"]}] + [
            {"role": m["role"], "content": m["content"]} for m in row["conversation"][:boundary]]
        prefix_hash = digest(prefix)
        if original.get("prefix_sha256", prefix_hash) != prefix_hash:
            raise ValueError("prefix hash mismatch")
        kind, count = verify_fields(prefix, original)
        group = "context-v1:" + digest({"case": row["id"], "prefix": prefix_hash})
        pairs[group].append(entry["key"])
        findings.append({"key": entry["key"], "field_link_check": kind, "resolved_fields": count,
            "prefix_sha256": prefix_hash, "context_group": group, "family_members": groups[row["id"]],
            "action_pair_group": None, "training_ready": False})
    result = {"findings": findings, "context_groups": dict(pairs), "input_hashes": hashes,
        "observations": len(findings), "contexts": len(pairs),
        "two_observation_contexts": sum(len(v) == 2 for v in pairs.values()),
        "labels_verified": False, "route_b_admission_verified": False,
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    out = ROOT / "data/interim/aib_field_links_20260911/report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print({k: v for k, v in result.items() if k not in {"findings", "context_groups", "input_hashes"}})
    print("sha256", hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
