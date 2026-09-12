# BUILD_PLAN.md

Working document. Delete before zipping, or keep it — it shows rigor either way,
but it is not part of the graded deliverable set.

Ordering is by points-per-hour given the 10/30/30/30 split. Spec-rule
correctness first, because those failures are binary and visible to a human
reading the code. Tuning last, because it is worth a fraction of one component.

---

## Phase 0 — Reconnaissance (do this first, ~30 min)

Do not design around risks you have not measured. Run these counts and write the
answers into `evaluation/dataset_report.md`. Several later decisions depend on
them, and the numbers are good interview material.

1. Events per user: distribution, minimum, bottom decile.
2. Requests whose `user_id` has no row in `financial_profiles.csv`. Expect 0.
3. Users with fewer than three events in any single category — the **thin
   category** risk, which is the realistic version of sparse data and hits many
   rows at once via phantom recurring debits.
4. Events with a blank `amount`.
5. Messages with only a `user_id` (no `related_event_id`, no `request_id`).
   Same count for images. This is the true size of the retrieval problem.
6. Requests with zero rows in `request_payment_options.csv`. If a user accepts
   only `installments` and no option exists, `not_recommended` may be the
   correct answer rather than a bug.
7. Distinct values of: `request_type`, event category, event flexibility,
   `payment_methods_user_will_consider`. These drive `R24` and the runtime
   synonym vocabulary.
8. Do messages/images carry a date? If so, count any dated **after** their
   request's `request_date`. Using future-dated evidence as known fact is
   leakage; the rule is record date ≤ `request_date`, though the *effect* may
   land in the future.
9. Currency pairs needed vs pairs present in `exchange_rates.csv`.
10. Exact formatting in `sample_requests.csv`: decimal places on amounts,
    `none` vs empty for each column, explanation length and sentence style.

---

## Phase 1 — Spec compliance (highest value)

### 1.1 Schema-lock writer + verification pass
- **Do:** fixed column list and order, one row per `request_id`, normalized
  value formatting, all `[VERIFY]` rules from `SPEC_RULES.md` asserted before
  write, repairs logged.
- **Accept:** running on the 25 samples produces 25 rows that pass every
  invariant; running on 250 produces exactly 250 rows plus header.
- **Why first:** everything downstream is validated by it, and it is trivial to
  build and catastrophic to skip.

### 1.2 `payment_methods_user_will_consider` eligibility gate (R10, R11)
- **Do:** intersect the safe-plan set with the user's accepted methods *after*
  safety is computed. `affordable_now` additionally requires `full_payment`
  acceptance. `wait` requires `full_payment` acceptance.
- **Accept:** no row recommends a method absent from that user's list. Assert it
  as an invariant.
- **Why:** this is the entire personalization axis and its absence is visible to
  a human code reviewer. Highest points-per-hour in the plan.

### 1.3 Freeze ordering (R4, R5)
- **Do:** forecast produces `amount_safe_to_pay` and
  `earliest_date_for_full_payment` before preference filtering and before
  spending-change exploration. Make them structurally immutable after that point
  so a later stage *cannot* write back.
- **Accept:** a test where spending changes are forced on still yields the
  pre-change `amount_safe_to_pay`.

### 1.4 Partial-payment gate and format (R12)
- **Do:** all four conditions, exactly two payments, exact sum, status forced to
  `affordable_with_plan`.
- **Accept:** every `partial_payment` row has a two-entry plan summing to
  `requested_amount` and `earliest_date_for_full_payment <= desired_completion_date`.

### 1.5 Essential/flexible tagging upstream of the forecast (R24)
- **Do:** explicit label on every event, from the event's own flexibility field
  where present, from runtime population statistics where absent. Visible in the
  case file.
- **Accept:** no event enters the forecast untagged; "safe" is well-defined.

### 1.6 Spending changes (R15)
- **Do:** max three, both verbs, flexible recurring only, stop/reduce mutually
  exclusive per event, `reduce_to` clamped at the floor. If the floor equals the
  current amount, drop the candidate rather than emit an invalid entry.
- **Accept:** every emitted entry parses, targets a flexible recurring event,
  and respects its floor.

### 1.7 Installment reconstruction (R13, R16)
- **Do:** rebuild each option's schedule from its own fields including financing
  fee; rank with the six rules verbatim. Confirm the interaction: fee-bearing
  installments lose to full payment under rule 3 when both are safe and
  accepted.
- **Accept:** every installment plan matches a supplied option exactly.

---

## Phase 2 — State reconstruction

### 2.1 Loader exclusions (R7, R8)
Pending credits, failed/cancelled, duplicates, unrealized investments; salary on
settlement date only; lifecycle collapse via `linked_event_id`.
**Accept:** reconstructed opening balance matches the profile balance on rows
where that is checkable.

### 2.2 Conflict-resolution ladder (R17)
Four rungs, explicit, with the firing rung recorded in the case file.

### 2.3 Recurring-series gate
Minimum occurrence count plus coefficient-of-variation before anything is
treated as periodic. This is the phantom-debit fix and it is row-independent, so
it can move many rows at once.

### 2.4 Image tiers + cache (R9, R28)
Tier 1 mandatory, tiers 2 and 3 by link and by retrieval score. Cache by
`image_id`, persist to disk. Offline degradation path that still opens files.
**Accept:** zero blank amounts treated as zero; each PNG read once per full run.

---

## Phase 3 — Retrieval

### 3.1 Runtime-derived vocabulary (R30)
Category synonyms built from the distinct categories in `financial_events.csv`
plus a general lexicon, with character n-gram fallback. No hand-written map.
**Accept:** you can answer "is this hardcoded to the dataset?" with "no, here is
where it is derived."

### 3.2 Abstention
Top-1/top-2 margin threshold; thin margin → abstain → `R17.4`. Series-level
attachment for messages that amend a whole recurring expense.
**Accept:** abstentions appear in case files and do not crash anything.

---

## Phase 4 — Explanation, evaluation, submission

### 4.1 `decision_explanation`
Template over the engine's own facts, citing the balance, the minimum balance,
the binding date and the specific events. Graded on usefulness **and
consistency** with the other seven columns, so it must never be free-generated.

### 4.2 Evaluation workflow (R29)
Three parts, per `evaluation/README.md`: per-field sample scoring, invariant
suite over all 250, distribution check.

### 4.3 `usage_report.md` (R27)
Wired to the token tracker, regenerated on every run, so it always corresponds
to the run that produced `output.csv`. Verify this immediately before zipping.

### 4.4 Header normalization (~20 min, low priority)
Lowercase, strip, collapse separators, regex alias per canonical field, log the
resolved mapping. Nobody is going to feed the program perturbed headers — the
judge has your submission, not a fuzzing harness — so this is insurance, not a
feature. Do not build fuzzy matching.

---

## Phase 5 — Tuning (only if time remains)

Smoothing window, cadence tolerance, reduction sizing. Remember the ceiling:
Output CSV is 30 points and these move a fraction of it. Prefer a spec-derived
rule over a tuned constant every time.

---

## Pre-submission checklist

- [ ] `output.csv` at **repo root**, 250 rows + header, exact column order
- [ ] every `0 <= amount_safe_to_pay <= requested_amount`
- [ ] every installment plan matches a supplied option
- [ ] every spending change targets a flexible recurring expense, ≤ 3 entries
- [ ] `affordable_now` rows have `earliest_date_for_full_payment == request_date`
- [ ] runs end-to-end **with no API key**, producing a complete valid CSV
- [ ] does not crash at import with `dataset/` absent
- [ ] `code.zip` = `code/` only; no venv, no `node_modules`, no `dataset/`, no `.env`
- [ ] `code/evaluation/usage_report.md` matches the final run
- [ ] `code/prompts/` contains every prompt as a file
- [ ] `code/case_files/` from the final run included
- [ ] no keys anywhere in the zip or in `log.txt`
- [ ] `log.txt` present at repo root and current
- [ ] `ARCHITECTURE.md` rewritten to describe what shipped, not what was sketched
