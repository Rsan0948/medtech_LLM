#!/usr/bin/env python3
"""
ZDS MedTech Genomic Variant Classification Pipeline
ZDS-ID: TOOL-700 (Orchestration Layer)

Usage:
  python run_pipeline.py --all               # Run full pipeline (stages 1-7)
  python run_pipeline.py --stage ingest      # Stage 1: ClinVar download
  python run_pipeline.py --stage filter      # Stage 2: CQF consensus filter
  python run_pipeline.py --stage prompts     # Stage 3: Generate R1 teacher prompts
  python run_pipeline.py --stage teacher     # Stage 4: R1 DeepSeek inference
  python run_pipeline.py --stage format      # Stage 5: Format MLX training data
  python run_pipeline.py --stage train       # Stage 6: MLX LoRA fine-tuning
  python run_pipeline.py --stage evaluate    # Stage 7: TBE evaluation report
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Ensure src is on the path for all stages
SRC_DIR = os.path.join(os.path.dirname(__file__), "src")
sys.path.insert(0, SRC_DIR)
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scripts")
sys.path.insert(0, SCRIPTS_DIR)


def stage_ingest():
    print("\n[Stage 1] ClinVar Ingestion")
    print("-" * 40)
    from ingestion.clinvar_ingestor import ClinVarIngestor

    ingestor = ClinVarIngestor(output_path="data/processed/variant_traces_raw.jsonl")
    ingestor.run()


def stage_filter():
    print("\n[Stage 2] Consensus Quality Filter (CQF)")
    print("-" * 40)
    from processing.consensus_filter import ConsensusFilter

    gate = ConsensusFilter(
        input_path="data/processed/variant_traces_raw.jsonl",
        output_path="data/processed/variant_traces_cqf_tier1.jsonl",
    )
    gate.run()


def stage_prompts():
    print("\n[Stage 3] Teacher Prompt Generation")
    print("-" * 40)
    # Reuse the existing generate_r1_prompts script
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "generate_r1_prompts", os.path.join(SCRIPTS_DIR, "generate_r1_prompts.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


def stage_teacher():
    print("\n[Stage 4] R1 Teacher Inference (DeepSeek API)")
    print("-" * 40)
    from modeling.r1_teacher import R1Teacher

    teacher = R1Teacher(
        prompts_path="data/app/teacher_prompts_1k.jsonl",
        output_path="data/app/teacher_responses.jsonl",
        max_workers=5,
    )
    teacher.run()


def stage_format():
    print("\n[Stage 5] Training Data Formatter")
    print("-" * 40)
    from modeling.training_data_formatter import TrainingDataFormatter

    formatter = TrainingDataFormatter(
        responses_path="data/app/teacher_responses.jsonl",
        output_dir="data/app/training_data",
    )
    formatter.run()


def stage_train():
    print("\n[Stage 6] MLX LoRA Fine-Tuning")
    print("-" * 40)
    # Validate the training config BEFORE launching (Pydantic schema).
    from schemas.training_config import load_and_validate

    try:
        load_and_validate("config/training_config.yaml")
        print("Config validation: OK")
    except Exception as e:
        print(f"ERROR: config/training_config.yaml failed validation: {e}")
        sys.exit(1)
    # NOTE: orchestration intentionally stays bash (train_mlx.sh wraps the
    # mlx_lm.lora CLI and tee's the log). Moving this into Python would only
    # re-implement the CLI's argument handling; keep the shell boundary thin.
    train_script = os.path.join(os.path.dirname(__file__), "src", "modeling", "train_mlx.sh")
    result = subprocess.run(["bash", train_script], cwd=os.path.dirname(os.path.abspath(__file__)))
    if result.returncode != 0:
        print(f"ERROR: Training script exited with code {result.returncode}")
        sys.exit(result.returncode)


def stage_check():
    """Preflight: credentials, config validity, and expected data dirs.

    Run this before --stage teacher (API spend) or --stage train (8h GPU).
    """
    print("\n[Preflight] Environment + Config Check")
    print("-" * 40)
    failures = 0

    # 1. DeepSeek API key (.env is loaded by r1_teacher; here we just verify)
    from dotenv import load_dotenv

    load_dotenv()
    if os.getenv("DEEPSEEK_API_KEY"):
        print("  OK   DEEPSEEK_API_KEY is set")
    else:
        print("  FAIL DEEPSEEK_API_KEY not set. Copy .env.example to .env and add your key.")
        failures += 1

    # 2. Training config validates
    from schemas.training_config import load_and_validate

    try:
        load_and_validate("config/training_config.yaml")
        print("  OK   config/training_config.yaml is valid")
    except Exception as e:
        print(f"  FAIL config/training_config.yaml: {e}")
        failures += 1

    # 3. Expected directories
    for d in ("data/raw", "data/app", "models/adapters", "logs"):
        if Path(d).exists():
            print(f"  OK   {d}/ exists")
        else:
            print(f"  WARN {d}/ missing (will be created on demand)")

    if failures:
        print(f"\nPreflight FAILED ({failures} problem(s)). Fix before spending API/GPU time.")
        sys.exit(1)
    print("\nPreflight passed.")


def stage_evaluate():
    print("\n[Stage 7] TBE Evaluation Report")
    print("-" * 40)
    results_path = "data/app/student_tbe_results.jsonl"
    if not Path(results_path).exists():
        print(f"Note: {results_path} not found.")
        print("To generate this file, run inference on your held-out test set and")
        print("write records with keys: verified_label, baseline_label, teacher_label,")
        print("student_label, student_confidence.")
        return
    from evaluation.tbe_metrics import TBEMetrics

    engine = TBEMetrics(results_path=results_path)
    engine.process_test_set()
    engine.report()


STAGES = {
    "check": stage_check,
    "ingest": stage_ingest,
    "filter": stage_filter,
    "prompts": stage_prompts,
    "teacher": stage_teacher,
    "format": stage_format,
    "train": stage_train,
    "evaluate": stage_evaluate,
}

FULL_PIPELINE = ["ingest", "filter", "prompts", "teacher", "format", "train", "evaluate"]


def main():
    parser = argparse.ArgumentParser(
        description="ZDS MedTech Genomic Variant Classification Pipeline"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Run the full pipeline (stages 1-7)")
    group.add_argument("--stage", choices=list(STAGES.keys()), help="Run a single pipeline stage")
    args = parser.parse_args()

    print("=" * 50)
    print("ZDS MedTech Distillation Pipeline")
    print("=" * 50)

    if args.all:
        for stage_name in FULL_PIPELINE:
            STAGES[stage_name]()
    else:
        STAGES[args.stage]()

    print("\nDone.")


if __name__ == "__main__":
    main()
