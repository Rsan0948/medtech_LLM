# MedTech Genomic Variant Classification - Distillation Pipeline

> **A privacy-first, auditable reasoning system for ACMG/AMP genomic variant classification.**  
> This project distills reasoning from a large teacher model (DeepSeek R1) into a small, local student model (Qwen3 via MLX LoRA) so variant classification can run on-device in clinical or research environments.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MLX](https://img.shields.io/badge/MLX-Apple_Silicon-orange.svg)](https://github.com/ml-explore/mlx)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## What this is

Clinical genomic interpretation is the bottleneck in precision medicine. Every detected variant must be classified into one of five ACMG tiers - from Pathogenic to Benign - using the 2015 ACMG/AMP guidelines. Today that work is largely manual and expensive.

This repository documents an end-to-end **reasoning distillation** pipeline that:

1. Pulls variant records from NCBI ClinVar for a focused hereditary-cancer gene panel.
2. Filters for high-confidence, expert-consensus classifications.
3. Prompts DeepSeek R1 to produce step-by-step ACMG reasoning traces.
4. Formats those traces into MLX-LM chat-format training data.
5. Fine-tunes a local Qwen3 model with LoRA adapters.
6. Evaluates the student against both a deterministic baseline and the teacher ceiling.
7. Serves the model locally so genomic data never leaves the machine.

---

## Results snapshot

Both students beat the InterVar-style rule baseline **and** their own DeepSeek-R1 teacher on held-out ClinVar labels, with calibrated high-confidence precision:

| Model | Valid (98) | True holdout (45) | High-conf precision (valid / holdout) |
|-------|-----------|-------------------|---------------------------------------|
| InterVar rule baseline | 75.51% | 73.33% | n/a |
| Logistic regression (classical ML) | 77.55% | 71.11% | n/a |
| Gradient boosting (classical ML) | 81.63% | 73.33% | n/a |
| DeepSeek R1 teacher | 69.39% | n/a | n/a |
| **Qwen3-8B student** (`genomics_v2`) | **89.80%** | **88.89%** | **88.89%** / **94.74%** |
| **Qwen3-4B student** (`genomics_v2_4b`, edge variant) | **86.73%** | **88.89%** | **85.48%** / **100.00%** |

Key findings (full analysis in [`docs/RESULTS.md`](docs/RESULTS.md)):

- **Data quality beat compute.** The jump from 56% → 90% came from label refinement (keeping only teacher traces that agree with ClinVar ground truth - verifier-guided distillation), removing label leakage from prompts, and deduplication - not from bigger adapters or longer training.
- **The students exceed their teacher by ~17–20 points** - they only ever trained on *correct* reasoning.
- **Early stopping mattered.** Validation loss bottomed at iteration 200 (8B) / ~350 (4B) of a 1000-iter schedule; an automated watchdog stopped training.
- **Pathogenic recall 23/23** on the validation split (both models) - zero missed pathogenic variants. The gradient-boosting baseline misses 4 of 23 (82.6% recall).
- **Stronger baselines, same conclusion.** Classical ML (gradient boosting on prompt-visible features: gene, variant type, gnomAD AF, HGVS consequence flags) reaches 81.63% valid / 73.33% holdout - both students still beat it by +5.1 to +8.2 points valid and +15.6 holdout (`scripts/classical_baseline.py`).

> Adapter weights are not committed to git (`models/` is ignored); reproduce them with the training commands below.

---

## Repository layout

```
medtech_LLM/
├── config/
│   ├── training_config.yaml          # MLX-LM LoRA hyperparameters (Qwen3-8B)
│   └── training_config_4b.yaml       # Edge variant (Qwen3-4B)
├── data/                             # NOT committed (regenerate via pipeline)
├── demo/
│   └── streamlit_app.py              # Local interactive classifier demo
├── docs/
│   ├── ACMG_GUIDELINES_V1.txt        # Prompt-injected guideline summary
│   ├── ARCHITECTURE_GENOMICS.md      # System architecture
│   ├── RESULTS.md                    # Full v2 evaluation results + analysis
│   ├── REASONING_REVIEW.md           # Community review bundle (50 blind cases)
│   ├── TBE_ACCEPTANCE_CRITERIA.md    # Pre-registered success criteria
│   └── ZDS_QUALIFICATION.md          # Domain qualification checklist
├── scripts/
│   ├── generate_r1_prompts.py        # Stage 3 prompt generator
│   ├── refine_training_data.py       # Data repair (dedupe, ClinVar filter, de-leak)
│   ├── training_watchdog.py          # Early-stopping monitor for training runs
│   ├── generate_tbe_results.py       # Eval-set inference (valid + --holdout)
│   ├── build_review_bundle.py        # Samples cases → docs/REASONING_REVIEW.md
│   ├── score_reasoning_review.py     # Scores community verdicts vs 70% criterion
│   └── preflight_check.py            # Environment sanity checks
├── src/
│   ├── ingestion/
│   │   ├── clinvar_ingestor.py       # NCBI E-utilities downloader
│   │   └── gnomad_enricher.py        # Optional gnomAD frequency enrichment
│   ├── processing/
│   │   └── consensus_filter.py       # CQF tier assignment
│   ├── modeling/
│   │   ├── prompt_factory.py         # ACMG prompt builder
│   │   ├── r1_teacher.py             # DeepSeek R1 concurrent caller
│   │   ├── training_data_formatter.py# MLX chat-format converter
│   │   └── train_mlx.sh              # MLX-LM training launcher (config arg)
│   ├── evaluation/
│   │   └── tbe_metrics.py            # Triadic benchmark evaluator + confusion matrix
│   └── serving/
│       └── variant_inference.py      # Local MLX inference engine
├── tests/                            # pytest suite
├── .github/workflows/
│   └── ci.yml                        # Lint + test CI
├── Makefile                          # Common tasks
├── pyproject.toml                    # Dependencies + tooling
├── run_pipeline.py                   # 7-stage orchestrator
└── README.md                         # You are here
```

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/Rsan0948/medtech_LLM.git
cd medtech_LLM
python -m venv .venv
source .venv/bin/activate
make install-all
```

### 2. Configure secrets (only for regenerating teacher traces)

```bash
cp .env.example .env
# Edit .env and add your DeepSeek API key
```

> **Note:** the dataset (`data/`) and adapter weights (`models/`) are not committed
> to git. Stages 1–5 regenerate the data (stage 4 needs a DeepSeek API key);
> training reproduces the adapters. Base models download automatically from
> HuggingFace (`mlx-community/Qwen3-8B-bf16` / `Qwen3-4B-bf16`).

### 3. Run the pipeline

```bash
# Stages 1-5: data → prompts → teacher responses → training splits
python run_pipeline.py --all

# Stage 5b: data refinement (dedupe, ClinVar-agreement filter, leak-free prompts)
python scripts/refine_training_data.py

# Stage 6: LoRA fine-tuning (Apple Silicon; hours)
bash src/modeling/train_mlx.sh                            # Qwen3-8B
bash src/modeling/train_mlx.sh config/training_config_4b.yaml  # Qwen3-4B (edge)

# Optional: early-stopping watchdog alongside training
python scripts/training_watchdog.py &

# Stage 7: evaluation
python scripts/generate_tbe_results.py             # validation split
python scripts/generate_tbe_results.py --holdout   # never-distilled holdout
python src/evaluation/tbe_metrics.py data/app/student_tbe_results.jsonl
```

Shortcut commands via `Makefile`:

```bash
make data          # Run stages 1-5
make train         # Run MLX LoRA fine-tuning
make evaluate      # Run TBE evaluation
make demo          # Launch Streamlit demo
make test          # Run pytest suite
```

---

## The 7-stage pipeline

| # | Stage | Script | What it does |
|---|-------|--------|--------------|
| 1 | Ingest | `src/ingestion/clinvar_ingestor.py` | Downloads ClinVar germline variants for BRCA1, BRCA2, MLH1, MSH2, MSH6, PMS2, PALB2, ATM, CHEK2, TP53. |
| 2 | Filter | `src/processing/consensus_filter.py` | Keeps Tier 1 (2+ stars) and Tier 2 (1 star) consensus classifications; rejects conflicts. |
| 3 | Prompts | `scripts/generate_r1_prompts.py` | Builds structured ACMG prompts from variant traces. |
| 4 | Teacher | `src/modeling/r1_teacher.py` | Calls DeepSeek R1 concurrently with retries, resume-on-failure, and quality analysis. |
| 5 | Format | `src/modeling/training_data_formatter.py` | Converts R1 responses into MLX-LM chat-format `train.jsonl` / `valid.jsonl`. |
| 6 | Train | `src/modeling/train_mlx.sh` | Runs LoRA fine-tuning via `mlx_lm.lora`. |
| 7 | Evaluate | `src/evaluation/tbe_metrics.py` | Computes accuracy vs verified label, baseline (InterVar), teacher (R1), and high-confidence precision. |

---

## Key design decisions

- **Privacy-first.** The student model and inference engine run locally via MLX. Genomic data never leaves the host.
- **Auditable reasoning.** Every output includes a `reasoning_trace` and `triggered_criteria`, satisfying clinical decision-support explainability requirements.
- **Verified outcomes.** Training examples are anchored to ClinVar expert consensus (2+ stars), not model guesses.
- **Temporal split.** Validation uses the most recent 10% of records so the evaluation mirrors real-world forward prediction.
- **Small-data distillation.** The current dataset is intentionally compact (~975 examples), demonstrating that structured reasoning distillation can work in low-resource medical domains.

---

## Training configuration

v2 configuration (what produced the results above):

- **Base:** Qwen3-8B / Qwen3-4B (MLX bf16, pulled from HuggingFace)
- **Method:** LoRA (rank 64, alpha 128, dropout 0.05, 32 layers)
- **Schedule:** up to 1000 iterations with cosine LR 2e-4 → 1e-6 and 100-step warmup, **early-stopped** by validation loss (best: iter 200 for 8B, ~350 for 4B)
- **Batch:** effective 16 (batch 8 × grad accum 2 for 8B; batch 4 × 4 for 4B)
- **Efficiency:** prompt masking (loss on assistant responses only), gradient checkpointing
- **Peak memory:** 47.8 GB (8B) / 23.7 GB (4B)
- **Adapter paths:** `models/adapters/genomics_v2`, `models/adapters/genomics_v2_4b`

See [`config/training_config.yaml`](config/training_config.yaml) and [`config/training_config_4b.yaml`](config/training_config_4b.yaml) for full details.

---

## Evaluation criteria (TBE)

A distillation run is considered successful when the student:

1. ✅ **Beats the floor:** Outperforms the InterVar rule-based baseline. (8B 89.80% vs 75.51%; 4B 86.73%)
2. ⚠️ **Closes the gap:** ≥ 40% of the InterVar→R1 improvement. *Degenerate here* - R1 scored below the baseline, so the pre-registered gap does not exist; both students beat baseline and teacher outright.
3. ✅ **High-confidence precision:** ≥ 85% when the student reports `High` confidence. (88.89–100%)
4. ⏳ **Reasoning integrity:** ≥ 70% on a 50-case manual review. **Community review in progress** - see [`docs/REASONING_REVIEW.md`](docs/REASONING_REVIEW.md).

Full criteria: [`docs/TBE_ACCEPTANCE_CRITERIA.md`](docs/TBE_ACCEPTANCE_CRITERIA.md)

---

## Community reasoning review

The last open acceptance criterion is a human audit of the student's clinical
reasoning. If you have clinical-genomics expertise, the review bundle
([`docs/REASONING_REVIEW.md`](docs/REASONING_REVIEW.md)) contains 50 blind,
stratified cases with a 4-point rubric - no setup required. Verdicts are scored
with `scripts/score_reasoning_review.py`. Contributions welcome via issue or PR.

---

## Demo

Launch a local Streamlit interface to classify variants with the trained model:

```bash
make demo
```

The demo lets you paste a variant profile (gene, HGVS, evidence) and returns the classification plus reasoning trace - all running locally.

---

## Testing

```bash
make test
```

The test suite covers schema validation, consensus filtering, prompt generation, training-data formatting, and JSON extraction from model outputs. CI runs on every push via GitHub Actions.

---

## Hardware requirements

- **Training:** Apple Silicon Mac (M1/M2/M3/M4) with ≥ 16 GB unified memory. The default config targets a 64 GB Mac Studio but a 7B QLoRA-style run works on smaller machines.
- **Inference:** Any Apple Silicon Mac. The 7B base + LoRA adapter loads locally through MLX.
- **Teacher generation:** Requires a DeepSeek API key and internet access.

---

## Limitations & disclaimers

- **Research prototype.** Not cleared for clinical diagnostic use without validation against local standards and regulatory review.
- **Focused scope.** Trained on a 10-gene hereditary cancer panel. Generalization to other genes or variant types is not guaranteed.
- **Small dataset.** The refined training split is 715 examples (from ~975 teacher responses after agreement filtering). This is sufficient to demonstrate low-data distillation but would need scaling for production deployment.
- **Gene coverage.** Despite the 10-gene panel design, the filtered dataset is ~99% BRCA1/BRCA2; other genes need more ingestion.
- **Weak ground truth.** 97% of verified labels are 1-star single-submitter ClinVar entries; accuracy is measured against them as a proxy.
- **No gnomAD enrichment in default path.** The base ClinVar ingestor captures review status and submissions; optional gnomAD enrichment is provided via `src/ingestion/gnomad_enricher.py`.

---

## Roadmap

- [x] Build end-to-end pipeline
- [x] Generate teacher reasoning traces
- [x] Format training / validation splits
- [x] Data-quality repair (ClinVar-agreement filter, leakage removal, dedup)
- [x] Run LoRA fine-tuning with early stopping (8B + 4B edge variant)
- [x] Evaluate and record TBE metrics in `docs/RESULTS.md`
- [ ] Complete community reasoning-integrity review (`docs/REASONING_REVIEW.md`)
- [ ] Publish adapters + refined dataset to HuggingFace
- [ ] Expand to a 500-variant post-2024 holdout via new ClinVar ingestion
- [ ] Integrate optional gnomAD enrichment into default pipeline
- [ ] Expand gene panel beyond hereditary cancer (current data is ~99% BRCA1/2)

---

## Author

Built by **Ruben Sanchez** as a portfolio demonstration of domain-specific reasoning distillation for clinical genomics.

- GitHub: [@Rsan0948](https://github.com/Rsan0948)
- Project: [medtech_LLM](https://github.com/Rsan0948/medtech_LLM)

---

## License

MIT - see [`LICENSE`](LICENSE). The base models (Qwen3, Apache-2.0) and teacher
(DeepSeek-R1, MIT) licenses permit this use, including distillation. The
clinical disclaimer in `LICENSE` applies: research prototype, not for
diagnostic use without validation and regulatory review.
