#!/usr/bin/env python3
"""
Early-stopping watchdog for the genomics_v2 MLX training run.

Tails the newest logs/training/*.log file and stops the training process when:

  a) validation loss has not improved for PATIENCE consecutive evaluations
     (after MIN_ITERS), or
  b) MAX_ITERS is reached (hard cap so the evaluation pipeline can still run
     before morning), or
  c) the training process exits on its own.

Stops training with `pkill -f "mlx_lm lora"`. The wrapper script
(train_mlx.sh) then exits normally; the checkpoints saved so far (every 200
iters) remain on disk for checkpoint selection.
"""

import re
import subprocess
import sys
import time
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs" / "training"
MIN_ITERS = 250  # never stop before this
PATIENCE = 3  # consecutive non-improving val evals before stopping
MAX_ITERS = 450  # hard cap (time budget for eval pipeline)
POLL_SECONDS = 60

VAL_RE = re.compile(r"Iter (\d+): Val loss ([\d.]+)")
TRAIN_RE = re.compile(r"Iter (\d+): Train loss")


def latest_log() -> Path | None:
    logs = sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None


def training_running() -> bool:
    result = subprocess.run(["pgrep", "-f", "mlx_lm lora"], capture_output=True, text=True)
    return result.returncode == 0


def main() -> None:
    print(
        f"Watchdog started: min_iters={MIN_ITERS} patience={PATIENCE} " f"max_iters={MAX_ITERS}",
        flush=True,
    )
    seen_val: list[tuple[int, float]] = []
    max_train_iter = 0

    while True:
        if not training_running():
            print("Training process no longer running. Watchdog exiting.", flush=True)
            return

        log = latest_log()
        if log is not None:
            text = log.read_text(errors="replace")
            for match in VAL_RE.finditer(text):
                seen_val.append((int(match.group(1)), float(match.group(2))))
            for match in TRAIN_RE.finditer(text):
                max_train_iter = max(max_train_iter, int(match.group(1)))
            # Deduplicate (log is re-scanned each poll).
            seen_val = sorted(set(seen_val))

        if seen_val:
            best_iter, best_loss = min(seen_val, key=lambda t: t[1])
            last_iter, last_loss = seen_val[-1]
            evals_since_best = sum(1 for it, _ in seen_val if it > best_iter)
            print(
                f"[status] train_iter={max_train_iter} val_evals={len(seen_val)} "
                f"best={best_loss:.4f}@{best_iter} last={last_loss:.4f}@{last_iter} "
                f"evals_since_best={evals_since_best}",
                flush=True,
            )
            if last_iter >= MIN_ITERS and evals_since_best >= PATIENCE:
                print(
                    f"[STOP] Val loss has not improved for {PATIENCE} evals "
                    f"(best {best_loss:.4f} @ iter {best_iter}). Early stopping.",
                    flush=True,
                )
                subprocess.run(["pkill", "-f", "mlx_lm lora"])
                return

        if max_train_iter >= MAX_ITERS:
            print(
                f"[STOP] Hard cap reached at iter {max_train_iter} "
                f"(MAX_ITERS={MAX_ITERS}). Stopping training.",
                flush=True,
            )
            subprocess.run(["pkill", "-f", "mlx_lm lora"])
            return

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
