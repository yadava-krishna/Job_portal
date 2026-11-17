"""Salary text -> currency, amounts and pay period, without AI and without exchange rates.

    "$130K – $150K • Offers Equity"     USD 130000-150000 per year
    "INR ?–3000000 per year salary"     INR up to 3000000 per year
    "₹5 Lakh"                           INR 500000-500000 per year
    "12-18 LPA"                         INR 1200000-1800000 per year
    "USD 2000 - 2500"                   USD 2000-2500, period not stated
    "€60k-€75k"                         EUR 60000-75000 per year

Rules that keep this honest:
* A period is taken from the text ("per month", "/hr", "LPA"); when it isn't stated, a figure of 10,000 or more in the
  currency's main unit (1,00,000 or more for INR) is read as yearly, since nobody advertises a five-figure monthly
  amount without saying so. Smaller figures with no period stay "period not stated" and are never annualised.
* Amounts are never converted between currencies. Comparing a USD salary with an INR minimum is reported as
  "not comparable", not guessed.
* "$" alone is USD unless the job's country uses dollars of its own (CA, AU, NZ, SG, HK).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PERIOD_FACTOR = {"year": 1, "month": 12, "week": 52, "day": 260, "hour": 2080}
_DOLLAR_COUNTRIES = {"CA": "CAD", "AU": "AUD", "NZ": "NZD", "SG": "SGD", "HK": "HKD"}

_CURRENCY = [
    ("INR", r"₹|\bINR\b|\bRs\.?(?=\s*\d)|\bLPA\b|\blakhs?\b|\blacs?\b|\bcrores?\b|\d\s*cr\b|\bL\.?P\.?A\b"),
    ("CAD", r"\bCAD\b|C\$|CA\$"), ("AUD", r"\bAUD\b|A\$|AU\$"), ("SGD", r"\bSGD\b|S\$"), ("NZD", r"\bNZD\b|NZ\$"),
    ("HKD", r"\bHKD\b|HK\$"), ("USD", r"\bUSD\b|US\$"), ("EUR", r"€|\bEUR\b"), ("GBP", r"£|\bGBP\b"), ("AED", r"\bAED\b"),
    ("JPY", r"¥|\bJPY\b"), ("PHP", r"₱|\bPHP\b"), ("BRL", r"R\$|\bBRL\b"), ("MXN", r"\bMXN\b"), ("PLN", r"\bPLN\b|zł"),
    ("CHF", r"\bCHF\b"), ("SEK", r"\bSEK\b"),
]
# Other ISO codes written before or after an amount ("CZK 690000", "45000 ZAR").
_ISO = {"CZK", "NOK", "DKK", "HUF", "RON", "BGN", "TRY", "ZAR", "NGN", "KES", "EGP", "PKR", "BDT", "LKR", "NPR", "SAR",
        "QAR", "KRW", "CNY", "TWD", "THB", "MYR", "IDR", "VND", "ILS", "ARS", "COP", "CLP", "UAH"}
_PERIODS = [
    ("hour", r"(?:per|an|a|/)\s*(?:hour|hr)\b|\bhourly\b|/h\b"),
    ("day", r"(?:per|a|/)\s*day\b|\bdaily rate\b|\bper diem\b"),
    ("week", r"(?:per|a|/)\s*(?:week|wk)\b|\bweekly\b"),
    ("month", r"(?:per|a|/)\s*(?:month|mo|mon)\b|\bmonthly\b|\bp\.?m\.?\b|\bpcm\b"),
    ("year", r"(?:per|a|/)\s*(?:year|yr|annum)\b|\bannual(?:ly)?\b|\byearly\b|\bp\.?a\.?\b|\bLPA\b|\bCTC\b|\bL\.?P\.?A\b"),
]
_NUM = r"(\d[\d,]*(?:\.\d+)?)\s*((?i:k|mn|m|lakhs?|lacs?|crores?|cr)|L)?(?![a-zA-Z])"
_RANGE = re.compile(_NUM + r"\s*(?:-|–|—|to)\s*(?:[^\d?]{0,6})?" + _NUM)
_OPEN_LOW = re.compile(r"\?\s*(?:-|–|—|to)\s*(?:[^\d]{0,6})?" + _NUM)          # "?–3000000"
_UP_TO = re.compile(r"(?:up\s*to|upto|max(?:imum)?|until)\s*(?:[^\d]{0,6})?" + _NUM, re.I)
_SINGLE = re.compile(_NUM)


@dataclass
class Salary:
    currency: str | None
    min: float | None           # as posted, in the currency's main unit, for the stated period
    max: float | None
    period: str | None          # year | month | week | day | hour | None (not stated)
    period_assumed: bool = False

    def annual(self) -> tuple[float | None, float | None]:
        """Yearly amounts, or (None, None) when the period isn't known."""
        if not self.period:
            return None, None
        f = PERIOD_FACTOR[self.period]
        return (None if self.min is None else self.min * f, None if self.max is None else self.max * f)

    def lpa(self) -> tuple[float | None, float | None]:
        """Lakhs per annum for INR salaries (the unit Indian postings and filters use)."""
        if self.currency != "INR":
            return None, None
        lo, hi = self.annual()
        return (None if lo is None else round(lo / 1e5, 2), None if hi is None else round(hi / 1e5, 2))

    def label(self) -> str | None:
        if self.min is None and self.max is None:
            return None
        cur = self.currency or ""

        def fmt(v: float) -> str:
            if cur == "INR" and self.period == "year" and v >= 1e5:
                return f"{v / 1e5:g} L"
            return f"{v / 1000:g}k" if v >= 10000 and v % 100 == 0 else f"{v:,.0f}"
        if self.min is not None and self.max is not None and self.min != self.max:
            amount = f"{fmt(self.min)}–{fmt(self.max)}"
        elif self.min is None:
            amount = f"up to {fmt(self.max)}"  # type: ignore[arg-type]
        else:
            amount = fmt(self.min if self.min is not None else self.max)  # type: ignore[arg-type]
        per = {"year": "a year", "month": "a month", "week": "a week", "day": "a day", "hour": "an hour"}.get(self.period or "", "")
        return " ".join(x for x in (cur, amount, per + (" (assumed)" if per and self.period_assumed else "")) if x)


def _value(num: str, unit: str | None) -> float:
    v = float(num.replace(",", ""))
    u = (unit or "").lower()
    if u == "k":
        v *= 1e3
    elif u in ("m", "mn"):
        v *= 1e6
    elif u.startswith("la") or u == "l":
        v *= 1e5
    elif u.startswith("cr"):
        v *= 1e7
    return v


def detect_currency(text: str, country: str | None = None) -> str | None:
    for code, pattern in _CURRENCY:
        if re.search(pattern, text, re.I if code == "INR" else 0):
            return code
    for m in re.finditer(r"\b([A-Z]{3})\b", text):
        if m.group(1) in _ISO:
            return m.group(1)
    if "$" in text:
        return _DOLLAR_COUNTRIES.get((country or "").upper(), "USD")
    return None


def parse(text: str | None, *, currency: str | None = None, period: str | None = None, country: str | None = None) -> Salary | None:
    """Parse a salary text. `currency`/`period` are a source's structured hints and win over the text."""
    if not text or not re.search(r"\d", text):
        return None
    t = " ".join(str(text).split())
    cur = (currency or "").upper() or detect_currency(t, country)
    per = period
    if not per:
        for name, pattern in _PERIODS:
            if re.search(pattern, t, re.I):
                per = name
                break
    lo = hi = None
    unit = None
    if m := _RANGE.search(t):
        u1, u2 = m.group(2), m.group(4)
        unit = u1 or u2
        lo, hi = _value(m.group(1), unit), _value(m.group(3), u2 or u1)
    elif m := _OPEN_LOW.search(t):
        unit = m.group(2)
        hi = _value(m.group(1), unit)
    elif m := _UP_TO.search(t):
        unit = m.group(2)
        hi = _value(m.group(1), unit)
    elif m := _SINGLE.search(t):
        unit = m.group(2)
        lo = hi = _value(m.group(1), unit)
    lakh_text = bool(re.search(r"\bLPA\b|L\.P\.A|lakh|\blacs?\b", t, re.I))
    if lakh_text and not unit and max(v for v in (lo, hi) if v is not None) < 1000:  # "12-18 LPA", "Up to 15 LPA"
        lo, hi = (None if lo is None else lo * 1e5), (None if hi is None else hi * 1e5)
    if cur is None and unit and unit.lower()[:1] in ("l", "c"):  # "10L - 14L", "1.2 Cr": lakhs and crores are Indian units
        cur = "INR"
    if cur is None and not unit and not per:
        return None  # a bare number with no currency, unit or period is not a salary ("401(k)", "5 years")
    if lo is None and hi is None or not any(v and v > 0 for v in (lo, hi)):
        return None
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    if cur == "INR" and (lakh_text or re.search(r"crore|\d\s*cr\b", t, re.I)):
        per = per or "year"
    assumed = False
    if not per:
        top = max(v for v in (lo, hi) if v is not None)
        if top >= (1e5 if cur == "INR" else 1e4):
            per, assumed = "year", True
    return Salary(currency=cur, min=lo, max=hi, period=per, period_assumed=assumed)


def comparable(job: Salary | None, want_annual: float | None, want_currency: str | None) -> tuple[bool | None, str]:
    """Does the job's pay meet the candidate's yearly minimum? (verdict, reason); verdict None means can't tell."""
    if job is None:
        return None, "the posting does not state a salary"
    if not want_annual or not want_currency:
        return None, "you have not set a minimum salary"
    if job.currency and job.currency != want_currency:
        return None, f"the salary is in {job.currency} and your minimum is in {want_currency}; JobPilot does not convert currencies"
    if not job.currency:
        return None, "the posting's salary currency is not stated"
    lo, hi = job.annual()
    top = hi if hi is not None else lo
    if top is None:
        return None, "the posting does not say whether the pay is hourly, monthly or yearly"
    return top >= want_annual, f"up to {job.label()}"
