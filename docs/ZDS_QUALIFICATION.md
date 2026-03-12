# ZDS Stage 0: MedTech Qualification - Genomic Variant Classification
**Status: QUALIFIED**
**ZDS-ID: TOOL-700 (Distillation Pipeline)**

---

## 1. Domain Overview
**Goal:** Distill reasoning capability for the 5-tier classification of genomic variants (Pathogenic, Likely Pathogenic, VUS, Likely Benign, Benign) based on the ACMG/AMP clinical framework.

---

## 2. Gate Requirements (Stage 0 Blueprint)

### A. Verified Outcome Oracle (VOD)
*   **Oracle Source:** [ClinVar (NCBI)](https://www.ncbi.nlm.nih.gov/clinvar/)
*   **Definition:** Public archive of interpretations of clinically relevant variants with expert-reviewed consensus.
*   **Status:** **Pass.** 2.4M+ variant records with timestamped interpretations and submitter-level confidence ratings.

### B. Minimum Dataset Size (VOD)
*   **Target:** 1,000+ Tier-1 events.
*   **Status:** **Pass.** Hundreds of thousands of variants have "Consensus" interpreted (2+ stars in ClinVar).

### C. Temporal Ordering (VOD)
*   **Definition:** Clear timestamps to prevent data leakage in a non-random split.
*   **Status:** **Pass.** Every ClinVar submission includes a `DateLastEvaluated`.

### D. Consensus Quality Filtering (CQF)
*   **Strategy:** Filter for "Two-Star" or "Three-Star" ClinVar classifications (where multiple expert labs agree and there are no conflicting interpretations).
*   **Status:** **Pass.** This provides the highest signal training set for Reasoning Distillation.

### E. Baseline Floor (TBE)
*   **Baseline:** InterVar (Rule-based ACMG classification tool).
*   **Status:** **Pass.** We will benchmark the student model's accuracy and reasoning against InterVar's deterministic scores.

---

## 3. The "Variant Trace" Contract (v1.0)
The **RichSpec (ZDS-ID: TOOL-801)** for the Teacher (DeepSeek R1) must include:

1.  **Identity:** HGVS genomic notation (e.g., `NM_000059.3:c.5946del`).
2.  **Evidence Profile:**
    *   Population frequency (gnomAD).
    *   Computational scores (CADD, SIFT, PolyPhen).
    *   Functional studies (if available).
3.  **ACMG Criteria Context:** Mapping specific data points to potential criteria (e.g., "Variant is absent from all populations" -> PM2).
4.  **Teacher Task:** "Apply the ACMG criteria to this evidence profile. Reason step-by-step. Identify which criteria apply and why. Conclude with the 5-tier classification."

---

*Last Updated: March 8, 2026*
*END OF STAGE 0*