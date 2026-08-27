import json
import tempfile
from pathlib import Path

from processing.consensus_filter import ConsensusFilter
from schemas.variant_trace_v1 import (
    ACMGClassification,
    EvidenceProfile,
    VariantIdentity,
    VariantTrace,
    VerifiedOutcome,
)


def _make_trace(trace_id: str, classification: ACMGClassification, stars: int):
    return VariantTrace(
        trace_id=trace_id,
        identity=VariantIdentity(
            clinvar_id=trace_id.split("-")[1],
            gene_symbol="BRCA1",
            hgvs_c=f"c.{trace_id}",
            chromosome="17",
            position=1,
            reference_allele="A",
            alternate_allele="G",
            variant_type="snv",
        ),
        evidence=EvidenceProfile(),
        verified_outcome=VerifiedOutcome(
            classification=classification,
            review_status="test",
            gold_stars=stars,
        ),
    )


def test_consensus_filter_keeps_consensus():
    traces = [
        _make_trace("CV-1", ACMGClassification.PATHOGENIC, 3),
        _make_trace("CV-2", ACMGClassification.BENIGN, 1),
        _make_trace("CV-3", ACMGClassification.CONFLICTING, 0),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "input.jsonl"
        output_path = Path(tmpdir) / "output.jsonl"

        with open(input_path, "w") as f:
            for t in traces:
                f.write(t.model_dump_json() + "\n")

        cf = ConsensusFilter(str(input_path), str(output_path))
        cf.run()

        with open(output_path) as f:
            results = [json.loads(line) for line in f]

        assert len(results) == 2
        assert cf.tier_counts[1] == 1
        assert cf.tier_counts[2] == 1
        assert cf.tier_counts[3] == 1
        assert all(r["cqf_tier"] <= 2 for r in results)
