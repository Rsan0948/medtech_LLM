import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Set

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-reasoner"
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

SYSTEM_PROMPT = (
    "You are a clinical genomics specialist trained in ACMG/AMP variant classification. "
    "When given a variant profile and ACMG guidelines, you reason through each criterion "
    "step-by-step and return a structured JSON classification.\n\n"
    "Your response MUST be valid JSON with exactly these keys:\n"
    "  classification: one of [Pathogenic, Likely Pathogenic, "
    "Variant of Uncertain Significance, Likely Benign, Benign]\n"
    "  triggered_criteria: list of ACMG criterion codes (e.g. [\"PVS1\", \"PM2\"])\n"
    "  reasoning_trace: detailed step-by-step reasoning string\n"
    "  confidence: one of [High, Medium, Low]"
)


class R1Teacher:
    """
    ZDS-ID: TOOL-701 (Teacher Trace Generation)
    Calls DeepSeek R1 to generate ACMG reasoning traces for each variant prompt.
    Supports resuming interrupted runs by skipping already-processed trace_ids.
    """

    def __init__(self, prompts_path: str, output_path: str):
        self.prompts_path = Path(prompts_path)
        self.output_path = Path(output_path)
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise EnvironmentError(
                "DEEPSEEK_API_KEY not set. Copy .env.example to .env and add your key."
            )

    def _load_processed_ids(self) -> Set[str]:
        """Load already-processed trace_ids to allow resume on interruption."""
        processed = set()
        if self.output_path.exists():
            with open(self.output_path, 'r') as f:
                for line in f:
                    if line.strip():
                        row = json.loads(line)
                        processed.add(row["trace_id"])
        return processed

    def _call_r1(self, prompt: str) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
        }

        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=120)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                return json.loads(content)
            except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_DELAY * (2 ** attempt)
                    print(f"    Retry {attempt + 1}/{MAX_RETRIES} after error: {e}. Waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise

    def run(self):
        if not self.prompts_path.exists():
            print(f"Error: {self.prompts_path} not found. Run 'prompts' stage first.")
            return

        processed_ids = self._load_processed_ids()
        if processed_ids:
            print(f"Resuming: {len(processed_ids)} variants already processed.")

        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        total = 0
        skipped = 0
        errors = 0

        with open(self.prompts_path, 'r') as f_in:
            prompts = [json.loads(l) for l in f_in if l.strip()]

        print(f"Running R1 teacher on {len(prompts)} prompts...")

        with open(self.output_path, 'a') as f_out:
            for i, item in enumerate(prompts):
                trace_id = item["trace_id"]

                if trace_id in processed_ids:
                    skipped += 1
                    continue

                try:
                    response = self._call_r1(item["prompt"])
                    record = {
                        "trace_id": trace_id,
                        "variant_clinvar_id": item["variant_clinvar_id"],
                        "verified_outcome": item["verified_outcome"],
                        "prompt": item["prompt"],
                        "teacher_classification": response.get("classification", ""),
                        "teacher_triggered_criteria": response.get("triggered_criteria", []),
                        "teacher_reasoning_trace": response.get("reasoning_trace", ""),
                        "teacher_confidence": response.get("confidence", "Low"),
                    }
                    f_out.write(json.dumps(record) + '\n')
                    f_out.flush()
                    total += 1

                    if (i + 1) % 10 == 0:
                        print(f"  [{i+1}/{len(prompts)}] processed {total}, skipped {skipped}, errors {errors}")

                except Exception as e:
                    print(f"  ERROR on {trace_id}: {e}")
                    errors += 1

        print("\n" + "=" * 50)
        print("R1 TEACHER COMPLETE")
        print(f"Processed: {total}")
        print(f"Skipped (resume): {skipped}")
        print(f"Errors: {errors}")
        print(f"Output: {self.output_path}")
        print("=" * 50)


if __name__ == "__main__":
    teacher = R1Teacher(
        prompts_path="data/app/teacher_prompts.jsonl",
        output_path="data/app/teacher_responses.jsonl",
    )
    teacher.run()
