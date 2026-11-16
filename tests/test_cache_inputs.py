"""Model inputs must be stable: anything that changes daily (today's date, prices, market cap) would
silently invalidate the content-addressed cache and re-bill every model call on every refresh."""
import json
from datetime import date, datetime, timedelta

from finn import push, research
from finn.util import IST


def _capture(monkeypatch, module):
    seen = []
    monkeypatch.setattr(module.llm, "run", lambda task, inputs, label="": seen.append((task, inputs)) or None)
    monkeypatch.setattr(module.llm, "latest", lambda *a, **k: None)
    return seen


def test_synthesis_inputs_have_no_dates_or_prices(monkeypatch):
    seen = _capture(monkeypatch, research)
    ledger = [{"id": "G1", "call": "Q1 FY27", "call_end": "2026-06-30", "metric": "capex", "kind": "quantitative", "statement": "FY27 capex ₹850 cr",
               "quote": "capex of about 850 crores", "horizon": "FY27", "target_low": 850, "target_high": 850, "unit": "INR crore", "check": None, "confidence": "high"}]
    research.synthesis({"name": "X Ltd", "kind": "operating", "symbol": "X"}, {"facts": {"F:ttm_revenue_cr": 100}},
                       {"pending": 0, "ledger": ledger, "drift": [], "context": [], "calls": [{"call": "Q1 FY27"}]})
    task, inputs = seen[0]
    blob = json.dumps(inputs)
    assert task == "synthesis"
    assert "as_of" not in inputs and date.today().isoformat() not in blob


def test_event_brief_inputs_exclude_market_cap(monkeypatch):
    seen = _capture(monkeypatch, push)
    monkeypatch.setattr(push, "_filing_text", lambda *a, **k: "[page 1]\nThe board approved a joint venture.")
    e = {"category": "M&A", "subtype": "deal", "tier": "material", "score": 75, "symbol": "X", "title": "Joint Venture", "summary_src": "",
         "url": "https://example.invalid/x.pdf", "facts": {"amount_cr": 10.0}, "dt": datetime.now(IST) - timedelta(hours=2), "reasons": []}
    co = {"name": "X Ltd", "symbol": "X", "kind": "operating", "top_ratios": {"Market Cap": "₹ 1,000 Cr."},
          "quarters": {"periods": ["Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"], "rows": {"Sales": [10, 10, 10, 10]}}}
    push.enrich(e, co, [])
    briefs = [i for t, i in seen if t == "event_brief"]
    assert briefs and "market_cap" not in briefs[0]["facts"]
