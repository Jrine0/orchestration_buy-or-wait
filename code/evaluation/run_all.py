"""Run the three evaluation checks in order: sample scoring, invariants, distributions."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    code = 0
    for script in ("score_samples.py", "check_invariants.py", "check_distributions.py"):
        print(f"\n===== {script} =====")
        code |= subprocess.call([sys.executable, str(HERE / script)])
    raise SystemExit(code)
