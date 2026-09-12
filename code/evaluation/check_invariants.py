"""Invariant suite: every [VERIFY] rule over output.csv (no labels needed), plus the same rules
asserted against the 25 solved sample rows. A solved row failing an invariant means the
invariant is wrong, not the data. Writes evaluation/invariant_report.md.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buyorwait.config import EVAL_DIR, output_path  # noqa: E402
from buyorwait.loader import load  # noqa: E402
from buyorwait.verify import COLUMNS, check_row  # noqa: E402


def main() -> int:
    ds = load()
    out = output_path()
    lines = ["# Invariant report", ""]
    fails = 0
    with open(out, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames
        rows = list(reader)
    req_ids = [r.request_id for r in ds.requests]
    by_req = {r.request_id: r for r in ds.requests}
    lines.append(f"- R22 header exact: {'PASS' if header == COLUMNS else 'FAIL ' + str(header)}")
    lines.append(f"- R22 row count {len(rows)} == {len(req_ids)}: {'PASS' if len(rows) == len(req_ids) else 'FAIL'}")
    lines.append(f"- R22 ids unique and complete: {'PASS' if sorted(r['request_id'] for r in rows) == sorted(req_ids) else 'FAIL'}")
    fails += (header != COLUMNS) + (len(rows) != len(req_ids))
    lines += ["", "## Row-level rules on output.csv", ""]
    row_fail = 0
    for row in rows:
        req = by_req.get(row["request_id"])
        if req is None:
            continue
        errs = check_row(row, req, ds.profiles[req.user_id], ds.options.get(req.request_id, []), ds.events.get(req.user_id, []))
        if errs:
            row_fail += 1
            lines.append(f"- {row['request_id']}: {'; '.join(errs)}")
    lines.append(f"\nRows failing any invariant: {row_fail}/{len(rows)}")
    fails += row_fail
    lines += ["", "## Same rules against solved sample rows (checks the invariants themselves)", ""]
    s_fail = 0
    for req in ds.samples:
        row = {"request_id": req.request_id, **{k: req.solved.get(k, "") for k in COLUMNS[1:]}}
        errs = check_row(row, req, ds.profiles[req.user_id], ds.options.get(req.request_id, []), ds.events.get(req.user_id, []))
        if errs:
            s_fail += 1
            lines.append(f"- {req.request_id}: {'; '.join(errs)}  <- invariant may be wrong")
    lines.append(f"\nSolved rows failing an invariant: {s_fail}/{len(ds.samples)}")
    fb = [r["request_id"] for r in rows if "forecast could not be completed" in r["decision_explanation"]]
    lines.append(f"\nFallback rows (exception path): {len(fb)} {fb}")
    text = "\n".join(lines) + "\n"
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DIR / "invariant_report.md").write_text(text, encoding="utf-8")
    print(text)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
