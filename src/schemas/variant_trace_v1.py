from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ACMGClassification(str, Enum):
    PATHOGENIC = "Pathogenic"
    LIKELY_PATHOGENIC = "Likely Pathogenic"
    VUS = "Variant of Uncertain Significance"
    LIKELY_BENIGN = "Likely Benign"
    BENIGN = "Benign"
    CONFLICTING = "Conflicting interpretations of pathogenicity"


class VariantIdentity(BaseModel):
    clinvar_id: str
    gene_symbol: str
    hgvs_c: str  # Coding DNA reference
    hgvs_p: str | None = None  # Protein reference
    chromosome: str
    position: int
    reference_allele: str
    alternate_allele: str
    variant_type: str  # e.g., single nucleotide variant, deletion


class EvidenceProfile(BaseModel):
    # Population Frequency (gnomAD)
    gnomad_af: float | None = None
    gnomad_filter: str | None = None

    # Computational/In Silico Predictors
    cadd_score: float | None = None
    sift_score: float | None = None
    polyphen_score: float | None = None
    revel_score: float | None = None

    # Clinical/Experimental Context
    functional_studies: str | None = None
    inheritance_mode: str | None = None
    prev_submissions_count: int = 0


class VerifiedOutcome(BaseModel):
    classification: ACMGClassification
    review_status: str  # e.g., "criteria provided, multiple submitters, no conflicts"
    gold_stars: int = 0  # 0 to 4 stars in ClinVar
    last_evaluated: datetime | None = None


class VariantTrace(BaseModel):
    """
    ZDS-ID: TOOL-801 (RichSpec) for Genomic Variants.
    The primary data unit for the MedTech Distillation Pipeline.
    """

    trace_id: str = Field(description="Unique ID for this training example")
    identity: VariantIdentity
    evidence: EvidenceProfile
    verified_outcome: VerifiedOutcome
    acmg_criteria_hints: list[str] = Field(
        default_factory=list, description="Explicit ACMG facts for Teacher reasoning"
    )

    # ZDS Metadata
    cqf_tier: int = 0  # 1 (Consensus), 2 (Majority), 3 (Conflict)
    schema_version: str = "v1.0"
    model_config = ConfigDict(use_enum_values=True)
