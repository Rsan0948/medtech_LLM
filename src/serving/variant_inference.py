import json
import os
import re
import sys
from typing import Any, cast

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mlx_lm import generate, load

from modeling.prompt_factory import PromptFactory
from schemas.variant_trace_v1 import VariantTrace

GUIDELINES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "ACMG_GUIDELINES_V1.txt"
)
MAX_TOKENS = 1024


class VariantInference:
    """
    ZDS-ID: TOOL-303 (Local-First Privacy & Retrieval Stack)
    Serves local variant classification reasoning on-premise via MLX.
    Genomic data never leaves the machine.
    """

    def __init__(self, model_path: str, adapter_path: str | None = None):
        self.model_path = model_path
        self.adapter_path = adapter_path
        self.model, self.tokenizer = load(model_path, adapter_path=adapter_path)  # type: ignore[misc]
        self.prompt_factory = PromptFactory(guidelines_path=os.path.abspath(GUIDELINES_PATH))
        print(f"Loaded local MedTech model: {model_path}")
        if adapter_path:
            print(f"Applied LoRA adapters: {adapter_path}")

    def classify(self, variant_json: str) -> dict[str, Any]:
        """
        Takes a JSON string of variant fields and returns ACMG classification + reasoning.

        Args:
            variant_json: JSON string conforming to VariantTrace schema (identity + evidence fields).

        Returns:
            Dict with keys: classification, triggered_criteria,
                            reasoning_trace, confidence, privacy_status.
        """
        # Parse and validate input
        data = json.loads(variant_json)
        trace = VariantTrace(**data)

        # Build prompt
        prompt_text = self.prompt_factory.create_prompt(trace)

        # Apply chat template
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a clinical genomics specialist. Respond only with valid JSON "
                    "containing keys: classification, triggered_criteria, reasoning_trace, confidence."
                ),
            },
            {"role": "user", "content": prompt_text},
        ]
        formatted = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        # Generate with MLX
        raw_output = generate(
            self.model,
            self.tokenizer,
            prompt=formatted,
            max_tokens=MAX_TOKENS,
            verbose=False,
        )

        # Parse JSON response
        try:
            # Strip Qwen3 reasoning tags and any markdown code fences
            clean = raw_output.strip()
            clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.DOTALL).strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            result = cast(dict[str, Any], json.loads(clean.strip()))
        except json.JSONDecodeError:
            result = {
                "classification": "Variant of Uncertain Significance",
                "triggered_criteria": [],
                "reasoning_trace": raw_output,
                "confidence": "Low",
            }

        result["privacy_status"] = "Secure - On-Premise Execution"
        return result


if __name__ == "__main__":
    engine = VariantInference(
        model_path="mlx-community/Qwen3-8B-bf16",
        adapter_path="models/adapters/genomics_v1",
    )
    sample = {
        "trace_id": "test-001",
        "identity": {
            "clinvar_id": "12345",
            "gene_symbol": "BRCA1",
            "hgvs_c": "c.5266dupC",
            "hgvs_p": "p.Gln1756ProfsTer74",
            "chromosome": "17",
            "position": 41246652,
            "reference_allele": "C",
            "alternate_allele": "CC",
            "variant_type": "Duplication",
        },
        "evidence": {"prev_submissions_count": 10},
        "verified_outcome": {
            "classification": "Pathogenic",
            "review_status": "criteria provided, multiple submitters, no conflicts",
            "gold_stars": 2,
        },
    }
    result = engine.classify(json.dumps(sample))
    print(json.dumps(result, indent=2))
