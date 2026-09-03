"""
ZDS-ID: TOOL-700-SCHEMA (Training Config Validation)

Pydantic validation for config/training_config.yaml. Catches typos, wrong
types, and out-of-range values BEFORE an 8-hour training run starts, rather
than after. mlx-lm accepts many more keys than are modeled here, so extra
keys are allowed; this schema validates the keys THIS project relies on.

Usage:
  python -m schemas.training_config [path/to/training_config.yaml]
"""

import sys
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoraParameters(BaseModel):
    rank: int = Field(gt=0, le=256)
    alpha: int = Field(gt=0)
    dropout: float = Field(ge=0.0, lt=1.0)
    scale: float | None = Field(default=None, gt=0)


class TrainingConfig(BaseModel):
    # Allow mlx-lm keys we do not explicitly model (iters, lr_schedule, etc.)
    model_config = ConfigDict(extra="allow")

    # Required by our pipeline
    data: str
    model: str
    adapter_path: str

    # Optional but constrained when present
    lora_parameters: LoraParameters | None = None
    batch_size: int | None = Field(default=None, gt=0, le=64)
    gradient_accumulation_steps: int | None = Field(default=None, gt=0, le=128)
    learning_rate: float | None = Field(default=None, gt=0, lt=1.0)
    epochs: int | None = Field(default=None, gt=0, le=100)
    iters: int | None = Field(default=None, gt=0, le=100000)
    max_seq_length: int | None = Field(default=None, ge=128, le=32768)
    save_every: int | None = Field(default=None, gt=0)
    val_batches: int | None = Field(default=None, gt=0, le=1000)
    grad_checkpoint: bool | None = None
    mask_prompt: bool | None = None
    seed: int | None = None

    @field_validator("data", "adapter_path")
    @classmethod
    def _no_trailing_globs(cls, v: str) -> str:
        if "*" in v:
            raise ValueError("globs are not supported in data/adapter_path")
        return v


def load_and_validate(path: str | Path) -> TrainingConfig:
    """Load a YAML training config and validate it. Raises on any problem."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Training config not found: {p}")
    with open(p) as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"Training config {p} is not a YAML mapping")
    cfg = TrainingConfig(**raw)
    # Warn (not fail) on missing grad_checkpoint: at 7B+ on 64 GB unified
    # memory it is effectively required for seq >= 2048.
    if cfg.grad_checkpoint is not True:
        print(
            "WARNING: grad_checkpoint is not enabled in the training config. "
            "Runs at 7B+ / seq>=2048 on 64 GB unified memory are likely to OOM "
            "without it.",
            file=sys.stderr,
        )
    return cfg


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "config/training_config.yaml"
    load_and_validate(target)
    print(f"OK: {target} is valid")
