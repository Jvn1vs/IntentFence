import csv
import io

from scripts.package_aib_alignment_review import csv_bytes, material


def test_material_allowlist_excludes_labels_future_and_policy():
    source = {"system_prompt": "system", "tools_available": [], "ground_truth": "secret label",
              "conversation": [{"role": "user", "content": "goal"},
                               {"role": "tool_result", "content": "data"},
                               {"role": "assistant", "content": "future answer"}]}
    result = material(source, 2, {"tool": "memory.test", "arguments": {}})
    assert set(result) == {"user_goal", "history_before_action", "source_tool_definitions", "proposed_action"}
    assert len(result["history_before_action"]) == 3
    assert "secret label" not in str(result) and "future answer" not in str(result)


def test_multiline_csv_and_empty_answer_fields():
    rows = [{"review_id": "x", "material_sha256": "fixture", "user_goal": 'line1\n"line2"',
             "history_before_action": [], "source_tool_definitions": [], "proposed_action": {}}]
    parsed = list(csv.DictReader(io.StringIO(csv_bytes(rows, "A").decode())))
    assert parsed[0]["user_goal"] == rows[0]["user_goal"]
    assert parsed[0]["task_alignment_label_review"] == ""
