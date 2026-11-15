"""PUSH pipeline: what changed across the portfolio, ranked by how much it could matter.

  sources ─► normalise ─► dedupe (BSE vs NSE copies) ─► classify (rules) ─► price reaction
          ─► enrich (results headline numbers · people in mgmt changes · one-line briefs)
          ─► events.json  (public data only; personal relevance is applied on the device)
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta

from . import llm
from .classify import CATEGORY_LABEL, classify, tier
from .config import DATA, INDEX_SYMBOL, PORTFOLIO, portfolio_symbols
from .documents import is_scanned, pdf_pages
from .entities import resolve
from .sources import nse, prices, screener
from .util import IST, call_quarter, fy_quarter, norm_org, now_ist, parse_period, pct

WINDOW_DAYS = 45


# ---------------------------------------------------------------------------------------------
# Results: headline numbers QoQ / YoY
# ---------------------------------------------------------------------------------------------
LINES = {
    "operating": [("revenue", "Revenue", "Sales"), ("ebitda", "EBITDA", "Operating Profit"),
                  ("pbt", "PBT", "Profit before tax"), ("pat", "PAT", "Net Profit")],
    "lender": [("revenue", "Revenue", "Revenue"), ("pbt", "PBT", "Profit before tax"), ("pat", "PAT", "Net Profit")],
}


def headline_from_table(company: dict, quarter_end: date) -> dict | None:
    q = company.get("quarters")
    if not q:
        return None
    ends = [parse_period(p) for p in q["periods"]]
    if quarter_end not in ends:
        return None
    i = ends.index(quarter_end)
    kind = company["kind"]
    rows = []
    for key, label, src in LINES[kind]:
        series = q["rows"].get(src)
        if not series:
            continue
        cur = series[i]
        prev = series[i - 1] if i >= 1 else None
        yago = series[i - 4] if i >= 4 else None
        rows.append({"key": key, "label": label, "cur": cur, "prev": prev, "yago": yago,
                     "qoq": pct(cur, prev), "yoy": pct(cur, yago)})
    by = {r["key"]: r for r in rows}
    margin = None
    if kind == "operating" and by.get("ebitda") and by.get("revenue") and by["revenue"]["cur"]:
        def m(a, b):
            return a / b * 100 if a is not None and b else None
        margin = {"label": "EBITDA margin",
                  "cur": m(by["ebitda"]["cur"], by["revenue"]["cur"]),
                  "prev": m(by["ebitda"]["prev"], by["revenue"]["prev"]),
                  "yago": m(by["ebitda"]["yago"], by["revenue"]["yago"])}
    extra = {}
    if kind == "lender":
        for lab in ("Gross NPA %", "Net NPA %"):
            s = q["rows"].get(lab)
            if s:
                extra[lab] = {"cur": s[i], "prev": s[i - 1] if i else None, "yago": s[i - 4] if i >= 4 else None}
    return {"quarter": fy_quarter(quarter_end), "quarter_end": quarter_end.isoformat(), "basis": company.get("basis"),
            "unit": "₹ crore", "kind": kind, "rows": rows, "margin": margin, "extra": extra, "source": "reported financials (screener.in)",
            "note": "EBITDA isn't meaningful for a lender (interest is its cost of goods); asset quality shown instead." if kind == "lender" else None}


def headline_from_filing(company: dict, url: str, quarter_end: date) -> dict | None:
    """Fallback when the standardised table hasn't caught up: read the filing itself (cheap model)."""
    try:
        pages = pdf_pages(url)
    except Exception:
        return None
    if not pages or is_scanned(pages[:6]):
        return None
    text = "\n\n".join(f"[page {i+1}]\n{p}" for i, p in enumerate(pages[:6]))[:28000]
    out = llm.run("results", {"company": company["name"], "kind": company["kind"], "expected_quarter_end": quarter_end.isoformat(),
                              "filing_text": text}, label=f"{company['symbol']} results {fy_quarter(quarter_end)}")
    if not out or all(out.get("current", {}).get(k) is None for k in ("revenue", "pbt", "pat")):
        return None   # e.g. the pages held only the auditor's review report — say "pending", don't show dashes
    unit = (out.get("unit") or "").lower()
    scale = 0.01 if "lakh" in unit else 0.1 if "million" in unit else 1.0
    rows = []
    labels = LINES[company["kind"]]
    for key, label, _ in labels:
        cur, prev, yago = (out.get(k, {}).get(key) for k in ("current", "prev_quarter", "year_ago"))
        cur, prev, yago = (None if v is None else v * scale for v in (cur, prev, yago))
        if cur is None and key == "ebitda":
            continue
        rows.append({"key": key, "label": label, "cur": cur, "prev": prev, "yago": yago, "qoq": pct(cur, prev), "yoy": pct(cur, yago)})
    by = {r["key"]: r for r in rows}
    margin = None
    if by.get("ebitda") and by.get("revenue") and by["revenue"]["cur"]:
        def m(a, b):
            return a / b * 100 if a is not None and b else None
        margin = {"label": "EBITDA margin", "cur": m(by["ebitda"]["cur"], by["revenue"]["cur"]),
                  "prev": m(by["ebitda"]["prev"], by["revenue"]["prev"]), "yago": m(by["ebitda"]["yago"], by["revenue"]["yago"])}
    return {"quarter": fy_quarter(quarter_end), "quarter_end": quarter_end.isoformat(), "basis": out.get("basis"),
            "unit": "₹ crore", "kind": company["kind"], "rows": rows, "margin": margin, "extra": {},
            "source": "extracted from the results filing", "notes": out.get("notes", []), "ebitda_method": out.get("ebitda_method")}


def quarter_for(ev_dt: datetime, text: str) -> date:
    m = re.search(r"(?:ended|ending)\s+(?:on\s+)?(\d{1,2})(?:st|nd|rd|th)?[\s,]+([A-Za-z]+)[\s,]+(\d{4})", text, re.I)
    if m:
        from .util import MONTHS
        mon = MONTHS.get(m.group(2)[:3].lower())
        if mon:
            return parse_period(f"{m.group(2)[:3]} {m.group(3)}") or call_quarter(ev_dt.date())
    return call_quarter(ev_dt.date())


# ---------------------------------------------------------------------------------------------
# Price reaction around an event (index-relative)
# ---------------------------------------------------------------------------------------------
def reaction(series: list[dict], index: list[dict], ev_dt: datetime) -> dict | None:
    if not series:
        return None
    d = ev_dt.astimezone(IST)
    # after 15:30 IST the first tradable reaction is the next session
    target = d.date() + timedelta(days=1) if (d.hour, d.minute) >= (15, 30) else d.date()
    days = [r["d"] for r in series]
    idx = next((i for i, x in enumerate(days) if x >= target.isoformat()), None)
    if idx is None or idx == 0:
        return None
    r = series[idx]["c"] / series[idx - 1]["c"] - 1
    imap = {x["d"]: x["c"] for x in index}
    ri = None
    if series[idx]["d"] in imap and series[idx - 1]["d"] in imap:
        ri = imap[series[idx]["d"]] / imap[series[idx - 1]["d"]] - 1
    return {"date": series[idx]["d"], "ret": round(r * 100, 2), "idx": None if ri is None else round(ri * 100, 2),
            "abn": None if ri is None else round((r - ri) * 100, 2)}


# ---------------------------------------------------------------------------------------------
# Collect, dedupe, classify
# ---------------------------------------------------------------------------------------------
def _eid(symbol: str, url: str | None, title: str, ts: str) -> str:
    return hashlib.sha1(f"{symbol}|{url or title}|{ts}".encode()).hexdigest()[:10]


def collect(companies: dict[str, dict]) -> list[dict]:
    cutoff = now_ist() - timedelta(days=WINDOW_DAYS)
    raw: list[dict] = []
    for sym, co in companies.items():
        for a in screener.recent_announcements(co):
            if not a["dt"] or a["dt"] < cutoff:
                continue
            raw.append({"symbol": sym, "title": a["title"], "subject": "", "summary_src": a["summary_src"],
                        "url": a["url"], "dt": a["dt"], "source": "BSE via screener.in"})
    # Filings referenced by in-window events but older than the poller (see data/backfill.json).
    bf = DATA / "backfill.json"
    if bf.exists():
        for f in json.loads(bf.read_text(encoding="utf-8"))["filings"]:
            dt = datetime.fromisoformat(f["dt"])
            if f["symbol"] in companies and dt >= cutoff:
                raw.append({"symbol": f["symbol"], "title": f["title"], "subject": "", "summary_src": f["summary_src"],
                            "url": f["url"], "dt": dt, "source": f["source"]})
    # Live NSE feed — map company names to portfolio symbols, and append to our own log: the feed only
    # holds ~130 items, so anything not captured on this poll would otherwise be gone.
    names = {norm_org(co["name"]): sym for sym, co in companies.items()}
    log = _load_log()
    try:
        master = {norm_org(m["name"]): m["symbol"] for m in nse.equity_master()}
        for it in nse.rss_items():
            sym = names.get(norm_org(it["company"])) or (master.get(norm_org(it["company"])) if master.get(norm_org(it["company"])) in companies else None)
            if not sym or not it["dt"]:
                continue
            key = it["url"] or f"{sym}|{it['subject']}|{it['dt'].isoformat()}"
            log[key] = {"symbol": sym, "title": it["subject"] or it["description"][:120], "subject": it["subject"],
                        "summary_src": it["description"], "url": it["url"], "dt": it["dt"].isoformat(), "source": "NSE live feed"}
    except Exception as exc:
        print("  ! NSE RSS unavailable:", exc)
    keep = {}
    for k, r in log.items():
        dt = datetime.fromisoformat(r["dt"])
        if dt >= cutoff - timedelta(days=30):
            keep[k] = r
        if dt >= cutoff and r["symbol"] in companies:
            raw.append({**r, "dt": dt})
    RSS_LOG.write_text(json.dumps(keep, ensure_ascii=False, indent=0), encoding="utf-8")
    return raw


RSS_LOG = DATA / "rss_log.json"


def _load_log() -> dict:
    try:
        return json.loads(RSS_LOG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", s.lower()) if w not in {"announcement", "regulation", "under", "lodr", "sebi", "regulations", "disclosure", "intimation"}}


def dedupe(events: list[dict]) -> list[dict]:
    """The same filing reaches us from BSE (screener) and NSE (RSS) with different URLs."""
    events.sort(key=lambda e: (-e["score"], e["dt"]))
    kept: list[dict] = []
    for e in events:
        dup = None
        for k in kept:
            if k["symbol"] != e["symbol"] or k["category"] != e["category"]:
                continue
            gap = abs((k["dt"] - e["dt"]).total_seconds())
            if gap > 36 * 3600:
                continue
            a, b = _tokens(k["title"] + " " + k["summary_src"]), _tokens(e["title"] + " " + e["summary_src"])
            same_filing = gap <= 6 * 3600 and k["source"] != e["source"]   # BSE and NSE copies land within hours
            if same_filing or k["category"] in ("results", "earnings_call", "investor_meetings", "unclassified") or (a and b and len(a & b) / len(a | b) >= 0.25):
                dup = k
                break
        if dup:
            dup.setdefault("related", []).append({"title": e["title"], "url": e["url"], "source": e["source"]})
        else:
            kept.append(e)
    return kept


# ---------------------------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------------------------
BRIEF_CATS = {"M&A", "litigation", "capex", "fund_raise", "press_release", "credit_rating", "pledging", "management_change", "bonus_split"}


def _filing_text(url: str | None, pages: int = 4, limit: int = 14000) -> str | None:
    if not url:
        return None
    try:
        p = pdf_pages(url)
    except Exception:
        return None
    if not p or is_scanned(p[:pages]):
        return None
    return "\n\n".join(f"[page {i+1}]\n{t}" for i, t in enumerate(p[:pages]))[:limit]


def ttm_revenue(co: dict) -> float | None:
    q = co.get("quarters")
    if not q:
        return None
    s = q["rows"].get("Sales") or q["rows"].get("Revenue")
    vals = [v for v in (s or [])[-4:] if v is not None]
    return sum(vals) if len(vals) == 4 else None


PROFILE = re.compile(r"brief profile|experience|qualification|joined|career|graduat|degree|\bage\b|served as|prior to|previously", re.I)


def _people_text(e: dict, store: list[dict], limit: int = 18000) -> str | None:
    """Profile pages from this filing, plus earlier same-company management filings it builds on.

    An appointment's *outcome* (e.g. a postal-ballot result) rarely repeats the appointee's profile;
    the earlier *notice* does. We look back 60 days in the event store for it.
    """
    chunks: list[str] = []
    sources = [e] + [x for x in store if x is not e and x["symbol"] == e["symbol"] and x.get("url")
                     and x["category"] in ("management_change", "postal_ballot", "agm_egm")
                     and timedelta(0) <= (e["dt"] - x["dt"]) <= timedelta(days=60)]
    for src in sources:
        try:
            pages = pdf_pages(src["url"])
        except Exception:
            continue
        if not pages or is_scanned(pages[:6]):
            continue
        picked = [i for i, t in enumerate(pages) if PROFILE.search(t)][:6] or list(range(min(4, len(pages))))
        for i in picked:
            chunks.append(f"[{src['source']} · {src['dt'].date().isoformat()} · page {i + 1}]\n{pages[i]}")
    text = "\n\n".join(chunks)
    return text[:limit] if text else None


def enrich(e: dict, co: dict, store: list[dict] | None = None) -> None:
    cat = e["category"]
    if cat == "results" and e["subtype"] == "filing":
        _attach_results(e, co)

    if cat == "management_change" and e["score"] >= 50:
        text = _people_text(e, store or [])
        if text:
            out = llm.run("people", {"company": co["name"], "title": e["title"], "filing_text": text}, label=f"{e['symbol']} people")
            if out:
                own = _own_text(e)
                people = []
                for ch in out.get("changes", []):
                    # The look-back can surface people from older filings; keep only those this filing names.
                    surname = ch["name"].split()[-1].lower()
                    if own and surname not in own:
                        continue
                    for c in ch.get("career", []):
                        c["org_id"] = resolve(c.get("org"))
                        if c.get("role"):
                            c["role"] = c["role"].split(";")[0].strip()
                    for ed in ch.get("education", []):
                        ed["org_id"] = resolve(ed.get("institution"))
                    ch["role"] = ch["role"].split(";")[0].strip()
                    people.append(ch)
                e["people"] = people
                _calibrate_people(e, co)

    if cat in BRIEF_CATS and e["tier"] != "routine":
        text = _filing_text(e.get("url"))
        if text:
            facts = {"amount_cr": e["facts"].get("amount_cr"), "ttm_revenue_cr": ttm_revenue(co),
                     "market_cap": co.get("top_ratios", {}).get("Market Cap")}
            out = llm.run("event_brief", {"company": co["name"], "category": cat, "title": e["title"],
                                           "filing_text": text, "facts": facts}, label=f"{e['symbol']} brief")
            if out:
                e["brief"] = out


def _attach_results(e: dict, co: dict) -> None:
    qe = quarter_for(e["dt"], e["title"] + " " + e["summary_src"])
    h = headline_from_table(co, qe)
    if h is None:
        try:
            h = headline_from_table(screener.fetch_standalone(co["symbol"]), qe)
        except Exception:
            h = None
    tried_filing = False
    if h is None and e.get("url"):
        tried_filing = True
        h = headline_from_filing(co, e["url"], qe)
    e["results"] = h or {"quarter": fy_quarter(qe), "pending": True,
                         "reason": ("The standardised tables don't have this quarter yet, and the filing's opening pages are the "
                                    "auditor's review report rather than the results table. FINN retries on every refresh.")
                         if tried_filing else "The standardised tables don't have this quarter yet. FINN retries on every refresh."}


def _own_text(e: dict) -> str:
    try:
        pages = pdf_pages(e["url"]) if e.get("url") else []
    except Exception:
        pages = []
    return " ".join([e["title"], e["summary_src"], *pages]).lower()


COMPANY_TOP = re.compile(r"\b(managing director|chief executive officer|ceo|chief financial officer|cfo|whole[- ]?time director|executive chairman)\b", re.I)
DIVISION = re.compile(r"\(|\bof\b|\s[-–]\s|division|complex|region|business|vertical|segment|unit|international", re.I)


def _calibrate_people(e: dict, co: dict) -> None:
    """Rules read 'CEO' in the subject; the extracted roles tell us whether it is the company's CEO or a division's."""
    ppl = [p for p in e.get("people", []) if p["change"] in ("appointed", "resigned", "retired", "other")]
    if not ppl or e["subtype"] != "top":
        return
    if any(COMPANY_TOP.search(p["role"]) and not DIVISION.search(p["role"]) for p in ppl):
        return
    e["subtype"], e["score"] = "senior", 60
    e["reasons"] = [r for r in e["reasons"] if "top" not in r] + ["Management · division-level role"]
    if "results" in e["facts"].get("also", []):
        # A board outcome that also approves results: the results lead, the people ride along.
        e["category"], e["subtype"], e["score"] = "results", "filing", 85
        e["facts"]["recategorised"] = True
        e["facts"]["also"] = [c for c in e["facts"]["also"] if c != "results"] + ["management_change"]
        e["reasons"] = ["Results"] + [r for r in e["reasons"] if not r.startswith("Management")] + ["Also: senior management changes"]
        _attach_results(e, co)


def size_against_revenue(e: dict, co: dict) -> None:
    """Orders / deals sized against trailing revenue — a deterministic 'so what'."""
    amt, ttm = e["facts"].get("amount_cr"), ttm_revenue(co)
    if amt and ttm and e["category"] in ("press_release", "M&A", "capex", "fund_raise"):
        share = amt / ttm * 100
        e["facts"]["pct_of_ttm_revenue"] = round(share, 1)
        if e["category"] == "press_release" and e["subtype"] == "order":
            bump = 25 if share >= 10 else 15 if share >= 3 else 5 if share >= 1 else -10
            e["score"] = max(5, min(95, e["score"] + bump))
            e["reasons"].append(f"Order ≈ {share:.1f}% of trailing-12m revenue")


def build_events(companies: dict[str, dict], eod: dict[str, list[dict]]) -> list[dict]:
    raw = collect(companies)
    events = []
    for r in raw:
        c = classify(r["title"], r["subject"], r["summary_src"])
        e = {**r, **c, "id": _eid(r["symbol"], r["url"], r["title"], r["dt"].isoformat()), "reasons": []}
        e["reasons"].append(f"{CATEGORY_LABEL.get(c['category'], c['category'])}" + (f" · {c['subtype'].replace('_', ' ')}" if c["subtype"] not in ("unknown", "routine", "filing", "deal", "matter", "action", "meet", "ballot", "meeting", "declared", "disclosure", "expansion", "change", "general") else ""))
        events.append(e)
    events = dedupe(events)
    index = eod.get(INDEX_SYMBOL, [])
    for e in events:
        co = companies[e["symbol"]]
        size_against_revenue(e, co)
        rx = reaction(eod.get(e["symbol"], []), index, e["dt"])
        if rx:
            e["reaction"] = rx
            if rx.get("abn") is not None and abs(rx["abn"]) >= 4 and e["score"] >= 25:
                e["score"] = min(98, e["score"] + 8)
                e["reasons"].append(f"Stock moved {rx['ret']:+.1f}% ({rx['abn']:+.1f}% vs Nifty) on {rx['date']}")
        e["tier"] = tier(e["score"])
        enrich(e, co, events)
        e["tier"] = tier(e["score"])   # extracted roles may have re-calibrated the score
    # A recategorised board outcome may now duplicate the results filing it bundles: fold it in.
    for e in [x for x in events if x["facts"].get("recategorised")]:
        twin = next((x for x in events if x is not e and x["symbol"] == e["symbol"] and x["category"] == "results"
                     and x["subtype"] == "filing" and abs((x["dt"] - e["dt"]).total_seconds()) <= 36 * 3600), None)
        if twin:
            twin["people"] = e.get("people", [])
            twin.setdefault("facts", {}).setdefault("also", []).append("management_change")
            twin.setdefault("related", []).append({"title": e["title"], "url": e["url"], "source": e["source"]})
            twin["brief"] = twin.get("brief") or e.get("brief")
            events.remove(e)
    out = []
    for e in sorted(events, key=lambda x: x["dt"], reverse=True):
        e["dt"] = e["dt"].isoformat()
        e["company"] = companies[e["symbol"]]["name"]
        out.append(e)
    return out


def build_eod(symbols: list[str]) -> dict[str, list[dict]]:
    out = {}
    for s in [*symbols, INDEX_SYMBOL]:
        try:
            out[s] = prices.eod(s, "1y")
        except Exception as exc:
            print(f"  ! prices {s}: {exc}")
            out[s] = []
    return out
