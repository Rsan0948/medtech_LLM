from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

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
    hgvs_p: Optional[str] = None  # Protein reference
    chromosome: str
    position: int
    reference_allele: str
    alternate_allele: str
    variant_type: str  # e.g., single nucleotide variant, deletion

class EvidenceProfile(BaseModel):
    # Population Frequency (gnomAD)
    gnomad_af: Optional[float] = None
    gnomad_filter: Optional[str] = None
    
    # Computational/In Silico Predictors
    cadd_score: Optional[float] = None
    sift_score: Optional[float] = None
    polyphen_score: Optional[float] = None
    revel_score: Optional[float] = None
    
    # Clinical/Experimental Context
    functional_studies: Optional[str] = None
    inheritance_mode: Optional[str] = None
    prev_submissions_count: int = 0

class VerifiedOutcome(BaseModel):
    classification: ACMGClassification
    review_status: str  # e.g., "criteria provided, multiple submitters, no conflicts"
    gold_stars: int = 0  # 0 to 4 stars in ClinVar
    last_evaluated: Optional[datetime] = None

class VariantTrace(BaseModel):
    """
    ZDS-ID: TOOL-801 (RichSpec) for Genomic Variants.
    The primary data unit for the MedTech Distillation Pipeline.
    """
    trace_id: str = Field(description="Unique ID for this training example")
    identity: VariantIdentity
    evidence: EvidenceProfile
    verified_outcome: VerifiedOutcome
    acmg_criteria_hints: List[str] = Field(default_factory=list, description="Explicit ACMG facts for Teacher reasoning")
    
    # ZDS Metadata
    cqf_tier: int = 0  # 1 (Consensus), 2 (Majority), 3 (Conflict)
    schema_version: str = "v1.0"
    
    class Config:
        use_enum_values = True
