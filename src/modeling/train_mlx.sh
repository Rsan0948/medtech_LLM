#!/bin/bash
# ZDS-ID: TOOL-700 (Student Model Training Protocol)
# Starts MLX-LM LoRA fine-tuning for Genomic Variant Classification.

echo "--- STARTING ZDS MEDTECH DISTILLATION (Genomics v1.0) ---"

# Ensure directories exist
mkdir -p models/adapters/genomics_v1
mkdir -p logs/training

# Start training using MLX-LM
# Note: Ensure the 'mlx-lm' package is installed in your venv.
python -m mlx_lm.lora \
    --config config/training_config.yaml \
    --train \
    --seed 42 \
    2>&1 | tee logs/training/run_$(date +%Y%m%d_%H%M%S).log

echo "--- TRAINING COMPLETE ---"
echo "Adapters saved to models/adapters/genomics_v1"
