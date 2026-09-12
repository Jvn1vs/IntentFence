import csv
import io

import pytest

from scripts.compare_aib_risk_reviews import validate
from scripts.package_aib_risk_review import FIELDS


def encode(row):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerow(row)
    return stream.getvalue().encode()


def test_risk_return_rejects_material_change_and_filled_abstention():
    template = dict.fromkeys(FIELDS, "") | {"review_id": "fixture", "material_sha256": "fixture", "untrusted_content": "text"}
    returned = template | {"review_status": "completed", "risk_label_review": "benign", "reviewer_id": "fixture", "reviewed_at": "2026-09-12T12:00:00+08:00"}
    assert len(validate(encode(template), encode(returned), "fixture")) == 1
    returned["untrusted_content"] = "changed"
    with pytest.raises(ValueError):
        validate(encode(template), encode(returned), "fixture")
    returned.update(untrusted_content="text", review_status="unable_to_determine", notes="reason")
    with pytest.raises(ValueError, match="abstention"):
        validate(encode(template), encode(returned), "fixture")
    returned["risk_label_review"] = ""
    assert len(validate(encode(template), encode(returned), "fixture")) == 1
