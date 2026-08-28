#!/bin/bash
set -euo pipefail

# MedTech Genomics v1.0 - MLX-LM LoRA fine-tuning launcher
# Uses the local Qwen3-8B model and the YAML config in config/training_config.yaml

CONFIG="${1:-config/training_config.yaml}"

if [[ ! -f "$CONFIG" ]]; then
    echo "ERROR: Config file not found: $CONFIG"
    exit 1
fi

echo "--- STARTING MEDTECH DISTILLATION (Genomics v1.0) ---"
echo "Config: $CONFIG"

# Ensure adapter/log directories exist
mkdir -p "$(dirname "$(grep -E '^adapter_path:' "$CONFIG" | sed 's/.*"\(.*\)"/\1/')")"
mkdir -p logs/training

# Use the project venv Python explicitly so this works whether or not
# the caller has activated the virtual environment.
PYTHON=".venv/bin/python"

if [[ ! -f "$PYTHON" ]]; then
    echo "ERROR: Project venv not found at $PYTHON"
    echo "Run: make install-all   or   python3.11 -m venv .venv && pip install -e '.[all]'"
    exit 1
fi

# Start training using MLX-LM and the YAML config.
# Command-line flags override YAML values if you need to experiment.
"$PYTHON" -m mlx_lm lora \
    --config "$CONFIG" \
    2>&1 | tee "logs/training/run_$(date +%Y%m%d_%H%M%S).log"

echo "--- TRAINING COMPLETE ---"
echo "Adapters saved per config: $CONFIG"
