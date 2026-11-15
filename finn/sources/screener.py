"""screener.in adapter: standardised multi-year financials + links to primary documents.

What we take from screener.in and why:
  * the standardised P&L / balance-sheet / cash-flow / ratio tables (numbers transcribed from
    the company's own filings) -> deterministic analytics, no model needed;
  * links to primary documents (annual reports, concall transcripts, exchange announcements);
  * the 5 most recent exchange announcements (backfill for the push feed).
What we deliberately do NOT use for analysis: screener's machine-generated pros/cons,
'key points' commentary and AI summaries — those are secondary interpretation.
robots.txt is respected (e.g. /company/source/quarter/* is never requested).
"""
from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from ..net import fetcher
from ..util import num, parse_period, parse_short_date

BASE = "https://www.screener.in"


def _table(soup: BeautifulSoup, section: str) -> dict | None:
    tb = soup.select_one(f"#{section} table")
    if not tb:
        return None
    periods = [th.get_text(strip=True) for th in tb.select("thead th")][1:]
    rows: dict[str, list] = {}
    for tr in tb.select("tbody tr"):
        cells = tr.select("td")
        if not cells:
            continue
        label = cells[0].get_text(" ", strip=True).replace("+", "").strip()
        label = re.sub(r"\s+", " ", label)
        if label.lower().startswith("raw pdf"):
            continue
        if label.startswith("CFO/EBITDA"):
            label = "CFO/EBITDA"
        rows[label] = [num(c.get_text(strip=True)) for c in cells[1:]]
    if not periods or not rows:
        return None
    return {"periods": periods, "rows": rows}


def _docs(soup: BeautifulSoup) -> dict:
    out = {"announcements": [], "annual_reports": [], "concalls": [], "credit_ratings": []}
    for blk in soup.select("#documents .documents"):
        h = blk.find(["h3", "h4"])
        title = h.get_text(strip=True).lower() if h else ""
        lis = blk.select("li")
        if title.startswith("announcements"):
            for li in lis:
                a = li.find("a")
                if not a:
                    continue
                t = li.find("time")
                meta = a.find("div")
                summary = ""
                if meta:
                    txt = meta.get_text(" ", strip=True)
                    summary = txt.split(" - ", 1)[1].strip() if " - " in txt else ""
                    meta.extract()
                ts = t.get("datetime") if t else None
                out["announcements"].append({
                    "title": " ".join(a.get_text(" ", strip=True).split()),
                    "url": a.get("href"),
                    "ts": ts,
                    "summary_src": summary,
                })
        elif title.startswith("annual"):
            for li in lis:
                a = li.find("a")
                if a and a.get("href"):
                    m = re.search(r"(\d{4})", a.get_text())
                    out["annual_reports"].append({"year": int(m.group(1)) if m else None, "url": a["href"]})
        elif title.startswith("concalls"):
            for li in lis:
                d = li.find("div")
                period = d.get_text(strip=True) if d else ""
                links = {a.get_text(strip=True).lower(): a.get("href") for a in li.select("a")}
                out["concalls"].append({
                    "month": period,
                    "transcript": links.get("transcript"),
                    "ppt": links.get("ppt"),
                    "rec": links.get("rec"),
                })
        elif title.startswith("credit"):
            for li in lis:
                a = li.find("a")
                if a:
                    out["credit_ratings"].append({"text": " ".join(a.get_text(" ", strip=True).split()), "url": a.get("href")})
    return out


def parse_company(html: str, symbol: str) -> dict:
    s = BeautifulSoup(html, "lxml")
    h1 = s.select_one("h1")
    ratios = {}
    for li in s.select("#top-ratios li"):
        name = li.select_one(".name")
        val = li.select_one(".value")
        if name and val:
            ratios[name.get_text(strip=True)] = " ".join(val.get_text(" ", strip=True).split())
    sector = [a.get_text(strip=True) for a in s.select('#peers a[href*="/market/"]')]
    about = s.select_one(".company-profile .about") or s.select_one(".about")
    bse = s.select_one('a[href*="bseindia.com/stock-share-price"]')
    bse_code = None
    if bse:
        m = re.search(r"/(\d{6})/", bse["href"])
        bse_code = m.group(1) if m else None
    html_ids = {k: (re.search(rf'data-{k}-id="(\d+)"', html) or [None, None])[1] for k in ("company", "warehouse")}
    q = _table(s, "quarters")
    pl = _table(s, "profit-loss")
    return {
        "symbol": symbol,
        "name": h1.get_text(strip=True) if h1 else symbol,
        "bse_code": bse_code,
        "company_id": html_ids["company"],
        "warehouse_id": html_ids["warehouse"],
        "sector_path": list(dict.fromkeys(sector)),
        "about": about.get_text(" ", strip=True) if about else "",
        "top_ratios": ratios,
        "kind": "lender" if q and "Financing Profit" in q["rows"] else "operating",
        "quarters": q,
        "annual": pl,
        "balance": _table(s, "balance-sheet"),
        "cashflow": _table(s, "cash-flow"),
        "ratios": _table(s, "ratios"),
        "shareholding": _table(s, "shareholding"),
        "docs": _docs(s),
    }


def _latest_q(c: dict) -> str | None:
    q = c.get("quarters")
    if not q:
        return None
    d = parse_period(q["periods"][-1])
    return d.isoformat() if d else None


def fetch_company(symbol: str, ttl: float = 6 * 3600) -> dict:
    """Consolidated first; fall back to standalone when consolidated is missing or stale."""
    f = fetcher()
    symbol = symbol.upper().strip()
    cons = parse_company(f.text(f"{BASE}/company/{symbol}/consolidated/", ttl), symbol)
    cons["basis"] = "consolidated"
    latest = _latest_q(cons)
    stale = latest is None or (datetime.now().date() - datetime.fromisoformat(latest).date()).days > 200
    if cons["quarters"] and cons["annual"] and not stale:
        return cons
    # No consolidated accounts, or a consolidated page that stopped updating (e.g. subsidiaries wound up).
    stand = parse_company(f.text(f"{BASE}/company/{symbol}/", ttl), symbol)
    stand["basis"] = "standalone"
    if not stand["quarters"]:
        return cons
    if cons["quarters"] and (_latest_q(stand) or "") <= (latest or ""):
        return cons
    return stand


def fetch_standalone(symbol: str, ttl: float = 6 * 3600) -> dict:
    c = parse_company(fetcher().text(f"{BASE}/company/{symbol.upper()}/", ttl), symbol.upper())
    c["basis"] = "standalone"
    return c


def fetch_capex(company: dict, ttl: float = 24 * 3600) -> dict[str, float]:
    """'Fixed assets purchased' by fiscal year from the cash-flow schedule (positive number = spend)."""
    cid = company.get("company_id")
    if not cid:
        return {}
    cons = "true" if company.get("basis") == "consolidated" else ""
    url = f"{BASE}/api/company/{cid}/schedules/?parent=Cash+from+Investing+Activity&section=cash-flow&consolidated={cons}"
    try:
        data = fetcher().json(url, ttl)
    except Exception:
        return {}
    row = data.get("Fixed assets purchased") or {}
    return {k: -v for k, v in ((k, num(v)) for k, v in row.items()) if v is not None}


def recent_announcements(company: dict) -> list[dict]:
    out = []
    for a in company["docs"]["announcements"]:
        ts = a["ts"]
        try:
            dt = datetime.fromisoformat(ts) if ts else None
        except ValueError:
            dt = None
        out.append({**a, "dt": dt})
    return out


def concall_transcripts(company: dict, n: int = 5) -> list[dict]:
    """Most recent n concalls that have a transcript, de-duplicated by month."""
    seen, out = set(), []
    for c in company["docs"]["concalls"]:
        if not c.get("transcript") or c["month"] in seen:
            continue
        seen.add(c["month"])
        d = parse_short_date("1 " + c["month"])
        out.append({**c, "month_date": d})
        if len(out) >= n:
            break
    return out
