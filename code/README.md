# Buy or Wait? — solution

A deterministic financial decision engine. It reconstructs each user's 90-day cash position from the
ledger, messages and images, then picks the safest eligible payment plan. A model is used only to read
amounts off images attached to blank-amount ledger rows. That output is a fact fed into the engine; the
model never makes a decision.

## Setup

```bash
pip install -r code/requirements.txt      # Python 3.10+; the engine itself is stdlib-only
export ANTHROPIC_API_KEY=...               # optional: only needed to read uncached images
```

## Run (from the repository root)

```bash
python code/main.py                        # dataset/requests.csv -> ./output.csv
python code/evaluation/run_all.py          # sample scores, invariants, distribution check
python code/main.py --samples              # solved samples -> code/evaluation/sample_output.csv
python code/main.py --no-images            # never call a model (cached extractions are not used either)
```

Environment overrides: `BOW_DATASET_DIR` (default `dataset/`), `BOW_OUTPUT` (default `./output.csv`),
`BOW_VISION_MODEL` (default `claude-opus-5`).

Every run writes:

- `output.csv` at the repository root (250 rows, exact column order)
- `code/evaluation/usage_report.md` for that exact run
- `code/case_files/<request_id>.json`: facts with provenance, detected series, applied evidence,
  projected flows, the binding constraint, every candidate plan and why it was or was not chosen

## Layout

| Path | Role |
|---|---|
| `buyorwait/loader.py` | CSV -> typed records, header normalization, currency conversion (R21) |
| `buyorwait/images.py` | blank-amount image reading with on-disk cache (R9, R28, R33) |
| `buyorwait/evidence.py` | bilingual rule-based message classifier -> fact deltas (R17, R18) |
| `buyorwait/state.py` | recurring-series detection (R34), essential/flexible tagging (R24) |
| `buyorwait/context.py` | per-request dated cash flows: pending/scheduled rows, income lifecycle, message deltas |
| `buyorwait/forecast.py` | pure 90-day balance simulation, safe amount, earliest full-payment date (R4-R6) |
| `buyorwait/decision.py` | candidate plans, preference gates (R10-R13, R35), spending changes (R15), ranking (R16) |
| `buyorwait/explain.py` | explanation templated from the engine's own numbers |
| `buyorwait/verify.py` | hard invariants shared by the pipeline and the evaluation suite |
| `prompts/` | every model prompt, as files |
| `evaluation/` | evaluation scripts, reports, `usage_report.md` |

See `ARCHITECTURE.md` for the design and `SPEC_RULES.md` for the numbered rules cited in code comments.
