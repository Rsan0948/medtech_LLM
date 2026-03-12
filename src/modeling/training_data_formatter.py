import json
import os
import sys
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

TRAIN_SPLIT = 0.9  # oldest 90% → train, newest 10% → valid


class TrainingDataFormatter:
    """
    ZDS-ID: TOOL-700 (Stage 5 - Training Data Preparation)
    Converts R1 teacher responses into MLX-LM compatible chat-format JSONL.
    Uses a temporal split: oldest 90% for training, most recent 10% for validation.
    """

    def __init__(self, responses_path: str, output_dir: str):
        self.responses_path = Path(responses_path)
        self.output_dir = Path(output_dir)

    def _build_message(self, record: Dict) -> Dict:
        """Format a single record into MLX-LM chat message format."""
        assistant_content = json.dumps({
            "classification": record["teacher_classification"],
            "triggered_criteria": record["teacher_triggered_criteria"],
            "reasoning_trace": record["teacher_reasoning_trace"],
            "confidence": record["teacher_confidence"],
        }, indent=2)

        return {
            "messages": [
                {"role": "user", "content": record["prompt"]},
                {"role": "assistant", "content": assistant_content},
            ]
        }

    def run(self):
        if not self.responses_path.exists():
            print(f"Error: {self.responses_path} not found. Run 'teacher' stage first.")
            return

        with open(self.responses_path, 'r') as f:
            records = [json.loads(l) for l in f if l.strip()]

        if not records:
            print("Error: No records found in teacher responses file.")
            return

        # Temporal split: preserve file order (ClinVar IDs are roughly chronological)
        split_idx = int(len(records) * TRAIN_SPLIT)
        train_records = records[:split_idx]
        valid_records = records[split_idx:]

        self.output_dir.mkdir(parents=True, exist_ok=True)
        train_path = self.output_dir / "train.jsonl"
        valid_path = self.output_dir / "valid.jsonl"

        with open(train_path, 'w') as f:
            for rec in train_records:
                f.write(json.dumps(self._build_message(rec)) + '\n')

        with open(valid_path, 'w') as f:
            for rec in valid_records:
                f.write(json.dumps(self._build_message(rec)) + '\n')

        print("=" * 50)
        print("TRAINING DATA FORMATTER COMPLETE")
        print(f"Total records:     {len(records)}")
        print(f"Train set (90%%):  {len(train_records)} → {train_path}")
        print(f"Valid set (10%%):  {len(valid_records)} → {valid_path}")
        print("=" * 50)


if __name__ == "__main__":
    formatter = TrainingDataFormatter(
        responses_path="data/app/teacher_responses.jsonl",
        output_dir="data/app/training_data",
    )
    formatter.run()
