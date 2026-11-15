"""Static configuration: the demo portfolio, the research set, paths and default thresholds.

Everything investor-specific (holdings, weights, alert thresholds) is *defaults* only —
the web client lets the investor change thresholds and categories locally.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("FINN_CACHE", ROOT / ".cache"))
WEB = ROOT / "web"
WEB_DATA = WEB / "data"
DATA = ROOT / "data"
PROMPTS = ROOT / "prompts"

# A courteous, identifiable client string. No personal data in it.
# (NSE's archive edge silently drops user agents that embed a URL, so keep it plain.)
USER_AGENT = "FINN-research-prototype/0.1"

# ---------------------------------------------------------------------------
# Demo portfolio: 17 NSE names across sizes and sectors. Weights are % of book.
# Chosen to give a lively demo in the week of 8-15 Nov 2026 (Q2 FY27 results
# season close, a bank CEO transition, defence orders, a regulatory clarification).
# ---------------------------------------------------------------------------
PORTFOLIO: list[dict] = [
    {"symbol": "HDFCBANK",   "weight": 11.0},
    {"symbol": "RELIANCE",   "weight": 10.0},
    {"symbol": "TCS",        "weight": 8.0},
    {"symbol": "ITC",        "weight": 7.0},
    {"symbol": "BAJFINANCE", "weight": 7.0},
    {"symbol": "HAL",        "weight": 6.5},
    {"symbol": "BEL",        "weight": 5.5},
    {"symbol": "DMART",      "weight": 5.5},
    {"symbol": "APOLLOHOSP", "weight": 5.0},
    {"symbol": "KAYNES",     "weight": 6.0},
    {"symbol": "NAVINFLUOR", "weight": 5.0},
    {"symbol": "DEEPAKNTR",  "weight": 5.0},
    {"symbol": "PAGEIND",    "weight": 4.5},
    {"symbol": "TIINDIA",    "weight": 4.0},
    {"symbol": "AMBER",      "weight": 3.5},
    {"symbol": "CREDITACC",  "weight": 3.5},
    {"symbol": "AAVAS",      "weight": 3.0},
]
assert abs(sum(p["weight"] for p in PORTFOLIO) - 100) < 1e-6

# Companies outside the portfolio used to demo on-demand research.
RESEARCH_SET: list[str] = ["SRF", "DIXON", "CHOLAFIN", "PERSISTENT"]

INDEX_SYMBOL = "^NSEI"  # Nifty 50, used for index-relative ("abnormal") moves

# Default alert thresholds (the client can override these per investor).
DEFAULT_RULES = {
    "volume_multiple": 2.0,      # volume >= k x 20-day average
    "volume_lookback": 20,
    "price_move_pct": 4.0,       # |day move| >= X %
    "relative_to_index": True,   # measure move net of Nifty
}

# Per-host minimum spacing between requests (seconds) - be a polite citizen.
HOST_INTERVAL = {
    "www.screener.in": 1.6,
    "www.bseindia.com": 1.0,
    "nsearchives.nseindia.com": 1.0,
    "query1.finance.yahoo.com": 0.35,
}


def portfolio_symbols() -> list[str]:
    return [p["symbol"] for p in PORTFOLIO]


def weight_of(symbol: str) -> float:
    for p in PORTFOLIO:
        if p["symbol"] == symbol:
            return p["weight"]
    return 0.0
