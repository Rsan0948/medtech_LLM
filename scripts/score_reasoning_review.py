#!/usr/bin/env python3
"""
Score community reasoning-integrity verdicts against the 70% criterion.

Input: a plain-text verdict file, one case per line, e.g.

    1: PASS
    2: FAIL (invented CADD score)
    3: BORDERLINE

Blank lines and lines starting with # are ignored. The case numbers refer to
docs/REASONING_REVIEW.md (mapping in data/app/reasoning_review_sample.json).

Usage:
    .venv/bin/python scripts/score_reasoning_review.py verdicts.txt

Exit code 0 if integrity >= 70%, 1 otherwise.
"""

import re
import sys
from pathlib import Path

THRESHOLD = 70.0
VERDICT_RE = re.compile(r"^\s*(\d+)\s*[:\-]\s*(PASS|FAIL|BORDERLINE)", re.IGNORECASE)


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)

    verdicts: dict[int, str] = {}
    for lineno, line in enumerate(Path(sys.argv[1]).read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = VERDICT_RE.match(line)
        if not match:
            print(f"Warning: line {lineno} not parseable, skipped: {line!r}")
            continue
        verdicts[int(match.group(1))] = match.group(2).upper()

    if not verdicts:
        print("No verdicts found.")
        sys.exit(2)

    passes = sum(1 for v in verdicts.values() if v == "PASS")
    fails = sum(1 for v in verdicts.values() if v == "FAIL")
    borderline = sum(1 for v in verdicts.values() if v == "BORDERLINE")
    # BORDERLINE counts as half a pass (conservative rounding down is reported too).
    integrity = (passes + 0.5 * borderline) / len(verdicts) * 100.0
    integrity_strict = passes / len(verdicts) * 100.0

    print(f"Cases scored:  {len(verdicts)}")
    print(f"PASS:          {passes}")
    print(f"FAIL:          {fails}")
    print(f"BORDERLINE:    {borderline}")
    print(f"Integrity (borderline=0.5): {integrity:.2f}%")
    print(f"Integrity (strict passes):  {integrity_strict:.2f}%")
    print(f"Threshold:                  {THRESHOLD:.0f}%")

    ok = integrity >= THRESHOLD
    print(f"Criterion 4 (reasoning integrity >= 70%): {'MET' if ok else 'NOT MET'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
