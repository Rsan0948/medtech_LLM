# MedTech Distillation — Results

> This file documents the dataset, training, and evaluation results for the MedTech genomic variant classification distillation pipeline.

## Dataset summary (v2, refined)

The v1 dataset audit found three problems, all fixed in v2 (`scripts/refine_training_data.py`):

1. **Teacher/ClinVar disagreement** — R1 agreed with the ClinVar verified label on only 75.3% of variants. Training on a reasoning trace that argues for a different label than the target JSON emits is contradictory signal. For the *train* split, only teacher responses that **agree with the ClinVar verified label** are kept (verifier-guided distillation, STaR-style).
2. **Label leakage** — stored teacher prompts embedded label-conditioned `acmg_criteria_hints` (e.g., "PS4 candidate" hints added only for pathogenic variants). All prompts are now rebuilt from the variant traces (whose hints are empty), so no label-derived signal remains.
3. **Duplicates / imbalance** — 20 duplicate trace_ids (5 with contradictory labels) deduped; rare classes oversampled to a floor of 40 (Benign 5→40, Likely Pathogenic 14→40).

Also fixed: prompt/response schema drift — the guidelines demanded a `predicted_classification` key while all targets and the inference parser use `classification`; guidelines and prompts now use `classification` consistently.

| Split | Count | Description |
|-------|-------|-------------|
| Raw ClinVar variants (10-gene panel) | ~2,000–5,000 | Germline variants from BRCA1, BRCA2, MLH1, MSH2, MSH6, PMS2, PALB2, ATM, CHEK2, TP53 |
| CQF Tier 1+2 (consensus / majority) | 1,000 | Variants with at least one-star ClinVar review status and no conflicting interpretations |
| Teacher responses | 975 (955 unique) | JSON reasoning traces from R1 |
| Train (v2, refined) | 715 | 654 ClinVar-agreeing examples + 61 oversampled rare-class copies (originals: `data/app/training_data_v1_backup/`) |
| Valid | 98 | Same trace IDs as v1 (temporal holdout), prompts rebuilt hint-free, unfiltered |
| True holdout | 45 | Tier-1 variants never distilled (no teacher response) — genuinely unseen |

## Teacher quality (DeepSeek R1)

| Metric | Value |
|--------|-------|
| Teacher accuracy vs verified | 69.39% (98-example validation split) — **below the rule baseline** |
| Teacher agreement with ClinVar (all 975) | 75.3% |
| Avg reasoning trace length | ~520 tokens |
| JSON parse success rate | 100% (after stripping `<think>` blocks) |

## Baseline (InterVar rule-based)

| Metric | Value |
|--------|-------|
| Baseline accuracy (valid) | 75.51% |
| Baseline accuracy (holdout) | 73.33% |

## Student (distilled Qwen3)

| Model | Adapter | Data | Overall accuracy | High-conf precision |
|-------|---------|------|------------------|---------------------|
| Qwen3-8B | `genomics_v1` (rank 16, 200 iters) | v1 (noisy, leaky) | 56.12% | 46.30% |
| Qwen3-8B | `genomics_v2` (rank 64, ckpt @ 200) | **v2 (refined)** | **89.80%** valid / **88.89%** holdout | **88.89%** valid / **94.74%** holdout |
| Qwen3-4B | `genomics_v2_4b` (rank 64, ckpt @ 400) | **v2 (refined)** | **86.73%** valid / **88.89%** holdout | **85.48%** valid / **100.00%** holdout |

### Qwen3-4B (edge variant) notes

- Same refined data, same recipe (`config/training_config_4b.yaml`; batch 4 × accum 4 after a Metal `Impacting Interactivity` kill under interactive load — smaller GPU bursts fixed it).
- Val-loss curve: 1.707 → 0.468 (50) → 0.464 (100) → 0.422 (150) → 0.428 (200) → 0.404 (250) → 0.392 (300) → **0.375 (350, best)** → 0.389 (400) → 0.398 (450, watchdog hard cap). Checkpoints exist at 200/400; shipped adapter = iter 400 (val 0.389, within noise of best).
- Peak training memory **23.7 GB** (vs 47.8 GB for 8B); ~88 tok/s (vs ~52).
- Pathogenic recall 23/23 on valid, 6/7 on holdout (1 P called VUS — conservative direction).
- Unlike the 8B, the 4B uses the `Medium` confidence tier for uncertain calls — a naturally better-calibrated behavior for edge triage.
- **Takeaway:** for edge/mobile deployment, the 4B gives up ~3 points on valid and *zero* on the true holdout at half the model size and ~2× inference speed.

### v2 validation-split detail (98 examples)

- Confusion matrix (rows = verified, cols = student):

|  | P | LP | VUS | LB | B |
|---|---|----|-----|----|---|
| **P**  | 23 | 0 | 0  | 0  | 0 |
| **LP** | 1  | 0 | 0  | 0  | 0 |
| **VUS**| 2  | 0 | 32 | 2  | 0 |
| **LB** | 0  | 0 | 3  | 32 | 1 |
| **B**  | 0  | 0 | 0  | 1  | 1 |

- Precision by confidence: High 88.89% (56/63), Low 91.43% (32/35). v1's degenerate "High on 55% of examples" over-confidence is gone; confidence now correlates with correctness.
- Pathogenic recall 23/23. Residual errors concentrate on the VUS ↔ Likely Benign boundary (expected — weakest evidence separation) and Likely-tier boundary calls.

### v2 true-holdout detail (45 never-distilled variants)

- Student **88.89%** vs baseline 73.33% — the gain generalizes to genuinely unseen variants, so it is not validation-split overfitting.
- Precision by confidence: High 94.74% (18/19), Low 84.62% (22/26).

## Training log

Run: `2026-08-26` → early-stopped `2026-08-27` (watchdog, `scripts/training_watchdog.py`)

| Hyperparameter | Value |
|----------------|-------|
| Model | Qwen3-8B-Instruct (local bf16) |
| LoRA rank / alpha / scale | 64 / 128 / 2.0 |
| LoRA dropout | 0.05 |
| LoRA layers | 32 |
| Iterations | 1000 configured, **early-stopped at ~360** (no val improvement for 3 evals) |
| Effective batch size | 16 (batch 8 × grad accum 2) |
| Learning rate | 2.0e-4, cosine → 1e-6, 100-step warmup |
| Max seq length | 2048 |
| Grad checkpoint | true |

Val-loss curve: 1.295 (init) → 0.412 (50) → 0.392 (100) → 0.384 (150) → **0.382 (200, best)** → 0.387 (250) → 0.404 (300) → 0.400 (350). Train loss kept falling to ~0.19 — classic overfitting onset after iter 200.

**Checkpoint selection:** best val loss at iter 200; `adapters.safetensors` == `0000200_adapters.safetensors` (md5-verified). Peak memory 47.8 GB.

```bash
bash src/modeling/train_mlx.sh                                  # 8B (config/training_config.yaml)
bash src/modeling/train_mlx.sh config/training_config_4b.yaml   # 4B edge variant
# evaluation (8B shown; 4B uses --model/--adapter/--output overrides)
PYTHONUNBUFFERED=1 .venv/bin/python -u scripts/generate_tbe_results.py            # valid split
PYTHONUNBUFFERED=1 .venv/bin/python -u scripts/generate_tbe_results.py --holdout  # 45-variant holdout
.venv/bin/python src/evaluation/tbe_metrics.py data/app/student_tbe_results.jsonl
.venv/bin/python src/evaluation/tbe_metrics.py data/app/student_tbe_results_holdout.jsonl
```

4B evaluation artifacts: `data/app/student_tbe_results_4b.jsonl` and `data/app/student_tbe_results_holdout_4b.jsonl`.

## Acceptance status

- [x] Student beats InterVar baseline (8B **89.80%**, 4B **86.73%** vs 75.51% valid; both **88.89%** vs 73.33% holdout)
- [ ] Student closes ≥ 40% of the R1 gap — **metric degenerate**: R1 (69.39%) is *below* the baseline (75.51%), so the pre-registered gap does not exist. Both students instead beat the baseline (+11.2/+14.3 pts) and the teacher (+17.3/+20.4 pts) outright.
- [x] High-confidence precision ≥ 85% (8B **88.89%** valid / **94.74%** holdout; 4B **85.48%** valid / **100.00%** holdout)
- [ ] Reasoning integrity ≥ 70% on manual review of 50 cases (**pending — community review bundle prepared**: `docs/REASONING_REVIEW.md`, 50 blind stratified cases + rubric; score returned verdicts with `scripts/score_reasoning_review.py`)

## Protocol caveats

- The pre-registered test protocol (`docs/TBE_ACCEPTANCE_CRITERIA.md`) calls for a 500-variant post-2024 holdout; only 1,000 variants exist locally, so evaluation used the 98-example temporal validation split plus the 45-variant never-distilled holdout. Full protocol compliance requires new ClinVar ingestion.
- Ground-truth labels are weak: 97% of variants are 1-star single-submitter ClinVar entries.
- v1 results (56.12%) were measured on the same 98 validation examples, but v1 prompts contained the label-leaking hints; v2 numbers are measured leak-free.

## Notes & lessons learned

- **Data quality >> training compute.** v1 → v2 gained +33.7 accuracy points, almost entirely from label refinement (ClinVar agreement filter), leakage removal, and dedup — not from the larger LoRA (rank 16→64) or more iterations (200 was still optimal).
- **Early stopping mattered.** Val loss bottomed at iter 200 of 1000; training to completion would have shipped an overfit adapter (train loss fell to 0.19 while val rose to 0.40).
- The student now exceeds its own teacher by 20 points — verifier-guided distillation (filter teacher traces by ground-truth agreement) lets the student learn only from correct reasoning.
- Remaining work: community reasoning-integrity review (criterion 4 — bundle ready in `docs/REASONING_REVIEW.md`), VUS ↔ Likely Benign boundary errors, and a larger post-2024 holdout via new ClinVar ingestion.
- The recipe transfers to smaller models unchanged: Qwen3-4B reaches 86.73%/88.89% with the same data and early stopping. For edge inference, note the trained JSON schema emits `"classification"` first — generation can be truncated after the first line for a near-instant label-only answer.
