# Buy or Wait? — solution

A deterministic financial decision engine. It reconstructs each user's cash position for the 87 days
from the request date (request date to +86, see `ARCHITECTURE.md`) from the ledger, messages and images,
then picks the safest eligible payment plan. A model is used only to read amounts off images attached
to blank-amount ledger rows. That output is a fact fed into the engine; the model never makes a decision.

## 1. Requirements

- Python 3.10 or newer (the engine uses only the standard library)
- The `anthropic` package, only for reading images: `pip install -r code/requirements.txt`
- An Anthropic API key, only if the image cache (`code/cache/image_extractions.json`) is missing or you
  want a fresh (cold) extraction

All commands below run from the **repository root** (the folder that contains `dataset/` and `code/`).

## 2. API key (optional)

Either export it:

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # macOS / Linux / Git Bash
$env:ANTHROPIC_API_KEY="sk-ant-..."        # Windows PowerShell
```

or put one line in `.env.local` (or `.env`) at the repository root, which `main.py` loads and which is
gitignored:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Values in these files override a key already set in the shell. The key is never printed or logged.

## 3. Produce the predictions

```bash
python code/main.py
```

This reads `dataset/`, reads any uncached images, and writes:

| Output | What it is |
|---|---|
| `output.csv` (repo root) | one row per request in `dataset/requests.csv`, exact column order |
| `code/evaluation/usage_report.md` | model calls, tokens and cost for this exact run |
| `code/case_files/<request_id>.json` | per-request reasoning trace (see below) |
| `code/cache/image_extractions.json` | image amounts, reused by later runs |

**Cold vs cached run.** If the cache file exists, images are not re-read, the run makes no model calls,
and the usage report shows the replayed extractions with their original cost. For a cold run that
re-reads all 16 images (about $0.25):

```bash
rm code/cache/image_extractions.json       # Windows PowerShell: Remove-Item code\cache\image_extractions.json
python code/main.py
```

**Offline.** With no key and no cache the run still completes: blank-amount rows stay unknown and every
other field is computed normally.

Other options:

```bash
python code/main.py --no-images            # never call a model and ignore the cache
python code/main.py --samples              # run the 25 solved samples -> code/evaluation/sample_output.csv
python code/main.py --output some/file.csv # write predictions elsewhere
```

Environment overrides: `BOW_DATASET_DIR` (default `dataset/`), `BOW_OUTPUT` (default `./output.csv`),
`BOW_VISION_MODEL` (default `claude-opus-5`).

## 4. Evaluate

```bash
python code/evaluation/run_all.py
```

Runs three checks and writes their reports to `code/evaluation/` (it does not touch `output.csv` or the
usage report):

| Script | Report | Checks |
|---|---|---|
| `score_samples.py` | `sample_scores.md` | per-field matches against the 25 solved samples |
| `check_invariants.py` | `invariant_report.md` | every hard output rule on all rows of `output.csv`, and the same rules on the solved rows |
| `check_distributions.py` | `distribution_report.md` | shape of the predictions vs the samples |

Each script can also be run on its own, e.g. `python code/evaluation/check_invariants.py`.

## 5. Read a decision

Open `code/case_files/<request_id>.json`. The useful sections, in order:

- `capacity_frozen`: `amount_safe_to_pay`, `earliest_date_for_full_payment`, and the binding constraint
  as a window (e.g. `2026-07-04→2026-07-15 pre-payday run, 20,161.15 of bills`)
- `recurring_series`, `evidence`, `trace`: what was detected and every rule that fired
- `projected_flows`: every dated cash flow in the forecast
- `spending_change_review`: every permitted change, what it frees before the low point, its 90-day cost,
  and which was chosen
- `candidate_plans`: every plan considered, with eligibility, safety, deadline and notes
- `output_row`: the row written to `output.csv`

## 6. Package

```bash
python code/package.py
```

Writes `code.zip` at the repository root from `code/` (excluding `__pycache__`, `.env*` files and
personal notes) after scanning it, `output.csv` and `log.txt` for anything that looks like an API key.

## 7. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `extraction failed (AuthenticationError ... 401)` | invalid key; set a valid one in `.env.local` (it overrides the shell) |
| `extraction failed (APIConnectionError ...)` | no network, or a proxy; the run still completes without image amounts |
| `ValueError: <file>: missing required columns` | a dataset file's header changed; the message names the missing columns |
| `UnicodeEncodeError` printing case-file text on Windows | set `PYTHONIOENCODING=utf-8` for that shell |
| usage report shows 0 live calls | the image cache was used; delete it for a cold run (section 3) |

## Layout

| Path | Role |
|---|---|
| `main.py` | entry point |
| `package.py` | builds `code.zip` with a secret scan |
| `buyorwait/loader.py` | CSV -> typed records, header normalization, currency conversion (R21) |
| `buyorwait/images.py` | blank-amount image reading with on-disk cache (R9, R28, R33) |
| `buyorwait/evidence.py` | bilingual rule-based message classifier -> fact deltas (R17, R18) |
| `buyorwait/state.py` | recurring-series detection (R34), essential/flexible tagging (R24) |
| `buyorwait/context.py` | per-request dated cash flows: pending/scheduled rows, income lifecycle, message deltas |
| `buyorwait/forecast.py` | pure balance simulation, safe amount, earliest full-payment date (R4-R6) |
| `buyorwait/decision.py` | candidate plans, preference gates (R10-R13, R35), spending changes (R15), ranking (R16) |
| `buyorwait/explain.py` | explanation templated from the engine's own numbers |
| `buyorwait/verify.py` | hard invariants shared by the pipeline and the evaluation suite |
| `prompts/` | every model prompt, as files |
| `evaluation/` | evaluation scripts, reports, `usage_report.md` |

See `ARCHITECTURE.md` for the design and `SPEC_RULES.md` for the numbered rules cited in code comments.
