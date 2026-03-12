import json
import time
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from schemas.variant_trace_v1 import (
    VariantTrace, VariantIdentity, EvidenceProfile, VerifiedOutcome, ACMGClassification
)

# Hereditary cancer gene panel — focused POC scope
TARGET_GENES = [
    "BRCA1", "BRCA2", "MLH1", "MSH2", "MSH6",
    "PMS2", "PALB2", "ATM", "CHEK2", "TP53"
]

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
BATCH_SIZE = 500
RATE_LIMIT_DELAY = 0.34  # ~3 requests/sec per NCBI guidelines

REVIEW_STATUS_TO_STARS = {
    "practice guideline": 4,
    "reviewed by expert panel": 3,
    "criteria provided, multiple submitters, no conflicts": 2,
    "criteria provided, single submitter": 1,
    "criteria provided, conflicting interpretations": 0,
    "no assertion criteria provided": 0,
    "no classification provided": 0,
    "no interpretation for the single variant": 0,
}

CLASSIFICATION_MAP = {
    "Pathogenic": ACMGClassification.PATHOGENIC,
    "Likely pathogenic": ACMGClassification.LIKELY_PATHOGENIC,
    "Likely Pathogenic": ACMGClassification.LIKELY_PATHOGENIC,
    "Uncertain significance": ACMGClassification.VUS,
    "Variant of uncertain significance": ACMGClassification.VUS,
    "Likely benign": ACMGClassification.LIKELY_BENIGN,
    "Likely Benign": ACMGClassification.LIKELY_BENIGN,
    "Benign": ACMGClassification.BENIGN,
    "Conflicting interpretations of pathogenicity": ACMGClassification.CONFLICTING,
    "Conflicting classifications of pathogenicity": ACMGClassification.CONFLICTING,
}


class ClinVarIngestor:
    """
    ZDS-ID: TOOL-600 (Layer 3 - Domain Ingestor)
    Downloads ClinVar germline variants for the target gene panel via NCBI E-utilities.
    Converts to VariantTrace JSONL for the ZDS pipeline.
    """

    def __init__(self, output_path: str, api_key: Optional[str] = None):
        self.output_path = Path(output_path)
        self.api_key = api_key  # NCBI API key (optional, raises rate limit to 10 req/sec)
        self.total_written = 0
        self.total_skipped = 0

    def _get(self, url: str, params: Dict) -> Dict:
        if self.api_key:
            params["api_key"] = self.api_key
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        time.sleep(RATE_LIMIT_DELAY)
        return resp.json()

    def _search_gene(self, gene: str) -> List[str]:
        """Return all ClinVar variation IDs for germline submissions of a gene."""
        ids = []
        retstart = 0
        query = f"{gene}[gene] AND germline[origin] AND single_gene[prop]"

        while True:
            data = self._get(f"{NCBI_BASE}/esearch.fcgi", {
                "db": "clinvar",
                "term": query,
                "retmax": BATCH_SIZE,
                "retstart": retstart,
                "retmode": "json",
            })
            result = data.get("esearchresult", {})
            batch = result.get("idlist", [])
            ids.extend(batch)

            total = int(result.get("count", 0))
            retstart += len(batch)
            if retstart >= total or not batch:
                break

        print(f"  {gene}: found {len(ids)} variants")
        return ids

    def _fetch_summaries(self, ids: List[str]) -> List[Dict]:
        """Fetch esummary records in batches of BATCH_SIZE."""
        summaries = []
        for i in range(0, len(ids), BATCH_SIZE):
            batch = ids[i:i + BATCH_SIZE]
            data = self._get(f"{NCBI_BASE}/esummary.fcgi", {
                "db": "clinvar",
                "id": ",".join(batch),
                "retmode": "json",
            })
            result = data.get("result", {})
            for uid in result.get("uids", []):
                summaries.append(result[uid])
        return summaries

    def _parse_classification(self, summary: Dict) -> Optional[ACMGClassification]:
        """Extract germline classification string and map to enum."""
        # Try germline_classification first (newer API), fall back to clinical_significance
        raw = (
            summary.get("germline_classification", {}).get("description", "")
            or summary.get("clinical_significance", {}).get("description", "")
        )
        return CLASSIFICATION_MAP.get(raw)

    def _parse_review_status(self, summary: Dict) -> str:
        return (
            summary.get("germline_classification", {}).get("review_status", "")
            or summary.get("clinical_significance", {}).get("review_status", "")
            or "no classification provided"
        )

    def _parse_hgvs(self, summary: Dict) -> tuple:
        """Return (hgvs_c, hgvs_p) strings."""
        hgvs_c, hgvs_p = "", None
        for expr in (summary.get("variation_set") or [{}])[0].get("variation_hgvs", []):
            assembly = expr.get("assembly_name", "")
            mol_type = expr.get("mol_type", "")
            hgvs = expr.get("hgvs", "")
            if "c." in hgvs:
                hgvs_c = hgvs
            elif "p." in hgvs:
                hgvs_p = hgvs
        return hgvs_c, hgvs_p

    def _summary_to_trace(self, summary: Dict, gene: str) -> Optional[VariantTrace]:
        classification = self._parse_classification(summary)
        if classification is None:
            self.total_skipped += 1
            return None

        review_status = self._parse_review_status(summary)
        gold_stars = REVIEW_STATUS_TO_STARS.get(review_status.lower(), 0)

        # Location
        loc = (summary.get("variation_set") or [{}])[0].get("variation_loc", [{}])
        chrom = str(loc[0].get("chr", "")) if loc else ""
        position = int(loc[0].get("start", 0)) if loc else 0
        ref = loc[0].get("ref_allele", "") if loc else ""
        alt = loc[0].get("alt_allele", "") if loc else ""

        # HGVS
        hgvs_c, hgvs_p = self._parse_hgvs(summary)
        if not hgvs_c:
            hgvs_c = summary.get("title", "")

        # Variant type
        var_type = (summary.get("variation_set") or [{}])[0].get("variant_type", "single nucleotide variant")

        # gnomAD allele frequency (not directly in esummary — default to None)
        # CADD/SIFT/PolyPhen also not in esummary; these would require Ensembl VEP enrichment
        # We store what we have; the PromptFactory gracefully handles None fields as "N/A"

        # Submission count as proxy for prev_submissions_count
        submissions = summary.get("supporting_submissions", {}).get("scv", [])
        submission_count = len(submissions) if isinstance(submissions, list) else 0

        identity = VariantIdentity(
            clinvar_id=str(summary.get("uid", "")),
            gene_symbol=gene,
            hgvs_c=hgvs_c,
            hgvs_p=hgvs_p,
            chromosome=chrom,
            position=position,
            reference_allele=ref,
            alternate_allele=alt,
            variant_type=var_type,
        )
        evidence = EvidenceProfile(
            prev_submissions_count=submission_count,
        )
        outcome = VerifiedOutcome(
            classification=classification,
            review_status=review_status,
            gold_stars=gold_stars,
        )

        # Build ACMG hints from known high-signal fields
        hints = []
        if gold_stars >= 3:
            hints.append("Expert panel or practice guideline reviewed")
        if classification in (ACMGClassification.PATHOGENIC, ACMGClassification.LIKELY_PATHOGENIC):
            if submission_count > 5:
                hints.append(f"PS4 candidate: {submission_count} independent submissions support pathogenicity")

        return VariantTrace(
            trace_id=f"CV-{summary.get('uid', '')}",
            identity=identity,
            evidence=evidence,
            verified_outcome=outcome,
            acmg_criteria_hints=hints,
        )

    def run(self):
        print("=" * 50)
        print("ClinVar Ingestor (ZDS MedTech Pipeline)")
        print(f"Target genes: {', '.join(TARGET_GENES)}")
        print("=" * 50)

        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.output_path, 'w') as f_out:
            for gene in TARGET_GENES:
                print(f"\nProcessing {gene}...")
                ids = self._search_gene(gene)
                if not ids:
                    continue

                summaries = self._fetch_summaries(ids)
                for summary in summaries:
                    trace = self._summary_to_trace(summary, gene)
                    if trace is not None:
                        f_out.write(trace.model_dump_json() + '\n')
                        self.total_written += 1

        print("\n" + "=" * 50)
        print("INGESTION COMPLETE")
        print(f"Written: {self.total_written} variants")
        print(f"Skipped: {self.total_skipped} (unrecognized classification)")
        print(f"Output:  {self.output_path}")
        print("=" * 50)


if __name__ == "__main__":
    ingestor = ClinVarIngestor(output_path="data/processed/variant_traces_raw.jsonl")
    ingestor.run()
