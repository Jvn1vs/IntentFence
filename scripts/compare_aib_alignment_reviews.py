"""Compare two returned pilot reviews; not a full-protocol acceptance decision."""
import hashlib
import json
from collections import Counter
from pathlib import Path

from scripts.validate_aib_alignment_return import FORM_HASHES, parse, validate

ROOT = Path(__file__).resolve().parents[1]


def compare(left, right):
    a = {r["review_id"]: r for r in left}
    b = {r["review_id"]: r for r in right}
    if len(a) != len(left) or len(b) != len(right) or set(a) != set(b) or not a:
        raise ValueError("duplicate or unmatched review identities")
    pairs, disagreements = [], []
    for key in sorted(a):
        x, y = a[key], b[key]
        if x["material_sha256"] != y["material_sha256"]:
            raise ValueError("review material mismatch")
        if x["review_status"] == y["review_status"] == "completed":
            pairs.append((x["task_alignment_label_review"], y["task_alignment_label_review"]))
        if (x["review_status"], x["task_alignment_label_review"], x["action_realism_review"]) != (
                y["review_status"], y["task_alignment_label_review"], y["action_realism_review"]):
            disagreements.append({"review_id": key, "A": {k: x[k] for k in ["review_status", "task_alignment_label_review", "action_realism_review", "notes"]},
                                  "B": {k: y[k] for k in ["review_status", "task_alignment_label_review", "action_realism_review", "notes"]}})
    n = len(pairs)
    counts_a = Counter(x for x, _ in pairs)
    counts_b = Counter(y for _, y in pairs)
    agreement = sum(x == y for x, y in pairs) / n if n else None
    chance = sum(counts_a[k] * counts_b[k] for k in counts_a) / n**2 if n else None
    kappa = (agreement - chance) / (1 - chance) if chance is not None and chance < 1 else None
    return {"rows": len(a), "both_completed": n, "alignment_agreement_on_both_completed": agreement,
            "cohen_kappa_on_both_completed": kappa, "confusion_counts": {
                f"{x}|{y}": count for (x, y), count in sorted(Counter(pairs).items())},
            "disagreements": disagreements, "full_protocol_acceptance": False,
            "labels_applied": 0, "human_verified": False, "training_ready": False}


def main():
    base = ROOT / "data/interim/aib_alignment_review_20260912"
    rows, receipts, validations = {}, {}, {}
    for slot, reviewer in [("A", "alignment-sol-20260912"), ("B", "alignment-terra-20260912")]:
        folder = base / f"reviewer_{slot}"
        template, returned = (folder / "alignment.csv").read_bytes(), (folder / "returned_alignment.csv").read_bytes()
        if hashlib.sha256(template).hexdigest() != FORM_HASHES[slot]:
            raise ValueError("template changed")
        validations[slot] = validate(template, returned, reviewer)
        rows[slot] = parse(returned)
        receipts[slot] = {"template_sha256": hashlib.sha256(template).hexdigest(),
                          "returned_sha256": hashlib.sha256(returned).hexdigest()}
        metadata = (folder / "execution_metadata.json").read_bytes()
        receipts[slot]["metadata_sha256"] = hashlib.sha256(metadata).hexdigest()
    report = compare(rows["A"], rows["B"])
    report |= {"file_receipts": receipts, "form_validation": validations,
               "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    out = base / "coordinator_only/comparison.json"
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in {"disagreements", "form_validation"}}, indent=2))
    print("comparison_sha256", hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
