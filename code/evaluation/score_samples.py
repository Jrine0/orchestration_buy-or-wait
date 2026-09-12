"""Per-field scoring against the 25 solved rows in dataset/sample_requests.csv.

Smoke test and format oracle, not a fitting target (see evaluation/README.md).
Writes evaluation/sample_scores.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buyorwait.config import EVAL_DIR  # noqa: E402
from buyorwait.loader import load  # noqa: E402
from buyorwait.pipeline import run  # noqa: E402

FIELDS = ["amount_safe_to_pay", "affordability_status", "recommended_payment_method", "payment_plan",
          "earliest_date_for_full_payment", "spending_changes_needed"]


def amount_ok(a: str, b: str, tol=0.02) -> bool:
    fa, fb = float(a or 0), float(b or 0)
    return abs(fa - fb) <= max(0.01, tol * max(abs(fb), 1e-9))


def main() -> int:
    ds = load()
    res = run(ds.samples, ds, write_cases=False)
    hits = {f: 0 for f in FIELDS}
    exact_amount = 0
    lines = ["# Sample scores", "", f"Rows: {len(res.rows)}", "",
             "| request | amount (ours / truth) | status | method | plan | earliest | changes |", "|---|---|---|---|---|---|---|"]
    detail = []
    for row, req in zip(res.rows, ds.samples):
        t = req.solved
        ok = {
            "amount_safe_to_pay": amount_ok(row["amount_safe_to_pay"], t["amount_safe_to_pay"]),
            "affordability_status": row["affordability_status"] == t["affordability_status"],
            "recommended_payment_method": row["recommended_payment_method"] == t["recommended_payment_method"],
            "payment_plan": row["payment_plan"] == t["payment_plan"],
            "earliest_date_for_full_payment": row["earliest_date_for_full_payment"] == t["earliest_date_for_full_payment"],
            "spending_changes_needed": row["spending_changes_needed"] == t["spending_changes_needed"],
        }
        exact_amount += abs(float(row["amount_safe_to_pay"]) - float(t["amount_safe_to_pay"])) < 0.011
        for f in FIELDS:
            hits[f] += ok[f]
        mark = lambda f: "ok" if ok[f] else "**x**"  # noqa: E731
        lines.append(f"| {req.request_id} | {row['amount_safe_to_pay']} / {t['amount_safe_to_pay']} {mark('amount_safe_to_pay')} | "
                     f"{mark('affordability_status')} | {mark('recommended_payment_method')} | {mark('payment_plan')} | "
                     f"{mark('earliest_date_for_full_payment')} | {mark('spending_changes_needed')} |")
        bad = [f for f in FIELDS if not ok[f]]
        if bad:
            detail.append(f"- {req.request_id}: first mismatch `{bad[0]}` — ours `{row[bad[0]]}` vs truth `{t[bad[0]]}`"
                          + (f"; also {', '.join(bad[1:])}" if bad[1:] else ""))
    n = len(res.rows)
    summary = ["", "## Per-field pass rate", ""] + [f"- {f}: {hits[f]}/{n}" for f in FIELDS] + \
              [f"- amount_safe_to_pay exact to the cent: {exact_amount}/{n}", f"- fallback rows: {len(res.fallbacks)}",
               "", "Amount passes within 2% of truth.", "", "## First mismatching field per row", ""] + detail
    text = "\n".join(lines + summary) + "\n"
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DIR / "sample_scores.md").write_text(text, encoding="utf-8")
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
