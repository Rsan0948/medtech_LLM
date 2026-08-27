import json

import pytest

from schemas.variant_trace_v1 import (
    ACMGClassification,
    EvidenceProfile,
    VariantIdentity,
    VariantTrace,
    VerifiedOutcome,
)


def test_variant_trace_creation():
    trace = VariantTrace(
        trace_id="CV-12345",
        identity=VariantIdentity(
            clinvar_id="12345",
            gene_symbol="BRCA1",
            hgvs_c="c.5266dupC",
            hgvs_p="p.Gln1756ProfsTer74",
            chromosome="17",
            position=41246652,
            reference_allele="C",
            alternate_allele="CC",
            variant_type="Duplication",
        ),
        evidence=EvidenceProfile(prev_submissions_count=10),
        verified_outcome=VerifiedOutcome(
            classification=ACMGClassification.PATHOGENIC,
            review_status="criteria provided, multiple submitters, no conflicts",
            gold_stars=2,
        ),
        acmg_criteria_hints=["Expert panel reviewed"],
    )
    assert trace.trace_id == "CV-12345"
    assert trace.identity.gene_symbol == "BRCA1"
    assert trace.verified_outcome.classification == "Pathogenic"
    assert trace.cqf_tier == 0
    assert trace.schema_version == "v1.0"


def test_variant_trace_serialization():
    trace = VariantTrace(
        trace_id="CV-999",
        identity=VariantIdentity(
            clinvar_id="999",
            gene_symbol="TP53",
            hgvs_c="c.123A>G",
            chromosome="17",
            position=7579472,
            reference_allele="A",
            alternate_allele="G",
            variant_type="single nucleotide variant",
        ),
        evidence=EvidenceProfile(),
        verified_outcome=VerifiedOutcome(
            classification=ACMGClassification.VUS,
            review_status="criteria provided, single submitter",
            gold_stars=1,
        ),
    )
    raw = trace.model_dump_json()
    data = json.loads(raw)
    assert data["trace_id"] == "CV-999"
    assert data["verified_outcome"]["classification"] == "Variant of Uncertain Significance"


def test_invalid_classification_raises():
    with pytest.raises(ValueError):
        VariantTrace(
            trace_id="CV-1",
            identity=VariantIdentity(
                clinvar_id="1",
                gene_symbol="BRCA1",
                hgvs_c="c.1A>G",
                chromosome="17",
                position=1,
                reference_allele="A",
                alternate_allele="G",
                variant_type="snv",
            ),
            evidence=EvidenceProfile(),
            verified_outcome=VerifiedOutcome(
                classification="Not a real classification",
                review_status="unknown",
                gold_stars=0,
            ),
        )
