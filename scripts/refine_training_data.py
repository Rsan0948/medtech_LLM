#!/usr/bin/env python3
"""
Refine the distillation training data (v2 data repair).

Repairs three problems found in the v1 dataset audit:

1. Duplicate trace_ids in the teacher responses (20 rows, 5 groups with
   contradictory labels). One record per variant is kept -- preferring the
   record whose teacher label matches the ClinVar verified label.
2. Teacher/ground-truth disagreement. For the *train* split, only records
   where the teacher classification matches the ClinVar verified label are
   kept, so the student never trains on a reasoning trace that argues for a
   different label than the target JSON emits (verifier-guided distillation).
   The *valid* split is left unfiltered and keeps the exact same trace IDs as
   before so evaluation stays comparable to v1.
3. Label leakage. User prompts are rebuilt from the variant traces with
   PromptFactory instead of copying the stored teacher prompt, which embeds
   label-conditioned `acmg_criteria_hints`. Trace-level hints are empty, so
   rebuilt prompts are guaranteed hint-free.

After filtering, rare classes (< MIN_CLASS_COUNT train examples) are
oversampled up to MIN_CLASS_COUNT to counter the severe class imbalance
(Benign is ~1% of the data).

Backs up the existing data/app/training_data/ directory to
data/app/training_data_v1_backup/ before writing.
"""

import json
import random
import shutil
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from modeling.prompt_factory import PromptFactory  # noqa: E402
from schemas.variant_trace_v1 import VariantTrace  # noqa: E402

TEACHER_PATH = PROJECT_ROOT / "data" / "app" / "teacher_responses.jsonl"
TRACES_PATH = PROJECT_ROOT / "data" / "processed" / "variant_traces_cqf_tier1.jsonl"
TRAINING_DIR = PROJECT_ROOT / "data" / "app" / "training_data"
BACKUP_DIR = PROJECT_ROOT / "data" / "app" / "training_data_v1_backup"
GUIDELINES_PATH = PROJECT_ROOT / "docs" / "ACMG_GUIDELINES_V1.txt"

MIN_CLASS_COUNT = 40
SEED = 42

LABEL_MAPPING = {
    "pathogenic": "Pathogenic",
    "likely pathogenic": "Likely Pathogenic",
    "likely_pathogenic": "Likely Pathogenic",
    "vus": "Variant of Uncertain Significance",
    "variant of uncertain significance": "Variant of Uncertain Significance",
    "uncertain significance": "Variant of Uncertain Significance",
    "likely benign": "Likely Benign",
    "likely_benign": "Likely Benign",
    "benign": "Benign",
}


def normalize_label(label: str) -> str:
    return LABEL_MAPPING.get(label.strip().rstrip(".").lower(), label.strip())


def load_jsonl(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    teachers = load_jsonl(TEACHER_PATH)
    traces = {rec["trace_id"]: rec for rec in load_jsonl(TRACES_PATH)}
    prompt_factory = PromptFactory(guidelines_path=str(GUIDELINES_PATH))

    # Preserve the existing valid split (same trace IDs) for comparability.
    valid_ids: set[str] = set()
    old_valid_path = TRAINING_DIR / "valid.jsonl"
    if old_valid_path.exists():
        import re

        for ex in load_jsonl(old_valid_path):
            match = re.search(r"ZDS-ID:\s*(CV-\d+)", ex["messages"][0]["content"])
            if match:
                valid_ids.add(match.group(1))
    print(f"Existing valid split: {len(valid_ids)} trace IDs preserved")

    # --- 1. Dedupe: one record per trace_id, preferring ClinVar agreement ---
    by_id: dict[str, list[dict]] = {}
    order: list[str] = []  # first-seen order for temporal stability
    for rec in teachers:
        tid = rec["trace_id"]
        if tid not in by_id:
            by_id[tid] = []
            order.append(tid)
        by_id[tid].append(rec)

    deduped: list[dict] = []
    dup_dropped = 0
    for tid in order:
        group = by_id[tid]
        dup_dropped += len(group) - 1
        trace = traces.get(tid)
        verified = normalize_label(trace["verified_outcome"]["classification"]) if trace else None
        # Prefer a record whose teacher label matches ClinVar ground truth.
        chosen = group[0]
        for rec in group:
            if verified and normalize_label(rec["teacher_classification"]) == verified:
                chosen = rec
                break
        deduped.append(chosen)
    print(f"Dedupe: {len(teachers)} -> {len(deduped)} ({dup_dropped} duplicates dropped)")

    # --- 2. Split, then agreement-filter the train split only ---
    train_pool = [r for r in deduped if r["trace_id"] not in valid_ids]
    valid_pool = [r for r in deduped if r["trace_id"] in valid_ids]

    def agrees(rec: dict) -> bool:
        trace = traces.get(rec["trace_id"])
        if trace is None:
            return False
        verified = normalize_label(trace["verified_outcome"]["classification"])
        return normalize_label(rec["teacher_classification"]) == verified

    train_kept = [r for r in train_pool if agrees(r)]
    train_dropped = len(train_pool) - len(train_kept)
    print(
        f"Agreement filter (train): kept {len(train_kept)}/{len(train_pool)} "
        f"({train_dropped} teacher/ClinVar disagreements dropped)"
    )
    print(f"Valid split: {len(valid_pool)} records (unfiltered)")

    # --- 3. Rebuild hint-free prompts from traces ---
    def build_example(rec: dict) -> dict | None:
        trace_dict = traces.get(rec["trace_id"])
        if trace_dict is None:
            return None
        trace = VariantTrace(**trace_dict)
        trace.acmg_criteria_hints = []  # belt-and-braces: never leak hints
        assistant = json.dumps(
            {
                "classification": rec["teacher_classification"],
                "triggered_criteria": rec["teacher_triggered_criteria"],
                "reasoning_trace": rec["teacher_reasoning_trace"],
                "confidence": rec["teacher_confidence"],
            },
            indent=2,
        )
        return {
            "messages": [
                {"role": "user", "content": prompt_factory.create_prompt(trace)},
                {"role": "assistant", "content": assistant},
            ]
        }

    train_examples = [ex for ex in (build_example(r) for r in train_kept) if ex]
    valid_examples = [ex for ex in (build_example(r) for r in valid_pool) if ex]

    def class_of(ex: dict) -> str:
        return normalize_label(json.loads(ex["messages"][1]["content"])["classification"])

    print("\nTrain class distribution (before oversampling):")
    for label, count in Counter(class_of(ex) for ex in train_examples).most_common():
        print(f"  {label:40s} {count}")

    # --- 4. Oversample rare classes in train ---
    by_class: dict[str, list[dict]] = {}
    for ex in train_examples:
        by_class.setdefault(class_of(ex), []).append(ex)
    augmented = list(train_examples)
    for label, examples in by_class.items():
        if 0 < len(examples) < MIN_CLASS_COUNT:
            needed = MIN_CLASS_COUNT - len(examples)
            augmented.extend(examples[i % len(examples)] for i in range(needed))
            print(f"Oversampled '{label}': {len(examples)} -> {MIN_CLASS_COUNT}")
    rng = random.Random(SEED)
    rng.shuffle(augmented)
    train_examples = augmented

    print("\nTrain class distribution (after oversampling):")
    for label, count in Counter(class_of(ex) for ex in train_examples).most_common():
        print(f"  {label:40s} {count}")

    # --- 5. Backup + write ---
    if TRAINING_DIR.exists() and not BACKUP_DIR.exists():
        shutil.move(str(TRAINING_DIR), str(BACKUP_DIR))
        print(f"\nBacked up original training data -> {BACKUP_DIR}")
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)

    for name, examples in (("train", train_examples), ("valid", valid_examples)):
        path = TRAINING_DIR / f"{name}.jsonl"
        with open(path, "w") as f:
            for ex in examples:
                f.write(json.dumps(ex) + "\n")
        print(f"Wrote {len(examples):4d} examples -> {path}")


if __name__ == "__main__":
    main()
