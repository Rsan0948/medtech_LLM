from modeling.prompt_factory import PromptFactory
from schemas.variant_trace_v1 import (
    ACMGClassification,
    EvidenceProfile,
    VariantIdentity,
    VariantTrace,
    VerifiedOutcome,
)


def test_prompt_includes_guidelines_and_variant():
    factory = PromptFactory(guidelines_path="docs/ACMG_GUIDELINES_V1.txt")
    trace = VariantTrace(
        trace_id="CV-TEST-1",
        identity=VariantIdentity(
            clinvar_id="TEST-1",
            gene_symbol="BRCA1",
            hgvs_c="c.5266dupC",
            hgvs_p="p.Gln1756ProfsTer74",
            chromosome="17",
            position=41246652,
            reference_allele="C",
            alternate_allele="CC",
            variant_type="Duplication",
        ),
        evidence=EvidenceProfile(
            gnomad_af=0.0001,
            cadd_score=25.0,
            prev_submissions_count=5,
        ),
        verified_outcome=VerifiedOutcome(
            classification=ACMGClassification.PATHOGENIC,
            review_status="criteria provided, multiple submitters, no conflicts",
            gold_stars=2,
        ),
        acmg_criteria_hints=["Expert panel reviewed"],
    )

    prompt = factory.create_prompt(trace)
    assert "BRCA1" in prompt
    assert "c.5266dupC" in prompt
    assert "ACMG" in prompt
    assert "BA1" in prompt
    assert "CV-TEST-1" in prompt
