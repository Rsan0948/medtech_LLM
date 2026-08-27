from schemas.variant_trace_v1 import VariantTrace


class PromptFactory:
    """
    ZDS-ID: TOOL-801 (RichSpec Prompting Strategy)
    Assembles a high-fidelity distillation prompt for the Teacher model.
    """

    def __init__(self, guidelines_path: str):
        with open(guidelines_path) as f:
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
CRITICAL INSTRUCTIONS FOR CLASSIFICATION:
1. First, check for PATHOGENIC criteria (PVS1, PS1-PS4, PM1-PM6, PP1-PP5).
2. Then, check for BENIGN criteria (BA1, BS1-BS4, BP1-BP7) - DO NOT SKIP THIS STEP.
3. BA1: If gnomAD allele frequency > 5% (AF > 0.05), this is standalone evidence for Benign.
4. BS1: If gnomAD AF > expected for disease (typically > 1% for rare diseases), this is strong evidence for Benign.
5. BP4: If in silico predictions (CADD, SIFT, PolyPhen) suggest no impact, this is supporting evidence for Benign.
6. Only classify as VUS if NEITHER pathogenic nor benign criteria are met.
7. Provide a step-by-step reasoning trace for EACH criterion checked (both pathogenic AND benign).
8. Classify the variant (Pathogenic, Likely Pathogenic, VUS, Likely Benign, Benign).
9. Return a JSON object with the final classification, triggered criteria codes, and reasoning.

IMPORTANT: Many variants are benign due to high population frequency. Always check BA1 and BS1 before defaulting to VUS.
"""
        return prompt.strip()


if __name__ == "__main__":
    # Test call
    factory = PromptFactory(guidelines_path="docs/ACMG_GUIDELINES_V1.txt")
    # This will be used in scripts/generate_r1_prompts.py
