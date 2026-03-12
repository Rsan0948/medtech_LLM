import json
import os
import sys
from pathlib import Path

# Add src to python path to import schemas and prompt_factory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from schemas.variant_trace_v1 import VariantTrace
from modeling.prompt_factory import PromptFactory

def main():
    """
    ZDS-ID: TOOL-701 (Teacher Trace Generation Preparation)
    Mass-generates prompts for the Teacher (R1) based on CQF Tier-1 filtered traces.
    """
    input_path = Path("data/processed/variant_traces_cqf_tier1.jsonl")
    output_path = Path("data/app/teacher_prompts.jsonl")
    guidelines_path = Path("docs/ACMG_GUIDELINES_V1.txt")
    
    if not input_path.exists():
        print(f"Error: {input_path} not found. Run ingestion and CQF filtering first.")
        return

    print(f"Generating Teacher prompts from {input_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    factory = PromptFactory(guidelines_path=str(guidelines_path))
    
    count = 0
    with open(input_path, 'r') as f_in, open(output_path, 'w') as f_out:
        for line in f_in:
            if not line.strip():
                continue
            
            data = json.loads(line)
            trace = VariantTrace(**data)
            
            # Create the high-fidelity prompt
            prompt_text = factory.create_prompt(trace)
            
            # Save for R1 processing
            payload = {
                "trace_id": trace.trace_id,
                "variant_clinvar_id": trace.identity.clinvar_id,
                "prompt": prompt_text,
                "verified_outcome": trace.verified_outcome.classification
            }
            f_out.write(json.dumps(payload) + '\n')
            count += 1
    
    print(f"Successfully generated {count} prompts in {output_path}")

if __name__ == "__main__":
    main()
