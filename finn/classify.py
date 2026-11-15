"""Announcement taxonomy: deterministic rules first, a cheap model only for the ambiguous rest.

Exchange subjects are drawn from a small controlled vocabulary (BSE/NSE filing categories),
so ~90% of filings classify exactly with rules. Rules are auditable, free, and instant — the
model is reserved for vague titles like 'General Updates' or 'Disclosure under Regulation 30'.

Each classification returns (category, subtype, intrinsic score 0-100, facts).
The intrinsic score answers "how much could this move the stock, in general?". Personal
relevance (position size, the investor's chosen categories, network) is layered on the client.
"""
from __future__ import annotations

import re

R = re.IGNORECASE

# (category, subtype, pattern over title|subject, base score). First match wins, so the order matters.
RULES: list[tuple[str, str, str, int]] = [
    # --- pure housekeeping first, so words like "letter" or "award" can't promote it ------------
    ("unclassified", "routine", r"dematerial|loss of share|duplicate share|kfin|registrar|rta|share transfer agent|change in (the )?(address|corporate office)|corporate office address|trading window|regulation 74|esg rating|brsr|declaration of nav|compliance certificate|infosys prize|prize|winners of|awards? 20\d\d|awards announced", 5),
    # --- results & earnings ----------------------------------------------------------------
    ("results", "ad", r"newspaper.*(financial result|unaudited|audited)|(financial result|unaudited|audited).*newspaper", 8),
    ("results", "filing", r"(un)?audited (standalone|consolidated|financial)|financial results? (for|of)|results? for the (quarter|second quarter|period)|^results\b|outcome.*board meeting.*(quarter|result)|board meeting outcome.*(quarter|half year|result)|approved (the )?(q[1-4]|quarterly|unaudited|audited|financial|half)[^.;]{0,30}results", 85),
    ("results", "commentary", r"results presentation|letter to shareholders|shareholders letter|media statement|investor presentation|earnings presentation", 45),
    ("earnings_call", "transcript", r"transcript", 40),
    ("earnings_call", "recording", r"audio|video recording|recording of (the )?earnings", 12),
    ("earnings_call", "schedule", r"earnings (conference )?call|con\.? ?call", 12),
    # --- management -------------------------------------------------------------------------
    ("management_change", "company_secretary", r"company secretary|compliance officer", 18),
    ("management_change", "change", r"change in (directorate|management|directors|key managerial)|resignation of (director|kmp|smp)|appointment of|cessation|change in directors/kmp|\bexits?\b|steps? down|appointed as|takes charge|superannuat|approved [a-z.’' ]{3,40} as (an? )?(director|managing|md|ceo|chief|whole)", 55),
    # --- corporate actions & capital ----------------------------------------------------------
    ("M&A", "deal", r"acquisition|acquir|stake (sale|purchase)|amalgamation|merger|demerger|scheme of arrangement|joint venture|binding term sheet|sale or disposal|divest|slump sale|restructuring", 75),
    ("fund_raise", "utilisation", r"monitoring agency|statement of deviation|utili[sz]ation of (issue )?proceeds", 12),
    ("fund_raise", "debt_routine", r"commercial paper|\bncd|non-convertible|interest payment|redemption", 10),
    ("fund_raise", "equity", r"\bqip\b|qualified institution|preferential|rights issue|buy ?back|fund ?rais|issue of (equity|securities)|allotment(?! of esop)", 60),
    ("credit_rating", "action", r"credit rating|\brating\b", 30),
    ("pledging", "pledge", r"pledg|encumbrance", 60),
    ("insider_trading", "disclosure", r"sast|reg(ulation)?\.? ?29|reg(ulation)?\.? ?31|insider trading|pit regulations|regulation 7\(2\)", 28),
    ("bonus_split", "action", r"\bbonus\b|sub-?division|stock split|split of", 50),
    ("dividend", "declared", r"dividend|record date", 28),
    ("capex", "expansion", r"capacity|capex|capital expenditure|commerciali[sz]ation|commissioning|new (plant|facility|unit)|expansion|greenfield|brownfield", 60),
    # --- legal ---------------------------------------------------------------------------------
    ("litigation", "matter", r"litigation|dispute|penalt|show cause|regulatory order|\border\b.*(sebi|court|tribunal|nclt|authority)|insolvency|cirp|non-?compliance|clarification on media|search and seizure|income tax search|investigation|demand notice|tax demand|\bgst\b|\bclosure\b|pollution control|high court|supreme court|nclat|nclt|bench|stay(ed)? (the|order)", 65),
    ("press_release", "clarification", r"clarification|rumou?r|verification", 45),
    ("press_release", "order", r"orders? (worth|of|for|from|received|valued|aggregating)|bagging|receipt of order|receiving of order|award(_| )of(_| )order|award of contract|contract (worth|from|for)|letter of (award|intent)|loa|wins .*order|secured .*order|order_receipt", 50),
    # --- meetings & routine --------------------------------------------------------------------
    ("investor_meetings", "meet", r"analyst|investor meet|institutional investor|investor conference|roadshow|investors? day|con\. call updates", 8),
    ("postal_ballot", "ballot", r"postal ballot|scrutini[sz]er|e-?voting", 18),
    ("agm_egm", "meeting", r"\bagm\b|\begm\b|general meeting", 18),
    ("press_release", "general", r"press release|media release|launch|partnership|wins|announces", 30),
    ("unclassified", "routine", r"esop|esps|employee stock|newspaper|registrar|\brta\b|share transfer agent|dematerial|loss of share certificate|duplicate share|compliance certificate|regulation 74|74\(5\)|trading window|esg|brsr|nav\b|corporate office address|address|kfin|production volume|store opening|half yearly report|asset/liability|infosys prize|awards?", 5),
]

# Regex-compiled once.
_RULES = [(c, s, re.compile(p, R), b) for c, s, p, b in RULES]

_TOP_ROLE = re.compile(r"\b(ceo|chief executive|managing director|\bmd\b|cfo|chief financial|chairman|chairperson|whole[- ]?time director)\b", R)
_EXEC_ROLE = re.compile(r"\b(executive director|president|chief [a-z]+ officer|coo|cto|head of|group head|business head|ceo of)\b", R)
_BOARD_ROLE = re.compile(r"\b(independent director|non[- ]executive|nominee director|additional director|director)\b", R)
_IN = re.compile(r"\b(appoint|appointment|joins|joined|elevat|designat|takes charge|inducted|named)\w*", R)
_OUT = re.compile(r"\b(resign|cessation|ceas|superannuat|retire|exit|step(s|ped)? down|demise)\w*", R)
_RE = re.compile(r"\bre-?appoint\w*", R)
_CR = re.compile(r"(rs\.?|₹|inr)\s*([\d,]+(?:\.\d+)?)\s*(crores?|cr\b|lakhs?|million|mn|billion|bn)?", R)


def _amount_cr(text: str) -> float | None:
    """Largest rupee amount mentioned, normalised to crore."""
    best = None
    for m in _CR.finditer(text):
        try:
            v = float(m.group(2).replace(",", ""))
        except ValueError:
            continue
        unit = (m.group(3) or "").lower().rstrip("s")
        if unit == "":
            v = v / 1e7            # bare rupees
        elif unit == "lakh":
            v = v / 100
        elif unit in ("million", "mn"):
            v = v / 10
        elif unit in ("billion", "bn"):
            v = v * 100
        best = v if best is None else max(best, v)
    return best


_TIE = {"management_change": 3, "litigation": 2, "M&A": 1}  # rarer, more informative labels win ties


def _refined(category: str, base: int, text: str) -> int:
    """Score a candidate label the way the post-rules would, so bundled outcomes rank correctly."""
    if category == "management_change" and _TOP_ROLE.search(text):
        return 85
    return base


def classify(title: str, subject: str = "", summary: str = "") -> dict:
    head = f"{title} | {subject}".strip(" |")
    text = f"{head} | {summary}"
    category, subtype, score = "unclassified", "unknown", 5
    matched_rule = None
    for c, s, rx, b in _RULES:
        if rx.search(head):
            category, subtype, score, matched_rule = c, s, b, rx.pattern
            break
    method = "rule" if matched_rule else "fallback"
    # Generic Reg-30 titles: let the one-line summary decide (still rules, applied to the summary).
    generic = re.search(r"general updates?|^disclosure under regulation 30|^intimation under|^announcement under regulation 30 of sebi|^updates?$|meeting updates|board meeting outcome|outcome of (the )?board meeting|change in management|^results|outcome of postal|outcome of (agm|egm)|scrutini[sz]er", head, R)
    also: list[str] = []
    if summary:
        hits = []
        for c, s, rx, b in _RULES:
            if c == "unclassified" and s == "routine" and rx.pattern.startswith("dematerial"):
                continue
            if rx.search(summary):
                hits.append((c, s, b))
        if hits and (not matched_rule or generic):
            # Board outcomes bundle several decisions: the most consequential one leads.
            best = max(hits, key=lambda h: (_refined(h[0], h[2], summary), _TIE.get(h[0], 0)))
            if not matched_rule or _refined(best[0], best[2], summary) > score:
                category, subtype, score, method = best[0], best[1], best[2], "rule:summary"
        also = sorted({c for c, s, b in hits if b >= 40 and c != category})

    facts: dict = {}
    amt = _amount_cr(text)
    if amt:
        facts["amount_cr"] = round(amt, 2)

    if category == "management_change" and subtype != "company_secretary":
        if _TOP_ROLE.search(text):
            subtype, score = "top", 85
        elif _EXEC_ROLE.search(text):
            subtype, score = "senior", 60
        elif _BOARD_ROLE.search(text):
            subtype, score = "board", 35
        if _RE.search(text) and not _OUT.search(text):
            facts["direction"] = "reappointed"
            score = min(score, 30)
        elif _OUT.search(text) and _IN.search(text):
            facts["direction"] = "transition"
        elif _OUT.search(text):
            facts["direction"] = "exit"
        elif _IN.search(text):
            facts["direction"] = "appointed"
        if re.search(r"superannuat|retire", text, R) and subtype != "top":
            score = min(score, 40)

    if category == "credit_rating" and re.search(r"\besg\b|sustainalytics", text, R):
        category, subtype, score = "unclassified", "routine", 5
    if category == "credit_rating":
        t = text.lower()
        if "downgrad" in t or "negative" in t:
            facts["rating_action"], score = "downgrade", 75
        elif "upgrad" in t or "positive" in t:
            facts["rating_action"], score = "upgrade", 50
        elif "withdr" in t:
            facts["rating_action"], score = "withdrawn", 15
        elif "reaffirm" in t:
            facts["rating_action"], score = "reaffirmed", 15
        elif "assign" in t:
            facts["rating_action"], score = "assigned", 25

    if category == "M&A" and re.search(r"(merger|amalgamation) of (its )?(wholly[- ]owned )?(step[- ]down )?subsidiar|internal (restructuring|reorgani)|investment in (its )?(wholly[- ]owned )?subsidiar|incorporation of (a )?(wholly[- ]owned )?subsidiar", text, R):
        facts["internal"] = True
        score = min(score, 45)

    if category == "management_change" and subtype == "top" and re.search(r"independent director|non[- ]executive", text, R)             and not re.search(r"(ceo|cfo|managing director|chief executive|chief financial)", text, R):
        subtype, score = "board_chair", 50

    if category == "litigation" and facts.get("amount_cr") is not None and facts["amount_cr"] < 5:
        facts["immaterial"] = True          # a ₹1.6 lakh penalty is not a story
        score = 18

    if category == "fund_raise" and re.search(r"commercial paper|ncd|debenture|bonds?", text, R):
        subtype = "debt"
        score = 40 if (facts.get("amount_cr") or 0) >= 1000 else 15

    if also:
        facts["also"] = also

    if category == "litigation" and re.search(r"clarification", text, R):
        subtype = "regulatory_clarification"

    return {"category": category, "subtype": subtype, "score": score, "method": method, "facts": facts}


TIERS = [(70, "material"), (40, "notable"), (0, "routine")]


def tier(score: float) -> str:
    for cut, name in TIERS:
        if score >= cut:
            return name
    return "routine"


CATEGORY_LABEL = {
    "results": "Results", "M&A": "M&A", "fund_raise": "Fund raise", "management_change": "Management",
    "litigation": "Legal & regulatory", "insider_trading": "Insider trade", "earnings_call": "Earnings call",
    "investor_meetings": "Investor meet", "credit_rating": "Credit rating", "dividend": "Dividend",
    "bonus_split": "Bonus / split", "capex": "Capex", "press_release": "Press release",
    "postal_ballot": "Postal ballot", "agm_egm": "AGM / EGM", "pledging": "Pledge", "unclassified": "Routine",
}
