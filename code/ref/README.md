# Evaluation workflow

Three independent checks. They catch different classes of error, and only the
first one needs labels — which matters, because labels exist for 25 of 250 rows
and the graded set is the hidden 250.

Run all three with:

```bash
python3 evaluation/run_all.py
```

Artifacts land in `evaluation/` and are regenerated on every full run.

---

## 1. Sample scoring — `score_samples.py`

Scores the pipeline against the 25 solved rows in `dataset/sample_requests.csv`,
**per field**, and prints the first mismatching field per row.

Output: `evaluation/sample_scores.md`

What it is for:

- **Structural errors.** Which *field* is wrong matters more than by how much.
  A 3% miss on `amount_safe_to_pay` is a smoothing issue. A wrong
  `recommended_payment_method` is a rule that is not implemented.
- **Format oracle.** Decimal places, `none` vs empty string, date format,
  explanation length and style. Exact-match these; they are free points.

What it is **not** for: fitting constants. Twenty-five rows is 10% of the graded
set, the known weak spots are category-dependent rather than row-dependent, and
tuning parameters until they fit 25 rows is the standard way to be locally
optimal and globally wrong. Treat a per-field pass rate as a smoke test, not a
target to maximize.

---

## 2. Invariant suite — `check_invariants.py`

Runs every `[VERIFY]` rule in `../SPEC_RULES.md` against all 250 output rows,
independent of ground truth.

Output: `evaluation/invariant_report.md`

Checks include: row count and uniqueness, exact column order, amount bounds,
`affordable_now` ⇒ `earliest_date_for_full_payment == request_date`,
partial-payment two-payment structure and exact sum, installment plans matching
a supplied option, spending-change cardinality/verbs/flexibility/floors,
recommended methods present in the user's accepted methods, chronological plan
ordering, enum validity.

Also asserted against the 25 solved rows. **A ground-truth row that fails one of
our invariants means the invariant is wrong**, not the data. That inversion has
caught more spec misreadings than the scorer has.

Reports the **fallback firing count** — how many rows were produced by the
last-resort exception path rather than by the engine. This should be
approximately zero; anything more means something upstream is broken.

---

## 3. Distribution check — `check_distributions.py`

Compares the shape of all 250 predictions against the 25 solved samples. No
labels required.

Output: `evaluation/distribution_report.md`

Compared: `affordability_status` mix, `recommended_payment_method` mix, fraction
with `none` for `spending_changes_needed`, fraction with an empty
`earliest_date_for_full_payment`, payment-plan length histogram, distribution of
`amount_safe_to_pay / requested_amount`.

This is the only check that can find a **systematic** bug on the hidden 90%. If
the 250 come out 60% `not_affordable` while the samples are 20%, something is
wrong at the rule level, and it is visible without a single ground-truth value.

---

## Supporting reports

- `evaluation/dataset_report.md` — reconnaissance counts over the dataset
  (events per user, blank amounts, orphan messages/images, requests with no
  payment options, distinct enum values, currency-pair coverage). Several design
  decisions depend on these numbers.
- `evaluation/schema_report.md` — the resolved input-header mapping from the
  loader: which canonical field matched which actual column, and which optional
  fields were absent and therefore degraded.
- `evaluation/usage_report.md` — token and cost accounting for the final
  full-dataset run that produced `output.csv`. Regenerated automatically, so it
  always corresponds to that run.
- `code/case_files/<request_id>.json` — per-request reasoning trace: the fact
  set with provenance, every candidate plan and why it was or was not safe, the
  binding constraint, recurring series detected, retrieval scores and
  abstentions, and which conflict-resolution rung fired.
