# Usage report

Generated: 2026-09-12 23:37 UTC by the run that wrote `output.csv`.
Requests processed: 250

All five decision fields come from the deterministic engine; the only model use is reading
amounts off images attached to blank-amount ledger rows. Extractions are cached on disk by
image_id, so a rerun replays the cache and makes no new calls. Cached replays are listed
separately and carry the tokens of the call that originally produced them.

## Per model (live calls this run)

| Provider | Model | Calls | Input tokens | Output tokens | Est. cost (USD) |
|---|---|---|---|---|---|
| anthropic | claude-opus-5 | 16 | 37,925 | 2,933 | 0.2630 |

## Overall (live calls this run)

- Model calls: 16
- Input tokens: 37,925
- Output tokens: 2,933
- Total tokens: 40,858
- Average tokens per request: 163.4
- Estimated total cost: $0.2630
- Estimated cost per request: $0.001052

## Cache replays this run

- Extractions served from cache: 0
- Tokens those extractions originally cost: 0
- Original cost of cached extractions: $0.0000
- Cost if the cache were cold (live + cached): $0.2630, $0.001052 per request

Pricing basis: USD per 1M tokens, claude-opus-5 $5.00 in / $25.00 out, claude-sonnet-5 $2.00 in / $10.00 out, claude-haiku-4-5 $1.00 in / $5.00 out.
