#!/usr/bin/env python3
"""
Classical ML baseline for 5-class variant classification.

Stronger comparator than the AF/LoF rule baseline: logistic regression and
histogram gradient boosting trained on the same distillation splits.

Fairness rules:
- Features are restricted to fields that appear in the student prompts
  (gene, variant type, gnomAD AF/filter, HGVS-derived consequence flags).
  review_status, gold_stars and prev_submissions_count are EXCLUDED because
  the students never see them and they are label-adjacent.
- Trains only on the 654 unique training trace IDs (verified ClinVar labels).
- Evaluates on the frozen 98-example validation split and the 45-variant
  holdout (never distilled), scoring against verified labels.

Usage:
    .venv/bin/python -m scripts.classical_baseline
    (or: .venv/bin/python scripts/classical_baseline.py)

Writes: data/app/classical_baseline_results.json
"""

import json
import math
import re
from pathlib import Path

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent.parent
TRACES = ROOT / "data/processed/variant_traces_cqf_tier1.jsonl"
TRAIN_JSONL = ROOT / "data/app/training_data/train.jsonl"
VALID_JSONL = ROOT / "data/app/training_data/valid.jsonl"
HOLDOUT_RESULTS = ROOT / "data/app/student_tbe_results_holdout.jsonl"
OUT = ROOT / "data/app/classical_baseline_results.json"

LABELS = [
    "Pathogenic",
    "Likely Pathogenic",
    "Variant of Uncertain Significance",
    "Likely Benign",
    "Benign",
]

NUMERIC = ["log_af", "af_missing", "gnomad_pass"]
CATEGORICAL = ["gene", "variant_type"]
FLAGS = ["is_frameshift", "is_nonsense", "is_synonymous", "is_inframe_indel", "is_splice_region"]


def extract_ids(jsonl_path: Path) -> list[str]:
    ids = []
    for line in open(jsonl_path):
        if not line.strip():
            continue
        text = json.loads(line)["messages"][0]["content"]
        m = re.search(r"ZDS-ID: (CV-\d+)", text)
        if m:
            ids.append(m.group(1))
    return ids


def featurize(trace: dict) -> dict:
    idn = trace["identity"]
    ev = trace["evidence"]
    hgvs_p = idn.get("hgvs_p") or ""
    hgvs_c = idn.get("hgvs_c") or ""
    af = ev.get("gnomad_af")
    return {
        "gene": idn.get("gene_symbol") or "unknown",
        "variant_type": idn.get("variant_type") or "unknown",
        "log_af": math.log10(af) if af else np.nan,
        "af_missing": 0.0 if af else 1.0,
        "gnomad_pass": 1.0 if (ev.get("gnomad_filter") or "PASS") == "PASS" else 0.0,
        "is_frameshift": 1.0 if "fs" in hgvs_p else 0.0,
        "is_nonsense": 1.0 if ("Ter" in hgvs_p or "*" in hgvs_p) else 0.0,
        "is_synonymous": 1.0 if hgvs_p.endswith("=") else 0.0,
        "is_inframe_indel": 1.0 if (("del" in hgvs_p or "dup" in hgvs_p) and "fs" not in hgvs_p) else 0.0,
        "is_splice_region": 1.0 if re.search(r"c\.\d+[+-]\d+", hgvs_c) else 0.0,
    }


FEATURE_ORDER = NUMERIC + CATEGORICAL + FLAGS
NUM_IDX = [FEATURE_ORDER.index(k) for k in NUMERIC]
CAT_IDX = [FEATURE_ORDER.index(k) for k in CATEGORICAL]
FLAG_IDX = [FEATURE_ORDER.index(k) for k in FLAGS]


def to_matrix(feats: list[dict]) -> np.ndarray:
    return np.array([[f[k] for k in FEATURE_ORDER] for f in feats], dtype=object)


def prf1(y_true: list[str], y_pred: list[str]) -> dict:
    out = {}
    for lab in LABELS:
        tp = sum(1 for t, p in zip(y_true, y_pred) if p == lab and t == lab)
        fp = sum(1 for t, p in zip(y_true, y_pred) if p == lab and t != lab)
        fn = sum(1 for t, p in zip(y_true, y_pred) if p != lab and t == lab)
        sup = sum(1 for t in y_true if t == lab)
        p = tp / (tp + fp) if tp + fp else None
        r = tp / (tp + fn) if tp + fn else (0.0 if sup else None)
        f1 = 2 * p * r / (p + r) if (p is not None and r is not None and p + r > 0) else (0.0 if p == 0.0 or r == 0.0 else None)
        out[lab] = {
            "precision": round(p, 4) if p is not None else None,
            "recall": round(r, 4) if r is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
            "support": sup,
        }
    return out


def confusion(y_true: list[str], y_pred: list[str]) -> dict:
    return {g: {p: sum(1 for t, q in zip(y_true, y_pred) if t == g and q == p) for p in LABELS} for g in LABELS}


def evaluate(y_true: list[str], y_pred: list[str]) -> dict:
    return {
        "n": len(y_true),
        "accuracy": round(sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true), 4),
        "per_class": prf1(y_true, y_pred),
        "confusion_matrix": confusion(y_true, y_pred),
    }


def main() -> None:
    traces = {}
    for line in open(TRACES):
        if line.strip():
            t = json.loads(line)
            traces[t["trace_id"]] = t

    train_ids = list(dict.fromkeys(extract_ids(TRAIN_JSONL)))  # unique, ordered
    valid_ids = extract_ids(VALID_JSONL)
    holdout = [json.loads(l) for l in open(HOLDOUT_RESULTS) if l.strip()]
    holdout_ids = [r["trace_id"] for r in holdout]
    holdout_gold = {r["trace_id"]: r["verified_label"] for r in holdout}

    missing = [i for i in train_ids + valid_ids + holdout_ids if i not in traces]
    if missing:
        raise SystemExit(f"trace_ids missing from traces file: {missing[:5]} ({len(missing)} total)")

    X_train = to_matrix([featurize(traces[i]) for i in train_ids])
    y_train = [traces[i]["verified_outcome"]["classification"] for i in train_ids]
    X_valid = to_matrix([featurize(traces[i]) for i in valid_ids])
    y_valid = [traces[i]["verified_outcome"]["classification"] for i in valid_ids]
    X_hold = to_matrix([featurize(traces[i]) for i in holdout_ids])
    y_hold = [holdout_gold[i] for i in holdout_ids]

    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_IDX),
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), NUM_IDX),
        ("flags", "passthrough", FLAG_IDX),
    ])

    models = {
        "logistic_regression": Pipeline([
            ("pre", pre),
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42)),
        ]),
        "gradient_boosting": Pipeline([
            ("pre", pre),
            ("clf", HistGradientBoostingClassifier(class_weight="balanced", random_state=42)),
        ]),
    }

    results = {
        "description": "Classical ML baselines trained on prompt-visible features only "
                       "(no review_status, gold_stars, or prev_submissions_count).",
        "features": NUMERIC + CATEGORICAL + FLAGS,
        "train_n": len(train_ids),
        "models": {},
    }
    for name, pipe in models.items():
        pipe.fit(X_train, y_train)
        results["models"][name] = {
            "validation": evaluate(y_valid, pipe.predict(X_valid)),
            "holdout": evaluate(y_hold, pipe.predict(X_hold)),
        }
        print(f"{name}: valid {results['models'][name]['validation']['accuracy']:.4f} "
              f"| holdout {results['models'][name]['holdout']['accuracy']:.4f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(results, open(OUT, "w"), indent=2)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
