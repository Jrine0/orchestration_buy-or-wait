"""Image evidence reading (R9, R28, R33).

Tier 1 (mandatory): images linked to ledger rows with a blank amount. The model
returns a FACT (an amount), never a decision. Results are cached on disk by
image_id so each PNG is read once and reruns are deterministic and free.
Without an API key or on failure, the row degrades to a recurring-series
estimate flagged as estimated (R23) - never zero.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Optional

from .config import CACHE_DIR, PROMPT_DIR
from .loader import Event, ImageRef
from .usage import UsageTracker

MODEL = os.environ.get("BOW_VISION_MODEL", "claude-opus-5")
CACHE_FILE = CACHE_DIR / "image_extractions.json"

SCHEMA = {
    "type": "object",
    "properties": {
        "amount": {"type": "number"},
        "currency": {"type": "string"},
        "document_date": {"type": "string"},
        "document_type": {"type": "string"},
        "other_amounts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "amount": {"type": "number"}},
                "required": ["label", "amount"],
                "additionalProperties": False,
            },
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["amount", "currency", "document_date", "document_type", "other_amounts", "confidence"],
    "additionalProperties": False,
}


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def _call_model(img: ImageRef, ev: Event, usage: UsageTracker) -> Optional[dict]:
    try:
        import anthropic
    except ImportError:
        return None
    prompt = (PROMPT_DIR / "image_amount_extraction.md").read_text(encoding="utf-8").format(
        description=ev.description, category=ev.category, direction=ev.direction,
        currency=ev.currency, event_date=ev.event_date)
    data = base64.standard_b64encode(img.path.read_bytes()).decode("utf-8")
    # gzip/deflate only: some environments ship a Brotli build whose decoder API the HTTP client rejects
    client = anthropic.Anthropic(default_headers={"Accept-Encoding": "gzip, deflate"})
    resp = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}},
            {"type": "text", "text": prompt},
        ]}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
    )
    usage.record("anthropic", MODEL, "image_amount_extraction",
                 resp.usage.input_tokens, resp.usage.output_tokens)
    if resp.stop_reason == "refusal":
        return None
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if not text:
        return None
    out = json.loads(text)
    out["_usage"] = {"model": MODEL, "input_tokens": resp.usage.input_tokens,
                     "output_tokens": resp.usage.output_tokens}
    return out


def resolve_blank_amounts(events: dict[str, list[Event]], images: list[ImageRef], rates,
                          home_currency: dict[str, str], usage: UsageTracker, log: list[str]) -> None:
    """Fill Event.amount for blank-amount rows from their linked image, in place."""
    by_event = {e.event_id: e for evs in events.values() for e in evs}
    cache = _load_cache()
    dirty = False
    have_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    for img in images:
        ev = by_event.get(img.related_event_id)
        if ev is None or ev.amount is not None:
            continue
        if not img.path.exists():  # R33: never invent evidence
            log.append(f"{img.image_id}: file missing for {ev.event_id}; amount stays unknown")
            continue
        hit = cache.get(img.image_id)
        if hit:
            u = hit.get("_usage", {})
            usage.record("anthropic", u.get("model", MODEL), "image_amount_extraction",
                         u.get("input_tokens", 0), u.get("output_tokens", 0), cached=True)
        elif have_key:
            try:
                hit = _call_model(img, ev, usage)
            except Exception as exc:  # network / auth failure degrades the fact, not the row
                log.append(f"{img.image_id}: extraction failed ({type(exc).__name__}: {exc})")
                hit = None
            if hit:
                cache[img.image_id] = hit
                dirty = True
        if not hit:
            log.append(f"{img.image_id}: no extraction available for {ev.event_id}")
            continue
        cur = (hit.get("currency") or ev.currency).upper()
        amt = float(hit["amount"])
        home = home_currency.get(ev.user_id, ev.currency)
        ev.original_amount = amt
        ev.amount = rates.convert(amt, cur, home, ev.settlement_date)
        ev.provenance = f"image:{img.image_id}"
        ev.notes.append(f"amount {amt} {cur} read from {img.image_id} ({hit.get('document_type')}, "
                        f"confidence {hit.get('confidence')})")
        log.append(f"{img.image_id}: {ev.event_id} amount={amt} {cur}")
    if dirty:
        _save_cache(cache)
