"""Validate and compare Risk-only pilot returns without label application."""
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from scripts.package_aib_risk_review import FIELDS

ROOT = Path(__file__).resolve().parents[1]
HASHES = {"A": "f87136fbe41d178e312724cbd4ff88d8ea6e62d630183f9f9fd9ce3c03ee0c4a",
          "B": "c7016c0045f28afb74bd00f27f7d520d892e706960c902179536ba24fdd1bcf8"}
LABELS = {"benign", "instruction_hijacking", "data_exfiltration", "privilege_escalation", "tool_manipulation"}


def validate(template, returned, reviewer):
    def parse(data):
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
        if reader.fieldnames != FIELDS:
            raise ValueError("header mismatch")
        rows = list(reader)
        if not rows or any(None in r or any(v is None for v in r.values()) for r in rows):
            raise ValueError("malformed rows")
        if len({r["review_id"] for r in rows}) != len(rows):
            raise ValueError("duplicate IDs")
        return rows
    before, after = parse(template), parse(returned)
    if len(before) != len(after):
        raise ValueError("row count changed")
    for x, y in zip(before, after, strict=True):
        if any(x[k] != y[k] for k in FIELDS[:3]) or y["reviewer_id"] != reviewer:
            raise ValueError("material, order or reviewer mismatch")
        if datetime.fromisoformat(y["reviewed_at"]).utcoffset() is None:
            raise ValueError("timezone missing")
        if y["review_status"] == "completed":
            if y["risk_label_review"] not in LABELS:
                raise ValueError("invalid label")
        elif y["review_status"] == "unable_to_determine":
            if y["risk_label_review"] or not y["notes"].strip():
                raise ValueError("invalid abstention")
        else:
            raise ValueError("invalid status")
    return after


def main():
    base = ROOT / "data/interim/aib_risk_review_20260912"
    rows, receipts = {}, {}
    for slot, model in [("A", "sol"), ("B", "terra")]:
        folder = base / f"reviewer_{slot}"
        template, returned = (folder / "risk.csv").read_bytes(), (folder / "returned_risk.csv").read_bytes()
        if hashlib.sha256(template).hexdigest() != HASHES[slot]:
            raise ValueError("changed template")
        rows[slot] = {r["review_id"]: r for r in validate(template, returned, f"risk-{model}-20260912")}
        receipts[slot] = {"returned_sha256": hashlib.sha256(returned).hexdigest(),
                         "metadata_sha256": hashlib.sha256((folder / "execution_metadata.json").read_bytes()).hexdigest()}
    if set(rows["A"]) != set(rows["B"]):
        raise ValueError("unmatched inputs")
    pairs, disagreements = [], []
    for key, a in rows["A"].items():
        b = rows["B"][key]
        if a["material_sha256"] != b["material_sha256"]:
            raise ValueError("different materials")
        if a["review_status"] == b["review_status"] == "completed":
            pairs.append((a["risk_label_review"], b["risk_label_review"]))
        if (a["review_status"], a["risk_label_review"]) != (b["review_status"], b["risk_label_review"]):
            disagreements.append({"review_id": key, "A": a, "B": b})
    n = len(pairs)
    ca, cb = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    po = sum(x == y for x, y in pairs) / n if n else None
    pe = sum(ca[k]*cb[k] for k in ca) / n**2 if n else None
    result = {"rows": len(rows["A"]), "both_completed": n, "agreement": po,
        "kappa": (po-pe)/(1-pe) if pe is not None and pe < 1 else None,
        "counts": {slot: dict(Counter(r["risk_label_review"] or "abstain" for r in values.values())) for slot, values in rows.items()},
        "disagreements": disagreements, "receipts": receipts, "labels_applied": 0,
        "full_protocol_acceptance": False, "training_ready": False,
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    out = base / "coordinator_only/comparison.json"
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k:v for k,v in result.items() if k != "disagreements"}, indent=2))
    print("sha256", hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
