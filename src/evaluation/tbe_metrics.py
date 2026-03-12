import json
from pathlib import Path
from typing import Dict, List, Any

class TBEMetrics:
    """
    ZDS-ID: TOOL-703 (Triadic Benchmark Evaluation)
    The primary acceptance testing engine for distilled MedTech models.
    """
    
    def __init__(self, results_path: str):
        self.results_path = Path(results_path)
        self.stats = {
            "baseline": {"correct": 0, "total": 0, "high_conf_correct": 0, "high_conf_total": 0},
            "teacher":  {"correct": 0, "total": 0, "high_conf_correct": 0, "high_conf_total": 0},
            "student":  {"correct": 0, "total": 0, "high_conf_correct": 0, "high_conf_total": 0}
        }

    def process_test_set(self):
        """
        Iterates through the test set results and computes accuracies.
        Each test result must contain:
        - verified_label: Pathogenic, Likely Pathogenic, etc.
        - baseline_label: InterVar classification.
        - teacher_label: R1 classification.
        - student_label: Distilled Qwen classification.
        - student_confidence: High, Medium, or Low.
        """
        if not self.results_path.exists():
            print(f"Error: {self.results_path} not found.")
            return

        with open(self.results_path, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                
                row = json.loads(line)
                verified = row["verified_label"]
                
                # Check Baseline
                self.stats["baseline"]["total"] += 1
                if row["baseline_label"] == verified:
                    self.stats["baseline"]["correct"] += 1
                
                # Check Teacher
                self.stats["teacher"]["total"] += 1
                if row["teacher_label"] == verified:
                    self.stats["teacher"]["correct"] += 1
                
                # Check Student
                self.stats["student"]["total"] += 1
                if row["student_label"] == verified:
                    self.stats["student"]["correct"] += 1
                    
                # High-Confidence Tracking (Student)
                if row.get("student_confidence") == "High":
                    self.stats["student"]["high_conf_total"] += 1
                    if row["student_label"] == verified:
                        self.stats["student"]["high_conf_correct"] += 1

    def _calc_acc(self, model_key: str) -> float:
        s = self.stats[model_key]
        return (s["correct"] / s["total"] * 100.0) if s["total"] > 0 else 0.0

    def report(self):
        print("="*40)
        print("TBE PERFORMANCE REPORT (ZDS-ID: TOOL-703)")
        print("="*40)
        
        acc_b = self._calc_acc("baseline")
        acc_t = self._calc_acc("teacher")
        acc_s = self._calc_acc("student")
        
        s = self.stats["student"]
        acc_s_high = (s["high_conf_correct"] / s["high_conf_total"] * 100.0) if s["high_conf_total"] > 0 else 0.0

        print(f"Baseline (InterVar):   {acc_b:.2f}%")
        print(f"Teacher (R1):          {acc_t:.2f}%")
        print(f"Student (Distilled):   {acc_s:.2f}%")
        print("-"*40)
        print(f"Student High-Conf:     {acc_s_high:.2f}% ({s['high_conf_total']} samples)")
        
        # Gap Closure Calculation
        if acc_t > acc_b:
            gap = acc_t - acc_b
            closed = acc_s - acc_b
            closure_pct = (closed / gap * 100.0) if gap > 0 else 0.0
            print(f"Gap Closed:            {closure_pct:.2f}%")
        
        print("="*40)

if __name__ == "__main__":
    # Test path - will be populated after Stage 7 (Evaluation)
    eval_engine = TBEMetrics(results_path="data/app/student_tbe_results.jsonl")
    # eval_engine.process_test_set()
    # eval_engine.report()
