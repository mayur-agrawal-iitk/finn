"""NSE public feeds: the live corporate-announcements RSS and the equity master list.

The RSS (`Online_announcements.xml`) is NSE's published machine-readable feed. It only
holds the latest ~130 items, so in production it is polled every few minutes and appended
to an event log; screener.in's per-company 'recent announcements' list fills any gaps.
We do not scrape NSE's cookie-protected JSON API.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from xml.etree import ElementTree as ET

from ..net import fetcher
from ..util import IST, norm_org

RSS = "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"
EQUITY_LIST = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"


def equity_master(ttl: float = 7 * 24 * 3600) -> list[dict]:
    raw = fetcher().text(EQUITY_LIST, ttl)
    rows = list(csv.DictReader(io.StringIO(raw)))
    out = []
    for r in rows:
        r = {k.strip(): (v or "").strip() for k, v in r.items()}
        if r.get("SERIES") not in ("EQ", "BE", "BZ", "SM", "ST"):
            continue
        out.append({"symbol": r["SYMBOL"], "name": r["NAME OF COMPANY"], "isin": r.get("ISIN NUMBER", "")})
    return out


def name_index(master: list[dict]) -> dict[str, str]:
    return {norm_org(m["name"]): m["symbol"] for m in master}


def rss_items(ttl: float = 240) -> list[dict]:
    """Parse the live feed. Each item: company name, PDF link, subject, description, timestamp."""
    raw = fetcher().get(RSS, ttl)
    root = ET.fromstring(raw)
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        desc = (it.findtext("description") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        subject = ""
        m = re.search(r"\|SUBJECT:\s*(.+)$", desc)
        if m:
            subject = m.group(1).strip()
            desc = desc[: m.start()].strip()
        try:
            dt = datetime.strptime(pub, "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
        except ValueError:
            dt = None
        out.append({"company": title, "url": link or None, "subject": subject, "description": desc, "dt": dt})
    return out
