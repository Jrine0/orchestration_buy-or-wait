"""Token and cost accounting for every model call in a run (R27)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# USD per 1M tokens (input, output), Anthropic first-party list prices.
PRICES = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


@dataclass
class Call:
    provider: str
    model: str
    purpose: str
    input_tokens: int
    output_tokens: int
    cached: bool


@dataclass
class UsageTracker:
    calls: list[Call] = field(default_factory=list)

    def record(self, provider, model, purpose, input_tokens, output_tokens, cached=False):
        self.calls.append(Call(provider, model, purpose, input_tokens, output_tokens, cached))

    def report(self, n_requests: int) -> str:
        live = [c for c in self.calls if not c.cached]
        cached = [c for c in self.calls if c.cached]
        lines = [
            "# Usage report",
            "",
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by the run that wrote `output.csv`.",
            f"Requests processed: {n_requests}",
            "",
            "All five decision fields come from the deterministic engine; the only model use is reading",
            "amounts off images attached to blank-amount ledger rows. Extractions are cached on disk by",
            "image_id, so a rerun replays the cache and makes no new calls. Cached replays are listed",
            "separately and carry the tokens of the call that originally produced them.",
            "",
            "## Per model (live calls this run)",
            "",
            "| Provider | Model | Calls | Input tokens | Output tokens | Est. cost (USD) |",
            "|---|---|---|---|---|---|",
        ]
        tot_in = tot_out = 0
        tot_cost = 0.0
        models = sorted({(c.provider, c.model) for c in live})
        for prov, model in models:
            cs = [c for c in live if c.model == model]
            i = sum(c.input_tokens for c in cs)
            o = sum(c.output_tokens for c in cs)
            pi, po = PRICES.get(model, (0.0, 0.0))
            cost = i / 1e6 * pi + o / 1e6 * po
            tot_in += i
            tot_out += o
            tot_cost += cost
            lines.append(f"| {prov} | {model} | {len(cs)} | {i:,} | {o:,} | {cost:.4f} |")
        if not models:
            lines.append("| - | - | 0 | 0 | 0 | 0.0000 |")
        n = max(n_requests, 1)
        lines += [
            "",
            "## Overall (live calls this run)",
            "",
            f"- Model calls: {len(live)}",
            f"- Input tokens: {tot_in:,}",
            f"- Output tokens: {tot_out:,}",
            f"- Total tokens: {tot_in + tot_out:,}",
            f"- Average tokens per request: {(tot_in + tot_out) / n:,.1f}",
            f"- Estimated total cost: ${tot_cost:.4f}",
            f"- Estimated cost per request: ${tot_cost / n:.6f}",
            "",
            "## Cache replays this run",
            "",
            f"- Extractions served from cache: {len(cached)}",
            f"- Tokens those extractions originally cost: {sum(c.input_tokens + c.output_tokens for c in cached):,}",
        ]
        orig_cost = sum(c.input_tokens / 1e6 * PRICES.get(c.model, (0, 0))[0]
                        + c.output_tokens / 1e6 * PRICES.get(c.model, (0, 0))[1] for c in cached)
        lines += [
            f"- Original cost of cached extractions: ${orig_cost:.4f}",
            f"- Cost if the cache were cold (live + cached): ${tot_cost + orig_cost:.4f}, "
            f"${(tot_cost + orig_cost) / n:.6f} per request",
            "",
            "Pricing basis: USD per 1M tokens, " + ", ".join(f"{m} ${p[0]:.2f} in / ${p[1]:.2f} out" for m, p in PRICES.items()) + ".",
            "",
        ]
        return "\n".join(lines)
