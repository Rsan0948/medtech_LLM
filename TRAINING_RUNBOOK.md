# MedTech Training Runbook

> Quick reference for running the LoRA fine-tuning tonight.

## 1. Before you start

### Required
- [ ] Apple Silicon Mac with ≥ 32 GB unified memory (64 GB recommended)
- [ ] Stable power / plugged in
- [ ] Local Qwen3-8B model exists at `mlx-community/Qwen3-8B-bf16`
- [ ] `.venv` is set up and dependencies installed (`make install-all`)
- [ ] Training data exists: `data/app/training_data/train.jsonl` and `valid.jsonl`

### Optional but recommended
- [ ] DeepSeek API key in `.env` (only needed if you regenerate teacher traces)
- [ ] Several hours of uninterrupted runtime

## 2. Activate environment

```bash
cd ~/Documents/Projects/medtech_LLM
source .venv/bin/activate
```

Verify MLX and the local model load:

```bash
python -c "from mlx_lm import load; m, t = load('mlx-community/Qwen3-8B-bf16'); print('Model + tokenizer OK')"
```

## 3. Start training

```bash
make train
```

This reads `config/training_config.yaml` and runs:

```bash
python -m mlx_lm.lora --config config/training_config.yaml
```

Current config defaults:

- **Base model:** `mlx-community/Qwen3-8B-bf16` (local Qwen3 8B)
- **LoRA:** rank 16, scale 2.0 (equivalent to alpha 32), dropout 0.05
- **Training:** 200 iterations ≈ 3.6 epochs on 877 examples
- **Batch:** 4 (effective 16 with gradient accumulation)
- **LR:** 2e-4 cosine with warmup
- **Efficiency:** `mask_prompt: true` (loss only on assistant responses)

To use a different local model, edit `config/training_config.yaml`:

```yaml
model: "/path/to/your/Qwen3-14B"
```

## 4. Monitor progress

Training logs are written to:

```
logs/training/run_YYYYMMDD_HHMMSS.log
```

Watch training loss, validation loss, tokens/sec, and peak memory.

Typical runtime for this config on Apple Silicon:

- Qwen3 8B on M1 Max/Pro 64 GB: ~1–2 hours
- Qwen3 14B on M2/M3 Max/Ultra: ~3–6 hours

## 5. After training completes

### Generate test predictions

You need a held-out test set. Create `data/app/mma_test.jsonl` or reuse `data/app/training_data/valid.jsonl` as an initial sanity check.

Run inference with the local model:

```bash
python src/serving/variant_inference.py
```

### Evaluate

Produce a `data/app/student_tbe_results.jsonl` file with records like:

```json
{
  "verified_label": "Pathogenic",
  "baseline_label": "Likely Pathogenic",
  "teacher_label": "Pathogenic",
  "student_label": "Pathogenic",
  "student_confidence": "High"
}
```

Then run:

```bash
make evaluate
```

## 6. Record results

Paste the numbers into:

- `docs/RESULTS.md`
- `README.md` results table

## 7. Common issues

### `mlx_lm` not found

```bash
source .venv/bin/activate
pip install -e ".[mlx]"
```

### Local model path not found

Verify the model directory contains `config.json`, `tokenizer.json`, and `model-*.safetensors`:

```bash
ls mlx-community/Qwen3-8B-bf16
```

If you want to use a HuggingFace repo instead, change `model:` in `config/training_config.yaml` to the HF ID (e.g., `Qwen/Qwen3-8B`).

### Out of memory

Option A - enable gradient checkpointing (slower but less RAM):

```yaml
grad_checkpoint: true
```

Option B - reduce batch size or effective batch size:

```yaml
batch_size: 2
gradient_accumulation_steps: 8  # still effective batch 16
```

Option C - use a 4-bit quantized base model (QLoRA). This requires converting the model first:

```bash
python -m mlx_lm.convert \
    --model mlx-community/Qwen3-8B-bf16 \
    -q \
    --q-bits 4 \
    --upload-repo "" \
    --output-dir models/qwen3-8b-4bit
```

Then point `model:` in the config to `models/qwen3-8b-4bit`.

### Adapter path does not exist

Training creates `models/adapters/genomics_v1/` automatically. If inference can't find it, verify the path in `src/serving/variant_inference.py` or the Streamlit demo sidebar.

## 8. Next morning

- Commit `logs/training/` summaries (not full logs if they are huge).
- Update `docs/RESULTS.md` with final metrics.
- Push to GitHub if ready to publish.
