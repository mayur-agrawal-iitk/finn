"""Orchestrates a refresh and writes the read-model the app consumes (web/data/*.json).

The app is a static PWA: the pipeline is the only writer, the browser is a reader. That keeps
the serving path trivially cheap (CDN/GitHub Pages) and lets a cron job keep it fresh.
"""
from __future__ import annotations

import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor

from . import llm, push, research
from .config import DATA, DEFAULT_RULES, INDEX_SYMBOL, PORTFOLIO, RESEARCH_SET, WEB_DATA, portfolio_symbols
from .net import fetcher
from .sources import nse, screener
from .util import now_ist


def _write(name: str, obj) -> None:
    p = WEB_DATA / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")


def _previous(name: str):
    p = WEB_DATA / name
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except Exception:
        return None


def write_research(symbol: str) -> dict:
    d = research.dossier(symbol)
    if d.get("status") != "ok":
        return d
    prev = _previous(f"research/{symbol}.json")
    # Never regress: if this run couldn't read the transcripts (a source blocking CI, a flaky IR site),
    # keep the last good promise ledger and judgement rather than shipping an empty one.
    if prev and len(prev.get("guidance", {}).get("ledger", [])) > len(d["guidance"]["ledger"]) and not d["guidance"]["ledger"]:
        for k in ("guidance", "context", "synthesis"):
            d[k] = prev.get(k)
        d["carried_over"] = prev.get("generated_at")
    elif prev and prev.get("synthesis") and not d.get("synthesis"):
        d["synthesis"] = {**prev["synthesis"], "stale_as_of": prev["synthesis"].get("stale_as_of") or prev.get("generated_at")}
    _write(f"research/{symbol}.json", d)
    return d


def _retain(events: list[dict]) -> None:
    """An event, once seen, stays until it ages out of the window.

    screener.in lists only each company's five latest filings, so a busy week pushes older ones off the
    list; the NSE feed holds ~130 items. Without this, a results filing could vanish a day after it landed.
    """
    from datetime import datetime, timedelta

    prev = _previous("events.json") or []
    cutoff = now_ist() - timedelta(days=push.WINDOW_DAYS)
    have = {e["id"] for e in events}
    for p in prev:
        if p["id"] in have:
            continue
        dt = datetime.fromisoformat(p["dt"])
        if dt < cutoff:
            continue
        twin = any(e["symbol"] == p["symbol"] and e["category"] == p["category"]
                   and abs(datetime.fromisoformat(e["dt"]) - dt) <= timedelta(hours=6) for e in events)
        if not twin:
            events.append({**p, "retained": True})
    events.sort(key=lambda e: e["dt"], reverse=True)


def _carry_over(events: list[dict]) -> None:
    """Keep enrichment from the last snapshot when this run couldn't recompute it."""
    prev = {e["id"]: e for e in (_previous("events.json") or [])}
    for e in events:
        p = prev.get(e["id"])
        if not p:
            continue
        for k in ("people", "brief"):
            if k not in e and p.get(k):   # absent = couldn't compute this run; [] = computed as empty
                e[k] = p[k]
        if (not e.get("results") or e["results"].get("pending")) and p.get("results") and not p["results"].get("pending"):
            e["results"] = p["results"]


def build(research_too: bool = True, research: bool | None = None) -> None:
    if research is not None:
        research_too = research
    t0 = time.time()
    syms = portfolio_symbols()
    print(f"[1/5] companies ({len(syms)})")
    companies = {}
    for s in syms:
        try:
            companies[s] = screener.fetch_company(s)
        except Exception as exc:
            print(f"  ! {s}: {exc}")
    if len(companies) < 0.8 * len(syms):
        # Never overwrite a good snapshot with a half-fetched one (e.g. a source blocking CI IPs).
        raise SystemExit(f"only {len(companies)}/{len(syms)} companies fetched — keeping the previous snapshot")
    print("[2/5] end-of-day prices")
    eod = push.build_eod(list(companies))
    print("[3/5] filings → events")
    events = push.build_events(companies, eod)
    _carry_over(events)
    _retain(events)
    # A results card that was waiting on numbers gets re-checked against today's tables.
    from datetime import datetime
    for e in events:
        if e.get("retained") and e["category"] == "results" and e.get("subtype") == "filing" \
                and (e.get("results") or {}).get("pending") and e["symbol"] in companies:
            tmp = {**e, "dt": datetime.fromisoformat(e["dt"])}
            push._attach_results(tmp, companies[e["symbol"]])
            e["results"] = tmp["results"]
    print(f"      {len(events)} events · tiers:", {t: sum(e['tier'] == t for e in events) for t in ('material', 'notable', 'routine')})

    holdings = []
    for p in PORTFOLIO:
        co = companies.get(p["symbol"])
        if not co:
            continue
        holdings.append({"symbol": p["symbol"], "name": co["name"], "weight": p["weight"], "sector": (co.get("sector_path") or ["", ""])[1:3],
                         "kind": co["kind"], "market_cap": co["top_ratios"].get("Market Cap"), "pe": co["top_ratios"].get("Stock P/E")})
    _write("portfolio.json", {"holdings": holdings, "rules": DEFAULT_RULES})
    _write("eod.json", {s: [[r["d"], r["c"], r["v"]] for r in rows[-260:]] for s, rows in eod.items()})
    _write("events.json", events)

    print("[4/5] research dossiers")
    index = []
    if research_too:
        targets = [*syms, *RESEARCH_SET]
        for s in targets:
            try:
                d = write_research(s)
                ok = d.get("status") == "ok"
                if ok:
                    g = d["guidance"]
                    print(f"  {s:11} ledger={len(g['ledger']):2} pending={g['pending']} synth={'y' if d['synthesis'] else 'n'}")
            except Exception as exc:
                print(f"  ! research {s}: {exc}")
    for f in sorted((WEB_DATA / "research").glob("*.json")):
        if f.name == "index.json":
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        index.append({"symbol": d["symbol"], "name": d["name"], "sector": (d.get("sector_path") or ["", ""])[1:3],
                      "in_portfolio": d["symbol"] in syms, "has_analysis": bool(d.get("synthesis")), "generated_at": d.get("generated_at")})
    _write("research/index.json", index)

    print("[5/5] reference data")
    try:
        _write("symbols.json", [[m["symbol"], m["name"]] for m in nse.equity_master()])
    except Exception as exc:
        print("  ! symbols:", exc)
    shutil.copy(DATA / "orgs.json", WEB_DATA / "orgs.json")
    net = DATA / "network" / "network.json"
    if net.exists():
        shutil.copy(net, WEB_DATA / "network.json")
    pend = llm.pending_jobs()
    _write("meta.json", {"generated_at": now_ist().isoformat(timespec="minutes"), "index": INDEX_SYMBOL,
                         "counts": {"events": len(events), "holdings": len(holdings), "research": len(index)},
                         "llm": {**llm.ledger_summary(), "pending": len(pend)},
                         "http": fetcher().stats, "seconds": round(time.time() - t0, 1)})
    print(f"done in {time.time() - t0:.0f}s · http {fetcher().stats} · llm pending {len(pend)}")
