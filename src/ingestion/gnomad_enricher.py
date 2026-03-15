"""
gnomAD Enrichment Module
ZDS-ID: TOOL-601 (Layer 3 Enhancement)

Fetches allele frequency data from gnomAD API to enrich variant traces.
This enables proper BA1/BS1 benign criteria classification.
"""

import json
import time
import requests
from typing import Dict, Any, Optional

GNOMAD_API_URL = "https://gnomad.broadinstitute.org/api"

# GraphQL query for variant data
VARIANT_QUERY = """
query VariantQuery($variantId: String!, $datasetId: DatasetId!) {
  variant(variantId: $variantId, dataset: $datasetId) {
    variantId
    chrom
    pos
    ref
    alt
    genome {
      af
      ac
      an
    }
    exome {
      af
      ac
      an
    }
    in_silico_predictors {
      cadd
      splice_ai
    }
  }
}
"""

# Alternative: Use mygene.info as a simpler REST API
MYGENE_URL = "https://mygene.info/v3/query"


class GnomADEnricher:
    """
    Enriches variant traces with gnomAD allele frequency data.
    """
    
    def __init__(self, rate_limit_delay: float = 0.5):
        self.rate_limit_delay = rate_limit_delay
        self.cache = {}  # Simple cache to avoid duplicate queries
    
    def _get_gnomad_variant(self, chrom: str, pos: int, ref: str = "N", alt: str = "N") -> Optional[Dict]:
        """
        Query gnomAD for variant data.
        Format: chrom-pos-ref-alt (e.g., 17-43106477-A-AT)
        """
        # Build variant ID
        variant_id = f"{chrom}-{pos}-{ref}-{alt}"
        
        if variant_id in self.cache:
            return self.cache[variant_id]
        
        try:
            # Try gnomAD v4 (genomes)
            payload = {
                "query": VARIANT_QUERY,
                "variables": {
                    "variantId": variant_id,
                    "datasetId": "gnomad_r4"
                }
            }
            
            resp = requests.post(
                GNOMAD_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if resp.status_code == 200:
                data = resp.json()
                variant_data = data.get("data", {}).get("variant")
                self.cache[variant_id] = variant_data
                time.sleep(self.rate_limit_delay)
                return variant_data
            else:
                # Try gnomAD v2 (exomes) as fallback
                payload["variables"]["datasetId"] = "gnomad_r2_1"
                resp = requests.post(
                    GNOMAD_API_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30
                )
                if resp.status_code == 200:
                    data = resp.json()
                    variant_data = data.get("data", {}).get("variant")
                    self.cache[variant_id] = variant_data
                    time.sleep(self.rate_limit_delay)
                    return variant_data
                
        except Exception as e:
            print(f"    gnomAD query failed for {variant_id}: {e}")
        
        time.sleep(self.rate_limit_delay)
        return None
    
    def enrich_variant(self, variant_trace: Dict) -> Dict:
        """
        Enrich a variant trace with gnomAD data.
        Returns updated trace.
        """
        identity = variant_trace.get("identity", {})
        evidence = variant_trace.get("evidence", {})
        
        chrom = identity.get("chromosome")
        pos = identity.get("position")
        
        if not chrom or not pos:
            return variant_trace
        
        # Query gnomAD
        gnomad_data = self._get_gnomad_variant(str(chrom), int(pos))
        
        if gnomad_data:
            # Extract allele frequencies
            genome_af = gnomad_data.get("genome", {}).get("af")
            exome_af = gnomad_data.get("exome", {}).get("af")
            
            # Use the higher AF (more data)
            if genome_af and exome_af:
                af = max(genome_af, exome_af)
            elif genome_af:
                af = genome_af
            elif exome_af:
                af = exome_af
            else:
                af = None
            
            # Update evidence
            if af is not None:
                evidence["gnomad_af"] = af
                evidence["gnomad_filter"] = "PASS" if af < 0.01 else "COMMON"
            
            # Add in silico predictors if available
            predictors = gnomad_data.get("in_silico_predictors", {})
            if predictors:
                if predictors.get("cadd") and not evidence.get("cadd_score"):
                    evidence["cadd_score"] = predictors["cadd"]
                if predictors.get("splice_ai") and not evidence.get("splice_ai_score"):
                    evidence["splice_ai_score"] = predictors["splice_ai"]
        
        variant_trace["evidence"] = evidence
        return variant_trace
    
    def enrich_batch(self, variant_traces: list) -> list:
        """Enrich a batch of variant traces."""
        enriched = []
        total = len(variant_traces)
        
        print(f"Enriching {total} variants with gnomAD data...")
        
        for i, trace in enumerate(variant_traces):
            enriched_trace = self.enrich_variant(trace)
            enriched.append(enriched_trace)
            
            if (i + 1) % 10 == 0:
                with_af = sum(1 for t in enriched if t.get("evidence", {}).get("gnomad_af"))
                print(f"  [{i+1}/{total}] {with_af} have gnomAD AF")
        
        # Final stats
        with_af = sum(1 for t in enriched if t.get("evidence", {}).get("gnomad_af"))
        print(f"\nEnrichment complete: {with_af}/{total} ({100*with_af/total:.1f}%) have gnomAD AF")
        
        return enriched


def main():
    """
    Standalone enrichment of existing variant traces.
    """
    import sys
    
    # Use the filtered 1K variants that match our prompts
    input_path = "data/processed/variant_traces_to_enrich.jsonl"
    output_path = "data/processed/variant_traces_enriched_1k.jsonl"
    
    print("=" * 60)
    print("gnomAD Enrichment Tool")
    print("=" * 60)
    
    # Load variants
    with open(input_path, 'r') as f:
        variants = [json.loads(l) for l in f if l.strip()]
    
    print(f"Loaded {len(variants)} variants from {input_path}")
    
    # Enrich
    enricher = GnomADEnricher(rate_limit_delay=0.5)
    enriched = enricher.enrich_batch(variants)
    
    # Save
    with open(output_path, 'w') as f:
        for v in enriched:
            f.write(json.dumps(v) + '\n')
    
    print(f"\nSaved enriched variants to {output_path}")


if __name__ == "__main__":
    main()
