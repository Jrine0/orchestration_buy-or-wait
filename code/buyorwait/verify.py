"""verify: hard invariants on an output row before it is written ([VERIFY] rules in SPEC_RULES.md).

`check_row` is shared by the pipeline (repair before write) and by
evaluation/check_invariants.py (audit after write), so both enforce one definition.
"""
from __future__ import annotations

import re
from datetime import date

COLUMNS = ["request_id", "amount_safe_to_pay", "affordability_status", "recommended_payment_method",
           "payment_plan", "earliest_date_for_full_payment", "spending_changes_needed", "decision_explanation"]
STATUSES = {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
METHODS = {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}
PLAN_RE = re.compile(r"^\d{4}-\d{2}-\d{2}:\d+(\.\d{1,2})?$")
CHANGE_RE = re.compile(r"^(stop:event_\d+|reduce_to:event_\d+:\d+(\.\d{1,2})?)$")


def parse_plan(s: str) -> list[tuple[date, float]]:
    if s == "none":
        return []
    out = []
    for part in s.split("|"):
        d, a = part.split(":")
        out.append((date.fromisoformat(d), float(a)))
    return out


def check_row(row: dict, req, profile=None, options=None, events=None) -> list[str]:
    errs = []
    try:
        amt = float(row["amount_safe_to_pay"])
    except ValueError:
        return ["R1 amount_safe_to_pay not numeric"]
    if not (-1e-9 <= amt <= req.requested_amount + 1e-6):
        errs.append("R1 amount out of [0, requested_amount]")
    st, m = row["affordability_status"], row["recommended_payment_method"]
    if st not in STATUSES:
        errs.append("enum affordability_status")
    if m not in METHODS:
        errs.append("enum recommended_payment_method")
    ed = row["earliest_date_for_full_payment"]
    if ed and ed != "":
        try:
            date.fromisoformat(ed)
        except ValueError:
            errs.append("R3 earliest date format")
    if st == "affordable_now" and ed != req.request_date.isoformat():
        errs.append("R2 affordable_now requires earliest == request_date")
    plan = row["payment_plan"]
    if plan != "none":
        parts = plan.split("|")
        if not all(PLAN_RE.match(p) for p in parts):
            errs.append("R14 payment_plan format")
        else:
            sched = parse_plan(plan)
            if [d for d, _ in sched] != sorted(d for d, _ in sched):
                errs.append("R14 plan not chronological")
            if m == "partial_payment":
                if len(sched) != 2:
                    errs.append("R12 partial plan must have two payments")
                else:
                    if abs(sum(a for _, a in sched) - req.requested_amount) > 0.011:
                        errs.append("R12 partial payments must sum to requested_amount")
                    if sched[0] != (req.request_date, round(amt, 2)):
                        errs.append("R12 first partial payment must be amount_safe_to_pay on request_date")
                    if ed != sched[1][0].isoformat():
                        errs.append("R12 second partial payment must be on earliest_date_for_full_payment")
                    if not (0 < amt < req.requested_amount):
                        errs.append("R12 partial requires 0 < amount < requested")
                    if not req.allows_partial_payment:
                        errs.append("R12 request does not allow partial payment")
                    if ed and date.fromisoformat(ed) > req.desired_completion_date:
                        errs.append("R12 remainder after desired_completion_date")
                if st != "affordable_with_plan":
                    errs.append("R12 partial requires affordable_with_plan")
            if m == "installments" and options is not None:
                ok = False
                for o in options:
                    if o.payment_method != "installments":
                        continue
                    step = o.payment_frequency_days or 30
                    from datetime import timedelta
                    exp = [(o.first_payment_date + timedelta(days=step * k), round(o.payment_amount, 2))
                           for k in range(o.number_of_payments)]
                    if [(d, round(a, 2)) for d, a in sched] == exp:
                        ok = True
                if not ok:
                    errs.append("R13 installment plan does not match a supplied option")
    elif m not in ("not_recommended",):
        errs.append("R14 plan 'none' only with not_recommended")
    if m == "not_recommended" and plan != "none":
        errs.append("R14 not_recommended must have plan none")
    if profile is not None and m in ("full_payment", "partial_payment", "installments") and m not in profile.methods:
        errs.append("R10 method not accepted by user")
    if profile is not None and m == "wait" and "full_payment" not in profile.methods:
        errs.append("R10 wait requires full_payment acceptance")
    sc = row["spending_changes_needed"]
    if sc != "none":
        parts = sc.split("|")
        if len(parts) > 3:
            errs.append("R15 more than three spending changes")
        if not all(CHANGE_RE.match(p) for p in parts):
            errs.append("R15 spending change format")
        ids = [p.split(":")[1] for p in parts]
        if len(ids) != len(set(ids)):
            errs.append("R15 stop and reduce on the same event")
        if events is not None and profile is not None:
            by_id = {e.event_id: e for e in events}
            for p in parts:
                bits = p.split(":")
                e = by_id.get(bits[1])
                if e is None:
                    errs.append(f"R15 unknown event {bits[1]}")
                    continue
                if e.category in profile.protected:
                    errs.append(f"R15 {bits[1]} is protected")
                if bits[0] == "stop" and (e.flexibility not in ("stoppable", "reducible_or_stoppable")
                                          or e.category not in profile.stoppable):
                    errs.append(f"R15 {bits[1]} not stoppable for this user")
                if bits[0] == "reduce_to":
                    if e.flexibility not in ("reducible", "reducible_or_stoppable") or e.category not in profile.reducible:
                        errs.append(f"R15 {bits[1]} not reducible for this user")
                    if e.minimum_allowed_amount is not None and float(bits[2]) < e.minimum_allowed_amount - 0.005:
                        errs.append(f"R15 {bits[1]} reduced below minimum_allowed_amount")
    if not row["decision_explanation"].strip():
        errs.append("explanation empty")
    return errs
