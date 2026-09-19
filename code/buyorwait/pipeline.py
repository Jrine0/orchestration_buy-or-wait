"""Pipeline: load -> image facts -> per-request context -> decision -> explanation -> verify -> row.

One failing request never aborts the run (R22, R23): it gets a conservative
fallback row, and the number of fallbacks is reported.
"""
from __future__ import annotations

import csv
import json
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config import CASE_DIR, SETTINGS, Settings
from .context import Context, build
from .decision import Decision, decide, fmt_plan_amount
from .explain import explain
from .images import resolve_blank_amounts
from .loader import Dataset, Request, load
from .usage import UsageTracker
from .verify import COLUMNS, check_row


def fmt_amount(x: float) -> str:
    x = round(x + 1e-9, 2)
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return s or "0"


@dataclass
class RunResult:
    rows: list[dict]
    contexts: dict[str, Context] = field(default_factory=dict)
    decisions: dict[str, Decision] = field(default_factory=dict)
    fallbacks: list[str] = field(default_factory=list)
    violations: dict[str, list[str]] = field(default_factory=dict)
    image_log: list[str] = field(default_factory=list)


def to_row(ctx: Context, dec: Decision) -> dict:
    r = ctx.request
    cap = dec.capacity
    plan = dec.plan
    return {
        "request_id": r.request_id,
        "amount_safe_to_pay": fmt_amount(cap.amount_safe_to_pay),
        "affordability_status": dec.status,
        "recommended_payment_method": dec.method,
        "payment_plan": "|".join(f"{d.isoformat()}:{fmt_plan_amount(a)}" for d, a in plan.schedule) if plan else "none",
        "earliest_date_for_full_payment": cap.earliest_date_for_full_payment.isoformat() if cap.earliest_date_for_full_payment else "",
        "spending_changes_needed": "|".join(c.render() for c in plan.changes) if plan and plan.changes else "none",
        "decision_explanation": explain(ctx, dec),
    }


def fallback_row(req: Request, profile) -> dict:
    return {
        "request_id": req.request_id, "amount_safe_to_pay": "0", "affordability_status": "not_affordable",
        "recommended_payment_method": "not_recommended", "payment_plan": "none",
        "earliest_date_for_full_payment": "", "spending_changes_needed": "none",
        "decision_explanation": (f"Do not proceed with the {profile.home_currency if profile else ''} "
                                 f"{fmt_plan_amount(req.requested_amount)} request; the forecast could not be completed safely."),
    }


def case_file(ctx: Context, dec: Decision, row: dict, violations: list[str]) -> dict:
    cap = dec.capacity
    p, r = ctx.profile, ctx.request
    return {
        "request": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.__dict__.items() if k != "solved"},
        "profile": {"home_currency": p.home_currency, "balance": p.balance, "minimum_balance": p.minimum_balance,
                    "methods": sorted(p.methods), "max_installment_months": p.max_installment_months,
                    "protected": sorted(p.protected), "reducible": sorted(p.reducible), "stoppable": sorted(p.stoppable)},
        "capacity_frozen": {"amount_safe_to_pay": cap.amount_safe_to_pay,
                            "earliest_date_for_full_payment": cap.earliest_date_for_full_payment.isoformat()
                            if cap.earliest_date_for_full_payment else None,
                            "lowest_projected_balance": round(cap.lowest_balance, 2),
                            "binding_constraint": {
                                "summary": cap.binding_text(),
                                "low_point_date": cap.binding_date.isoformat() if cap.binding_date else None,
                                "bills_window_start": cap.window_start.isoformat() if cap.window_start else None,
                                "next_credit": cap.window_end.isoformat() if cap.window_end else None,
                                "bills_in_window": cap.window_debits,
                                "last_debit_before_low": cap.binding_label}},
        "recurring_series": [{"key": s.key, "cadence": s.cadence, "last": s.last_date.isoformat(), "amount": round(s.amount, 2),
                              "occurrences": len(s.events), "flexibility": s.flexibility,
                              "latest_event": s.latest_event.event_id} for s in ctx.series],
        "evidence": [{"message_id": d.message_id, "intent": d.intent, "amount": d.amount, "currency": d.currency,
                      "date": d.on.isoformat() if d.on else None} for d in ctx.deltas],
        "trace": ctx.trace,
        "projected_flows": [{"date": f.date.isoformat(), "amount": round(f.amount, 2), "kind": f.kind, "label": f.label}
                            for f in sorted(ctx.flows, key=lambda f: f.date)],
        "spending_change_review": dec.change_review,
        "candidate_plans": [{"label": c.method + (" with spending changes" if c.changes else ""),
                             "method": c.method, "option": c.option_id or None, "total_paid": c.total_paid,
                             "schedule": [[d.isoformat(), a] for d, a in c.schedule], "eligible": c.eligible, "safe": c.safe,
                             "completes_by_deadline": c.completes_by_deadline,
                             "changes": [ch.render() for ch in c.changes], "notes": c.notes} for c in dec.candidates],
        "output_row": row,
        "verification_errors": violations,
    }


def run(requests: Optional[list[Request]] = None, ds: Optional[Dataset] = None, s: Settings = SETTINGS,
        usage: Optional[UsageTracker] = None, write_cases: bool = True, use_images: bool = True) -> RunResult:
    ds = ds or load()
    usage = usage if usage is not None else UsageTracker()
    res = RunResult(rows=[])
    if use_images:
        resolve_blank_amounts(ds.events, ds.images, ds.rates,
                              {k: p.home_currency for k, p in ds.profiles.items()}, usage, res.image_log)
    requests = ds.requests if requests is None else requests
    if write_cases:
        CASE_DIR.mkdir(parents=True, exist_ok=True)
    for req in requests:
        prof = ds.profiles.get(req.user_id)
        try:
            ctx = build(ds, req, s)
            dec = decide(ctx, ds.options.get(req.request_id, []), s)
            row = to_row(ctx, dec)
            errs = check_row(row, req, prof, ds.options.get(req.request_id, []), ds.events.get(req.user_id, []))
            if errs:
                res.violations[req.request_id] = errs
                if any(e.startswith(("R1 ", "R2 ", "R12", "R13", "R14", "R10", "R15")) for e in errs):
                    row = fallback_row(req, prof)  # repair to a safe value, logged
                    res.fallbacks.append(req.request_id)
            res.contexts[req.request_id] = ctx
            res.decisions[req.request_id] = dec
            if write_cases:
                (CASE_DIR / f"{req.request_id}.json").write_text(
                    json.dumps(case_file(ctx, dec, row, errs), indent=2, default=str, ensure_ascii=False), encoding="utf-8")
        except Exception:
            res.fallbacks.append(req.request_id)
            res.violations[req.request_id] = ["exception: " + traceback.format_exc(limit=3)]
            row = fallback_row(req, prof)
        res.rows.append(row)
    return res


def write_csv(rows: list[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r[c] for c in COLUMNS})
