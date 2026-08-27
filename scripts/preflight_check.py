#!/usr/bin/env python3
"""
Preflight check for the MedTech distillation training run.

Verifies:
- Python environment and key dependencies
- Training data files exist and are non-empty
- Config file is present and parseable
- Adapter output directory can be created
- MLX is available (Apple Silicon)
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def check(condition: bool, message: str) -> bool:
    status = "✅" if condition else "❌"
    print(f"{status} {message}")
    return condition


def main() -> int:
    print("=" * 60)
    print("MedTech Training Preflight Check")
    print("=" * 60)

    all_ok = True

    # 1. Python version
    version = sys.version_info
    all_ok &= check(
        version.major == 3 and version.minor >= 10,
        f"Python {version.major}.{version.minor}.{version.micro} (>= 3.10 required)",
    )

    # 2. Key imports
    try:
        import pydantic

        all_ok &= check(True, f"pydantic {pydantic.__version__}")
    except ImportError:
        all_ok &= check(False, "pydantic not installed")

    try:
        import mlx
        import mlx_lm  # noqa: F401  (import = availability check)

        version = getattr(mlx, "__version__", "unknown")
        all_ok &= check(True, f"mlx {version}, mlx_lm available")
    except ImportError:
        all_ok &= check(False, "mlx / mlx_lm not installed (run: make install-all)")

    # 3. Training data
    train_path = PROJECT_ROOT / "data" / "app" / "training_data" / "train.jsonl"
    valid_path = PROJECT_ROOT / "data" / "app" / "training_data" / "valid.jsonl"

    all_ok &= check(train_path.exists(), f"Training data exists: {train_path}")
    all_ok &= check(valid_path.exists(), f"Validation data exists: {valid_path}")

    if train_path.exists():
        with open(train_path) as f:
            train_count = sum(1 for _ in f)
        all_ok &= check(train_count > 0, f"Training examples: {train_count}")

    if valid_path.exists():
        with open(valid_path) as f:
            valid_count = sum(1 for _ in f)
        all_ok &= check(valid_count > 0, f"Validation examples: {valid_count}")

    # 4. Config
    config_path = PROJECT_ROOT / "config" / "training_config.yaml"
    all_ok &= check(config_path.exists(), f"Training config exists: {config_path}")

    if config_path.exists():
        try:
            import yaml

            with open(config_path) as f:
                cfg = yaml.safe_load(f)
            all_ok &= check(
                "data" in cfg and "model" in cfg and "adapter_path" in cfg,
                "Config has required keys: data, model, adapter_path",
            )
        except ImportError:
            all_ok &= check(False, "PyYAML not installed (needed to parse config)")
        except Exception as e:
            all_ok &= check(False, f"Failed to parse config: {e}")

    # 5. Adapter output directory
    adapter_dir = PROJECT_ROOT / "models" / "adapters" / "genomics_v1"
    try:
        adapter_dir.mkdir(parents=True, exist_ok=True)
        all_ok &= check(True, f"Adapter output directory ready: {adapter_dir}")
    except Exception as e:
        all_ok &= check(False, f"Cannot create adapter directory: {e}")

    # 6. Disk space (rough check)
    stat = os.statvfs(PROJECT_ROOT)
    free_gb = stat.f_bavail * stat.f_frsize / (1024**3)
    all_ok &= check(free_gb >= 20, f"Free disk space: {free_gb:.1f} GB (≥ 20 GB recommended)")

    # 7. DeepSeek API key (optional for training, required only for regenerating traces)
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    has_key = bool(deepseek_key and deepseek_key != "your_key_here")
    check(
        has_key,
        "DEEPSEEK_API_KEY set (only needed to regenerate teacher traces)",
    )

    print("=" * 60)
    if all_ok:
        print("🚀 Ready for training. Run: make train")
        return 0
    else:
        print("⚠️  Some checks failed. Fix the issues above before training.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
