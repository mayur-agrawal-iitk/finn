"""Parsing helpers: Indian number formats, dates, fiscal quarters, name normalisation."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def now_ist() -> datetime:
    return datetime.now(IST)


def num(s: str | None) -> float | None:
    """'65,799' -> 65799.0 ; '27%' -> 27.0 ; '-2,273' -> -2273.0 ; '' -> None."""
    if s is None:
        return None
    t = s.strip().replace(",", "").replace("%", "").replace("₹", "").replace("Cr.", "").strip()
    if t in ("", "-", "--", "NA", "N/A"):
        return None
    try:
        return float(t)
    except ValueError:
        m = re.search(r"-?\d+(\.\d+)?", t)
        return float(m.group()) if m else None


def parse_period(label: str) -> date | None:
    """'Sep 2026' -> date(2026, 9, 30)  (period end)."""
    m = re.match(r"([A-Za-z]{3})\w*\s+(\d{4})", label.strip())
    if not m:
        return None
    mon, yr = MONTHS.get(m.group(1).lower()), int(m.group(2))
    if not mon:
        return None
    nxt = date(yr + (mon == 12), mon % 12 + 1, 1)
    return nxt - timedelta(days=1)


def fy_quarter(period_end: date) -> str:
    """Indian fiscal labels. date(2026,9,30) -> 'Q2 FY27'."""
    m, y = period_end.month, period_end.year
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(m)
    fy = y + 1 if m >= 4 else y
    return f"Q{q} FY{str(fy)[-2:]}" if q else period_end.strftime("%b %Y")


def fy_label(period_end: date) -> str:
    """Annual label: date(2026,3,31) -> 'FY26'."""
    fy = period_end.year + 1 if period_end.month >= 4 else period_end.year
    return f"FY{str(fy)[-2:]}"


def call_quarter(call_month: date) -> date:
    """A results call held in month M discusses the quarter that ended before M.

    Oct/Nov/Dec -> Sep quarter, Jan/Feb/Mar -> Dec, Apr/May/Jun -> Mar, Jul/Aug/Sep -> Jun.
    """
    m, y = call_month.month, call_month.year
    if m in (10, 11, 12):
        return date(y, 9, 30)
    if m in (1, 2, 3):
        return date(y - 1, 12, 31)
    if m in (4, 5, 6):
        return date(y, 3, 31)
    return date(y, 6, 30)


def parse_short_date(s: str, today: date | None = None) -> date | None:
    """Screener writes '9 Nov' for this year and '25 Aug 2025' otherwise."""
    today = today or now_ist().date()
    m = re.match(r"\s*(\d{1,2})\s+([A-Za-z]{3})\w*\s*(\d{4})?", s)
    if not m:
        return None
    d, mon = int(m.group(1)), MONTHS.get(m.group(2).lower())
    if not mon:
        return None
    if m.group(3):
        return date(int(m.group(3)), mon, d)
    cand = date(today.year, mon, d)
    return cand if cand <= today + timedelta(days=1) else date(today.year - 1, mon, d)


_STOP = {"limited", "ltd", "ltd.", "pvt", "private", "the", "india", "co", "company", "corporation", "corp", "inc", "&", "and", "of"}


def norm_org(name: str) -> str:
    """Canonical comparison key for organisation names."""
    t = re.sub(r"[^a-z0-9& ]+", " ", name.lower())
    toks = [w for w in t.split() if w not in _STOP]
    return " ".join(toks)


def norm_person(name: str) -> str:
    t = re.sub(r"\b(mr|mrs|ms|dr|shri|smt|prof|ca|cs)\b\.?", " ", name.lower())
    t = re.sub(r"[^a-z ]+", " ", t)
    return " ".join(t.split())


def pct(a: float | None, b: float | None) -> float | None:
    """% change from b to a."""
    if a is None or b is None or b == 0:
        return None
    return (a - b) / abs(b) * 100.0


def cagr(end: float | None, start: float | None, years: float) -> float | None:
    if not end or not start or start <= 0 or end <= 0 or years <= 0:
        return None
    return ((end / start) ** (1 / years) - 1) * 100.0
