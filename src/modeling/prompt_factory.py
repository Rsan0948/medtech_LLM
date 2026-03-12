import json
from pathlib import Path
from schemas.variant_trace_v1 import VariantTrace

class PromptFactory:
    """
    ZDS-ID: TOOL-801 (RichSpec Prompting Strategy)
    Assembles a high-fidelity distillation prompt for the Teacher model.
    """
    
    def __init__(self, guidelines_path: str):
        with open(guidelines_path, 'r') as f:
            self.guidelines = f.read()

    def create_prompt(self, trace: VariantTrace) -> str:
        """
        Combines the Variant Trace with the ACMG Guidelines for R1 reasoning.
        """
        identity = trace.identity
        evidence = trace.evidence
        
        prompt = f"""
{self.guidelines}

---
VARIANT DATA FOR ANALYSIS (ZDS-ID: {trace.trace_id})
---
IDENTITY:
- Gene: {identity.gene_symbol}
- HGVS (Coding): {identity.hgvs_c}
- HGVS (Protein): {identity.hgvs_p or "N/A"}
- Type: {identity.variant_type}
- Genomic Position: {identity.chromosome}:{identity.position}

EVIDENCE PROFILE:
- Population Frequency (gnomAD): {evidence.gnomad_af or "N/A"}
- Filter Status: {evidence.gnomad_filter or "PASS"}
- CADD Score: {evidence.cadd_score or "N/A"}
- SIFT/PolyPhen: {evidence.sift_score or "N/A"} / {evidence.polyphen_score or "N/A"}
- Functional Studies: {evidence.functional_studies or "N/A"}

ADDITIONAL ACMG FACTS (HINTS):
{chr(10).join([f"- {hint}" for hint in trace.acmg_criteria_hints]) if trace.acmg_criteria_hints else "None provided."}

---
TASK: 
1. Review the ACMG guidelines and the variant data above.
2. Provide a step-by-step reasoning trace for each criterion.
3. Classify the variant (Pathogenic, Likely Pathogenic, VUS, Likely Benign, Benign).
4. Return a JSON object with the final classification, triggered criteria codes, and reasoning.
"""
        return prompt.strip()

if __name__ == "__main__":
    # Test call
    factory = PromptFactory(guidelines_path="docs/ACMG_GUIDELINES_V1.txt")
    # This will be used in scripts/generate_r1_prompts.py
