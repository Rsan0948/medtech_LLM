import json
import tempfile
from pathlib import Path

from modeling.r1_teacher import R1Teacher


def test_extract_json_strips_markdown():
    teacher = R1Teacher(prompts_path="/dev/null", output_path="/dev/null")

    raw = '```json\n{"classification": "Pathogenic", "triggered_criteria": ["PVS1"]}\n```'
    result = teacher._extract_json(raw)
    assert result["classification"] == "Pathogenic"
    assert result["triggered_criteria"] == ["PVS1"]

    raw_no_lang = '```\n{"classification": "Benign"}\n```'
    result2 = teacher._extract_json(raw_no_lang)
    assert result2["classification"] == "Benign"


def test_load_processed_ids():
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "responses.jsonl"
        with open(output_path, "w") as f:
            f.write(json.dumps({"trace_id": "CV-1", "data": "x"}) + "\n")
            f.write(json.dumps({"trace_id": "CV-2", "data": "y"}) + "\n")
            f.write("not valid json\n")

        teacher = R1Teacher(prompts_path="/dev/null", output_path=str(output_path))
        processed = teacher._load_processed_ids()
        assert processed == {"CV-1", "CV-2"}
