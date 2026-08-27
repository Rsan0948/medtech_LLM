"""
MedTech Variant Classifier — Local Demo

A lightweight Streamlit interface for the distilled MLX student model.
All inference runs locally; no genomic data is sent to external APIs.
"""

import os
import sys
from pathlib import Path

import streamlit as st

# Add src to path so we can import the inference engine
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from schemas.variant_trace_v1 import (
    ACMGClassification,
    EvidenceProfile,
    VariantIdentity,
    VariantTrace,
    VerifiedOutcome,
)


def build_variant(gene, hgvs_c, hgvs_p, chrom, pos, ref, alt, vtype, af, cadd, submissions):
    """Build a VariantTrace from demo form inputs."""
    return VariantTrace(
        trace_id="demo-001",
        identity=VariantIdentity(
            clinvar_id="demo",
            gene_symbol=gene,
            hgvs_c=hgvs_c,
            hgvs_p=hgvs_p or None,
            chromosome=chrom,
            position=pos,
            reference_allele=ref,
            alternate_allele=alt,
            variant_type=vtype,
        ),
        evidence=EvidenceProfile(
            gnomad_af=af if af > 0 else None,
            cadd_score=cadd if cadd > 0 else None,
            prev_submissions_count=int(submissions),
        ),
        verified_outcome=VerifiedOutcome(
            classification=ACMGClassification.VUS,
            review_status="demo",
            gold_stars=0,
        ),
    )


def main():
    st.set_page_config(
        page_title="MedTech Variant Classifier",
        page_icon="🧬",
        layout="wide",
    )

    st.title("🧬 MedTech Variant Classifier")
    st.markdown("""
        A privacy-first demo of the distilled ACMG/AMP variant classification model.
        All inference runs **locally** on your machine via MLX.
        """)

    model_path = st.sidebar.text_input(
        "Base model path",
        value="mlx-community/Qwen3-8B-bf16",
        help="HuggingFace model ID or local path",
    )
    adapter_path = st.sidebar.text_input(
        "LoRA adapter path",
        value="models/adapters/genomics_v2",
        help="Path to the fine-tuned LoRA adapter",
    )

    if not os.path.exists(adapter_path):
        st.sidebar.warning(
            "Adapter not found at the default path. Run `make train` first, "
            "or enter the correct path to a trained adapter."
        )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "**Privacy note:** Your variant data stays in this browser session "
        "and is processed only by the local MLX model."
    )

    with st.form("variant_form"):
        st.subheader("Variant input")
        col1, col2 = st.columns(2)
        with col1:
            gene = st.text_input("Gene symbol", value="BRCA1")
            hgvs_c = st.text_input("HGVS coding", value="c.5266dupC")
            hgvs_p = st.text_input("HGVS protein (optional)", value="p.Gln1756ProfsTer74")
            chrom = st.text_input("Chromosome", value="17")
        with col2:
            pos = st.number_input("Position", value=41246652, step=1)
            ref = st.text_input("Reference allele", value="C")
            alt = st.text_input("Alternate allele", value="CC")
            vtype = st.selectbox(
                "Variant type",
                ["single nucleotide variant", "Deletion", "Duplication", "Insertion"],
            )

        st.subheader("Evidence profile")
        ec1, ec2, ec3 = st.columns(3)
        with ec1:
            af = st.number_input(
                "gnomAD allele frequency",
                value=0.0,
                min_value=0.0,
                max_value=1.0,
                step=0.0001,
                format="%.6f",
            )
        with ec2:
            cadd = st.number_input("CADD score (optional)", value=0.0, min_value=0.0, step=0.1)
        with ec3:
            submissions = st.number_input("Prior submissions", value=5, min_value=0, step=1)

        submitted = st.form_submit_button("Classify variant")

    if submitted:
        trace = build_variant(
            gene, hgvs_c, hgvs_p, chrom, pos, ref, alt, vtype, af, cadd, submissions
        )

        with st.spinner("Running local inference..."):
            try:
                from serving.variant_inference import VariantInference

                engine = VariantInference(
                    model_path=model_path,
                    adapter_path=adapter_path if os.path.exists(adapter_path) else None,
                )
                result = engine.classify(trace.model_dump_json())
            except Exception as e:
                st.error(f"Inference failed: {e}")
                st.info(
                    "If you have not trained the adapter yet, the demo will fall back "
                    "to the base model and may not produce reliable ACMG classifications."
                )
                return

        st.subheader("Result")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Classification", result.get("classification", "N/A"))
        with col_b:
            st.metric("Confidence", result.get("confidence", "N/A"))
        with col_c:
            st.metric("Privacy", result.get("privacy_status", "N/A"))

        st.subheader("Triggered criteria")
        criteria = result.get("triggered_criteria", [])
        if criteria:
            st.write(", ".join(criteria))
        else:
            st.write("None reported")

        st.subheader("Reasoning trace")
        st.markdown(result.get("reasoning_trace", "_No reasoning trace provided._"))

        with st.expander("Raw variant trace"):
            st.json(trace.model_dump())

        with st.expander("Raw model output"):
            st.json(result)


if __name__ == "__main__":
    main()
