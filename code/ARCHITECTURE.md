# Buy or Wait? — Architecture (as shipped)

This describes the system that produced the submitted `output.csv`. Rule IDs (`R1`…`R40`) refer to
`SPEC_RULES.md` and are cited in code comments where each rule is enforced.

## One-paragraph summary

A deterministic engine rebuilds each user's cash position for the 90 days starting on `request_date`. It
uses the ledger (`financial_events.csv`), fixed exchange rates, the user's messages, and amounts read off
images. It then lists every payment plan the request allows, keeps the ones that stay above
`minimum_balance_to_keep`, filters them by the user's accepted payment methods, and ranks them with the
six R16 rules. A model is called for exactly one job: reading the amount on the 16 images attached to
ledger rows whose amount is blank. That output is a fact fed into the forecast. No model produces any
output column.

## Pipeline

```
dataset/*.csv, dataset/media/images/*.png
  │
  ├─ loader.py      CSV -> typed records. Normalizes headers; a missing required column fails with its
  │                 name. Converts every event to home_currency at its settlement-date rate (R21).
  │                 A blank amount stays None, never 0 (R9).
  ├─ images.py      Blank-amount rows only. claude-opus-5 vision + JSON-schema output, cached on disk
  │                 by image_id (code/cache/image_extractions.json). A missing file or no key leaves
  │                 the amount unknown and the run continues (R23, R33).
  ├─ evidence.py    Messages -> typed Delta facts. Rule-based, English + Indonesian keyword patterns,
  │                 regex for amounts and ISO dates. Unrecognized messages -> no_effect (abstain).
  ├─ state.py       Settled history -> recurring Series (cadence, day-of-month, projected amount,
  │                 flexibility, latest event id). Everything else is a one-off.
  ├─ context.py     Per request: projects the series into dated Flows, adds pending/scheduled rows,
  │                 applies income lifecycle and message deltas; every step goes to `trace`.
  ├─ forecast.py    Pure simulation over Flows: lowest balance, amount_safe_to_pay, earliest full-payment
  │                 date, and is_safe(schedule).
  ├─ decision.py    Freezes capacity (R4, R5), builds candidate plans, applies preference gates,
  │                 searches spending changes, ranks by R16, derives status.
  ├─ explain.py     decision_explanation filled into templates from the same numbers as the row.
  ├─ verify.py      Hard invariants, shared by the pipeline (repair before writing) and the evaluation suite.
  └─ pipeline.py    Orchestration, exception fallback row, case files, CSV writer with a fixed column list.
```

`main.py` loads `.env` / `.env.local`, runs the pipeline, writes `output.csv` at the repo root, and
writes `evaluation/usage_report.md` for that exact run.

## Forecast conventions

The problem statement leaves some mechanics open. Each choice below was checked against the 25 solved
rows as a structural question (which reading reproduces the solved dates and plans), not by fitting a
number.

| Question | Choice | Evidence |
|---|---|---|
| Forecast window | `request_date` … `request_date + 86` | See "Choosing the window" below |
| Flows on `request_date` | Included | request_06 reserves rent due on the request date; excluding them matched fewer solved earliest dates (13 vs 15 in the early calibration grid) |
| Same-day ordering | Credits first, then bills, then plan payments | Solved earliest dates fall *on* paydays (the 15th), not the day after. Also swept debits-first (119) and variable-spending-before-credit (121) against credits-first (122) |
| Pending / scheduled debits | Reserved on their settlement date (R7) | — |
| Pending credits, refunds, bonuses, prizes, unrealized value | Never counted (R7) | — |
| Failed / cancelled rows | Ignored (R7). Tested reserving an outstanding failed bill; it made request_25 worse | request_25 |
| Variable spending amount | Mean of all settled occurrences | Sweep below |
| Income amount | Latest settled amount, not an average of past raises and cuts | request_06, request_08 |

### Choosing the window

Once a user has no income left in the window, the low point is the last flow of the window, so the
window length sets `amount_safe_to_pay` directly. Two solved no-income rows fix where the window ends:
- **request_05:** the solved reserve is reached just before rent on day +88.
- **request_10:** the solved reserve is reached just before rent on day +87, and it includes spending
  on day +84.
- **request_09:** rent on day +90 is also excluded.

Together these place the last day in +84 … +86. A sweep of the window end on the 25 solved rows:

| Last day in window | amount ±2% | status | method | plan | earliest | changes | total |
|---|---|---|---|---|---|---|---|
| +89 | 8 | 21 | 22 | 21 | 18 | 21 | 111 |
| +88 | 8 | 21 | 22 | 21 | 18 | 21 | 111 |
| +87 | 8 | 22 | 23 | 22 | 19 | 21 | 115 |
| **+86 (shipped)** | 9 | 23 | 24 | 23 | 21 | 22 | **122** |
| +79 … +85 | 9 | 23 | 24 | 23 | 21 | 22 | 122 |

The shipped window is the widest one consistent with the evidence, so it is the most conservative. It
fixes request_08, request_12 and request_13, which previously fell short on the window's last day, and
breaks no row. Moving from +89 to +86 changes 23 of the 250 predictions; the choice within +84 … +86
changes 7.

### Choosing the smoothing definition

A sweep over the recurring-amount definition, per-field matches on the 25 solved rows (run with the earlier +89 window; the ranking is what matters):

| Definition | amount ±2% | status | method | plan | earliest | changes | total |
|---|---|---|---|---|---|---|---|
| **mean of all (shipped)** | 8 | 21 | 22 | 21 | 18 | 21 | **111** |
| median of last 3 | 8 | 19 | 20 | 19 | 18 | 22 | 106 |
| mean of last 3 | 7 | 19 | 20 | 19 | 18 | 21 | 104 |
| last observed | 6 | 18 | 19 | 18 | 18 | 21 | 100 |
| max of last 3 / last 5 / all | 3 | 13–14 | 14–15 | 13–14 | 13 | 21–22 | 78–80 |

The error on `amount_safe_to_pay` is spread, not bias. Over the 21 rows where the truth is strictly
between 0 and the requested amount, 11 over-predict and 10 under-predict, and the median ratio
(ours / truth) is 1.002. The solved amounts come from the generator's own base amounts, and the ledger
only shows those plus noise (request_22 reserves exactly 157.00 before payday). A history-based estimate
lands within a few percent but rarely within 2%.

A second hypothesis was also checked and rejected: that the rows we under-predict are really capped at
`requested_amount` in truth. Only 4 of 25 solved rows are capped (request_01, 09, 12, 16), and we match
3 of those exactly. The round solved values (1,425,000; 873,000; 5,400) are not requested amounts. "Conservative max" estimators push every row
pessimistic and lose 30 structural points, so the shipped estimate is the unbiased mean. See Known
limitations.

## Recurring-series detection (R34)

- Candidates are settled debits and credits that are not refunds, investment rows, windfalls, work
  reimbursements, or rows linked to an earlier lifecycle event.
- **Pass 1:** the whole category is one regular stream. Monthly means intervals of 27–32 days. Every-k-days
  means all intervals within ±1 day of the median. Needs at least 3 occurrences.
- **Pass 1b:** the category is regular apart from a few off-cadence one-offs (for example a large invoice
  read from an image). The engine walks back from the latest events along the most common interval and
  accepts the chain if it covers at least 75% of the events.
- **Pass 2:** split by description (base payroll next to commission, arrears or bonus rows).
- A monthly stream whose latest occurrence slipped (a delayed payroll, up to 45 days) still counts as monthly.

## Income lifecycle and evidence

Income is where messages matter, so it gets explicit rules, each written to `trace`:

- A series whose latest row reads like a final payroll ("Final employer payroll") is not projected.
- A credit series that has missed an expected occurrence before `request_date` is treated as stopped
  (R19). Example: a second household income that skipped a month.
- A scheduled "Next confirmed salary" replaces the nearest projected payroll. With no payroll history it
  starts a monthly stream. A first salary confirmed by message follows the same rule when no payroll stream
  continues after it (request_15: two prior "First-job payroll" credits are one short of the recurrence gate). If its amount differs from settled payroll, only that one payroll uses the new
  amount; later months stay at the settled figure, and the trace says so.
- Message deltas are applied oldest first, and only if `sent_at <= request_date`:

| Intent | Effect |
|---|---|
| employment ended / seasonal contract ended | remove projected salary |
| salary raise "applies from DATE" | new amount from DATE (explicit amendment, R17 rung 1) |
| next salary reduced / temporary pay / regular salary confirmed | new amount carried forward (latest confirmed pay) |
| salary with one-time arrears | next payroll = base + arrears, then base |
| salary date moved | next payroll moves to DATE |
| salary resumes on DATE | monthly salary from DATE |
| first salary / foreign-currency salary confirmed for DATE | credit on DATE, converted at that date's rate; continues monthly if no payroll stream follows it |
| approved invoice, settlement DATE | one credit on DATE; unapproved invoices excluded |
| rent increases by N% | projected rent raised N% |
| household income ended / base salary with commission pending | drop the other income streams; keep the settled payroll amount (see below) |
| bonus pending, gig payout pending, prize processing, refund pending, portfolio value moved, internal transfer, duplicate charge under dispute, scam "pay a release fee" | no cash-flow change, logged |

**Conflict resolution (R17), worked example.** "Your confirmed base salary is X" messages state about
1.67× the base payroll actually settled every month in the ledger. The message has no effective date, so
it is not an explicit amendment. R17 rung 3 (a settled event beats an estimate) keeps the ledger amount.
Solved request_11 only reproduces under that reading.

**Why no retrieval layer.** The plan called for TF-IDF retrieval to attach orphan messages. The data made
it unnecessary: every user has exactly one request, so the 76 messages without a request or event id
still belong to exactly one request through `user_id`. All 215 messages match one of about 25 templates,
and all 215 classify with the rule set, with no `no_effect` abstentions on this dataset. Retrieval would
have added a failure mode without adding a correct attachment.

**Untrusted content (R18).** Messages and images only produce typed facts (amount, date, intent). They
never reach a scored field directly, so an embedded instruction has nothing to act on. The scam template
is classified and ignored, and the image prompt says the document is untrusted evidence.

## Decision

1. **Capacity, frozen first (R4, R5).**
   - `amount_safe_to_pay` = min(requested amount, max(0, lowest projected balance − minimum)).
   - `earliest_date_for_full_payment` = the first day in the window on which one full payment keeps every
     later balance at or above the minimum.
   - Both are computed from the baseline flows and stored in a frozen dataclass before preferences or
     spending changes are considered.
2. **Candidate plans.**
   - Full payment today.
   - Every supplied installment option, with its schedule rebuilt from its own fields (R13).
   - Partial payment: `amount_safe_to_pay` today plus the remainder on the earliest date (R12).
   - Wait: full payment on the earliest date.
3. **Gates.**
   - Each method must appear in `payment_methods_user_will_consider` (R10).
   - Wait requires `full_payment` acceptance.
   - Installments need a non-blank `max_installment_months` and a payment count within it (R35).
   - Partial payment requires all four R12 conditions.
   - Every plan must finish by `desired_completion_date` and pass `is_safe` over the whole window.
4. **Spending changes (R15)** are searched only when no plan passes without them (R16 rule 2).
   - Changeable series: not in a protected category, flexibility `reducible`/`stoppable`, and a category
     the user allows for that verb.
   - Stop removes every projected occurrence. `reduce_to` sets them to `minimum_allowed_amount`, or the
     lowest observed amount if none is given.
   - Up to 3 changes per plan; stop and reduce on the same series are alternatives, never combined.
   - The emitted event id is the latest settled historical event of the series, which is the convention
     in all four solved spending changes.
5. **Ranking** uses R16 in its exact order. Status is `affordable_now` for full payment today with no
   changes, `affordable_with_plan` for partial payment, installments or any spending change,
   `affordable_later` for wait, and `not_affordable` otherwise.

### Spending-change tiebreak (our principle, not the spec's)

When several change sets make the same payment safe, they tie on all six R16 rules. The engine picks the
set that takes the least money from the user over the 90-day forecast, then the fewest changes, then
the lowest event ids. It covers the shortfall with the smallest disruption.

Hand-checked against the three solved spending-change rows, using each row's *solved* shortfall and low
point, the principle picks the solved answer every time:
- **request_06:** stopping streaming is the only permitted change that lands before payday.
- **request_11:** reducing dining alone covers the gap. Entertainment falls after the low point, and
  cloud storage alone is too small.
- **request_21:** the solved answer, stop cloud storage plus reduce streaming, takes less over 90 days
  than either single cut that would also work (stop streaming, or reduce shopping).

Our own rows match only where our shortfall estimate matches. On request_11 our larger estimated gap
needs cloud storage plus dining. On request_21 we over-estimate headroom and pay in full with no change.

Each case file's `spending_change_review` lists every permitted change with the amount it frees before
the low point, its 90-day cost, whether it covers the gap alone, and whether it was chosen.

## Explanations

The explanation text is a template filled from the decision object: amount, minimum, schedule, change
descriptions, and the safe amount without changes. It cannot contradict the other seven columns.

## Verification and robustness

- `verify.check_row` enforces:
  - amount bounds (R1) and the `affordable_now` date rule (R2)
  - plan format and chronological order (R14)
  - partial-payment structure and exact sum (R12)
  - installment plans matching a supplied option exactly (R13)
  - method acceptance (R10)
  - spending-change cardinality, format, flexibility, permission and floor (R15)
- A row that breaks a hard rule is replaced by a conservative `not_recommended` row and counted. An
  exception in one request produces the same fallback, and the other rows still write (R22, R23).
- Final run: 0 fallbacks, 0 invariant failures on 250 rows. The same checks pass on all 25 solved rows,
  which validates the checks themselves.
- Runs fully offline. With no key, blank image amounts stay unknown: a pending bill is not reserved, and
  a settled one simply drops out of the series average.

## Case files

`code/case_files/<request_id>.json`, one per request:
- request and profile (native numbers, booleans, ISO dates)
- frozen capacity, with the binding constraint as a window, e.g.
  `"2026-07-04→2026-07-15 pre-payday run, 20,161.15 of bills"`
- detected series, applied evidence, and the full trace
- every projected flow and the spending-change review
- every candidate plan with its eligibility, safety and deadline flags and notes
- the output row and any verification findings

## Model usage and cost

- **Calls:** one call per blank-amount image, 16 in total, to `claude-opus-5` with low effort and a
  JSON-schema output.
- **Cache:** results are cached by `image_id`, so a rerun makes no calls.
- **Reporting:** `usage_report.md` covers both live calls and cache replays, including the cold-cache cost.
- **Cold run:** about 41k tokens, about $0.26 in total, about $0.001 per request.
- **Prompt:** `prompts/image_amount_extraction.md`.

## Known limitations

- **Amount precision.** Variable spending is estimated from noisy history, and the low point sums many
  such estimates. That lands within a few percent of the solved amount, but only 9 of 25 are within 2%.
  Rows whose margin is smaller than that error can flip status: request_06 is short by 79, and
  request_21 is over by 31. The over-predicting rows share no missing reserve. Payday-ordering
  variants explain parts of request_02, 13 and 18 but break others, and request_03, 14, 20 and 21 have
  no payday debit, recent one-off or missed bill to account for the gap.
- **Gig income** (weekly or irregular payouts) is never projected. With no income, request_10's safe
  amount rests entirely on its spending estimate, which comes out low (32,527 vs 12,700); its status
  still matches.
- **Undated "confirmed salary" statements** defer to settled payroll. That is correct on the solved row
  but is a judgment call on unseen ones.
- **Unknown-amount obligations.** A "new recurring childcare payment" mentioned without an amount is
  logged but not reserved, because there is no amount to reserve.

## Running

```bash
pip install -r code/requirements.txt
python code/main.py                   # -> ./output.csv, code/evaluation/usage_report.md, code/case_files/
python code/evaluation/run_all.py     # sample scores, invariants, distribution check
```
