"""extraction: messages -> typed fact deltas (rule-based, bilingual EN/ID).

Messages are untrusted evidence (R18). Each is classified into one intent with
explicit keyword patterns and its numbers/dates are pulled by regex. The output
is a list of Delta objects the context builder applies to the forecast; nothing
here can touch a scored field directly. Unrecognised messages produce a
`no_effect` delta that is logged in the case file (abstain -> R17.4).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from .loader import Message

AMOUNT_RE = re.compile(r"\b(IDR|INR|ZAR|USD|EUR)\s?([\d][\d,]*(?:\.\d+)?)")
DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s?%")


@dataclass
class Delta:
    message_id: str
    intent: str
    amount: Optional[float] = None
    currency: Optional[str] = None
    amount2: Optional[float] = None
    on: Optional[date] = None
    pct: Optional[float] = None
    related_event_id: str = ""
    note: str = ""


# (intent, all-of keyword groups; each group is any-of). Order matters: first match wins.
RULES: list[tuple[str, list[list[str]]]] = [
    ("scam_ignore", [["release charge", "processing charge now", "biaya pencairan", "biaya pemrosesan sekarang"]]),
    ("employment_ended", [["employment has ended", "hubungan kerja anda telah berakhir"]]),
    ("income_stream_ended", [["seasonal contract has ended", "kontrak musiman saat ini telah berakhir"]]),
    ("household_income_ended", [["household employment record has ended", "sumber pendapatan kerja rumah tangga telah berakhir"]]),
    ("salary_resumes", [["resumes on", "dilanjutkan pada", "kembali dibayarkan"]]),
    ("salary_date_moved", [["now expected on", "replaces the payroll date", "kini diperkirakan masuk", "menggantikan tanggal"]]),
    ("salary_raise_from", [["increased to", "naik menjadi"], ["applies from", "berlaku mulai"]]),
    ("salary_next_reduced", [["next salary is reduced", "gaji berikutnya dikurangi", "gaji anda berikutnya dikurangi"]]),
    ("salary_temporary", [["temporary monthly pay", "gaji bulanan sementara"]]),
    ("salary_with_arrears", [["arrears adjustment", "penyesuaian tunggakan"]]),
    ("base_salary_commission_pending", [["base salary", "gaji pokok"], ["commission", "komisi"]]),
    ("first_salary", [["first salary", "gaji pertama"]]),
    ("fx_salary_confirmed", [["confirmed for", "dikonfirmasi untuk", "confirmed a"], ["salary", "gaji"]]),
    ("invoice_approved", [["approved an invoice payment", "menyetujui pembayaran faktur"]]),
    ("rent_increase", [["increases monthly rent", "menaikkan biaya sewa"]]),
    ("bonus_pending", [["quarterly bonus", "bonus kuartalan"]]),
    ("regular_salary_confirmed", [["regular salary for the next payroll", "gaji rutin untuk penggajian berikutnya"]]),
    ("gig_payout_pending", [["payout is still pending", "payout is closed", "pembayaran berikutnya dari", "masih tertunda"]]),
    ("prize_pending", [["prize claim has been verified", "klaim hadiah anda sudah diverifikasi"]]),
    ("prize_received", [["prize proceeds have reached", "hadiah"]]),
    ("refund_pending", [["refund has been initiated", "refund is still processing", "pengembalian dana sudah diproses", "belum masuk ke rekening"]]),
    ("unrealized_investment", [["displayed market value", "displayed value", "nilai investasi yang ditampilkan"]]),
    ("investment_sale_settled", [["sale have settled", "proceeds from your investment sale", "hasil penjualan investasi"]]),
    ("reimbursement_closed", [["reimbursement", "penggantian atas biaya kerja"]]),
    ("internal_transfer", [["transfer between your two accounts", "transfer antara dua rekening"]]),
    ("failed_debit_retry", [["previous debit attempt failed", "another debit will be attempted"]]),
    ("duplicate_charge_open", [["extra card charge", "tagihan kartu tambahan"]]),
    ("separate_card_minimums", [["minimum payments due on two separate", "separate accounts"]]),
    ("fx_charge_pending", [["charged in a foreign currency", "dikenakan dalam mata uang asing"]]),
    ("receipt_final_amount", [["receipt", "final inr amount", "final amount"]]),
]


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def classify(msg: Message) -> list[Delta]:
    text = msg.text
    low = text.lower()
    amounts = [(c, _num(v)) for c, v in AMOUNT_RE.findall(text)]
    dates = [date.fromisoformat(d) for d in DATE_RE.findall(text)]
    pct = PCT_RE.search(text)
    out: list[Delta] = []
    for intent, groups in RULES:
        if all(any(k in low for k in g) for g in groups):
            d = Delta(message_id=msg.message_id, intent=intent, related_event_id=msg.related_event_id)
            if amounts:
                d.currency, d.amount = amounts[0]
                if len(amounts) > 1:
                    d.amount2 = amounts[1][1]
            if dates:
                d.on = dates[-1]
            if pct and intent == "rent_increase":
                d.pct = float(pct.group(1))
            out.append(d)
            break
    if not out:
        out.append(Delta(message_id=msg.message_id, intent="no_effect", related_event_id=msg.related_event_id,
                         note="unrecognised; abstained"))
    # a wallet/receipt notice can also confirm an upcoming salary (e.g. "confirmed a USD 1296 salary credit for 15 September 2026")
    m = re.search(r"confirmed a (\w{3}) ([\d,.]+) salary credit for (\d{1,2}) (\w+) (\d{4})", text)
    if m:
        try:
            from datetime import datetime
            on = datetime.strptime(f"{m.group(3)} {m.group(4)} {m.group(5)}", "%d %B %Y").date()
            out.append(Delta(message_id=msg.message_id, intent="fx_salary_confirmed", currency=m.group(1),
                             amount=_num(m.group(2)), on=on))
        except ValueError:
            pass
    return out
