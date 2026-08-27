import json
from pathlib import Path


class TBEMetrics:
    """
    ZDS-ID: TOOL-703 (Triadic Benchmark Evaluation)
    The primary acceptance testing engine for distilled MedTech models.
    """

    LABELS = [
        "Pathogenic",
        "Likely Pathogenic",
        "Variant of Uncertain Significance",
        "Likely Benign",
        "Benign",
    ]
    CONFIDENCE_LEVELS = ["High", "Medium", "Low"]

    def __init__(self, results_path: str):
        self.results_path = Path(results_path)
        self.stats = {
            "baseline": {"correct": 0, "total": 0},
            "teacher": {"correct": 0, "total": 0},
            "student": {"correct": 0, "total": 0},
        }
        # Per-confidence-level precision tracking (student only).
        self.conf_stats = {level: {"correct": 0, "total": 0} for level in self.CONFIDENCE_LEVELS}
        # Confusion matrix: confusion[verified][student] = count.
        self.confusion = {
            verified: {student: 0 for student in self.LABELS} for verified in self.LABELS
        }

    def process_test_set(self):
        """
        Iterates through the test set results and computes accuracies.
        Each test result must contain:
        - verified_label: Pathogenic, Likely Pathogenic, etc.
        - baseline_label: InterVar classification.
        - teacher_label: R1 classification.
        - student_label: Distilled Qwen3 classification.
        - student_confidence: High, Medium, or Low.
        """
        if not self.results_path.exists():
            print(f"Error: {self.results_path} not found.")
            return

        with open(self.results_path) as f:
            for line in f:
                if not line.strip():
                    continue

                row = json.loads(line)
                verified = row["verified_label"]

                # Check Baseline
                self.stats["baseline"]["total"] += 1
                if row["baseline_label"] == verified:
                    self.stats["baseline"]["correct"] += 1

                # Check Teacher (skipped for holdout rows without a teacher label)
                teacher_label = row.get("teacher_label")
                if teacher_label is not None:
                    self.stats["teacher"]["total"] += 1
                    if teacher_label == verified:
                        self.stats["teacher"]["correct"] += 1

                # Check Student
                self.stats["student"]["total"] += 1
                if row["student_label"] == verified:
                    self.stats["student"]["correct"] += 1

                # Per-confidence precision tracking (Student)
                confidence = row.get("student_confidence")
                if confidence in self.conf_stats:
                    self.conf_stats[confidence]["total"] += 1
                    if row["student_label"] == verified:
                        self.conf_stats[confidence]["correct"] += 1

                # Confusion matrix (verified vs student)
                if verified in self.confusion and row["student_label"] in self.LABELS:
                    self.confusion[verified][row["student_label"]] += 1

    def _calc_acc(self, model_key: str) -> float | None:
        s = self.stats[model_key]
        return (s["correct"] / s["total"] * 100.0) if s["total"] > 0 else None

    @staticmethod
    def _fmt_acc(acc: float | None) -> str:
        return f"{acc:.2f}%" if acc is not None else "n/a (no labels)"

    def report(self):
        print("=" * 40)
        print("TBE PERFORMANCE REPORT (ZDS-ID: TOOL-703)")
        print("=" * 40)

        acc_b = self._calc_acc("baseline")
        acc_t = self._calc_acc("teacher")
        acc_s = self._calc_acc("student")

        print(f"Baseline (InterVar):   {self._fmt_acc(acc_b)}")
        print(f"Teacher (R1):          {self._fmt_acc(acc_t)}")
        print(f"Student (Distilled):   {self._fmt_acc(acc_s)}")
        print("-" * 40)
        print("Student precision by confidence level:")
        for level in self.CONFIDENCE_LEVELS:
            c = self.conf_stats[level]
            if c["total"] > 0:
                pct = c["correct"] / c["total"] * 100.0
                print(f"  {level:8s} {pct:6.2f}% ({c['correct']}/{c['total']} samples)")
            else:
                print(f"  {level:8s}   n/a  (0 samples)")

        # Gap Closure Calculation
        if acc_t is not None and acc_b is not None and acc_s is not None and acc_t > acc_b:
            gap = acc_t - acc_b
            closed = acc_s - acc_b
            closure_pct = (closed / gap * 100.0) if gap > 0 else 0.0
            print(f"Gap Closed:            {closure_pct:.2f}%")
        else:
            print(
                "Gap Closed:            n/a (teacher does not beat baseline; "
                "gap-closure metric is degenerate)"
            )

        self._print_confusion_matrix()
        print("=" * 40)

    def _print_confusion_matrix(self):
        short = {
            "Pathogenic": "P",
            "Likely Pathogenic": "LP",
            "Variant of Uncertain Significance": "VUS",
            "Likely Benign": "LB",
            "Benign": "B",
        }
        print("-" * 40)
        print("Confusion matrix (rows=verified, cols=student):")
        header = "      " + "".join(f"{short[lbl]:>6s}" for lbl in self.LABELS)
        print(header)
        for verified in self.LABELS:
            row = self.confusion[verified]
            cells = "".join(f"{row[student]:6d}" for student in self.LABELS)
            print(f"{short[verified]:>5s} {cells}")
        print("      (P=Pathogenic, LP=Likely Pathogenic, VUS, LB=Likely Benign, B=Benign)")


if __name__ == "__main__":
    import sys

    results_path = sys.argv[1] if len(sys.argv) > 1 else "data/app/student_tbe_results.jsonl"
    eval_engine = TBEMetrics(results_path=results_path)
    eval_engine.process_test_set()
    eval_engine.report()
