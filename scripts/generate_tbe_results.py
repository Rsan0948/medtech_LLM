#!/usr/bin/env python3
"""
Generate the TBE evaluation file for the MedTech distillation pipeline.

Uses the held-out validation split (newest 10% of teacher responses) and runs
local MLX inference with the trained Qwen3-8B LoRA adapter.  Produces
`data/app/student_tbe_results.jsonl` with verified, baseline, teacher, and
student labels.
"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from serving.variant_inference import VariantInference

VALID_PATH = PROJECT_ROOT / "data" / "app" / "training_data" / "valid.jsonl"
TRACES_PATH = PROJECT_ROOT / "data" / "processed" / "variant_traces_cqf_tier1.jsonl"
TEACHER_PATH = PROJECT_ROOT / "data" / "app" / "teacher_responses.jsonl"
OUTPUT_PATH = PROJECT_ROOT / "data" / "app" / "student_tbe_results.jsonl"
HOLDOUT_OUTPUT_PATH = PROJECT_ROOT / "data" / "app" / "student_tbe_results_holdout.jsonl"
MODEL_PATH = "mlx-community/Qwen3-8B-bf16"
ADAPTER_PATH = PROJECT_ROOT / "models" / "adapters" / "genomics_v2"

# The five canonical ACMG labels, in the form used by the schema / teacher.
CANONICAL_LABELS = {
    "Pathogenic",
    "Likely Pathogenic",
    "Variant of Uncertain Significance",
    "Likely Benign",
    "Benign",
}


def normalize_label(label: str) -> str:
    """Map model outputs to canonical ACMG labels."""
    label = label.strip().rstrip(".").lower()
    mapping = {
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
    return mapping.get(label, "Variant of Uncertain Significance")


def rule_baseline(trace: dict) -> str:
    """
    Simple InterVar-style rule baseline.
    Uses population frequency and predicted consequence when available.
    """
    evidence = trace.get("evidence", {})
    identity = trace.get("identity", {})
    af = evidence.get("gnomad_af")
    hgvs_c = (identity.get("hgvs_c") or "").lower()
    hgvs_p = (identity.get("hgvs_p") or "").lower()
    vtype = (identity.get("variant_type") or "").lower()

    null_variant = any(
        marker in hgvs_c or marker in hgvs_p
        for marker in ["fs", "*", "ter", "nonsense", "frameshift"]
    ) or vtype in {"frameshift", "nonsense"}

    # High allele frequency → benign
    if isinstance(af, (int, float)):
        if af > 0.05:
            return "Benign"
        if af > 0.01:
            return "Likely Benign"

    # Strong LoF signal without contradicting frequency
    if null_variant:
        return "Pathogenic"

    return "Variant of Uncertain Significance"


def extract_trace_id(prompt: str) -> str:
    match = re.search(r"ZDS-ID:\s*(CV-\d+)", prompt)
    if not match:
        raise ValueError("Could not find ZDS-ID in prompt")
    return match.group(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--holdout",
        action="store_true",
        help=(
            "Evaluate the true holdout set: tier-1 variants that were never "
            "distilled (no teacher response), instead of the validation split."
        ),
    )
    parser.add_argument(
        "--model",
        default=MODEL_PATH,
        help="Base model path (default: local Qwen3-8B).",
    )
    parser.add_argument(
        "--adapter",
        default=str(ADAPTER_PATH),
        help="LoRA adapter directory (default: models/adapters/genomics_v2).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Override the output JSONL path.",
    )
    args = parser.parse_args()

    if not args.holdout and not VALID_PATH.exists():
        print(f"Error: validation file not found: {VALID_PATH}")
        sys.exit(1)

    # Load full variant traces and teacher responses keyed by trace_id.
    traces = {}
    with open(TRACES_PATH) as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                traces[rec["trace_id"]] = rec

    teachers = {}
    with open(TEACHER_PATH) as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                teachers[rec["trace_id"]] = rec

    if args.holdout:
        # True holdout: tier-1 variants with no teacher response.
        eval_ids = [tid for tid in traces if tid not in teachers]
        output_path = Path(args.output) if args.output else HOLDOUT_OUTPUT_PATH
        print(f"Holdout mode: {len(eval_ids)} never-distilled variants", flush=True)
    else:
        # Validation split, original order.
        eval_ids = []
        with open(VALID_PATH) as f:
            for line in f:
                if line.strip():
                    ex = json.loads(line)
                    eval_ids.append(extract_trace_id(ex["messages"][0]["content"]))
        output_path = Path(args.output) if args.output else OUTPUT_PATH
        print(f"Loaded {len(eval_ids)} validation examples", flush=True)

    print("Loading local model + LoRA adapter...", flush=True)
    inference = VariantInference(
        model_path=args.model,
        adapter_path=args.adapter,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    for idx, trace_id in enumerate(eval_ids, start=1):
        trace = traces.get(trace_id)
        teacher_rec = teachers.get(trace_id)

        if trace is None:
            print(f"[{idx}/{len(eval_ids)}] Warning: trace not found for {trace_id}")
            continue
        if teacher_rec is None and not args.holdout:
            print(f"[{idx}/{len(eval_ids)}] Warning: teacher response not found for {trace_id}")
            continue

        verified_label = trace["verified_outcome"]["classification"]
        baseline_label = rule_baseline(trace)
        teacher_label = teacher_rec["teacher_classification"] if teacher_rec else None

        # Run local student inference.
        student_result = inference.classify(json.dumps(trace))
        student_label = normalize_label(student_result.get("classification", "VUS"))
        student_confidence = student_result.get("confidence", "Low")
        if student_confidence not in {"Low", "Medium", "High"}:
            student_confidence = "Low"

        record = {
            "trace_id": trace_id,
            "verified_label": verified_label,
            "baseline_label": baseline_label,
            "teacher_label": teacher_label,
            "student_label": student_label,
            "student_confidence": student_confidence,
            "student_reasoning_trace": student_result.get("reasoning_trace", ""),
        }
        results.append(record)
        print(
            f"[{idx}/{len(eval_ids)}] {trace_id} "
            f"verified={verified_label} baseline={baseline_label} "
            f"teacher={teacher_label} student={student_label} ({student_confidence})",
            flush=True,
        )

    with open(output_path, "w") as f:
        for rec in results:
            f.write(json.dumps(rec) + "\n")

    print(f"\nWrote {len(results)} TBE records to {output_path}", flush=True)


if __name__ == "__main__":
    main()
