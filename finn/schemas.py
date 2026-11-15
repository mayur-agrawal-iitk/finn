"""JSON schemas for every model task (sent as `output_config.format`, re-validated on return)."""
from __future__ import annotations

CATEGORIES = ["results", "M&A", "fund_raise", "management_change", "litigation", "insider_trading", "earnings_call",
              "investor_meetings", "credit_rating", "dividend", "bonus_split", "capex", "press_release",
              "postal_ballot", "agm_egm", "pledging", "unclassified"]

METRICS = ["revenue_growth", "revenue", "ebitda_margin", "ebitda", "pat_growth", "pat", "capex", "order_book",
           "order_inflow", "volume_growth", "capacity", "debt", "working_capital", "asset_quality", "loan_growth",
           "nim", "credit_cost", "roe_roa", "segment", "product_or_launch", "other"]


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props), "additionalProperties": False}


S = {"type": "string"}
N = {"type": ["number", "null"]}
I = {"type": ["integer", "null"]}
SN = {"type": ["string", "null"]}
SL = {"type": "array", "items": S}

SCHEMAS: dict[str, dict] = {
    "classify": _obj({
        "category": {"type": "string", "enum": CATEGORIES},
        "subtype": S,
        "one_line": S,
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    }),
    "event_brief": _obj({
        "one_line": S,
        "so_what": S,
        "key_numbers": {"type": "array", "items": _obj({"label": S, "value": S})},
        "expertise_needed": SL,
        "questions": SL,
    }),
    "people": _obj({
        "changes": {"type": "array", "items": _obj({
            "name": S,
            "role": S,
            "change": {"type": "string", "enum": ["appointed", "resigned", "retired", "reappointed", "redesignated", "other"]},
            "effective_date": SN,
            "is_kmp": {"type": "boolean"},
            "bio": S,
            "age": I,
            "career": {"type": "array", "items": _obj({"org": S, "role": SN, "start_year": I, "end_year": I})},
            "education": {"type": "array", "items": _obj({"institution": S, "degree": SN, "year": I})},
        })},
    }),
    "results": _obj({
        "basis": {"type": "string", "enum": ["consolidated", "standalone"]},
        "unit": S,
        "quarter_end": S,
        "current": _obj({"revenue": N, "ebitda": N, "pbt": N, "pat": N}),
        "prev_quarter": _obj({"revenue": N, "ebitda": N, "pbt": N, "pat": N}),
        "year_ago": _obj({"revenue": N, "ebitda": N, "pbt": N, "pat": N}),
        "ebitda_method": S,
        "notes": SL,
    }),
    "guidance": _obj({
        "items": {"type": "array", "items": _obj({
            "passage_id": S,
            "quote": S,
            "statement": S,
            "metric": {"type": "string", "enum": METRICS},
            "kind": {"type": "string", "enum": ["quantitative", "milestone", "qualitative"]},
            "target_low": N,
            "target_high": N,
            "unit": SN,
            "horizon": S,
            "speaker": SN,
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        })},
        "tone": _obj({"label": {"type": "string", "enum": ["confident", "cautious", "defensive", "mixed"]}, "why": S}),
    }),
    "synthesis": _obj({
        "business": _obj({
            "what_it_does": S,
            "segments": {"type": "array", "items": _obj({"name": S, "share_pct": N, "comment": S})},
            "source_ids": SL,
        }),
        "credibility": _obj({
            "score": {"type": "integer"},
            "label": {"type": "string", "enum": ["high", "medium", "low"]},
            "summary": S,
        }),
        "promises": {"type": "array", "items": _obj({
            "guidance_id": S,
            "status": {"type": "string", "enum": ["delivered", "missed", "on_track", "at_risk", "walked_back", "pending", "unverifiable"]},
            "evidence": S,
            "actual": SN,
        })},
        "narrative_vs_numbers": {"type": "array", "items": _obj({
            "claim": S, "reality": S,
            "verdict": {"type": "string", "enum": ["agrees", "diverges", "too_early"]},
            "evidence_ids": SL,
        })},
        "bull": {"type": "array", "items": _obj({"point": S, "evidence_ids": SL})},
        "bear": {"type": "array", "items": _obj({"point": S, "evidence_ids": SL})},
        "questions": SL,
    }),
}
