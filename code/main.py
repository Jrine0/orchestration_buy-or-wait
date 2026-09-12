"""Buy or Wait? — entry point.

    python code/main.py                 # all requests in dataset/requests.csv -> ./output.csv
    python code/main.py --samples       # solved samples -> code/evaluation/sample_output.csv
    python code/main.py --no-images     # skip model calls entirely (offline, cache still replayed if present)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from buyorwait.config import EVAL_DIR, load_env_files, output_path  # noqa: E402
from buyorwait.loader import load  # noqa: E402
from buyorwait.pipeline import run, write_csv  # noqa: E402
from buyorwait.usage import UsageTracker  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", action="store_true", help="run on sample_requests.csv instead")
    ap.add_argument("--no-images", action="store_true", help="do not call the vision model")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()
    keys = load_env_files()
    if keys:
        print(f"loaded env vars from .env files: {sorted(set(keys))} (values not shown)")

    ds = load()
    usage = UsageTracker()
    reqs = ds.samples if args.samples else ds.requests
    res = run(reqs, ds, usage=usage, use_images=True, write_cases=not args.samples) if not args.no_images else \
        run(reqs, ds, usage=usage, use_images=False, write_cases=not args.samples)
    out = Path(args.output) if args.output else (EVAL_DIR / "sample_output.csv" if args.samples else output_path())
    write_csv(res.rows, out)
    for line in res.image_log:
        print("[image]", line)
    print(f"wrote {len(res.rows)} rows -> {out}")
    print(f"fallback rows: {len(res.fallbacks)} {res.fallbacks[:10]}")
    if res.violations:
        print(f"rows with verification findings: {len(res.violations)}")
        for k, v in list(res.violations.items())[:10]:
            print("  ", k, v[:3])
    if not args.samples:
        EVAL_DIR.mkdir(parents=True, exist_ok=True)
        (EVAL_DIR / "usage_report.md").write_text(usage.report(len(reqs)), encoding="utf-8")
        print(f"usage report -> {EVAL_DIR / 'usage_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
