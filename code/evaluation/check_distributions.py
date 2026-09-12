"""Distribution check: shape of all predictions vs the 25 solved samples. No labels needed;
finds systematic rule-level bugs on the hidden rows. Writes evaluation/distribution_report.md.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buyorwait.config import EVAL_DIR, dataset_dir, output_path  # noqa: E402


def dist(rows, key, fn=None):
    c = Counter((fn or (lambda r: r[key]))(r) for r in rows)
    n = max(len(rows), 1)
    return {k: v / n for k, v in c.items()}


def table(title, a, b):
    keys = sorted(set(a) | set(b), key=str)
    out = [f"### {title}", "", "| value | predictions | samples | gap |", "|---|---|---|---|"]
    for k in keys:
        pa, pb = a.get(k, 0), b.get(k, 0)
        flag = " **check**" if abs(pa - pb) >= 0.15 else ""
        out.append(f"| {k} | {pa:.0%} | {pb:.0%} | {pa - pb:+.0%}{flag} |")
    return out + [""]


def main() -> int:
    with open(output_path(), encoding="utf-8") as fh:
        pred = list(csv.DictReader(fh))
    with open(dataset_dir() / "sample_requests.csv", encoding="utf-8") as fh:
        samp = list(csv.DictReader(fh))
    with open(dataset_dir() / "requests.csv", encoding="utf-8") as fh:
        req = {r["request_id"]: r for r in csv.DictReader(fh)}
    for r in samp:
        req[r["request_id"]] = r

    def ratio(r):
        v = float(r["amount_safe_to_pay"] or 0) / float(req[r["request_id"]]["requested_amount"])
        return "0" if v == 0 else ("1 (full)" if v >= 0.9999 else f"({int(v * 4) / 4:.2f}, {int(v * 4) / 4 + 0.25:.2f})")

    lines = ["# Distribution report", "", f"Predictions: {len(pred)} rows; samples: {len(samp)} rows.",
             "Gaps of 15 points or more are flagged for review.", ""]
    lines += table("affordability_status", dist(pred, "affordability_status"), dist(samp, "affordability_status"))
    lines += table("recommended_payment_method", dist(pred, "recommended_payment_method"), dist(samp, "recommended_payment_method"))
    lines += table("spending_changes_needed is none", dist(pred, "", lambda r: r["spending_changes_needed"] == "none"),
                   dist(samp, "", lambda r: r["spending_changes_needed"] == "none"))
    lines += table("earliest_date_for_full_payment empty", dist(pred, "", lambda r: r["earliest_date_for_full_payment"] == ""),
                   dist(samp, "", lambda r: r["earliest_date_for_full_payment"] == ""))
    lines += table("payment_plan length", dist(pred, "", lambda r: 0 if r["payment_plan"] == "none" else len(r["payment_plan"].split("|"))),
                   dist(samp, "", lambda r: 0 if r["payment_plan"] == "none" else len(r["payment_plan"].split("|"))))
    lines += table("amount_safe_to_pay / requested_amount", dist(pred, "", ratio), dist(samp, "", ratio))
    text = "\n".join(lines)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DIR / "distribution_report.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
