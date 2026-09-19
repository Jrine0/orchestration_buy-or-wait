"""Per-request financial context: history as of request_date + evidence -> dated flows.

Order of application (each step recorded in `trace` for the case file):
  1. recurring series from settled history (state.detect_series)
  2. income lifecycle from the ledger itself (a series whose latest row is a final payroll ends)
  3. pending / scheduled ledger rows (R7, R8)
  4. message deltas, oldest first, only if sent on or before request_date (no leakage)
Conflicts follow R17: an explicit amendment (message) overrides the projection it amends.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .config import SETTINGS, Settings
from .evidence import Delta, classify
from .forecast import window
from .loader import Dataset, Event, Profile, Request
from .state import Flow, Series, add_months, detect_series

# ledger descriptions that mark the last row of an income stream (lifecycle vocabulary, not labels)
ENDING_WORDS = ("final", "last ", "terminal", "severance")


@dataclass
class Context:
    request: Request
    profile: Profile
    series: list[Series]
    one_offs: list[Event]
    flows: list[Flow]
    deltas: list[Delta] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)


def series_flows(sr: Series, start: date, end: date, amount: float | None = None) -> list[Flow]:
    sign = -1 if sr.direction == "debit" else 1
    amt = sr.amount if amount is None else amount
    return [Flow(date=d, amount=sign * amt, label=sr.key, category=sr.category, kind="recurring",
                 series_key=sr.key, event_id=sr.latest_event.event_id, essential=sr.is_essential,
                 monthly=sr.cadence == "monthly")
            for d in sr.occurrences(start, end)]


def _salary_flows(flows: list[Flow]) -> list[Flow]:
    return sorted([f for f in flows if f.category == "salary" and f.amount > 0], key=lambda f: f.date)


def _monthly(day_anchor: date, amount: float, start: date, end: date, label: str, include_anchor=True) -> list[Flow]:
    out, n = [], 0 if include_anchor else 1
    while True:
        d = add_months(day_anchor, n, day_anchor.day)
        if d > end:
            break
        if d >= start:
            out.append(Flow(date=d, amount=amount, label=label, category="salary", kind="evidence"))
        n += 1
    return out


def build(ds: Dataset, req: Request, s: Settings = SETTINGS) -> Context:
    prof = ds.profiles[req.user_id]
    events = ds.events.get(req.user_id, [])
    start, end = window(req.request_date, s)
    first = start if s.include_request_day_flows else start + timedelta(days=1)
    trace: list[str] = []

    history = [e for e in events if e.settlement_date and e.settlement_date < req.request_date and e.status == "settled"]
    series, one_offs = detect_series(history, s)

    flows: list[Flow] = []
    for sr in series:
        if sr.direction == "credit":
            sr.amount = sr.amounts[-1]  # income: latest confirmed amount, never an average of past raises/cuts
            if any(w in sr.latest_event.description.lower() for w in ENDING_WORDS):
                trace.append(f"income series {sr.key} ended at {sr.latest_event.event_id} "
                             f"('{sr.latest_event.description}'); not projected")
                continue
            if sr.occurrences(sr.last_date + timedelta(days=1), req.request_date - timedelta(days=7)):
                trace.append(f"income series {sr.key} missed an expected credit after {sr.last_date}; "
                             f"treated as stopped (R19: no unsupported income)")
                continue
        flows.extend(series_flows(sr, first, end))
        trace.append(f"series {sr.key}: {sr.cadence} last={sr.last_date} amount={sr.amount:.2f} "
                     f"n={len(sr.events)} flex={sr.flexibility}")

    # R7/R8: pending and scheduled ledger rows
    for e in events:
        if e.amount is None:
            if e.status in ("pending", "scheduled"):
                trace.append(f"{e.event_id} {e.status} amount unknown (no readable image); not reserved")
            continue
        sd = e.settlement_date or start
        if e.status in ("pending", "scheduled") and e.direction == "debit":
            flows.append(Flow(date=max(sd, first), amount=-e.amount, label=e.description, category=e.category,
                              kind=e.status, event_id=e.event_id))
            trace.append(f"reserved {e.status} debit {e.event_id} {e.amount:.2f} on {max(sd, first)} (R7)")
        elif e.status == "scheduled" and e.direction == "credit" and e.category == "salary":
            existing = _salary_flows(flows)
            near = sorted([f for f in existing if abs((f.date - sd).days) <= 12
                           and abs(f.amount - e.amount) <= 0.25 * e.amount], key=lambda f: abs((f.date - sd).days))
            if near:
                flows.remove(near[0])
            if not existing:
                # confirmed pay with no regular history (new job): continues monthly from the confirmed date
                flows.extend(_monthly(sd, e.amount, first, end, e.description))
                trace.append(f"confirmed salary {e.event_id} {e.amount:.2f} on {sd}, continued monthly (R8)")
            elif start <= sd <= end:
                flows.append(Flow(date=sd, amount=e.amount, label=e.description, category="salary",
                                  kind="scheduled", event_id=e.event_id))
                trace.append(f"confirmed salary {e.event_id} {e.amount:.2f} on {sd} replaces projection (R8)")
                settled = near[0].amount if near else max(f.amount for f in existing)
                if abs(settled - e.amount) > 0.01:
                    later = [f for f in _salary_flows(flows) if f.date > sd]
                    trace.append(f"confirmed amount {e.amount:.2f} differs from settled payroll {settled:.2f}; only the "
                                 f"{sd} payroll is confirmed at the new amount, so the {len(later)} later projected "
                                 f"payroll(s) stay at {settled:.2f} (R19: no unsupported income; the safer reading)")
        elif e.status in ("pending",) and e.direction == "credit":
            trace.append(f"ignored pending credit {e.event_id} {e.amount:.2f} (R7)")
        elif e.status in ("failed", "cancelled", "unrealized"):
            trace.append(f"ignored {e.status} {e.event_id} (R7)")

    ctx = Context(request=req, profile=prof, series=series, one_offs=one_offs, flows=flows, trace=trace)
    msgs = sorted([m for m in ds.messages if m.user_id == req.user_id
                   and (m.sent_at is None or m.sent_at <= req.request_date)],
                  key=lambda m: (m.sent_at or date.min, m.message_id))
    for m in msgs:
        for d in classify(m):
            ctx.deltas.append(d)
            apply_delta(ctx, d, ds, first, end)
    return ctx


def apply_delta(ctx: Context, d: Delta, ds: Dataset, first: date, end: date) -> None:
    flows, trace = ctx.flows, ctx.trace
    home = ctx.profile.home_currency
    sal = _salary_flows(flows)

    def conv(amount, on):
        return ds.rates.convert(amount, d.currency or home, home, on or first) if amount is not None else None

    def primary_key():
        keys = {}
        for f in sal:
            keys[f.series_key or f.label] = max(keys.get(f.series_key or f.label, 0), f.amount)
        return max(keys, key=keys.get) if keys else None

    tag = f"{d.message_id} {d.intent}"
    if d.intent in ("employment_ended", "income_stream_ended"):
        for f in sal:
            flows.remove(f)
        trace.append(f"{tag}: removed {len(sal)} projected salary credits")
    elif d.intent in ("household_income_ended", "base_salary_commission_pending"):
        # drop the ended / unearned streams; the undated "confirmed" figure conflicts with the settled
        # payroll amount, so the settled ledger amount is kept (R17 rung 3) and the message is recorded
        pk = primary_key()
        dropped = 0
        for f in sal:
            if (f.series_key or f.label) != pk:
                flows.remove(f)
                dropped += 1
        kept = next((f.amount for f in sal if (f.series_key or f.label) == pk), None)
        msg_amt = conv(d.amount, first)
        rung = "R17.3 settled payroll amount kept" if kept is not None and msg_amt is not None and abs(kept - msg_amt) > 0.01 else "consistent"
        trace.append(f"{tag}: dropped {dropped} other income flows; primary salary {kept} "
                     f"(message states {msg_amt}; {rung})")
    elif d.intent == "salary_resumes" and d.on:
        amt = conv(d.amount, d.on)
        for f in sal:
            flows.remove(f)
        flows.extend(_monthly(d.on, amt, first, end, "salary (resumed)"))
        trace.append(f"{tag}: salary {amt} monthly from {d.on}")
    elif d.intent == "salary_raise_from" and d.on:
        amt = conv(d.amount, d.on)
        for f in sal:
            if f.date >= d.on:
                f.amount = amt
        trace.append(f"{tag}: salary {amt} from {d.on}")
    elif d.intent in ("salary_next_reduced", "salary_temporary", "regular_salary_confirmed"):
        # the confirmed amount is the latest payroll fact; no later change is confirmed, so it carries forward
        if sal and d.amount is not None:
            for f in sal:
                f.amount = conv(d.amount, f.date)
            trace.append(f"{tag}: salary from {sal[0].date} = {sal[0].amount:.2f} (latest confirmed pay)")
    elif d.intent == "salary_with_arrears":
        if sal and d.amount is not None:
            base = conv(d.amount, sal[0].date)
            arrears = conv(d.amount2 or 0.0, sal[0].date)
            for f in sal:
                f.amount = base
            sal[0].amount = base + arrears
            trace.append(f"{tag}: next salary {base:.2f} + one-time arrears {arrears:.2f}, then {base:.2f}")
    elif d.intent == "salary_date_moved" and d.on:
        if sal:
            nxt = sal[0]
            trace.append(f"{tag}: salary on {nxt.date} moved to {d.on}")
            nxt.date = d.on
            if d.on > end:
                flows.remove(nxt)
    elif d.intent in ("first_salary", "fx_salary_confirmed") and d.on and d.amount is not None:
        amt = conv(d.amount, d.on)
        for f in sal:
            if abs((f.date - d.on).days) <= 12:
                flows.remove(f)
        continues = [f for f in _salary_flows(flows) if f.date > d.on]
        if continues:
            if first <= d.on <= end:
                flows.append(Flow(date=d.on, amount=amt, label=f"confirmed salary ({d.message_id})",
                                  category="salary", kind="evidence"))
            trace.append(f"{tag}: confirmed salary {amt:.2f} on {d.on} (R8); existing payroll stream continues after it")
        else:
            # confirmed start of a salaried job with no regular payroll history yet: the same rule as a scheduled
            # "Next confirmed salary" without history - it continues monthly from the confirmed date
            flows.extend(_monthly(d.on, amt, first, end, f"confirmed salary ({d.message_id})"))
            trace.append(f"{tag}: confirmed salary {amt:.2f} on {d.on}, continued monthly (no payroll stream to "
                         f"continue it; same rule as a scheduled confirmed salary without history)")
    elif d.intent == "invoice_approved" and d.on and d.amount is not None:
        amt = conv(d.amount, d.on)
        if first <= d.on <= end:
            flows.append(Flow(date=d.on, amount=amt, label=f"approved invoice ({d.message_id})",
                              category="salary", kind="evidence"))
        trace.append(f"{tag}: approved invoice {amt:.2f} on {d.on}; unapproved invoices excluded")
    elif d.intent == "rent_increase" and d.pct:
        n = 0
        for f in flows:
            if f.category in ("rent", "housing") and f.amount < 0 and f.kind == "recurring" and "rent" in f.label + f.category:
                f.amount *= 1 + d.pct / 100
                n += 1
        trace.append(f"{tag}: {n} projected rent payments raised {d.pct}%")
    else:
        trace.append(f"{tag}: no cash-flow change ({d.note or 'informational, pending, or non-cash'})")
