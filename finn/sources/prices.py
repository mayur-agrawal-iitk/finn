"""End-of-day price & volume from Yahoo Finance's public chart endpoint.

We call the JSON chart endpoint directly instead of the yfinance library: one request per
symbol, no pandas dependency, and the response shape is stable. NSE symbols get '.NS'.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..net import fetcher
from ..util import IST

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1d&includePrePost=false"


def yahoo_symbol(symbol: str) -> str:
    if symbol.startswith("^") or "." in symbol:
        return symbol
    return f"{symbol}.NS"


def eod(symbol: str, rng: str = "1y", ttl: float = 3 * 3600) -> list[dict]:
    """[{d:'2026-11-13', o,h,l,c, v}] oldest -> newest; rows with missing close are dropped."""
    data = fetcher().json(CHART.format(sym=yahoo_symbol(symbol).replace("^", "%5E"), rng=rng), ttl)
    res = (data.get("chart") or {}).get("result") or []
    if not res:
        return []
    r = res[0]
    ts = r.get("timestamp") or []
    q = (r.get("indicators") or {}).get("quote", [{}])[0]
    out = []
    for i, t in enumerate(ts):
        c = q.get("close", [None])[i]
        if c is None:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).astimezone(IST).date().isoformat()
        row = {
            "d": d,
            "o": _r(q.get("open", [None])[i]),
            "h": _r(q.get("high", [None])[i]),
            "l": _r(q.get("low", [None])[i]),
            "c": _r(c),
            "v": int(q.get("volume", [0])[i] or 0),
        }
        if out and out[-1]["d"] == d:  # Yahoo sometimes repeats the live bar
            out[-1] = row
        else:
            out.append(row)
    return out


def _r(x):
    return None if x is None else round(float(x), 2)
