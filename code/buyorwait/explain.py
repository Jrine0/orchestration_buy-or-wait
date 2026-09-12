"""explain: decision_explanation as a template over the engine's own facts (never free text)."""
from __future__ import annotations

from datetime import date

from .decision import Decision
from .context import Context


def money(cur: str, x: float) -> str:
    x = round(x + 1e-9, 2)
    if abs(x - round(x)) < 0.005:
        return f"{cur} {int(round(x)):,}"
    return f"{cur} {x:,.2f}"


def day(d: date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def _change_phrase(ctx: Context, dec: Decision) -> str:
    cur = ctx.profile.home_currency
    parts = []
    for c in dec.plan.changes:
        what = c.description[:1].lower() + c.description[1:]
        if c.verb == "stop":
            parts.append(f"stop the {what}")
        else:
            parts.append(f"reduce the {what} to {money(cur, c.new_amount)}")
    text = " and ".join(parts)
    return text[:1].upper() + text[1:]


def explain(ctx: Context, dec: Decision) -> str:
    p, r = ctx.profile, ctx.request
    cur = p.home_currency
    cap = dec.capacity
    minimum = money(cur, p.minimum_balance)
    amt = money(cur, r.requested_amount)
    plan = dec.plan
    if dec.method == "full_payment" and not plan.changes:
        return f"Pay {amt} today. This leaves at least {minimum} available over the next 90 days."
    if dec.method == "full_payment":
        return (f"{_change_phrase(ctx, dec)}, then pay {amt} today. This leaves at least {minimum} available; "
                f"without the change only {money(cur, cap.amount_safe_to_pay)} is safe today.")
    if dec.method == "installments":
        n = len(plan.schedule)
        lead = f"{_change_phrase(ctx, dec)}, then use" if plan.changes else "Use"
        return (f"{lead} {n} installments of {money(cur, plan.schedule[0][1])}, starting {day(plan.schedule[0][0])}. "
                f"This leaves at least {minimum} available.")
    if dec.method == "partial_payment":
        (d1, a1), (d2, a2) = plan.schedule
        return (f"Pay {money(cur, a1)} today and the remaining {money(cur, a2)} on {day(d2)}. "
                f"This completes the full request and keeps the {minimum} minimum protected.")
    if dec.method == "wait":
        return (f"Pay {amt} in full on {day(plan.schedule[0][0])}. "
                f"Paying earlier would take the balance below the {minimum} minimum.")
    # not_recommended
    if cap.amount_safe_to_pay > 0 and cap.earliest_date_for_full_payment is None:
        return (f"Do not proceed with the {amt} request. Although {money(cur, cap.amount_safe_to_pay)} is available "
                f"today, the full amount cannot be completed safely within 90 days.")
    if cap.earliest_date_for_full_payment and cap.earliest_date_for_full_payment > r.desired_completion_date:
        return (f"Do not make this payment by {day(r.desired_completion_date)}. The full amount only becomes safe "
                f"on {day(cap.earliest_date_for_full_payment)}, and no accepted option keeps the {minimum} minimum protected sooner.")
    return (f"Do not make this payment by {day(r.desired_completion_date)}. "
            f"None of the available options keeps the {minimum} minimum protected.")
