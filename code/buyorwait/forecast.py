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
        credit_rank = 1 if s.same_day_debits_first else 0
        if f.kind == "plan":
            return 2
        return credit_rank if f.amount >= 0 else 1 - credit_rank
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
    return request_date, request_date + timedelta(days=s.horizon_days - 1)  # 90 calendar days incl. request_date


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


def earliest_full_payment(opening: float, minimum: float, flows: list[Flow], request_date: date,
                          requested: float, s: Settings = SETTINGS) -> Optional[date]:
    start, end = window(request_date, s)
    d = start
    while d <= end:
        if is_safe(opening, minimum, flows, [(d, requested)], s):
            return d
        d += timedelta(days=1)
    return None
