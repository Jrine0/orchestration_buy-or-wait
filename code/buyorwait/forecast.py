"""forecast: pure deterministic 90-day balance simulation (R6).

No model calls. Given an opening balance, a minimum, and dated flows, answers:
  - lowest balance and the binding (date, flow) that produced it
  - amount_safe_to_pay on request_date (R5, before spending changes)
  - earliest_date_for_full_payment (R4, independent of preferences)
  - whether an arbitrary payment schedule keeps the balance >= minimum
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from .config import SETTINGS, Settings
from .state import Flow

EPS = 0.005


@dataclass
class Trajectory:
    points: list[tuple[date, float, Flow]]   # balance after each flow, in application order
    minimum: float
    binding: Optional[tuple[date, float, Flow]]


def _order(flows: list[Flow], s: Settings) -> list[Flow]:
    # same-day ordering: credits post at start of day (payday), then bills, then plan payments
    def rank(f: Flow) -> int:
        if f.kind == "plan":
            return 3
        if s.same_day_debits_first:
            return 1 if f.amount >= 0 else 0
        if f.amount >= 0:
            return 1
        return 0 if (s.variable_spend_before_credit and not f.monthly) else 2
    return sorted(flows, key=lambda f: (f.date, rank(f)))


def simulate(opening: float, flows: list[Flow], s: Settings = SETTINGS) -> Trajectory:
    bal = opening
    pts = []
    low, bind = opening, None
    for f in _order(flows, s):
        bal += f.amount
        pts.append((f.date, bal, f))
        if bal < low - 1e-9:
            low, bind = bal, (f.date, bal, f)
    return Trajectory(points=pts, minimum=low, binding=bind)


def window(request_date: date, s: Settings = SETTINGS) -> tuple[date, date]:
    return request_date, request_date + timedelta(days=s.horizon_days - 1)  # inclusive of both ends


def min_balance_from(opening: float, flows: list[Flow], start: date, s: Settings = SETTINGS) -> float:
    """Lowest balance at or after `start` (balance at start of `start` included)."""
    bal = opening
    low = None
    for f in _order(flows, s):
        if f.date >= start and low is None:
            low = bal
        bal += f.amount
        if f.date >= start:
            low = min(low, bal)
    return bal if low is None else low


def plan_flows(schedule: list[tuple[date, float]], label="payment") -> list[Flow]:
    return [Flow(date=d, amount=-a, label=label, category="request", kind="plan") for d, a in schedule]


def is_safe(opening: float, minimum: float, flows: list[Flow], schedule: list[tuple[date, float]],
            s: Settings = SETTINGS) -> bool:
    tr = simulate(opening, flows + plan_flows(schedule), s)
    return tr.minimum >= minimum - EPS


def safe_amount_today(opening: float, minimum: float, flows: list[Flow], request_date: date,
                      requested: float, s: Settings = SETTINGS) -> float:
    tr = simulate(opening, flows, s)
    headroom = tr.minimum - minimum
    return round(max(0.0, min(requested, headroom)), 2)


def capacity_from_baseline(opening: float, minimum: float, flows: list[Flow], request_date: date,
                           requested: float, s: Settings = SETTINGS):
    """One baseline trajectory -> (trajectory, amount_safe_to_pay, earliest_date_for_full_payment).

    Both capacity fields come from the same simulated path, so they cannot disagree (R4, R5).
    A single payment X on day d is applied after every flow dated d (see _order). It is safe iff
      every baseline balance up to and including day d is >= minimum, and
      (balance at end of day d, and every later balance) - X >= minimum.
    """
    tr = simulate(opening, flows, s)
    safe = round(max(0.0, min(requested, tr.minimum - minimum)), 2)
    start, end = window(request_date, s)
    pts = tr.points
    # end-of-day balance and prefix minimum (opening included) for each day in the window
    earliest = None
    bal, prefix_low, i = opening, opening, 0
    n = len(pts)
    suffix_low = [0.0] * (n + 1)          # min balance over pts[k:]
    suffix_low[n] = float("inf")
    for k in range(n - 1, -1, -1):
        suffix_low[k] = min(pts[k][1], suffix_low[k + 1])
    d = start
    while d <= end:
        while i < n and pts[i][0] <= d:
            bal = pts[i][1]
            prefix_low = min(prefix_low, bal)
            i += 1
        after_low = min(bal, suffix_low[i])
        if prefix_low >= minimum - EPS and after_low - requested >= minimum - EPS:
            earliest = d
            break
        d += timedelta(days=1)
    return tr, safe, earliest


def earliest_full_payment(opening: float, minimum: float, flows: list[Flow], request_date: date,
                          requested: float, s: Settings = SETTINGS) -> Optional[date]:
    start, end = window(request_date, s)
    d = start
    while d <= end:
        if is_safe(opening, minimum, flows, [(d, requested)], s):
            return d
        d += timedelta(days=1)
    return None
