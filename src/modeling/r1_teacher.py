import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, cast

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

load_dotenv()

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-reasoner"
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
MAX_WORKERS = 5  # 5 concurrent workers - DON'T run other DeepSeek programs simultaneously
BATCH_SIZE = 50  # Reduced from 100 for faster checkpoints
REQUEST_TIMEOUT = 180  # 3 minutes per request (R1 is slow but shouldn't take longer)
BATCH_TIMEOUT = 1800  # 30 minutes max per batch (was too short at 10 min)

SYSTEM_PROMPT = (
    "You are a clinical genomics specialist trained in ACMG/AMP variant classification. "
    "When given a variant profile and ACMG guidelines, you reason through each criterion "
    "step-by-step and return a structured JSON classification.\n\n"
    "Your response MUST be valid JSON with exactly these keys:\n"
    "  classification: one of [Pathogenic, Likely Pathogenic, "
    "Variant of Uncertain Significance, Likely Benign, Benign]\n"
    '  triggered_criteria: list of ACMG criterion codes (e.g. ["PVS1", "PM2"])\n'
    "  reasoning_trace: detailed step-by-step reasoning string\n"
    "  confidence: one of [High, Medium, Low]"
)


class R1Teacher:
    """
    ZDS-ID: TOOL-701 (Teacher Trace Generation)
    Calls DeepSeek R1 to generate ACMG reasoning traces for each variant prompt.
    Supports resuming interrupted runs by skipping already-processed trace_ids.
    NOW WITH CONCURRENT PROCESSING (5 workers) AND BATCH CHECKPOINTS.
    """

    def __init__(self, prompts_path: str, output_path: str, max_workers: int = MAX_WORKERS):
        self.prompts_path = Path(prompts_path)
        self.output_path = Path(output_path)
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.max_workers = max_workers

    def _ensure_api_key(self):
        if not self.api_key:
            raise OSError("DEEPSEEK_API_KEY not set. Copy .env.example to .env and add your key.")

        # Thread-safe counters
        self._lock = threading.Lock()
        self.total_processed = 0
        self.total_skipped = 0
        self.total_errors = 0

    def _load_processed_ids(self) -> set[str]:
        """Load already-processed trace_ids to allow resume on interruption."""
        processed = set()
        if self.output_path.exists():
            with open(self.output_path) as f:
                for line in f:
                    if line.strip():
                        try:
                            row = json.loads(line)
                            processed.add(row["trace_id"])
                        except (json.JSONDecodeError, KeyError):
                            continue
        return processed

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Parse JSON from response content, stripping markdown fences if present."""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return cast(dict[str, Any], json.loads(text.strip()))

    def _get_session(self) -> requests.Session:
        """Create a requests session with connection pooling and retry logic."""
        session = requests.Session()

        # Retry strategy for connection errors (not for timeouts)
        retry_strategy = Retry(
            total=2,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        )

        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=MAX_WORKERS,
            pool_maxsize=MAX_WORKERS * 2,
        )

        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _call_r1(self, prompt: str) -> dict[str, Any]:
        """Call DeepSeek R1 API with retry logic and proper timeout handling."""
        self._ensure_api_key()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
        }

        session = self._get_session()
        last_exception: Exception | None = None

        for attempt in range(MAX_RETRIES):
            start_time = time.time()
            try:
                # Use a session for connection reuse
                resp = session.post(
                    DEEPSEEK_API_URL,
                    headers=headers,
                    json=payload,
                    timeout=(30, REQUEST_TIMEOUT),  # (connect timeout, read timeout)
                )
                elapsed = time.time() - start_time
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                result = self._extract_json(content)

                # Log slow requests for monitoring
                if elapsed > 60:
                    print(f"    ⚠️  Slow request: {elapsed:.1f}s")

                return result

            except requests.exceptions.Timeout:
                elapsed = time.time() - start_time
                print(f"    ⏱️  Timeout after {elapsed:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_DELAY * (2**attempt)
                    print(f"    Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise Exception(
                        f"Request timed out after {MAX_RETRIES} attempts ({elapsed:.1f}s total)"
                    )

            except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
                elapsed = time.time() - start_time
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_DELAY * (2**attempt)
                    print(
                        f"    Retry {attempt + 1}/{MAX_RETRIES} after error: {e}. Waiting {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    raise

        raise last_exception or Exception("Unexpected end of retry loop")

    def _process_single_item(self, item: dict, processed_ids: set[str]) -> dict[str, Any] | None:
        """Process a single prompt item. Returns record or None if skipped/error."""
        trace_id = item["trace_id"]

        # Check if already processed
        if trace_id in processed_ids:
            with self._lock:
                self.total_skipped += 1
            return None

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

            with self._lock:
                self.total_processed += 1
                current = self.total_processed
                if current % 10 == 0:
                    print(f"  [Progress] {current} processed in current batch")

            return record

        except Exception as e:
            with self._lock:
                self.total_errors += 1
            print(f"  ERROR on {trace_id}: {e}")
            return None

    def process_batch(self, batch: list[dict], processed_ids: set[str], f_out) -> list[dict]:
        """Process a batch of prompts concurrently with timeout protection."""
        results = []
        pending = set()
        completed_count = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks in batch
            future_to_item = {
                executor.submit(self._process_single_item, item, processed_ids): item
                for item in batch
            }
            pending = set(future_to_item.keys())

            # Collect results with timeout protection per future
            batch_start = time.time()
            while pending and (time.time() - batch_start) < BATCH_TIMEOUT:
                # Check for completed futures with a short timeout
                done = set()
                for future in list(pending):
                    if future.done():
                        done.add(future)
                        pending.remove(future)

                        try:
                            record = future.result(timeout=0)  # Already done, no wait
                            if record:
                                with self._lock:
                                    f_out.write(json.dumps(record) + "\n")
                                    f_out.flush()
                                results.append(record)
                                completed_count += 1
                        except Exception as e:
                            item = future_to_item[future]
                            print(f"  ERROR processing {item['trace_id']}: {e}")

                if not done:
                    # No futures completed, wait a bit before checking again
                    time.sleep(0.5)

                    # Progress update every 30 seconds if stuck
                    elapsed = time.time() - batch_start
                    if int(elapsed) % 30 == 0 and int(elapsed) > 0:
                        print(
                            f"  ⏳ Batch in progress... {completed_count}/{len(batch)} done, {len(pending)} pending ({elapsed:.0f}s elapsed)"
                        )

            # Cancel any remaining pending futures (timed out)
            for future in pending:
                future.cancel()
                item = future_to_item[future]
                print(f"  ⚠️  CANCELLED (timeout): {item['trace_id']}")

        if len(results) < len(batch):
            print(
                f"  ⚠️  Batch incomplete: {len(results)}/{len(batch)} succeeded ({len(batch) - len(results)} failed/timed out)"
            )

        return results

    def analyze_batch_quality(self, records: list[dict]) -> dict[str, Any]:
        """Analyze quality metrics for a batch of records."""
        if not records:
            return {}

        # Accuracy
        matches = 0
        confusion: dict[tuple[str, str], int] = {}
        reasoning_lengths = []

        for r in records:
            verified = r.get("verified_outcome", "")
            teacher = r.get("teacher_classification", "")

            v_norm = verified.lower().replace("_", " ")
            t_norm = teacher.lower()

            match = v_norm in t_norm or t_norm in v_norm or verified == teacher
            if match:
                matches += 1

            key = (verified, teacher)
            confusion[key] = confusion.get(key, 0) + 1

            rt = r.get("teacher_reasoning_trace", "")
            reasoning_lengths.append(len(rt.split()))

        return {
            "count": len(records),
            "accuracy": 100 * matches / len(records),
            "confusion": confusion,
            "avg_reasoning_words": sum(reasoning_lengths) / len(reasoning_lengths),
            "min_reasoning": min(reasoning_lengths),
            "max_reasoning": max(reasoning_lengths),
        }

    def run(self):
        """Run the teacher - simple approach, no batches, just process until done."""
        if not self.prompts_path.exists():
            print(f"Error: {self.prompts_path} not found. Run 'prompts' stage first.")
            return

        processed_ids = self._load_processed_ids()

        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        # Load all prompts
        with open(self.prompts_path) as f_in:
            all_prompts = [json.loads(line) for line in f_in if line.strip()]

        # Filter to first 1000
        TARGET_COUNT = 1000
        if len(all_prompts) > TARGET_COUNT:
            all_prompts = all_prompts[:TARGET_COUNT]

        # Filter out already processed
        prompts_to_process = [p for p in all_prompts if p["trace_id"] not in processed_ids]
        already_done = len(all_prompts) - len(prompts_to_process)

        print(f"\n{'='*60}")
        print("R1 TEACHER - SIMPLE MODE (NO BATCHES)")
        print(f"{'='*60}")
        print(f"Total target: {len(all_prompts)}")
        print(f"Already done: {already_done}")
        print(f"Remaining: {len(prompts_to_process)}")
        print(f"Workers: {self.max_workers}")
        print(f"ETA: ~{len(prompts_to_process) * 3 / 60 / self.max_workers:.1f} hours")
        print(f"{'='*60}\n")

        if not prompts_to_process:
            print("All done!")
            return

        # Process all remaining with thread pool - NO BATCHES, NO TIMEOUTS
        results = []
        completed = 0
        failed = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_item = {
                executor.submit(self._process_single_item, item, processed_ids): item
                for item in prompts_to_process
            }

            print(f"Submitted {len(future_to_item)} tasks to {self.max_workers} workers...")
            print("Processing (this will take a while)...\n")

            # Collect results as they complete
            with open(self.output_path, "a") as f_out:
                for future in as_completed(future_to_item):
                    try:
                        record = future.result()
                        if record:
                            f_out.write(json.dumps(record) + "\n")
                            f_out.flush()
                            results.append(record)
                            completed += 1

                            # Progress every 10
                            if completed % 10 == 0:
                                print(
                                    f"  Progress: {completed}/{len(prompts_to_process)} ({100*completed/len(prompts_to_process):.1f}%)"
                                )
                        else:
                            failed += 1
                    except Exception as e:
                        failed += 1
                        item = future_to_item[future]
                        print(f"  ERROR on {item['trace_id']}: {e}")

        # Final summary
        print(f"\n{'='*60}")
        print("R1 TEACHER COMPLETE")
        print(f"{'='*60}")
        print(f"Completed: {completed}")
        print(f"Failed: {failed}")
        print(f"Total now in file: {already_done + completed}")
        print(f"Output: {self.output_path}")
        print(f"{'='*60}")

    def _show_detailed_analysis(self, records: list[dict]):
        """Show detailed analysis of batch results."""
        print(f"\n{'='*60}")
        print("DETAILED BATCH ANALYSIS")
        print(f"{'='*60}")

        for i, r in enumerate(records[:5], 1):  # Show first 5
            print(f"\n--- Example {i}: {r['trace_id']} ---")
            print(f"Verified: {r['verified_outcome']}")
            print(f"Teacher: {r['teacher_classification']}")
            print(f"Match: {r['verified_outcome'].lower() in r['teacher_classification'].lower()}")
            print(f"Confidence: {r['teacher_confidence']}")
            print(f"Criteria: {r['teacher_triggered_criteria']}")
            rt = r["teacher_reasoning_trace"]
            print(f"Reasoning ({len(rt.split())} words):")
            print(rt[:500] + "..." if len(rt) > 500 else rt)
            print("-" * 40)


if __name__ == "__main__":
    teacher = R1Teacher(
        prompts_path="data/app/teacher_prompts_1k.jsonl",
        output_path="data/app/teacher_responses.jsonl",
    )
    teacher.run()
