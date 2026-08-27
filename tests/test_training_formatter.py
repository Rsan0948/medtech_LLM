import json
import tempfile
from pathlib import Path

from modeling.training_data_formatter import TrainingDataFormatter


def test_formatter_creates_chat_splits():
    responses = [
        {
            "trace_id": f"CV-{i:05d}",
            "variant_clinvar_id": str(i),
            "verified_outcome": "Pathogenic",
            "prompt": f"prompt {i}",
            "teacher_classification": "Pathogenic",
            "teacher_triggered_criteria": ["PVS1"],
            "teacher_reasoning_trace": f"reasoning {i}",
            "teacher_confidence": "High",
        }
        for i in range(20)
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        responses_path = Path(tmpdir) / "responses.jsonl"
        output_dir = Path(tmpdir) / "out"

        with open(responses_path, "w") as f:
            for r in responses:
                f.write(json.dumps(r) + "\n")

        formatter = TrainingDataFormatter(str(responses_path), str(output_dir))
        formatter.run()

        train_path = output_dir / "train.jsonl"
        valid_path = output_dir / "valid.jsonl"
        assert train_path.exists()
        assert valid_path.exists()

        with open(train_path) as f:
            train = [json.loads(line) for line in f]
        with open(valid_path) as f:
            valid = [json.loads(line) for line in f]

        assert len(train) == 18
        assert len(valid) == 2
        assert "messages" in train[0]
        assert train[0]["messages"][0]["role"] == "user"
        assert train[0]["messages"][1]["role"] == "assistant"
