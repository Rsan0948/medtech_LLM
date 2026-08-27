#!/usr/bin/env python3
"""
Build the community reasoning-integrity review bundle.

Samples 50 stratified cases from the student TBE results and renders a
self-contained markdown document (docs/REASONING_REVIEW.md) that external
reviewers can work through without any local setup:

  - all student errors (student label != ClinVar verified label),
  - plus a stratified random sample of the remainder (seeded, reproducible),
    balanced across confidence levels and classes.

Reviewers see the variant evidence, the student's label/confidence, and its
full reasoning trace -- but NOT the ClinVar verified label (blind review).
The mapping from case number to trace_id is kept in
data/app/reasoning_review_sample.json so verdicts can be scored later with
scripts/score_reasoning_review.py.
"""

import json
import random
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RESULTS_PATH = PROJECT_ROOT / "data" / "app" / "student_tbe_results.jsonl"
TRACES_PATH = PROJECT_ROOT / "data" / "processed" / "variant_traces_cqf_tier1.jsonl"
SAMPLE_PATH = PROJECT_ROOT / "data" / "app" / "reasoning_review_sample.json"
OUTPUT_PATH = PROJECT_ROOT / "docs" / "REASONING_REVIEW.md"

N_CASES = 50
SEED = 42

RUBRIC = """\
## Review rubric — what counts as "integrity"

Judge the **reasoning**, not the final label. A case **FAILS** if any of these hold:

1. **Invalid criterion** — an ACMG/AMP code is triggered that does not apply
   (e.g., claiming BA1 with a gnomAD AF far below 5%).
2. **Fabricated evidence** — a number or fact is cited that is not present in
   the variant evidence (e.g., an invented CADD score).
3. **Incomplete check** — the trace does not check BOTH pathogenic and benign
   criteria before concluding.
4. **Incoherent logic** — the conclusion contradicts the stated criteria
   (e.g., argues benign throughout, then outputs Pathogenic).

Otherwise the case **PASSES** — even if you suspect the final label is wrong.
Use **BORDERLINE** sparingly, when a violation is ambiguous.
"""


def load_jsonl(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def evidence_block(trace: dict) -> str:
    identity = trace["identity"]
    evidence = trace["evidence"]

    def fmt(value: object) -> str:
        return str(value) if value not in (None, "") else "N/A"

    return "\n".join(
        [
            f"- Gene: {identity['gene_symbol']}",
            f"- HGVS (coding): {identity['hgvs_c']}",
            f"- HGVS (protein): {fmt(identity.get('hgvs_p'))}",
            f"- Type: {identity['variant_type']}",
            f"- gnomAD AF: {fmt(evidence.get('gnomad_af'))}",
            f"- gnomAD filter: {fmt(evidence.get('gnomad_filter'))}",
            f"- CADD: {fmt(evidence.get('cadd_score'))}",
            f"- SIFT / PolyPhen: {fmt(evidence.get('sift_score'))} / "
            f"{fmt(evidence.get('polyphen_score'))}",
            f"- Functional studies: {fmt(evidence.get('functional_studies'))}",
        ]
    )


def main() -> None:
    results = load_jsonl(RESULTS_PATH)
    traces = {rec["trace_id"]: rec for rec in load_jsonl(TRACES_PATH)}

    errors = [r for r in results if r["student_label"] != r["verified_label"]]
    correct = [r for r in results if r["student_label"] == r["verified_label"]]

    rng = random.Random(SEED)
    sampled_correct = rng.sample(correct, min(N_CASES - len(errors), len(correct)))
    sample = errors + sampled_correct
    rng.shuffle(sample)

    SAMPLE_PATH.write_text(
        json.dumps(
            [
                {
                    "case": i,
                    "trace_id": r["trace_id"],
                    "verified_label": r["verified_label"],
                    "student_label": r["student_label"],
                    "student_confidence": r["student_confidence"],
                    "was_error": r in errors,
                }
                for i, r in enumerate(sample, start=1)
            ],
            indent=2,
        )
    )

    lines = [
        "# Community Review: Reasoning Integrity of a Distilled Genomics Model",
        "",
        "We distilled a Qwen3-8B student model to classify germline variants "
        "(BRCA1/2 and related genes) under ACMG/AMP guidelines. On held-out "
        "ClinVar labels it reaches ~90% accuracy, beating both an InterVar-style "
        "rule baseline (75.5%) and its own DeepSeek-R1 teacher (69.4%).",
        "",
        "**What we need from you:** clinical-genomics expertise to audit whether "
        "the model's *reasoning* is sound — not just whether the label is right. "
        "This is the last unchecked acceptance criterion (target: ≥ 70% of 50 "
        "cases pass).",
        "",
        "**How to review:** each case below shows the variant evidence given to "
        "the model, its predicted label/confidence, and its full reasoning trace. "
        "Apply the rubric and record `PASS`, `FAIL`, or `BORDERLINE` per case "
        "(optionally with a one-line note). The ClinVar label is deliberately "
        "hidden to keep the review blind. Submit verdicts however is easiest — "
        "a filled copy of this file, a spreadsheet, or a list like "
        "`1: PASS, 2: FAIL (invented CADD score), ...`.",
        "",
        RUBRIC,
        "---",
        "",
    ]

    for i, r in enumerate(sample, start=1):
        trace = traces[r["trace_id"]]
        lines += [
            f"## Case {i}",
            "",
            "**Variant evidence:**",
            "",
            evidence_block(trace),
            "",
            f"**Model output:** {r['student_label']} " f"(confidence: {r['student_confidence']})",
            "",
            "**Reasoning trace:**",
            "",
            f"> {r['student_reasoning_trace'].strip()}",
            "",
            "**Verdict:** `PASS / FAIL / BORDERLINE` — note: ______",
            "",
            "---",
            "",
        ]

    OUTPUT_PATH.write_text("\n".join(lines))
    print(
        f"Sampled {len(sample)} cases ({len(errors)} errors, "
        f"{len(sampled_correct)} correct) -> {OUTPUT_PATH}"
    )
    print(f"Case mapping -> {SAMPLE_PATH}")


if __name__ == "__main__":
    main()
