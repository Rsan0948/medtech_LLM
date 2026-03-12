import json
from pathlib import Path
from typing import List, Dict, Any
from schemas.variant_trace_v1 import VariantTrace, ACMGClassification

class ConsensusFilter:
    """
    ZDS-ID: TOOL-702 (Consensus Quality Filtering)
    Filters variant datasets for high-signal consensus cases.
    """
    
    def __init__(self, input_path: str, output_path: str):
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.tier_counts = {1: 0, 2: 0, 3: 0}

    def _assign_tier(self, trace: VariantTrace) -> int:
        """
        Consensus Logic:
        Tier 1: 2+ Stars in ClinVar (Consensus)
        Tier 2: 1 Star in ClinVar (Majority)
        Tier 3: 0 Stars or 'Conflicting' (No Consensus)
        """
        if trace.verified_outcome.classification == ACMGClassification.CONFLICTING:
            return 3
        
        stars = trace.verified_outcome.gold_stars
        if stars >= 2:
            return 1
        elif stars == 1:
            return 2
        else:
            return 3

    def run(self):
        print(f"Starting CQF Filter (ZDS-ID: TOOL-702)...")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.input_path, 'r') as f_in, open(self.output_path, 'w') as f_out:
            for line in f_in:
                if not line.strip():
                    continue
                
                data = json.loads(line)
                trace = VariantTrace(**data)
                
                # Apply CQF Tier Assignment
                tier = self._assign_tier(trace)
                trace.cqf_tier = tier
                self.tier_counts[tier] += 1
                
                # Only write out Tier 1 and 2 for distillation
                if tier <= 2:
                    f_out.write(trace.model_dump_json() + '\n')
        
        self.report()

    def report(self):
        total = sum(self.tier_counts.values())
        print("="*40)
        print("CQF FILTER REPORT")
        print("="*40)
        print(f"Total Variants: {total}")
        print(f"Tier 1 (Consensus - High Signal): {self.tier_counts[1]}")
        print(f"Tier 2 (Majority - Med Signal):   {self.tier_counts[2]}")
        print(f"Tier 3 (Conflict - Rejected):     {self.tier_counts[3]}")
        print("="*40)
        print(f"Filtered output saved to: {self.output_path}")

if __name__ == "__main__":
    # Example paths - these will be used once ingestion is run
    filter_gate = ConsensusFilter(
        input_path="data/processed/variant_traces_raw.jsonl",
        output_path="data/processed/variant_traces_cqf_tier1.jsonl"
    )
    # filter_gate.run()  <-- Ready for injection
