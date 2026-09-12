"""ingest: CSV files -> typed records. Knows nothing about decisions.

Header names are normalized (lowercase, separators collapsed) so cosmetic header
drift does not break the run; required columns missing fail loudly by name.
Currency conversion to home_currency happens here (R21) so nothing downstream
sees mixed currency.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from .config import dataset_dir


def _norm_header(h: str) -> str:
    return re.sub(r"[\s\-_]+", "_", h.strip().lower().lstrip("﻿"))


def read_csv(path: Path, required: list[str]) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = [_norm_header(h) for h in next(reader)]
        missing = [c for c in required if c not in header]
        if missing:
            raise ValueError(f"{path.name}: missing required columns {missing}; found {header}")
        return [dict(zip(header, [v.strip() for v in row])) for row in reader if any(row)]


def to_float(v: str) -> Optional[float]:
    if v is None or v == "":
        return None  # R9: blank is unknown, never zero
    return float(re.sub(r"[^\d.\-]", "", v))


def to_date(v: str) -> Optional[date]:
    return date.fromisoformat(v[:10]) if v else None


def to_bool(v: str) -> bool:
    return v.strip().lower() in {"true", "1", "yes", "y", "t"}


def split_list(v: str) -> list[str]:
    return [x.strip() for x in v.split("|") if x.strip()] if v else []


@dataclass
class Profile:
    user_id: str
    home_currency: str
    balance: float
    minimum_balance: float
    priorities: list[str]
    protected: set[str]
    reducible: set[str]
    stoppable: set[str]
    methods: set[str]
    max_installment_months: Optional[float]


@dataclass
class Event:
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str
    amount: Optional[float]          # home currency after conversion; None = unknown
    original_amount: Optional[float]
    currency: str
    event_date: Optional[date]
    settlement_date: Optional[date]
    status: str
    linked_event_id: str
    flexibility: str
    minimum_allowed_amount: Optional[float]
    provenance: str = "financial_events.csv"
    notes: list[str] = field(default_factory=list)

    @property
    def num(self) -> int:
        return int(re.sub(r"\D", "", self.event_id) or 0)


@dataclass
class Request:
    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: float
    desired_completion_date: date
    allows_partial_payment: bool
    request_text: str
    solved: dict = field(default_factory=dict)  # sample rows only; never read by the engine


@dataclass
class PaymentOption:
    payment_option_id: str
    request_id: str
    payment_method: str
    payment_amount: float
    number_of_payments: int
    first_payment_date: date
    payment_frequency_days: Optional[int]
    financing_fee: float
    total_payable_amount: float

    @property
    def num(self) -> int:
        return int(re.sub(r"\D", "", self.payment_option_id) or 0)


@dataclass
class Message:
    message_id: str
    user_id: str
    request_id: str
    related_event_id: str
    sent_at: Optional[date]
    source_type: str
    text: str


@dataclass
class ImageRef:
    image_id: str
    user_id: str
    request_id: str
    related_event_id: str
    path: Path


REQUEST_TYPES = {"purchase", "travel", "education", "family_transfer", "debt_repayment",
                 "investment", "housing", "emergency_expense", "other"}


class Rates:
    """Fixed dated rates (R21). Direct row for the date first, then inverse, then nearest earlier date."""

    def __init__(self, rows: list[dict]):
        self.table: dict[tuple[str, str], list[tuple[date, float]]] = {}
        for r in rows:
            key = (r["from_currency"], r["to_currency"])
            self.table.setdefault(key, []).append((to_date(r["rate_date"]), float(r["rate"])))
        for v in self.table.values():
            v.sort()

    def _lookup(self, key, d: date) -> Optional[float]:
        series = self.table.get(key)
        if not series:
            return None
        exact = [r for (dd, r) in series if dd == d]
        if exact:
            return exact[-1]
        earlier = [r for (dd, r) in series if dd <= d]
        return earlier[-1] if earlier else series[0][1]

    def convert(self, amount: float, src: str, dst: str, d: date) -> float:
        if src == dst or amount is None:
            return amount
        r = self._lookup((src, dst), d)
        if r is not None:
            return amount * r
        r = self._lookup((dst, src), d)
        if r:
            return amount / r
        raise ValueError(f"no exchange rate {src}->{dst} near {d}")


@dataclass
class Dataset:
    profiles: dict[str, Profile]
    events: dict[str, list[Event]]
    requests: list[Request]
    samples: list[Request]
    options: dict[str, list[PaymentOption]]
    messages: list[Message]
    images: list[ImageRef]
    rates: Rates


def load(root: Optional[Path] = None) -> Dataset:
    root = Path(root or dataset_dir())
    rates = Rates(read_csv(root / "exchange_rates.csv", ["rate_date", "from_currency", "to_currency", "rate"]))

    profiles = {}
    for r in read_csv(root / "financial_profiles.csv",
                      ["user_id", "home_currency", "current_available_balance", "minimum_balance_to_keep"]):
        mim = to_float(r.get("max_installment_months", ""))
        profiles[r["user_id"]] = Profile(
            user_id=r["user_id"], home_currency=r["home_currency"],
            balance=to_float(r["current_available_balance"]) or 0.0,
            minimum_balance=to_float(r["minimum_balance_to_keep"]) or 0.0,
            priorities=split_list(r.get("financial_priorities", "")),
            protected=set(split_list(r.get("expense_categories_to_protect", ""))),
            reducible=set(split_list(r.get("expense_categories_user_is_willing_to_reduce", ""))),
            stoppable=set(split_list(r.get("expense_categories_user_is_willing_to_stop", ""))),
            methods=set(split_list(r.get("payment_methods_user_will_consider", ""))),
            max_installment_months=mim,
        )

    events: dict[str, list[Event]] = {}
    for r in read_csv(root / "financial_events.csv",
                      ["event_id", "user_id", "category", "direction", "amount", "currency", "status"]):
        prof = profiles.get(r["user_id"])
        amt = to_float(r["amount"])
        sd = to_date(r.get("settlement_date", "")) or to_date(r.get("event_date", ""))
        home = prof.home_currency if prof else r["currency"]
        conv = rates.convert(amt, r["currency"], home, sd) if amt is not None and sd else amt
        events.setdefault(r["user_id"], []).append(Event(
            event_id=r["event_id"], user_id=r["user_id"], event_type=r.get("event_type", ""),
            description=r.get("description", ""), category=r["category"], direction=r["direction"],
            amount=conv, original_amount=amt, currency=r["currency"],
            event_date=to_date(r.get("event_date", "")), settlement_date=sd,
            status=r["status"].lower(), linked_event_id=r.get("linked_event_id", ""),
            flexibility=r.get("flexibility", "fixed") or "fixed",
            minimum_allowed_amount=to_float(r.get("minimum_allowed_amount", "")),
        ))

    def parse_requests(path: Path, solved: bool) -> list[Request]:
        out = []
        if not path.exists():
            return out
        for r in read_csv(path, ["request_id", "user_id", "request_date", "requested_amount"]):
            rt = r.get("request_type", "other")
            out.append(Request(
                request_id=r["request_id"], user_id=r["user_id"], request_date=to_date(r["request_date"]),
                request_type=rt if rt in REQUEST_TYPES else "other",  # R38
                requested_amount=to_float(r["requested_amount"]),
                desired_completion_date=to_date(r.get("desired_completion_date", "")) or to_date(r["request_date"]),
                allows_partial_payment=to_bool(r.get("allows_partial_payment", "false")),
                request_text=r.get("request_text", ""),
                solved={k: r[k] for k in r if k in {
                    "amount_safe_to_pay", "affordability_status", "recommended_payment_method", "payment_plan",
                    "earliest_date_for_full_payment", "spending_changes_needed", "decision_explanation"}} if solved else {},
            ))
        return out

    options: dict[str, list[PaymentOption]] = {}
    for r in read_csv(root / "request_payment_options.csv", ["payment_option_id", "request_id", "payment_method"]):
        freq = to_float(r.get("payment_frequency_days", ""))
        options.setdefault(r["request_id"], []).append(PaymentOption(
            payment_option_id=r["payment_option_id"], request_id=r["request_id"],
            payment_method=r["payment_method"], payment_amount=to_float(r["payment_amount"]),
            number_of_payments=int(to_float(r["number_of_payments"]) or 1),
            first_payment_date=to_date(r["first_payment_date"]),
            payment_frequency_days=int(freq) if freq else None,
            financing_fee=to_float(r.get("financing_fee", "")) or 0.0,
            total_payable_amount=to_float(r["total_payable_amount"]),
        ))

    messages = [Message(
        message_id=r["message_id"], user_id=r["user_id"], request_id=r.get("request_id", ""),
        related_event_id=r.get("related_event_id", ""), sent_at=to_date(r.get("sent_at", "")),
        source_type=r.get("source_type", ""), text=r.get("message_text", ""),
    ) for r in read_csv(root / "messages.csv", ["message_id", "user_id", "message_text"])]

    images = [ImageRef(
        image_id=r["image_id"], user_id=r["user_id"], request_id=r.get("request_id", ""),
        related_event_id=r.get("related_event_id", ""),
        path=root / "media" / "images" / f"{r['image_id']}.png",
    ) for r in read_csv(root / "images.csv", ["image_id", "user_id"])]

    return Dataset(profiles=profiles, events=events,
                   requests=parse_requests(root / "requests.csv", False),
                   samples=parse_requests(root / "sample_requests.csv", True),
                   options=options, messages=messages, images=images, rates=rates)
