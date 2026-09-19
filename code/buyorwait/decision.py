"""decision: enumerate candidate plans -> keep safe ones -> preference gate -> R16 ranking -> status.

The two capacity fields (amount_safe_to_pay, earliest_date_for_full_payment) are
computed first from the baseline forecast and frozen in a `Capacity` object
(R4, R5). Nothing below writes to it; spending-change exploration works on a
copy of the flows.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from .config import SETTINGS, Settings
from .context import Context
from .forecast import capacity_from_baseline, is_safe, simulate, window
from .loader import PaymentOption
from .state import CHANGEABLE_FLEX, Flow


@dataclass(frozen=True)
class Capacity:  # R4/R5: frozen before preferences and spending changes
    amount_safe_to_pay: float
    earliest_date_for_full_payment: Optional[date]
    lowest_balance: float
    binding_date: Optional[date]
    binding_label: str
    window_start: Optional[date] = None      # the run of bills that produces the low point
    window_end: Optional[date] = None        # next credit after the low point (None = end of forecast)
    window_debits: float = 0.0

    def binding_text(self) -> str:
        if self.binding_date is None:
            return "balance never falls below its opening level"
        end = f"{self.window_end}" if self.window_end else "end of forecast"
        kind = "pre-payday run" if self.window_end else "run to end of forecast with no further income"
        return f"{self.window_start}→{end} {kind}, {self.window_debits:,.2f} of bills"


@dataclass
class Change:
    verb: str                 # stop | reduce_to
    event_id: str
    series_key: str
    description: str
    new_amount: Optional[float] = None
    horizon_saving: float = 0.0

    def render(self) -> str:
        if self.verb == "stop":
            return f"stop:{self.event_id}"
        return f"reduce_to:{self.event_id}:{fmt_plan_amount(self.new_amount)}"


@dataclass
class Plan:
    method: str
    schedule: list[tuple[date, float]]
    total_paid: float
    option_id: str = ""
    option_num: int = 0
    changes: list[Change] = field(default_factory=list)
    safe: bool = False
    eligible: bool = True
    completes_by_deadline: bool = True
    notes: list[str] = field(default_factory=list)

    def rank_key(self):  # R16, verbatim order
        return (not self.completes_by_deadline, len(self.changes) > 0, round(self.total_paid, 2),
                self.schedule[0][0] if self.schedule else date.max, len(self.schedule), self.option_num)


@dataclass
class Decision:
    capacity: Capacity
    status: str
    method: str
    plan: Optional[Plan]
    candidates: list[Plan]
    change_review: list[dict] = field(default_factory=list)


def fmt_plan_amount(x: float) -> str:
    x = round(x + 1e-9, 2)
    return str(int(round(x))) if abs(x - round(x)) < 0.005 else f"{x:.2f}"


def capacity(ctx: Context, s: Settings = SETTINGS) -> Capacity:
    p, r = ctx.profile, ctx.request
    # one baseline trajectory feeds both frozen fields, so the amount and the date cannot disagree
    tr, safe, earliest = capacity_from_baseline(p.balance, p.minimum_balance, ctx.flows, r.request_date,
                                                r.requested_amount, s)
    w_start = w_end = None
    w_debits = 0.0
    if tr.binding:
        low_d = tr.binding[0]
        credits_before = [d for d, _, f in tr.points if f.amount > 0 and d <= low_d]
        credits_after = [d for d, _, f in tr.points if f.amount > 0 and d > low_d]
        w_start = max(credits_before) if credits_before else r.request_date
        w_end = min(credits_after) if credits_after else None
        w_debits = -sum(f.amount for d, _, f in tr.points if f.amount < 0 and w_start <= d <= low_d)
    return Capacity(amount_safe_to_pay=safe, earliest_date_for_full_payment=earliest,
                    lowest_balance=tr.minimum,
                    binding_date=tr.binding[0] if tr.binding else None,
                    binding_label=tr.binding[2].label if tr.binding else "",
                    window_start=w_start, window_end=w_end, window_debits=round(w_debits, 2))


def installment_schedule(o: PaymentOption) -> list[tuple[date, float]]:  # R13: rebuilt from the option's own fields
    step = o.payment_frequency_days or 30
    return [(o.first_payment_date + timedelta(days=step * k), o.payment_amount) for k in range(o.number_of_payments)]


def installment_months(o: PaymentOption) -> float:
    step = o.payment_frequency_days or 30
    return o.number_of_payments if step >= 28 else o.number_of_payments * step / 30.0


def change_candidates(ctx: Context) -> list[list[Change]]:
    """Per changeable series, the mutually exclusive actions allowed (R15)."""
    p = ctx.profile
    start, end = window(ctx.request.request_date)
    groups = []
    for sr in ctx.series:
        if sr.direction != "debit" or sr.flexibility not in CHANGEABLE_FLEX or sr.category in p.protected:
            continue
        future = [f for f in ctx.flows if f.series_key == sr.key and f.amount < 0]
        if not future:
            continue
        opts = []
        if sr.flexibility in ("stoppable", "reducible_or_stoppable") and sr.category in p.stoppable:
            opts.append(Change("stop", sr.latest_event.event_id, sr.key, sr.latest_event.description,
                               horizon_saving=-sum(f.amount for f in future)))
        if sr.flexibility in ("reducible", "reducible_or_stoppable") and sr.category in p.reducible:
            floor = sr.minimum_allowed_amount
            if floor is None:  # R23: observed historical minimum when no floor is supplied
                floor = min(sr.amounts)
            if floor < sr.amount - 0.005:
                opts.append(Change("reduce_to", sr.latest_event.event_id, sr.key, sr.latest_event.description,
                                   new_amount=round(floor, 2),
                                   horizon_saving=sum(-f.amount - floor for f in future)))
        if opts:
            groups.append(opts)
    return groups


def apply_changes(flows: list[Flow], changes: list[Change]) -> list[Flow]:
    out = []
    by_key = {c.series_key: c for c in changes}
    for f in flows:
        c = by_key.get(f.series_key) if f.series_key else None
        if c is None or f.amount >= 0:
            out.append(f)
        elif c.verb == "reduce_to":
            out.append(Flow(**{**f.__dict__, "amount": -c.new_amount}))
    return out


def decide(ctx: Context, options: list[PaymentOption], s: Settings = SETTINGS) -> Decision:
    p, r = ctx.profile, ctx.request
    cap = capacity(ctx, s)
    methods = p.methods
    cands: list[Plan] = []

    def check(plan: Plan, flows=None):
        plan.safe = is_safe(p.balance, p.minimum_balance, flows if flows is not None else ctx.flows, plan.schedule, s)
        last = plan.schedule[-1][0] if plan.schedule else r.request_date
        plan.completes_by_deadline = last <= r.desired_completion_date
        return plan

    # full payment today (R10: needs full_payment acceptance; R11)
    full = check(Plan("full_payment", [(r.request_date, r.requested_amount)], r.requested_amount,
                      option_num=0))
    full.eligible = "full_payment" in methods
    if not full.eligible:
        full.notes.append("user does not consider full_payment")
    cands.append(full)

    # supplied installment options (R13, R35, R36)
    for o in sorted(options, key=lambda o: o.num):
        if o.payment_method != "installments":
            continue
        plan = check(Plan("installments", installment_schedule(o), o.total_payable_amount,
                          option_id=o.payment_option_id, option_num=o.num))
        if "installments" not in methods:
            plan.eligible = False
            plan.notes.append("user does not consider installments")
        elif p.max_installment_months is None:
            plan.eligible = False
            plan.notes.append("max_installment_months blank: installments not considered (R35)")
        elif installment_months(o) > p.max_installment_months:
            plan.eligible = False
            plan.notes.append(f"{o.number_of_payments} payments exceed max_installment_months={p.max_installment_months:g} (R35)")
        cands.append(plan)

    # partial payment (R12)
    safe, earliest = cap.amount_safe_to_pay, cap.earliest_date_for_full_payment
    if 0 < safe < r.requested_amount and earliest is not None:
        rest = round(r.requested_amount - safe, 2)
        plan = check(Plan("partial_payment", [(r.request_date, safe), (earliest, rest)], r.requested_amount))
        reasons = []
        if not r.allows_partial_payment:
            reasons.append("request does not allow partial payment")
        if "partial_payment" not in methods:
            reasons.append("user does not consider partial_payment")
        if earliest > r.desired_completion_date:
            reasons.append("remainder date is after desired_completion_date")
        if earliest <= r.request_date:
            reasons.append("second payment would fall on request_date")
        plan.eligible = not reasons
        plan.notes.extend(reasons)
        cands.append(plan)

    # wait (R10: full payment becomes safe later and user accepts full_payment)
    if earliest is not None and earliest > r.request_date:
        plan = check(Plan("wait", [(earliest, r.requested_amount)], r.requested_amount))
        plan.eligible = "full_payment" in methods
        if not plan.eligible:
            plan.notes.append("wait requires full_payment acceptance")
        cands.append(plan)

    viable = [c for c in cands if c.eligible and c.safe and c.completes_by_deadline]

    # spending changes only when nothing completes on time without them (R16 rule 2)
    if not viable:
        groups = change_candidates(ctx)
        base_plans = [c for c in cands if c.eligible and c.completes_by_deadline and c.method != "wait"]
        best: Optional[Plan] = None
        for base in sorted(base_plans, key=lambda c: c.rank_key()):
            options_sets = []
            for k in range(1, min(3, len(groups)) + 1):
                for combo in itertools.combinations(groups, k):
                    for pick in itertools.product(*combo):
                        options_sets.append(list(pick))
            options_sets.sort(key=lambda cs: (round(sum(c.horizon_saving for c in cs), 2), len(cs),
                                              [c.event_id for c in cs]))
            for cs in options_sets:
                flows = apply_changes(ctx.flows, cs)
                trial = Plan(base.method, list(base.schedule), base.total_paid, base.option_id, base.option_num,
                             changes=sorted(cs, key=lambda c: int("".join(ch for ch in c.event_id if ch.isdigit()) or 0)))
                check(trial, flows)
                if trial.safe:
                    trial.notes.append("safe only with spending changes")
                    if best is None or trial.rank_key() < best.rank_key():
                        best = trial
                    break
        if best is not None:
            cands.append(best)
            viable = [best]
        review = review_changes(ctx, cap, groups, best)
    else:
        review = []

    if not viable:
        return Decision(cap, "not_affordable", "not_recommended", None, cands, review)
    chosen = min(viable, key=lambda c: c.rank_key())
    if chosen.changes or chosen.method in ("partial_payment", "installments"):
        status = "affordable_with_plan"
    elif chosen.method == "wait":
        status = "affordable_later"
    else:
        status = "affordable_now"
    return Decision(cap, status, chosen.method, chosen, cands, review)


def review_changes(ctx: Context, cap: Capacity, groups: list[list[Change]], best: Optional[Plan]) -> list[dict]:
    """Every permitted single change, for the case file.

    R16 ranks plans but says nothing about WHICH spending changes to use: two change sets that both
    make the same payment safe tie on all six rules. Our tiebreak principle (not from the spec):
    choose the set that takes the least money away from the user over the 90-day forecast, then the
    fewest changes, then the lowest event ids. It disturbs the user's spending the least while still
    covering the gap, and it reproduces every spending-change choice in the solved samples."""
    chosen = {(c.verb, c.event_id) for c in (best.changes if best else [])}
    gap = round(ctx.request.requested_amount - cap.amount_safe_to_pay, 2)
    low = cap.binding_date
    out = []
    for opts in groups:
        for c in opts:
            flows = [f for f in ctx.flows if f.series_key == c.series_key and f.amount < 0]
            per = (lambda f: -f.amount) if c.verb == "stop" else (lambda f: -f.amount - c.new_amount)
            freed = sum(per(f) for f in flows if low is None or f.date <= low)
            out.append({
                "change": c.render(),
                "series": c.series_key,
                "description": c.description,
                "freed_before_low_point": round(freed, 2),
                "covers_gap_alone": freed + 0.005 >= gap,
                "cost_over_90_days": round(c.horizon_saving, 2),
                "chosen": (c.verb, c.event_id) in chosen,
            })
    out.sort(key=lambda d: (not d["chosen"], d["cost_over_90_days"]))
    return [{"gap_to_cover_today": gap, "low_point": str(low),
             "principle": "R16 ties on every change set; pick the least 90-day cost that makes the plan safe, "
                          "then fewest changes, then lowest event id"}] + out
