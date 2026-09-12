# Usage report

Generated: 2026-09-12 19:07 UTC by the run that wrote `output.csv`.
Requests processed: 250

All five decision fields come from the deterministic engine; the only model use is reading
amounts off images attached to blank-amount ledger rows. Extractions are cached on disk by
image_id, so a rerun replays the cache and makes no new calls. Cached replays are listed
separately and carry the tokens of the call that originally produced them.

## Per model (live calls this run)

| Provider | Model | Calls | Input tokens | Output tokens | Est. cost (USD) |
|---|---|---|---|---|---|
| - | - | 0 | 0 | 0 | 0.0000 |

## Overall (live calls this run)

- Model calls: 0
- Input tokens: 0
- Output tokens: 0
- Total tokens: 0
- Average tokens per request: 0.0
- Estimated total cost: $0.0000
- Estimated cost per request: $0.000000

## Cache replays this run

- Extractions served from cache: 16
- Tokens those extractions originally cost: 40,884
- Original cost of cached extractions: $0.2636
- Cost if the cache were cold (live + cached): $0.2636, $0.001054 per request

Pricing basis: USD per 1M tokens, claude-opus-5 $5.00 in / $25.00 out, claude-sonnet-5 $2.00 in / $10.00 out, claude-haiku-4-5 $1.00 in / $5.00 out.
