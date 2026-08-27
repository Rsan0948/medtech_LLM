# TBE Acceptance Criteria: Genomic Variant Classification
**Project: MedTech ZDS POC (Genomics)**
**ZDS-ID: TOOL-703 (Triadic Benchmark Evaluation)**

---

## 1. The Evaluation Split
*   **Methodology:** Temporal Split (Section 4.1 of ZDS Blueprint).
*   **Training Set:** Variants evaluated in ClinVar prior to **January 1, 2024**.
*   **Test Set (Held-out):** Most recent 500 variants evaluated after **January 1, 2024**.
*   **Non-Negotiable:** Test set variants must not appear in the CQF Tier-1 training data.

---

## 2. The Triadic Benchmarks

| Metric | Baseline Floor (InterVar) | Teacher Ceiling (DeepSeek R1) | Student Target (Qwen3 8B/14B) |
|--------|---------------------------|-------------------------------|------------------------------|
| **Overall Accuracy** | ~60-65% (est.) | ~85-90% (est.) | **> Baseline Floor** |
| **High-Conf Accuracy**| ~70% (est.) | ~95% (est.) | **> 80%** |
| **Reasoning Fidelity**| N/A (Rules-only) | 100% (Gold Standard) | **> 70% Agreement** |

---

## 3. Passing Thresholds (Pre-registered)
A distillation run is considered **SUCCESSFUL** only if it meets these criteria:

1.  **Beat the Floor:** Student Overall Accuracy must be strictly greater than the InterVar baseline.
2.  **Gap Closure:** Student must close at least **40% of the gap** between InterVar and R1.
3.  **High-Confidence Precision:** In cases where the Student outputs `confidence: High`, accuracy must be **>= 85%**.
4.  **Reasoning Integrity:** In a manual review of 50 test cases, the Student's "Reasoning Trace" must correctly identify the primary ACMG criterion (e.g., PVS1) at least 70% of the time.

---

## 4. Why this standard matters
In a MedTech room, "Accuracy" isn't enough. We must prove:
- **Improvement:** We are better than the current automated rule-based state-of-the-art (InterVar).
- **Calibration:** The model knows when it is right (High-Confidence Precision).
- **Auditability:** The model reaches the right conclusion for the right reason (Reasoning Integrity).

---

*Last Updated: March 8, 2026*
*PRE-EVALUATION LOCK*
