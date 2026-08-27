# MedTech LLM Distillation — Handoff Prompt

Use this prompt to continue optimizing the MedTech genomic variant-classification distillation project in a fresh conversation.

## Project basics

- **Working directory:** `~/Documents/Projects/medtech_LLM-EVICTED`
  - Note: the folder was renamed from `medtech_LLM` by an external event; all contents are intact. Renaming back would fix the `.venv` entry-point shebangs (they still point at the old path — use `.venv/bin/python -m <tool>` instead of `.venv/bin/<tool>`).
- **Virtual environment:** `.venv/` (Python 3.11.11)
- **Key packages:** `mlx==0.32.2`, `mlx-lm==0.31.3`, `transformers`, `pydantic==2.13.4`, `pytest`, `black`, `ruff`, `mypy`
- **Base model (local bf16):** `mlx-community/Qwen3-8B-bf16`
- **Task:** Distill a Qwen3-8B student that classifies germline variants (BRCA1/2, MLH1, MSH2, MSH6, PMS2, PALB2, ATM, CHEK2, TP53) using ACMG/AMP criteria, evaluated against ClinVar verified labels.

## Current status (2026-08-27): v2 complete — baseline and teacher beaten (8B + 4B)

**Qwen3-8B — Validation split (98):** **89.80%** | Baseline 75.51% | Teacher 69.39% | High-conf precision **88.89%**
**Qwen3-8B — True holdout (45):** **88.89%** | Baseline 73.33% | High-conf precision **94.74%**
**Qwen3-4B (edge) — Validation split (98):** **86.73%** | High-conf precision **85.48%**
**Qwen3-4B (edge) — True holdout (45):** **88.89%** | High-conf precision **100.00%**

Acceptance criteria: (1) student > baseline ✅ (both models), (2) R1 gap closure — degenerate (R1 < baseline, documented in RESULTS.md), (3) high-conf precision ≥ 85% ✅ (both models), (4) reasoning integrity ≥ 70% manual review — **community review bundle ready at `docs/REASONING_REVIEW.md`** (50 blind cases + rubric; score verdicts with `scripts/score_reasoning_review.py`).

## What changed in v2 (2026-08-26/27)

1. **Data repair** (`scripts/refine_training_data.py`): deduped 20 duplicate trace_ids; kept only teacher responses agreeing with the ClinVar verified label for train (654/857, verifier-guided distillation); rebuilt all prompts hint-free from traces (stored teacher prompts leaked label-conditioned `acmg_criteria_hints`); oversampled rare classes to 40 (Benign 5→40, Likely Pathogenic 14→40). Result: 715 train / 98 valid. Originals backed up at `data/app/training_data_v1_backup/`.
2. **Schema drift fix**: guidelines demanded `predicted_classification`; everything else uses `classification`. Fixed in `docs/ACMG_GUIDELINES_V1.txt`.
3. **Training**: rank 64 / alpha 128 / 32 layers, batch 8 × accum 2, cosine 2e-4→1e-6 warmup 100, `steps_per_eval: 50`. Configured 1000 iters, **early-stopped at ~360** by `scripts/training_watchdog.py` (patience 3, val loss rose after iter 200). Best checkpoint = iter 200 (val loss 0.382); `models/adapters/genomics_v2/adapters.safetensors` is that checkpoint (md5-verified).
4. **Eval upgrades**: `tbe_metrics.py` now reports per-confidence-level precision + 5×5 confusion matrix, accepts a results-file CLI arg, handles missing teacher labels. `generate_tbe_results.py` gained `--holdout` mode for the 45 never-distilled variants.
5. Full details in `docs/RESULTS.md`.

## What changed in v2.1 (2026-08-27, 4B edge variant)

1. **Qwen3-4B trained with the same recipe** (`config/training_config_4b.yaml`, adapter `models/adapters/genomics_v2_4b`). Val loss bottomed at iter 350 (0.375); watchdog stopped at the 450 hard cap; shipped adapter = iter-400 checkpoint.
2. **Metal crash workaround**: first 4B run died with `kIOGPUCommandBufferCallbackErrorImpactingInteractivity` while the machine was in interactive use. Fix: batch 8→4 / accum 2→4 (same effective batch 16) — smaller GPU command buffers. Peak mem 23.7 GB, ~88 tok/s.
3. **`train_mlx.sh` accepts a config path arg**; `generate_tbe_results.py` gained `--model/--adapter/--output` flags.
4. **Community review bundle** (`scripts/build_review_bundle.py` → `docs/REASONING_REVIEW.md` + `data/app/reasoning_review_sample.json`) and scorer (`scripts/score_reasoning_review.py`).

## Data

- Raw traces: `data/processed/variant_traces_raw.jsonl`
- CQF-filtered tier 1+2: `data/processed/variant_traces_cqf_tier1.jsonl` (1,000 records)
- Teacher responses: `data/app/teacher_responses.jsonl` (975 records, 955 unique)
- Training chat data (v2 refined): `data/app/training_data/train.jsonl` (715), `valid.jsonl` (98)
- Eval results: `data/app/student_tbe_results.jsonl` (98, 8B valid), `student_tbe_results_holdout.jsonl` (45, 8B), `student_tbe_results_4b.jsonl` (98, 4B), `student_tbe_results_holdout_4b.jsonl` (45, 4B)

## Architecture / code layout

- Pipeline orchestrator: `run_pipeline.py`
- Training script: `src/modeling/train_mlx.sh` (config: `config/training_config.yaml`)
- Data refinement: `scripts/refine_training_data.py`
- Early-stopping watchdog: `scripts/training_watchdog.py`
- Local inference: `src/serving/variant_inference.py`
- Evaluation: `src/evaluation/tbe_metrics.py`, generator `scripts/generate_tbe_results.py [--holdout]`
- Results doc: `docs/RESULTS.md`

## Critical implementation notes

- `mlx-lm` LoRA invocation: `python -m mlx_lm lora --config <yaml>`; expects `train: true` in YAML.
- `.venv` console scripts (black/mypy/pytest binaries) have broken shebangs from the folder rename — always use `.venv/bin/python -m <tool>`.
- `mask_prompt: true` trains only on assistant responses.
- `make train` fails (`python: command not found`) — use `bash src/modeling/train_mlx.sh`.

## Remaining work / next steps

1. **Reasoning-integrity review** (acceptance criterion 4): share `docs/REASONING_REVIEW.md` with clinical-genomics folks (LinkedIn/HuggingFace); when verdicts come back as a text file (`1: PASS`, `2: FAIL (note)`, ...), run `.venv/bin/python scripts/score_reasoning_review.py verdicts.txt`.
2. **Residual errors**: VUS ↔ Likely Benign boundary (see confusion matrices in RESULTS.md). Options: more training data near the boundary, better gnomAD/feature coverage (CADD/SIFT/REVEL are mostly null).
3. **Protocol gap**: pre-registered test = 500 post-2024 variants; only 1,000 variants exist locally. New ClinVar ingestion needed for full compliance.
4. If retraining: 8B optimum was iter 200, 4B was ~350 (early stop with patience ~3 evals); bigger LoRA/more iters overfit. For edge inference, the trained JSON schema emits `"classification"` first — truncate generation after the first line for a label-only answer. Consider Qwen3-14B only with new data.

## Quick commands

```bash
cd ~/Documents/Projects/medtech_LLM-EVICTED

# Regenerate refined training data (idempotent; backup already exists)
.venv/bin/python scripts/refine_training_data.py

# Train (watchdog recommended for early stopping)
bash src/modeling/train_mlx.sh &
.venv/bin/python -u scripts/training_watchdog.py &

# Evaluate
PYTHONUNBUFFERED=1 .venv/bin/python -u scripts/generate_tbe_results.py
PYTHONUNBUFFERED=1 .venv/bin/python -u scripts/generate_tbe_results.py --holdout
.venv/bin/python src/evaluation/tbe_metrics.py data/app/student_tbe_results.jsonl
.venv/bin/python src/evaluation/tbe_metrics.py data/app/student_tbe_results_holdout.jsonl

# Lint / test (venv shebangs are broken — use python -m)
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m black --fast . && .venv/bin/python -m ruff check . && .venv/bin/python -m mypy src/
```
