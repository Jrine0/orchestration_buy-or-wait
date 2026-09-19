"""state: financial-state reconstruction.

Turns a user's event history into (a) detected recurring series and (b) the list
of dated future cash flows the 90-day forecast consumes. Cash-state rules:
  R7/R32  settled history only drives recurrence; pending/scheduled debits are
          reserved; pending credits, failed, cancelled, unrealized are ignored.
  R8      confirmed salary counts on its settlement date.
  R34     recurrence only with enough regular history.
"""
from __future__ import annotations

import calendar
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from .config import SETTINGS, Settings
from .loader import Event

ONE_OFF_TYPES = {"refund", "investment_sale", "investment_valuation", "investment_purchase"}
ONE_OFF_CATEGORIES = {"windfall", "work_expense"}
CHANGEABLE_FLEX = {"reducible", "stoppable", "reducible_or_stoppable"}


def add_months(d: date, n: int, day: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(day, calendar.monthrange(y, m)[1]))


@dataclass
class Series:
    key: str
    category: str
    direction: str
    event_type: str
    cadence: str                 # "monthly" | "every_<k>_days"
    interval: int
    day_of_month: Optional[int]
    last_date: date
    amounts: list[float]
    events: list[Event]
    flexibility: str
    minimum_allowed_amount: Optional[float]
    amount: float = 0.0          # projected per-occurrence amount (positive)
    notes: list[str] = field(default_factory=list)

    @property
    def latest_event(self) -> Event:
        return self.events[-1]

    @property
    def is_essential(self) -> bool:  # R24
        return self.flexibility not in CHANGEABLE_FLEX

    def occurrences(self, start: date, end: date) -> list[date]:
        out = []
        if self.cadence == "monthly":
            n = 1
            while True:
                d = add_months(self.last_date, n, self.day_of_month)
                if d > end:
                    break
                if d >= start:
                    out.append(d)
                n += 1
        else:
            d = self.last_date + timedelta(days=self.interval)
            while d <= end:
                if d >= start:
                    out.append(d)
                d += timedelta(days=self.interval)
        return out


@dataclass
class Flow:
    date: date
    amount: float                # signed: + credit, - debit
    label: str
    category: str
    kind: str                    # recurring | pending | scheduled | evidence | plan
    series_key: str = ""
    event_id: str = ""
    essential: bool = True
    monthly: bool = True          # False for every-k-days variable spending (groceries, dining, transport)


def _regular(dates: list[date], s: Settings) -> Optional[tuple[str, int]]:
    if len(dates) < s.min_occurrences:
        return None
    iv = [(b - a).days for a, b in zip(dates, dates[1:])]
    if all(27 <= x <= 32 for x in iv):
        return ("monthly", 30)
    med = statistics.median(iv)
    if med > 0 and all(abs(x - med) <= 1 for x in iv):
        return (f"every_{int(med)}_days", int(med))
    # tolerate one gap (e.g. a paused month) if recent intervals are regular
    recent = iv[-(s.min_occurrences - 1):]
    if all(27 <= x <= 32 for x in recent) and len(dates) >= s.min_occurrences + 1:
        return ("monthly", 30)
    # a regular monthly stream whose latest occurrence slipped (e.g. a delayed payroll)
    if len(iv) >= s.min_occurrences - 1 and all(27 <= x <= 32 for x in iv[:-1]) and 27 <= iv[-1] <= 45:
        return ("monthly", 30)
    return None


def _on_cadence(evs: list[Event], s: Settings) -> tuple[list[Event], list[Event]]:
    """Walk back from the latest event along the modal interval; keep events on that grid.
    Accept only if the grid holds >= 75% of events (otherwise it is not one stream)."""
    if len(evs) < s.min_occurrences + 1:
        return [], evs
    iv = [(b.settlement_date - a.settlement_date).days for a, b in zip(evs, evs[1:])]
    iv = [x for x in iv if x > 0]
    if not iv:
        return [], evs
    step = max(set(iv), key=lambda x: (iv.count(x), -x))
    best: list[Event] = []
    for anchor in reversed(evs[-3:]):  # the latest event itself may be the one-off
        chain = [anchor]
        for e in reversed([x for x in evs if x.settlement_date < anchor.settlement_date]):
            gap = (chain[-1].settlement_date - e.settlement_date).days
            if abs(gap - step) <= 1 or (27 <= step <= 32 and 27 <= gap <= 32):
                chain.append(e)
        chain.reverse()
        if len(chain) > len(best):
            best = chain
    if len(best) >= max(s.min_occurrences, 0.75 * len(evs)) and _regular([e.settlement_date for e in best], s):
        ids = {e.event_id for e in best}
        return best, [e for e in evs if e.event_id not in ids]
    return [], evs


def detect_series(history: list[Event], s: Settings = SETTINGS) -> tuple[list[Series], list[Event]]:
    """Group settled history into recurring series; return (series, one_offs)."""
    cands = [e for e in history
             if e.status == "settled" and e.direction in ("debit", "credit")
             and e.event_type not in ONE_OFF_TYPES and e.category not in ONE_OFF_CATEGORIES
             and not e.linked_event_id and e.amount is not None]
    series: list[Series] = []
    used: set[str] = set()

    def build(key, evs, reg):
        evs = sorted(evs, key=lambda e: (e.settlement_date, e.num))
        cadence, interval = reg
        days = [e.settlement_date.day for e in evs]
        dom = max(set(days), key=lambda d: (days.count(d), d)) if cadence == "monthly" else None
        last = evs[-1]
        return Series(key=key, category=last.category, direction=last.direction, event_type=last.event_type,
                      cadence=cadence, interval=interval, day_of_month=dom, last_date=last.settlement_date,
                      amounts=[e.amount for e in evs], events=evs, flexibility=last.flexibility,
                      minimum_allowed_amount=last.minimum_allowed_amount)

    by_cat: dict[tuple, list[Event]] = {}
    for e in cands:
        by_cat.setdefault((e.category, e.direction), []).append(e)
    one_offs = []
    for (cat, dirn), evs in sorted(by_cat.items()):
        evs.sort(key=lambda e: (e.settlement_date, e.num))
        # pass 1: the whole category is one regular stream (bills, subscriptions, pooled groceries)
        reg = _regular([e.settlement_date for e in evs], s)
        if reg:
            series.append(build(f"{cat}:{dirn}:*", evs, reg))
            continue
        # pass 1b: a regular stream with a few off-cadence one-offs mixed in (e.g. a large invoice)
        chain, extras = _on_cadence(evs, s)
        if chain:
            series.append(build(f"{cat}:{dirn}:*", chain, _regular([e.settlement_date for e in chain], s)))
            one_offs.extend(extras)
            continue
        # pass 2: split by stable description (payroll next to arrears/bonus, bill next to one-off purchase)
        by_desc: dict[str, list[Event]] = {}
        for e in evs:
            by_desc.setdefault(e.description, []).append(e)
        for desc, sub in sorted(by_desc.items()):
            reg = _regular([e.settlement_date for e in sub], s)
            if reg:
                series.append(build(f"{cat}:{dirn}:{desc}", sub, reg))
            else:
                one_offs.extend(sub)
    for sr in series:
        sr.amount = project_amount(sr, s)
    return series, one_offs


def project_amount(sr: Series, s: Settings) -> float:
    a = sr.amounts
    if max(a) - min(a) < 1e-9:
        return a[-1]
    if s.variable_amount == "max":
        return max(a)
    if s.variable_amount == "last":
        return a[-1]
    if s.variable_amount == "recent_mean":
        w = a[-s.recent_window:]
        return sum(w) / len(w)
    if s.variable_amount == "recent_median":
        return statistics.median(a[-s.recent_window:])
    if s.variable_amount == "recent_max":
        return max(a[-s.recent_window:])
    if s.variable_amount == "median":
        return statistics.median(a)
    if s.variable_amount == "mean_std":
        return statistics.mean(a) + statistics.pstdev(a)
    if s.variable_amount == "p75":
        q = sorted(a)
        return q[int(round(0.75 * (len(q) - 1)))]
    return sum(a) / len(a)
