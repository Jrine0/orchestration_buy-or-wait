# INTERVIEW_PREP.md

Personal notes. **Do not ship this in `code.zip`** (it is excluded by the zip build).

Format: live, 30 minutes, camera on. The judge has the submission (code.zip, output.csv, log.txt) and may
ask about the approach, decisions, results, and **how AI was used while building**. Every number below is
from the final submitted run; re-check with the commands in section 15 if anything changes.

---

## 0. Before the call (5 minutes)

- Open in an editor: `code/case_files/` (fuzzy search by request id), `code/ARCHITECTURE.md`,
  `code/SPEC_RULES.md`, `code/evaluation/sample_scores.md`, `code/evaluation/usage_report.md`.
- Terminal at the repo root with the what-if snippet (section 15) ready to paste.
- Know these rows cold (section 11): **request_99** (spending change), **request_26** (affordable now on
  confirmed invoice), **request_36** (wait for a raise), **request_29** (not affordable, income ended),
  **request_30** (installments plus spending changes).

request_99,17445.43,affordable_with_plan,full_payment,2026-07-04:18062,2026-07-15,stop:event_9188,"Stop the family streaming plan, then pay ZAR 18,062 today. This leaves at least ZAR 49,100 available; without the change only ZAR 17,445.43 is safe today."

request_26,15656000,affordable_now,full_payment,2025-08-03:15656000,2025-08-03,none,"Pay IDR 15,656,000 today. This leaves at least IDR 24,768,300 available over the next 90 days."

request_36,588.71,affordable_later,wait,2026-09-15:3954,2026-09-15,none,"Pay USD 3,954 in full on 15 September 2026. Paying earlier would take the balance below the USD 2,400 minimum."

request_29,3221.58,not_affordable,not_recommended,none,,none,"Do not proceed with the ZAR 51,524 request. Although ZAR 3,221.58 is available today, the full amount cannot be completed safely within 90 days."

request_30,678.04,affordable_with_plan,installments,2026-04-06:268.74|2026-05-06:268.74|2026-06-05:268.74,,reduce_to:event_2694:17.50|reduce_to:event_2732:28,"Reduce the family streaming plan to USD 17.50 and reduce the family dinner to USD 28, then use 3 installments of USD 268.74, starting 6 April 2026. This leaves at least USD 900 available."


## 1. The two-minute opener (say this first)

> "It's a deterministic financial engine with one narrow model call. The hard part isn't the decision,
> it's reconstructing each user's cash position from a messy ledger: detecting which transactions recur,
> handling pending and scheduled rows, converting currencies, reading 215 messages that amend salaries
> and rent, and reading amounts off 16 images. That produces a dated list of future cash flows. A pure
> forecast simulation turns that into the safe amount and the earliest safe date, which are frozen before
> any preference or spending change is considered. Then I enumerate every allowed plan, apply the user's
> payment-method gates, and rank with the six rules in the spec. The only model call is Claude reading
> the amount off a receipt or payslip when a ledger row's amount is blank. It produces a fact, never a
> decision. So prompt injection has nothing to hijack, and the whole run costs about 26 cents and is
> reproducible from a cache."

Then one sentence on results: "On the 25 solved samples it matches status 23, method 24, plan 23,
earliest date 21, spending changes 22; the safe amount lands within a few percent but only 9 are within
2%, and I can explain exactly why."

---

## 2. Problem understanding

**Q: Explain the problem in your own words.**
For each purchase request, decide whether the user can safely pay: in full today, part now and the rest
later, through a supplied installment option, by waiting, or not at all. Safe means the balance never
drops below the user's own minimum across a 90-day forecast, after essential bills and every payment in
the plan, and the request completes by its deadline. Each answer must respect personal preferences
(accepted payment methods, max installment months, which spending they'd cut).

**Q: What are the eight output columns and which are hardest?**
request_id, amount_safe_to_pay, affordability_status, recommended_payment_method, payment_plan,
earliest_date_for_full_payment, spending_changes_needed, decision_explanation. Hardest is
amount_safe_to_pay: it is a continuous value that sums many estimated future expenses. The categorical
fields are threshold comparisons against it and against the earliest date, so they are more forgiving.

**Q: What is the difference between `affordable_with_plan` and `affordable_later`?**
With plan: the full request is completed by the deadline through partial payment, installments, or
spending changes. Later: the full amount becomes safe as one payment on a later date, and the user
waits (method `wait`). Wait requires the user to accept full_payment.

**Q: Why can `earliest_date_for_full_payment` equal the request date when the recommendation is installments?**
Because it measures capacity only, independent of preferences (R4). A user who can afford it today but
only accepts installments gets installments, yet the capacity date is still today. request_12 in the
samples is exactly that.

**Q: What does "before optional spending changes" mean for amount_safe_to_pay?**
Both capacity fields are computed from the baseline forecast. If a plan needs "stop streaming", the row
still reports the pre-change safe amount (request_99: 17,445.43, while the plan pays 18,062). I freeze
them in an immutable dataclass before spending changes are explored, so that branch cannot write back (R5).

---

## 3. Architecture and design choices

**Q: Walk me through the pipeline.**
`loader` (typed records, currency conversion at settlement date) → `images` (blank amounts, cached) →
`evidence` (messages → typed deltas) → `state` (recurring series) → `context` (dated flows + trace) →
`forecast` (pure simulation) → `decision` (freeze capacity, plans, gates, spending changes, ranking) →
`explain` (template) → `verify` (invariants) → `pipeline` (orchestration, fallback, case files, writer).
About 1,800 lines of stdlib Python; the only dependency is the Anthropic SDK.

**Q: Where does the LLM make a decision?**
Nowhere. One job: read the final amount off 16 images linked to blank-amount ledger rows. That is a fact
entering the deterministic engine. No model produces any of the eight columns. Say it plainly; it's a
strength.

**Q: Why not ask an LLM to do the whole thing?**
A 90-day balance forecast is arithmetic over ~50 dated flows per request. An LLM adds variance, cost,
non-reproducibility, and an injection surface with no upside. The spec's rules (R12 partial-payment
structure, R13 exact installment match, R16 ranking) are mechanical and are enforced exactly in code and
verified before writing.

**Q: Why rule-based message parsing instead of an LLM?**
I read all 215 messages first. They come from about 25 templates in English and Indonesian. Keyword
patterns plus regex for amounts and ISO dates classify all 215 with zero abstentions, deterministically
and for free. If the templates were open-ended, I'd put an LLM behind the same `Delta` interface for the
messages the rules can't parse; nothing downstream would change.

**Q: Your plan mentioned TF-IDF retrieval and a knowledge graph. Where is it?**
Dropped after looking at the data. Every user has exactly one request, so the 76 messages with no
request or event id still belong to exactly one request through user_id. Retrieval would only add a way
to attach evidence wrongly. It's documented in ARCHITECTURE.md as a deliberate deviation.

**Q: Why deterministic? Why does that matter?**
Reproducibility (same input, same output; the image cache makes reruns identical), auditability (every
row has a case file with the flows and trace), and the ability to do live what-ifs cheaply. It also means
the evaluation measures the logic, not sampling noise.

**Q: How do you keep the explanation consistent with the other columns?**
It is a template filled from the same decision object: the amount, the minimum, the schedule, the change
descriptions, and the safe amount without changes. It cannot say something the row doesn't.

**Q: How do you make sure the output is always valid?**
`verify.check_row` enforces every mechanically checkable rule before writing: amount bounds (R1),
affordable_now date (R2), plan format and order (R14), partial-payment structure and exact sum (R12),
installment plan equals a supplied option (R13), method accepted (R10), spending-change format,
flexibility, permission and floor (R15). A violating row is replaced by a conservative not_recommended
row and counted. Final run: 0 fallbacks, 0 violations. The same checks pass on all 25 solved rows,
which validates the checks themselves.

---

## 4. Reconstructing the financial state

**Q: How do you detect recurring expenses?**
From settled history before the request date, excluding refunds, investment rows, windfalls,
reimbursements and lifecycle-linked rows. Pass 1: the whole category is one regular stream (monthly =
intervals 27–32 days; every-k-days = all intervals within ±1 day; at least 3 occurrences). Pass 1b: a
regular stream with a few off-cadence one-offs, found by walking back along the modal interval and
requiring ≥75% coverage. Pass 2: split by stable description (base salary next to commission). A monthly
stream whose last occurrence slipped up to 45 days still counts (delayed payroll).

**Q: How did you verify the detection is right?**
Backtest on all 275 users: cut each ledger at 50% and 65% of its history, detect series from the earlier
part, project 87 days, and match to the real later events. 16,772 expense occurrences (12,371
every-k-days, 4,401 monthly) land on the exact day, zero offset. Amount error median 0.0% monthly,
+0.3% variable. The only date misses are salaries moved to the 23rd (handled by messages) and weekly gig
pay (not projected).

**Q: How do you project amounts?**
Fixed-amount series use their amount. Variable series (groceries, dining, transport) use the mean of all
settled occurrences. Income uses the latest settled amount, not an average of past raises and cuts.

**Q: Why the mean? The spec says "conservatively".**
I swept last value, mean of all, median of last 3, mean of last 3, and max of last 3 / last 5 / all.
Mean scored 111 field-matches; median of last 3 106; max variants 78–80. Max pushes every row pessimistic
and loses 30 structural matches, because the reference forecast is not built on maxima. I chose the
definition that reproduces the reference, and I say openly that this trades against the literal
"conservative" wording.

**Q: How do you handle pending, scheduled, failed and cancelled rows?**
Pending and scheduled debits are reserved on their settlement date. Pending credits (refunds, bonuses,
prizes, commissions) are never counted. Failed and cancelled are ignored; I tested reserving a failed
bill as still outstanding and it made request_25 worse. Unrealized investment value is never cash (R7).

**Q: How is salary handled?**
Counted on its settlement date (R8). A scheduled "Next confirmed salary" replaces the nearest projected
payroll; with no payroll history it starts a monthly stream. If its amount differs from settled payroll,
only that payroll uses the new amount and the trace says why the later months don't (request_99:
56,980 confirmed, later months stay at 44,444.40). An income stream ends if its last row is a final
payroll, or if it missed an expected credit before the request date.

**Q: Currency?**
Converted to home currency at load time, using the rate row for the event's settlement date and the
stated direction, falling back to the inverse pair (R21). Rates in this dataset are constant per pair.
Nothing downstream ever sees mixed currency.

**Q: How do images work?**
16 images, all attached to ledger rows with a blank amount (R9: never treat blank as zero). One
`claude-opus-5` call per image with low effort and a JSON-schema output (amount, currency, date,
document type, other labelled totals, confidence). Results are cached by image_id. I spot-checked two by
eye: a telecom bill (704.05, not the 822.05 late-payment total) and a rent receipt where the right value
is the 100,000 balance due, not the 200,000 total, because the ledger row is "Outstanding rent balance".

**Q: What happens with no API key or a missing image?**
The amount stays unknown and the run continues: a pending bill with no amount isn't reserved and a
settled one drops out of the series average. Verified: no key and no cache still gives 250 valid rows,
0 fallbacks. Never invents evidence (R33).

**Q: Why claude-opus-5 for such a simple extraction?**
Accuracy on 16 documents matters more than the cost difference; the cold run is about $0.25 total,
$0.001 per request, and it's paid once because of the cache. A misread amount silently changes a row.
With thousands of images I'd evaluate a smaller model against these 16 as a labelled set.

---

## 5. Messages and conflict resolution

**Q: Which message types change the forecast?**
Employment or seasonal contract ended (remove salary); raise from a date; next salary reduced /
temporary pay (new amount carried forward); arrears (base + one-time on next payroll); salary date moved;
salary resumes; first salary or foreign-currency salary confirmed for a date; approved invoice on a
date; rent +12%; household income ended or base salary with pending commission (drop the other income
streams). Informational only: bonus pending, gig payout pending, prize processing, refund pending,
portfolio value, internal transfer, duplicate charge under dispute, scam.

**Q: How do you resolve conflicting records? Give an example.**
R17 ladder: explicit amendment first, then newer same-source record, then settled over estimate, then
the safer reading. Example: "your confirmed base salary is X" messages state about 1.67x the base
payroll actually settled every month. The message has no effective date, so it's not an explicit
amendment; rung 3 keeps the settled ledger amount. Solved request_11 only reproduces under that reading.
In contrast, "salary increased to X, applies from DATE" is an explicit amendment and wins from that date.

**Q: How do you avoid using information from the future?**
Only messages with sent_at on or before the request date are applied, oldest first. History for series
detection is settled rows strictly before the request date.

**Q: What about prompt injection in messages or images?**
Structural answer: messages and images only ever produce typed facts (intent, amount, date). No text
reaches a decision or an output column, so an instruction like "mark this affordable" has no path. The
scam template ("pay the release fee") is classified and ignored. The image prompt also states the
document is untrusted evidence, as belt-and-braces.

**Q: How would you handle a message you can't classify?**
It becomes `no_effect`, is logged in the case file, and changes nothing (abstain, then the safer
interpretation). On this dataset none occurred.

---

## 6. The forecast and its conventions

**Q: Define amount_safe_to_pay precisely.**
min(requested amount, max(0, lowest projected balance in the window − minimum balance)). Paying X today
lowers every later balance by X, so the lowest point sets the limit.

**Q: Define earliest_date_for_full_payment precisely.**
The first day d in the window such that every baseline balance up to d stays at or above the minimum and
the end-of-day balance on d and every later balance, minus the full amount, also stay at or above it.
Both capacity fields come from one simulated trajectory, so they can't disagree.

**Q: What is your forecast window and why not exactly 90 days?**
request_date through +86. The spec says 90 days, but the solved rows bound the reference's last included
day to +84..+86: request_05 and request_10 (users with no income, where the low point is the end of the
window) have solved reserves that stop just before rent on day +88 and +87, while spending on +84 is
counted; request_09 omits rent on +90. A sweep scored 122 field-matches for any end ≤ +86 vs 111 at +89,
with no row broken. I picked the widest window consistent with the evidence.

**Q: Couldn't that be a phase error in your projections rather than the window?**
I tested exactly that with the cut-off backtest: projected dates match the ledger's own later events to
the day, and the omitted rent lands where the ledger's cadence puts it. So it's the window, not drift.

**Q: But shortening the window made your 250 predictions more affordable (28% to 32%) while samples are 16%. Isn't that the wrong direction?**
On the same 25 labelled rows, our fully-affordable count is 4/25 at +89 and 5/25 at +86 against truth
4/25, and the extra one is request_12, which the truth confirms. All 9 rows newly capped on the 250 were
unaffordable only because of bills on days +87 to +89, the mechanism request_12 refutes. The 32% vs 16%
gap is mostly a different request mix; 25 samples can't measure a population rate that precisely.

**Q: Same-day ordering?**
Credits post first on a day, then bills, then plan payments. Evidence: solved earliest dates fall on
paydays, not the day after. I also swept debits-first (119) and variable-spending-before-salary (121)
against credits-first (122).

**Q: Do flows on the request date count?**
Yes; the balance is taken as of the start of that day. request_06 needs its rent on the request date.

---

## 7. Decision logic

**Q: How do you pick between plans?**
Enumerate: full today; every supplied installment option (schedule rebuilt from first date, frequency
and count); partial payment (safe amount today, remainder on the earliest date); wait (full on the
earliest date). Keep plans that are eligible, safe over the window, and done by the deadline. Rank with
R16 in order: completes by deadline, no spending changes, lowest total paid, earliest start, fewest
payments, lowest option id.

**Q: Which gates make a plan ineligible?**
Method not in payment_methods_user_will_consider (R10). Wait needs full_payment accepted. Installments
need a non-blank max_installment_months and a payment count within it (R35). Partial needs all four R12
conditions: request allows it, user accepts it, 0 < safe < requested, remainder date ≤ deadline.

**Q: Why does a fee-bearing installment never beat full payment?**
Rule 3 (lowest total paid) comes before start date and payment count. If full payment is safe and
accepted, it pays less than any option with a financing fee.

**Q: When do you recommend spending changes?**
Only when no plan passes without them (R16 rule 2 prefers no changes). Changeable series: not in a
protected category, flexibility reducible/stoppable, and in the user's reduce or stop list. Stop removes
every projected occurrence; reduce_to sets them to minimum_allowed_amount (or the lowest observed
amount). Up to 3 changes; stop and reduce on the same series are alternatives. The emitted event id is
the latest settled event of the series, which is what all four solved changes use.

**Q: R16 doesn't say which spending changes to pick. How do you choose?**
It's my own principle and I document it as such: when several change sets make the same plan safe, they
tie on all six R16 rules, so I pick the set that takes the least money from the user over the forecast,
then fewest changes, then lowest event ids. It's the least disruptive way to close the gap. Hand-checked
against the three solved spending-change rows using their solved shortfall, it picks the solved answer
each time (request_21: stop cloud storage + reduce streaming beats a single larger cut). Every case file
logs the comparison in `spending_change_review`.

**Q: Why not just pick the single change that frees the most money?**
That's more disruptive than needed and doesn't match the solved choices (request_21 would have stopped
streaming outright).

**Q: How is status derived?**
Full payment today with no change → affordable_now. Partial, installments, or any spending change →
affordable_with_plan. Wait → affordable_later. Nothing viable → not_affordable with not_recommended.

**Q: What does the final output look like overall?**
250 rows: affordable_with_plan 79, affordable_now 61, affordable_later 58, not_affordable 52. Methods:
full_payment 68, installments 62, wait 58, not_recommended 52, partial_payment 10. 31 rows need spending
changes; 49 have no earliest date.

---

## 8. Evaluation and results

**Q: How did you evaluate without the hidden labels?**
Three independent checks. (1) Per-field scoring on the 25 solved samples. (2) An invariant suite over all
250 outputs, also run against the 25 solved rows (if a solved row fails an invariant, the invariant is
wrong). (3) A distribution comparison of the 250 predictions against the samples. Plus the phase
backtest on the ledger itself.

**Q: What are your sample scores?**
Status 23/25, method 24/25, plan 23/25, earliest date 21/25, spending changes 22/25, safe amount within
2% 9/25 (4 exact to the cent). 0/250 invariant failures, 0 fallback rows.

**Q: Why is the amount so much weaker than the other fields?**
The solved amounts come from the generator's own base amounts; the ledger only shows those plus noise
(request_22's solved reserve before payday is exactly 157.00). Summing ~8–10 noisy estimates up to the
low point lands within a few percent but rarely within 2%. The categorical fields only flip when that
error crosses a threshold, which is why they score 84–96%.

**Q: How do you know it's noise and not a bug?**
I checked for bias: over the 21 interior rows, 11 over-predict and 10 under-predict, median ratio 1.002.
The smoothing sweep can't fix both directions. I then tested three specific hypotheses and rejected each
with data: undershoot rows being capped at requested amount in truth (only 4 are capped, we match 3),
divergence between the safe-amount and date computations (identical on all 275 rows), and projection
phase drift (zero offset on 16,772 occurrences). The fixes that did land were structural: the window
end and a confirmed-salary continuation rule.

**Q: Aren't you overfitting 25 samples?**
I only chose between discrete conventions that the spec leaves open (window end, ordering, smoothing
definition), and each choice has a mechanism behind it, not a tuned number. No constants were fitted
and nothing is keyed to request ids. When a change fixed some rows but broke others (payday-ordering
variants), I rejected it. I stopped at a planned point rather than chasing the last rows.

**Q: What do the misses look like?**
request_06 and request_21 flip on small amount errors in opposite directions (−79, +31). request_11 and
request_17 get the payday one month off (a level error crossing a payday). request_10 is a no-income
user whose safe amount rests entirely on the spending estimate.

---

## 9. Model use, cost, security

**Q: What does the usage report say?**
Final cold run: 16 calls to claude-opus-5 (Anthropic), 37,925 input and 2,933 output tokens, 40,858
total, 163.4 tokens per request averaged over 250, $0.263 total and $0.001 per request. (Output tokens
vary slightly between cold runs; the extracted amounts were identical each time.) The report
also lists cache replays with their original cost, so a rerun still shows the cold-cache cost.

**Q: How is the API key handled?**
Environment variables only. main.py reads `.env` / `.env.local` (gitignored) and never prints values.
code.zip, output.csv and log.txt were scanned for key patterns before packaging: clean.

**Q: Anything that surprised you while integrating the API?**
Two environment issues. The shell's inherited key was invalid (401), so file values override it. Then
the SDK's HTTP client crashed decoding Brotli responses with the locally installed Brotli build; I fixed
it by requesting gzip/deflate only, rather than changing global packages.

**Q: Privacy concerns with sending documents to a model?**
Only blank-amount documents are sent, once, with only the context the extraction needs (description,
category, currency, date). Everything else runs locally. In production I'd add redaction of account
numbers and names before the call and a data-retention agreement.

---

## 10. Robustness and edge cases

**Q: What if a user has no events? No options? A missing profile?**
No events: flat forecast from balance and minimum, still a real answer. No installment options: those
plans just don't exist; full/partial/wait still evaluated. Missing profile or any exception: the row
falls back to a conservative not_recommended row and is counted, and the other 249 still write.

**Q: What if the CSV headers change?**
Headers are normalized (case, spaces, separators); a missing required column fails loudly with its name
and the headers found. Unknown request types bucket to "other".

**Q: What if the dataset folder is absent at import?**
Paths resolve lazily; modules import fine (tested). BOW_DATASET_DIR overrides the location.

**Q: What if an installment option has more payments than max_installment_months?**
Rejected with a note in the case file (R35), even if the user accepts installments.

**Q: A user has two card accounts with separate minimum payments.**
Both are reserved; the "separate accounts" message confirms they are not duplicates.

**Q: A disputed duplicate card charge?**
The pending debit stays reserved until a reversal actually posts; the dispute message changes nothing.

**Q: A salary in USD for an IDR user?**
Converted at the rate for its settlement date; confirmed foreign salaries are placed on their confirmed
date at that date's rate.

---

## 11. Row walkthroughs (open the case file, name the binding constraint)

**request_99 — spending change.** Balance 86,706.58, minimum 49,100. Bills 07-04→07-15 total 20,161.15
before the 56,980 salary, so the low point is 66,545.43 and the safe amount 17,445.43, 616.57 short of
18,062. Waiting misses the 07-14 deadline by a day. Change review: stop streaming frees 1,051.60 before
the low point (90-day cost 3,154.80) and is chosen; reduce streaming to 525.80 isn't enough; reduce
dining to 1,065.90 would work but costs 7,322.62 over 90 days. Output: full_payment with
`stop:event_9188`, affordable_with_plan, earliest 2026-07-15. Margin after the change is only ~435.

**request_26 — affordable now on confirmed income.** Freelancer with irregular history; an approved
invoice (IDR 30,780,000 on 2025-08-15) is the only projected income. Pays 15,656,000 today and stays
above the 24,768,300 minimum through the window.

**request_36 — wait for a raise.** Message: salary increased to USD 2,988 from 2026-07-15. Safe today is
588.71 of 3,954; full payment becomes safe on 2026-09-15, a payday. Method wait, affordable_later.

**request_29 — not affordable.** Seasonal contract ended, so no income is projected; ZAR 3,221.58 is safe
today but the 51,524 request never becomes safe inside the window; earliest date empty.

**request_30 — installments with spending changes.** No accepted plan is safe as-is; reducing streaming
to USD 17.50 and dining to USD 28 makes 3 installments safe. Good example of R16 rule 2 (changes only
when nothing works without them) combined with preference gates.

---

## 12. Engineering questions

**Q: How fast is it?**
Full 250-request run about 1.1 seconds of engine time (4.3 ms per request), plus about 0.2 s for case
files; the image calls dominate a cold run. Profiling showed the earliest-date search was ~55% of time.
I unified capacity into one trajectory for correctness; I deliberately didn't micro-optimize further
because speed doesn't matter at this scale and every change carries regression risk.

**Q: How would you test this properly?**
Today: the invariant suite, sample scoring, distribution check, and the projection backtest, plus
byte-identical output diffs after refactors. Next: unit tests per module (series detection on synthetic
cadences, R12/R13 structure, each message template), property tests (paying less never makes a safe plan
unsafe; adding income never lowers the safe amount), and golden case files.

**Q: How would you scale it to real banking data and millions of users?**
The engine is per-user and pure, so it parallelizes trivially. The weak points are ingestion: real
ledgers need merchant categorization, deduplication of pending vs posted rows, and far messier messages,
so the rule classifier would get an LLM fallback behind the same Delta interface, with evaluation sets.
Forecast uncertainty should become explicit (ranges or confidence), not a single number.

**Q: What's the worst design decision you made?**
Early on I let calibration use a few rows' coincidences before building the backtest; the backtest
should have come first because it's label-free and covers every user. Also the amount estimator is a
point estimate with no uncertainty, so rows with tiny margins (request_99, ~435) are presented with the
same confidence as rows with huge margins.

---

## 13. How AI was used to build this (answer honestly, with judgment)

**Q: How did you use AI while building?**
I planned the project myself first: ARCHITECTURE, BUILD_PLAN, SPEC_RULES (40 numbered rules reconciled
from the three spec documents), and the evaluation plan. Then I used Claude Code as the implementer
inside that plan: it did the data reconnaissance, wrote the modules, and ran the experiments. Every
session is logged in log.txt as the rules require.

**Q: Where did you direct or override it?**
- I set the order of work and timeboxes, and told it to freeze the engine at planned points instead of
  chasing scores.
- I rejected its offer of speed optimizations (1.1 s → 0.3 s) as regression risk with no benefit, but
  kept the one that removed a correctness hazard (single baseline trajectory).
- I pushed back on its conclusions three times with specific hypotheses: a level bias, the cap on
  undershoot rows, and projection phase drift. It tested each against data; all three were refuted, which
  is itself the useful result.
- I caught a tension it had noted but not connected: the window change improved field-matches but moved
  the affordable rate away from the samples. That led to the phase backtest and the labelled-row check.

**Q: What did the AI get wrong, and how was it caught?**
- Double-counted groceries when a description subset looked regular on its own; caught by a trajectory
  dump that showed two grocery series.
- Overclaimed in ARCHITECTURE.md that the spending-change tiebreak reproduces every solved row; caught
  when verifying the doc's numbers against actual case files, and corrected to "using the solved
  shortfall".
- Overclaimed evidence for one convention (cited a row that didn't support it); corrected.
- A regression after images were added (a large one-off invoice broke groceries detection); caught by
  re-scoring after every change.

**Q: How did you verify the AI's work instead of trusting it?**
Re-score after every change; byte-identical diffs after refactors; invariants on both the output and
the solved rows; opening case files and recomputing a row by hand (request_99); spot-checking image
extractions by eye; and asking for data, not assertions, whenever a claim mattered.

**Q: Would you have built it differently without AI?**
Same architecture, far fewer experiments. The AI made hypotheses cheap to test (a sweep or a backtest in
minutes), which is why I could afford to kill wrong ideas with data. The judgment about which hypotheses
to test and when to stop stayed with me.

---

## 14. Weaknesses and what I'd do with another day

- **Uncertainty.** Replace point estimates with a distribution per series (mean ± spread) and report how
  robust each recommendation is; flag thin-margin rows like request_99.
- **Amount precision.** Only 9/25 within 2%. The remaining error is estimation noise against the
  generator's base amounts; I'd try to model the generator's base amounts (e.g. round-number priors)
  only if it generalizes, validated with the backtest, not the 25 samples.
- **Gig and irregular income** is never projected. A conservative floor (e.g. lowest recent payout) is
  defensible, but request_10's evidence says the reference doesn't count it, so I'd gate it on data.
- **Unknown-amount obligations** ("a new recurring childcare payment begins") are logged but not reserved.
- **Tests.** Unit and property tests per module; today correctness rests on invariants and evaluations.
- **Message classifier** is template-shaped; real messages would need an LLM fallback with an eval set.
- **Spending-change principle** is my own tiebreak; I'd validate it with users, since "least money" and
  "least annoying" aren't the same (stopping a subscription vs trimming groceries).

---

## 15. Commands to have ready

```bash
python code/main.py                     # full run (cold only if code/cache is empty; overwrites usage_report)
python code/evaluation/run_all.py       # sample scores, invariants, distributions (safe to run anytime)
```

Live what-if (e.g. "what if request_99's balance were 20% higher?") — no files written:

```bash
PYTHONIOENCODING=utf-8 python - <<'EOF'
import sys, dataclasses
sys.path.insert(0, "code")
from buyorwait.loader import load
from buyorwait.images import resolve_blank_amounts
from buyorwait.usage import UsageTracker
from buyorwait.pipeline import run
ds = load()
resolve_blank_amounts(ds.events, ds.images, ds.rates, {k: p.home_currency for k, p in ds.profiles.items()}, UsageTracker(), [])
rid, factor = "request_99", 1.20          # change these live
req = next(r for r in ds.requests + ds.samples if r.request_id == rid)
base = run([req], ds, write_cases=False, use_images=False).rows[0]
p = ds.profiles[req.user_id]
ds.profiles[req.user_id] = dataclasses.replace(p, balance=p.balance * factor)
what = run([req], ds, write_cases=False, use_images=False).rows[0]
for k in ["amount_safe_to_pay", "affordability_status", "recommended_payment_method", "payment_plan", "spending_changes_needed"]:
    print(f"{k:28s} {base[k]:>22s} -> {what[k]}")
EOF
```

Tested result: request_99 at +20% balance goes from `affordable_with_plan` + `stop:event_9188` to
`affordable_now` with no change. Swap `balance` for `minimum_balance` to demo the other lever.

---

## 16. Rapid-fire list (one-liners)

- Rows: 250. Users: 275. Events: 25,342. Payment options: 790. Messages: 215. Images: 16.
- Window: request_date..+86. Credits before bills on the same day. Request-day flows included.
- Variable spending: mean of all occurrences. Income: latest settled amount.
- Series per request: 8–12 (median 10). Requests that searched spending changes: 83.
- Model: claude-opus-5, 16 calls, 40,858 tokens, $0.263, cached by image_id.
- Samples: status 23, method 24, plan 23, earliest 21, changes 22, amount ±2% 9.
- Invariants: 0/250 failures; 0 fallbacks; solved rows pass all invariants.
- Rules doc: SPEC_RULES.md R1–R40; cite R4/R5 (freeze), R10 (methods), R12 (partial), R13
  (installments), R15 (changes), R16 (ranking), R17 (conflicts), R18 (untrusted), R35 (max months).
