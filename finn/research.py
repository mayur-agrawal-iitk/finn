"""PULL engine: a research dossier for ANY NSE symbol, grounded only in primary data.

Layers (cheapest first):
  1. Deterministic analytics on reported financials  -> snapshot, trajectory, balance sheet, cash quality, flags.
  2. Retrieval over the last 4 concall transcripts    -> only forward-looking, numeric passages (~80% fewer tokens).
  3. Cheap model (Haiku) extracts guidance            -> every quote machine-verified against the transcript.
  4. Code checks promises against reported numbers    -> delivered / missed / on-track, and guidance drift.
  5. Strong model (Opus) adjudicates the rest         -> credibility, narrative-vs-numbers, bull/bear, questions.
No broker notes, no news, no model memory: inputs are the company's own filings and transcripts.
"""
from __future__ import annotations

import difflib
import re
from datetime import date

from . import llm
from .documents import doc_id, is_scanned, pdf_pages
from .sources import prices, screener
from .util import cagr, call_quarter, fy_label, fy_quarter, now_ist, parse_period, pct

# ---------------------------------------------------------------------------------------------
# helpers over screener tables
# ---------------------------------------------------------------------------------------------


def _series(tbl: dict | None, *labels: str) -> list:
    if not tbl:
        return []
    for lab in labels:
        if lab in tbl["rows"]:
            return tbl["rows"][lab]
    return []


def _annual_cols(tbl: dict | None) -> list[tuple[int, str, date]]:
    """Fiscal-year-end columns only (drop TTM and half-year columns)."""
    out = []
    if not tbl:
        return out
    for i, p in enumerate(tbl["periods"]):
        d = parse_period(p)
        if d and d.month == 3:
            out.append((i, p, d))
    return out


def _r(x, n=1):
    return None if x is None else round(x, n)


def _sum(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


# ---------------------------------------------------------------------------------------------
# 1. deterministic analytics
# ---------------------------------------------------------------------------------------------


def analytics(co: dict, capex: dict[str, float]) -> dict:
    lender = co["kind"] == "lender"
    q, a, bs, cf, rt = co.get("quarters"), co.get("annual"), co.get("balance"), co.get("cashflow"), co.get("ratios")
    facts: dict[str, object] = {}
    statements: list[dict] = []
    flags: list[dict] = []

    # ---- quarterly series (last 12)
    qp = q["periods"] if q else []
    qends = [parse_period(p) for p in qp]
    rev_q = _series(q, "Sales", "Revenue")
    # Lenders: screener's "financing profit" nets provisions and can be negative, so margins on it mislead.
    # Pre-tax profit over revenue is the stable profitability line for banks and NBFCs.
    op_q = _series(q, "Profit before tax") if lender else _series(q, "Operating Profit")
    pat_q = _series(q, "Net Profit")
    pbt_q = _series(q, "Profit before tax")
    quarters = []
    for i, p in enumerate(qp):
        r_, o_, n_ = (rev_q[i] if i < len(rev_q) else None), (op_q[i] if i < len(op_q) else None), (pat_q[i] if i < len(pat_q) else None)
        quarters.append({
            "label": fy_quarter(qends[i]) if qends[i] else p, "end": qends[i].isoformat() if qends[i] else None,
            "revenue": r_, "ebitda": o_, "pat": n_, "pbt": pbt_q[i] if i < len(pbt_q) else None,
            "margin": _r(o_ / r_ * 100) if (o_ is not None and r_) else None,
            "rev_yoy": _r(pct(r_, rev_q[i - 4])) if i >= 4 else None,
            "pat_yoy": _r(pct(n_, pat_q[i - 4])) if i >= 4 and i < len(pat_q) else None,
        })
    if lender:
        for lab, key in (("Gross NPA %", "gnpa"), ("Net NPA %", "nnpa")):
            s = _series(q, lab)
            for i, row in enumerate(quarters):
                row[key] = s[i] if i < len(s) else None

    # ---- TTM
    ttm = {}
    if len(rev_q) >= 4:
        ttm = {"revenue": _sum(rev_q[-4:]), "ebitda": _sum(op_q[-4:]), "pat": _sum(pat_q[-4:])}
        if ttm["revenue"]:
            ttm["margin"] = _r((ttm["ebitda"] or 0) / ttm["revenue"] * 100)
            ttm["pat_margin"] = _r((ttm["pat"] or 0) / ttm["revenue"] * 100)
    last = quarters[-1] if quarters else {}
    facts.update({"F:ttm_revenue_cr": _r(ttm.get("revenue"), 0), "F:ttm_margin_pct": ttm.get("margin"),
                  "F:ttm_pat_cr": _r(ttm.get("pat"), 0), "F:last_quarter": last.get("label"),
                  "F:rev_yoy_last_q_pct": last.get("rev_yoy"), "F:pat_yoy_last_q_pct": last.get("pat_yoy"),
                  "F:margin_last_q_pct": last.get("margin"),
                  "F:margin_same_q_last_year_pct": quarters[-5]["margin"] if len(quarters) >= 5 else None,
                  "F:rev_yoy_last4_pct": [x["rev_yoy"] for x in quarters[-4:]],
                  "F:margin_last4_pct": [x["margin"] for x in quarters[-4:]]})

    # ---- annual trajectory
    cols = _annual_cols(a)
    rev_a, op_a, pat_a, eps_a = (_series(a, "Sales", "Revenue"), _series(a, "Profit before tax") if lender else _series(a, "Operating Profit"),
                                 _series(a, "Net Profit"), _series(a, "EPS in Rs"))
    years = []
    for i, p, d in cols:
        r_, o_ = rev_a[i] if i < len(rev_a) else None, op_a[i] if i < len(op_a) else None
        years.append({"fy": fy_label(d), "end": d.isoformat(), "revenue": r_, "ebitda": o_,
                      "pat": pat_a[i] if i < len(pat_a) else None, "eps": eps_a[i] if i < len(eps_a) else None,
                      "margin": _r(o_ / r_ * 100) if (o_ is not None and r_) else None})
    traj = {}
    if len(years) >= 2:
        last_y = years[-1]
        for n in (3, 5, 10):
            if len(years) > n:
                base = years[-1 - n]
                traj[f"rev_cagr_{n}y"] = _r(cagr(last_y["revenue"], base["revenue"], n))
                traj[f"ebitda_cagr_{n}y"] = _r(cagr(last_y["ebitda"], base["ebitda"], n))
                traj[f"pat_cagr_{n}y"] = _r(cagr(last_y["pat"], base["pat"], n))
                if last_y["margin"] is not None and base["margin"] is not None:
                    traj[f"margin_change_{n}y_bps"] = round((last_y["margin"] - base["margin"]) * 100)
        facts.update({f"F:{k}": v for k, v in traj.items() if k.startswith(("rev_cagr_3", "rev_cagr_5", "pat_cagr_3", "pat_cagr_5", "margin_change"))})
        n = 5 if len(years) > 5 else 3 if len(years) > 3 else None
        if n:
            b = years[-1 - n]
            rc, pc = traj.get(f"rev_cagr_{n}y"), traj.get(f"pat_cagr_{n}y")
            if rc is not None:
                statements.append({"kind": "growth", "text": f"Revenue compounded {rc:.1f}% a year over {n} years ({b['fy']}→{last_y['fy']})"
                                   + (f"; profit after tax {pc:.1f}%." if pc is not None else ".")})
            mc = traj.get(f"margin_change_{n}y_bps")
            if mc is not None and not lender:
                verb = "expanded" if mc > 50 else "compressed" if mc < -50 else "held roughly flat"
                statements.append({"kind": "margin", "dir": "up" if mc > 50 else "down" if mc < -50 else "flat",
                                   "text": f"EBITDA margin {verb} {abs(mc)} bps over {n} years ({b['margin']:.1f}% → {last_y['margin']:.1f}%)."
                                   if verb != "held roughly flat" else f"EBITDA margin held roughly flat over {n} years ({b['margin']:.1f}% → {last_y['margin']:.1f}%)."})
    yoys = [x["rev_yoy"] for x in quarters[-4:] if x["rev_yoy"] is not None]
    if len(yoys) >= 3:
        d_ = yoys[-1] - yoys[0]
        if abs(d_) >= 4:
            statements.append({"kind": "momentum", "dir": "up" if d_ > 0 else "down",
                               "text": f"Revenue growth {'accelerated' if d_ > 0 else 'slowed'} from {yoys[0]:.0f}% to {yoys[-1]:.0f}% YoY over the last {len(yoys)} quarters."})
        else:
            statements.append({"kind": "momentum", "dir": "flat", "text": f"Revenue growth steady at {min(yoys):.0f}–{max(yoys):.0f}% YoY over the last {len(yoys)} quarters."})
    if not lender and len(quarters) >= 5 and quarters[-1]["margin"] is not None and quarters[-5]["margin"] is not None:
        mb = round((quarters[-1]["margin"] - quarters[-5]["margin"]) * 100)
        if abs(mb) >= 100:
            statements.append({"kind": "margin_q", "dir": "up" if mb > 0 else "down",
                               "text": f"{quarters[-1]['label']} EBITDA margin {quarters[-1]['margin']:.1f}%, {abs(mb)} bps {'above' if mb > 0 else 'below'} a year ago."})

    # ---- balance sheet
    bcols = list(enumerate(bs["periods"])) if bs else []
    eq = [(_series(bs, "Equity Capital")[i] or 0) + (_series(bs, "Reserves")[i] or 0) for i, _ in bcols] if bs else []
    borrow = _series(bs, "Borrowings", "Borrowing")
    deposits = _series(bs, "Deposits")
    total = _series(bs, "Total Liabilities")
    cwip = _series(bs, "CWIP")
    fixed = _series(bs, "Fixed Assets")
    bal_rows = []
    for i, p in bcols:
        d = parse_period(p)
        bal_rows.append({"label": (fy_label(d) if d and d.month == 3 else p), "equity": eq[i] if i < len(eq) else None,
                         "borrowings": borrow[i] if i < len(borrow) else None, "deposits": deposits[i] if i < len(deposits) else None,
                         "total": total[i] if i < len(total) else None, "cwip": cwip[i] if i < len(cwip) else None,
                         "fixed": fixed[i] if i < len(fixed) else None,
                         "de": _r((borrow[i] or 0) / eq[i], 2) if i < len(borrow) and i < len(eq) and eq[i] else None})
    wc = []
    if rt:
        for i, p in enumerate(rt["periods"]):
            d = parse_period(p)
            row = {"fy": fy_label(d) if d else p}
            for lab, key in (("Debtor Days", "debtor"), ("Inventory Days", "inventory"), ("Days Payable", "payable"),
                             ("Cash Conversion Cycle", "ccc"), ("Working Capital Days", "wc_days"), ("ROCE %", "roce"), ("ROE %", "roe")):
                s = rt["rows"].get(lab)
                if s:
                    row[key] = s[i] if i < len(s) else None
            wc.append(row)
    latest_b = bal_rows[-1] if bal_rows else {}
    funding = None
    if latest_b.get("total"):
        t = latest_b["total"]
        e_, b_, dp = latest_b.get("equity") or 0, latest_b.get("borrowings") or 0, latest_b.get("deposits") or 0
        funding = {"equity": _r(e_ / t * 100), "debt": _r(b_ / t * 100), "deposits": _r(dp / t * 100) if dp else None,
                   "other": _r(max(0.0, (t - e_ - b_ - dp)) / t * 100)}
    facts.update({"F:debt_to_equity": latest_b.get("de"), "F:borrowings_cr": latest_b.get("borrowings")})
    if wc:
        facts["F:ccc_days_latest"] = wc[-1].get("ccc")
        if len(wc) > 3:
            facts["F:ccc_days_3y_ago"] = wc[-4].get("ccc")
        facts["F:roce_latest_pct"] = wc[-1].get("roce")
        facts["F:roe_latest_pct"] = wc[-1].get("roe")

    # ---- cash quality
    cfo = _series(cf, "Cash from Operating Activity")
    cfi = _series(cf, "Cash from Investing Activity")
    cash_rows = []
    cf_cols = _annual_cols(cf)
    pat_by_fy = {y["fy"]: y["pat"] for y in years}
    ebitda_by_fy = {y["fy"]: y["ebitda"] for y in years}
    for i, p, d in cf_cols:
        fy = fy_label(d)
        cx = capex.get(p)
        c = cfo[i] if i < len(cfo) else None
        cash_rows.append({"fy": fy, "cfo": c, "cfi": cfi[i] if i < len(cfi) else None, "capex": cx,
                          "fcf": (c - cx) if (c is not None and cx is not None) else None, "pat": pat_by_fy.get(fy),
                          "cfo_pat": _r(c / pat_by_fy[fy], 2) if (c is not None and pat_by_fy.get(fy)) else None,
                          "cfo_ebitda": _r(c / ebitda_by_fy[fy], 2) if (c is not None and ebitda_by_fy.get(fy)) else None})
    cash = {"rows": cash_rows}
    if len(cash_rows) >= 5 and not lender:
        last5 = cash_rows[-5:]
        scfo, spat = _sum([x["cfo"] for x in last5]), _sum([x["pat"] for x in last5])
        sfcf = _sum([x["fcf"] for x in last5])
        cash["cfo_pat_5y"] = _r(scfo / spat, 2) if scfo is not None and spat else None
        cash["fcf_5y"] = _r(sfcf, 0)
        facts["F:cfo_to_pat_5y"] = cash["cfo_pat_5y"]
        facts["F:fcf_5y_cr"] = cash["fcf_5y"]
        if cash["cfo_pat_5y"] is not None:
            v = cash["cfo_pat_5y"]
            def inr(x):
                return f"{'−' if x < 0 else ''}₹{abs(x):,.0f} cr"
            tail = ("." if v >= 0.9 else " — profits are not turning into cash." if v < 0 else
                    ", weaker than reported profit suggests." if v < 0.7 else ", adequate.")
            statements.append({"kind": "cash", "dir": "up" if v >= 0.9 else "down" if v < 0.7 else "flat",
                               "text": f"Over 5 years: {inr(spat)} of profit, {inr(scfo)} of operating cash — conversion {v:.2f}x{tail}"})
    if lender:
        cash["note"] = "For lenders, operating cash flow mostly reflects loan-book growth; cash conversion isn't a meaningful test."

    # ---- flags (deterministic)
    if not lender:
        v = cash.get("cfo_pat_5y")
        if v is not None and v < 0.7:
            flags.append({"level": "red", "text": f"Profits not turning into cash: 5-yr CFO/PAT {v:.2f}x"})
        de = latest_b.get("de")
        if de is not None and de > 1:
            flags.append({"level": "amber", "text": f"Leverage high: debt/equity {de:.2f}x"})
        if len(bal_rows) >= 4 and bal_rows[-1].get("de") is not None and bal_rows[-4].get("de") is not None and bal_rows[-1]["de"] - bal_rows[-4]["de"] > 0.3:
            flags.append({"level": "amber", "text": f"Debt/equity rising: {bal_rows[-4]['de']:.2f}x → {bal_rows[-1]['de']:.2f}x"})
        if len(wc) >= 4 and wc[-1].get("debtor") and wc[-4].get("debtor") and wc[-1]["debtor"] > wc[-4]["debtor"] * 1.25 and wc[-1]["debtor"] - wc[-4]["debtor"] > 10:
            flags.append({"level": "amber", "text": f"Receivables stretching: debtor days {wc[-4]['debtor']:.0f} → {wc[-1]['debtor']:.0f}"})
        if len(wc) >= 4 and wc[-1].get("ccc") is not None and wc[-4].get("ccc") is not None and wc[-1]["ccc"] - wc[-4]["ccc"] > 20:
            flags.append({"level": "amber", "text": f"Working-capital cycle lengthening: {wc[-4]['ccc']:.0f} → {wc[-1]['ccc']:.0f} days"})
        if latest_b.get("cwip") and latest_b.get("fixed") and latest_b["cwip"] > 0.3 * latest_b["fixed"]:
            flags.append({"level": "info", "text": f"Large capex underway: CWIP ₹{latest_b['cwip']:,.0f} cr = {latest_b['cwip'] / latest_b['fixed'] * 100:.0f}% of fixed assets"})
        mc = traj.get("margin_change_3y_bps")
        if mc is not None and mc < -300:
            flags.append({"level": "amber", "text": f"Margins compressed {abs(mc)} bps in 3 years"})
    else:
        g = [x.get("gnpa") for x in quarters[-4:] if x.get("gnpa") is not None]
        if len(g) >= 3 and all(g[i] < g[i + 1] for i in range(len(g) - 1)):
            flags.append({"level": "amber", "text": f"Gross NPA rising {len(g)} quarters in a row: {g[0]:.2f}% → {g[-1]:.2f}%"})
    sh = co.get("shareholding")
    if sh and "Promoters" in sh["rows"]:
        s = [v for v in sh["rows"]["Promoters"] if v is not None]
        if len(s) >= 5 and s[-5] - s[-1] >= 2:
            flags.append({"level": "amber", "text": f"Promoter holding down {s[-5] - s[-1]:.1f} pp in a year ({s[-5]:.1f}% → {s[-1]:.1f}%)"})
        if s:
            facts["F:promoter_holding_pct"] = s[-1]

    return {"kind": co["kind"], "quarters": quarters[-12:], "years": years[-11:], "ttm": ttm, "trajectory": traj, "statements": statements,
            "balance": {"rows": bal_rows[-11:], "wc": wc[-11:], "funding": funding}, "cash": cash, "flags": flags, "facts": facts}


# ---------------------------------------------------------------------------------------------
# 2. retrieval over transcripts
# ---------------------------------------------------------------------------------------------
FL = re.compile(r"\b(guid\w*|expect\w*|target\w*|outlook|aim\w*|aspir\w*|plan(?:ned|ning)? to|going forward|next (?:year|quarter|fiscal|few|two|three)|"
                r"in (?:the )?(?:coming|next)|by (?:the )?end of|fy ?['’]?\d{2}|h[12] ?fy|q[1-4] ?fy|double[- ]digit|mid[- ]teens?|high[- ]single|"
                r"low[- ]double|teens|margin (?:band|range|trajectory)|commission\w*|ramp[- ]?up|capex|will (?:be|grow|achieve|reach|deliver|see|cross|touch|double|come)|"
                r"should (?:be|grow|see)|confident|visibility|maintain\w*|sustain\w*|on track|delay\w*|postpon\w*)\b", re.I)
NUM = re.compile(r"\d+(?:\.\d+)?\s*(?:%|percent|per cent|bps|basis points|crore|cr\b|billion|million|mtpa|tonnes|x\b)", re.I)
BOILER = re.compile(r"safe harbo|forward[- ]looking statements|ladies and gentlemen|welcome to (the|our)|on behalf of|thank you for (joining|standing by)|"
                    r"participant lines|listen[- ]only|this (conference|call) (is being|may be) recorded|disclaimer|have been uploaded|"
                    r"hand (it )?over|i would now like to|dear sir|stock exchange|scrip code|kindly take", re.I)
SPEAKER = re.compile(r"^([A-Z][A-Za-z.\-'’ ]{2,48}?)\s*[:–-]\s+(?=\S)")


def _turns(pages: list[str]) -> list[dict]:
    turns, cur = [], None
    for pi, page in enumerate(pages, 1):
        for line in page.splitlines():
            m = SPEAKER.match(line.strip())
            if m and len(m.group(1).split()) <= 6:
                if cur:
                    turns.append(cur)
                cur = {"speaker": m.group(1).strip(), "page": pi, "text": line.strip()[m.end():]}
            elif cur:
                cur["text"] += " " + line.strip()
            else:
                cur = {"speaker": "", "page": pi, "text": line.strip()}
    if cur:
        turns.append(cur)
    return turns


def select_passages(pages: list[str], tag: str, budget_chars: int = 16000) -> tuple[list[dict], list[dict]]:
    """Forward-looking numeric windows from management turns; plus opening remarks for context."""
    turns = _turns(pages)
    cands, opening = [], []
    for t_i, t in enumerate(turns):
        sp = t["speaker"].lower()
        if "moderator" in sp or "operator" in sp:
            continue
        text = re.sub(r"\s+", " ", t["text"]).strip()
        if len(text) < 80:
            continue
        is_question = text.rstrip().endswith("?") and len(text) < 700
        if (len(opening) < 4 and not is_question and len(text) > 300 and not BOILER.search(text[:400])
                and len(NUM.findall(text)) >= 2):
            # context for synthesis: substantive management commentary, not safe-harbour or call logistics
            opening.append({"id": f"{tag}-open{len(opening) + 1}", "page": t["page"], "speaker": t["speaker"], "text": text[:1800]})
        if is_question:
            continue
        # windows of ~650 chars with 1-sentence overlap
        sents = re.split(r"(?<=[.!?])\s+", text)
        win, n = "", 0
        for s in sents + [""]:
            if len(win) + len(s) < 650 and s:
                win += " " + s
                continue
            w = win.strip()
            if w:
                score = len(FL.findall(w)) + 1.5 * len(NUM.findall(w))
                if FL.search(w) and score >= 2.5:
                    n += 1
                    cands.append({"id": f"{tag}-p{t['page']}-{t_i}-{n}", "page": t["page"], "speaker": t["speaker"], "text": w, "score": score})
            win = s
    cands.sort(key=lambda c: -c["score"])
    keep, used = [], 0
    for c in cands:
        if used + len(c["text"]) > budget_chars:
            continue
        keep.append(c)
        used += len(c["text"])
    keep.sort(key=lambda c: (c["page"], c["id"]))
    for c in keep:
        c.pop("score", None)
    return keep, opening


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", s.lower()).split())


def verify_quote(quote: str, haystack_norm: str) -> bool:
    qn = _norm(quote)
    if len(qn) < 12:
        return False
    if qn in haystack_norm:
        return True
    # tolerate minor OCR / hyphenation differences: longest common block >= 85% of the quote
    sm = difflib.SequenceMatcher(None, qn, haystack_norm, autojunk=False)
    m = sm.find_longest_match(0, len(qn), 0, len(haystack_norm))
    return m.size >= 0.85 * len(qn)


# ---------------------------------------------------------------------------------------------
# 4. deterministic promise checks
# ---------------------------------------------------------------------------------------------
HZ_FY = re.compile(r"\bFY\s?['’]?(\d{2,4})\b", re.I)
HZ_Q = re.compile(r"\bQ([1-4])\s?FY\s?['’]?(\d{2,4})\b", re.I)
HZ_H = re.compile(r"\bH([12])\s?FY\s?['’]?(\d{2,4})\b", re.I)


def _fy(y: str) -> int:
    y = int(y)
    return 2000 + y if y < 100 else y


def _quarter_ends_for(horizon: str) -> tuple[list[date], str] | None:
    m = HZ_Q.search(horizon)
    if m:
        qn, fy = int(m.group(1)), _fy(m.group(2))
        end = {1: date(fy - 1, 6, 30), 2: date(fy - 1, 9, 30), 3: date(fy - 1, 12, 31), 4: date(fy, 3, 31)}[qn]
        return [end], f"Q{qn} FY{str(fy)[-2:]}"
    m = HZ_H.search(horizon)
    if m:
        h, fy = int(m.group(1)), _fy(m.group(2))
        ends = [date(fy - 1, 6, 30), date(fy - 1, 9, 30)] if h == 1 else [date(fy - 1, 12, 31), date(fy, 3, 31)]
        return ends, f"H{h} FY{str(fy)[-2:]}"
    m = HZ_FY.search(horizon)
    if m:
        fy = _fy(m.group(1))
        return [date(fy - 1, 6, 30), date(fy - 1, 9, 30), date(fy - 1, 12, 31), date(fy, 3, 31)], f"FY{str(fy)[-2:]}"
    return None


def _prior(d: date) -> date:
    return date(d.year - 1, d.month, d.day)


SUBLEVEL = re.compile(r"\b(segment|business|division|vertical|unit|portfolio|product|exports?|domestic|international|overseas|subsidiar\w*|plant|"
                      r"region|channel|brand|category|book|branch|deposits?|rail|metering|smart|osat|pcb|ems|retail|wholesale|mobile|lighting|"
                      r"consumer|industrial|auto|aero|defen[cs]e|gross|cumulative|pc board|phase|project|facility|debottleneck\w*)\b", re.I)


def is_segment(statement: str) -> bool:
    """Is the *subject* of a promise a sub-business? Look only before the first number, so
    'FY27 capex of ₹850 cr: OSAT 300, PCB 300' stays company-level and 'Rail margins above 30%' doesn't."""
    s = re.sub(r"\b(?:[QH][1-4]\s?)?FY\s?['’]?\d{2,4}\b", " ", statement, flags=re.I)
    subject = re.split(r"[:(]|\d", s, maxsplit=1)[0]
    return bool(SUBLEVEL.search(subject))


def check_promise(item: dict, an: dict) -> dict | None:
    """Return a computed check for quantitative, COMPANY-LEVEL items on standard metrics, else None.

    Segment targets ("rail margins above 30%") can't be checked against consolidated numbers,
    so they are left for the model to judge from later calls rather than mis-scored by code.
    """
    if item["kind"] != "quantitative" or item.get("target_low") is None and item.get("target_high") is None:
        return None
    if is_segment(item.get("statement", "")):
        return None
    if re.search(r"\bqoq\b|q-o-q|sequential|quarter[- ]on[- ]quarter|run[- ]rate|exit", f"{item.get('statement', '')} {item.get('quote', '')}", re.I):
        return None   # sequential / exit-rate guidance isn't comparable with YoY or full-period numbers
    hz = _quarter_ends_for(item.get("horizon", ""))
    if not hz:
        return None
    ends, label = hz
    qmap = {x["end"]: x for x in an["quarters"]}
    # need the prior-year quarters too; rebuild from the longer series kept in analytics
    have = [qmap.get(e.isoformat()) for e in ends]
    have_prior = [qmap.get(_prior(e).isoformat()) for e in ends]
    done = [i for i, h in enumerate(have) if h]
    if not done:
        return None
    complete = len(done) == len(ends)
    metric, unit = item["metric"], (item.get("unit") or "").lower()
    lo, hi = item.get("target_low"), item.get("target_high")
    actual, basis = None, None
    if metric in ("revenue_growth", "pat_growth") and "%" in unit:   # loan growth is AUM, not revenue: left to the model
        k = "pat" if metric == "pat_growth" else "revenue"
        cur = _sum([have[i][k] for i in done])
        prv = _sum([have_prior[i][k] for i in done if have_prior[i]]) if all(have_prior[i] for i in done) else None
        if cur is None or not prv:
            return None
        actual = pct(cur, prv)
        basis = f"{label} YoY" if complete else f"{label} to date ({len(done)} of {len(ends)} quarters) YoY"
    elif metric == "ebitda_margin" and an.get("kind") != "lender" and ("%" in unit or "bps" not in unit):
        r = _sum([have[i]["revenue"] for i in done])
        e = _sum([have[i]["ebitda"] for i in done])
        if not r or e is None:
            return None
        actual = e / r * 100
        basis = f"{label} EBITDA margin" + ("" if complete else f" to date ({len(done)} of {len(ends)} quarters)")
    elif metric in ("revenue", "pat") and "crore" in unit and complete:
        actual = _sum([have[i][metric] for i in done])
        basis = f"{label} reported"
    else:
        return None
    if actual is None:
        return None
    # Plausibility: a target 3x away from the actual (or 25 pts for %) is almost always a different basis
    # (a segment, a run-rate, a currency) — leave it to the model rather than score it wrongly.
    ref = lo if lo is not None else hi
    if "%" in unit:
        if abs(actual - ref) > 25:
            return None
    elif ref and not (ref / 3 <= abs(actual) <= ref * 3):
        return None
    tol = 0.5 if ("%" in unit) else 0.02 * (lo or hi or 1)
    if lo is not None and actual >= lo - tol:
        status = "delivered" if complete else "on_track"
        if hi is not None and actual > hi + tol:
            status = "delivered" if complete else "on_track"  # beat
    elif lo is None and hi is not None:
        status = ("delivered" if actual <= hi + tol else "missed") if complete else ("on_track" if actual <= hi + tol else "at_risk")
    else:
        status = "missed" if complete else "at_risk"
    return {"actual": _r(actual), "basis": basis, "status": status, "complete": complete}


DRIFT_METRICS = {"revenue_growth", "revenue", "ebitda_margin", "ebitda", "pat_growth", "pat", "capex", "order_inflow", "order_book",
                 "loan_growth", "credit_cost", "nim", "volume_growth", "asset_quality", "roe_roa"}


def drift(ledger: list[dict]) -> list[dict]:
    """Same metric & horizon guided on several calls: was it raised, cut, or held?"""
    groups: dict[tuple, list] = {}
    for g in ledger:
        # Only like-for-like: a standard metric, a dated horizon, the same unit, company-level wording.
        if g["kind"] != "quantitative" or g.get("target_low") is None or g["metric"] not in DRIFT_METRICS:
            continue
        hz = _quarter_ends_for(g.get("horizon", ""))
        if not hz or is_segment(g.get("statement", "")):
            continue
        key = (g["metric"], hz[1], (g.get("unit") or "").lower().strip())
        groups.setdefault(key, []).append(g)
    out = []
    for (metric, horizon, _unit), items in groups.items():
        calls = sorted({(i["call_end"], i["call"]) for i in items})
        if len(calls) < 2:
            continue
        seq, mixed = [], False
        for end, call in calls:
            it = [i for i in items if i["call_end"] == end]
            lo = min(i["target_low"] for i in it)
            hi = max((i.get("target_high") or i["target_low"]) for i in it)
            if lo > 0 and hi / lo > 1.4:
                mixed = True   # one call, several very different numbers = several different things
            seq.append({"call": call, "low": lo, "high": hi, "ids": [i["id"] for i in it]})
        if mixed:
            continue
        first, lastv = (seq[0]["low"] + seq[0]["high"]) / 2, (seq[-1]["low"] + seq[-1]["high"]) / 2
        pct_unit = "%" in (_unit or "") or "bps" in (_unit or "")
        if pct_unit and abs(lastv - first) > 10:
            continue
        if not pct_unit and first and lastv and not (0.6 <= lastv / first <= 1.6):
            continue   # guidance is rarely revised by more than ~40%; bigger gaps are different things
        move = "raised" if lastv > first * 1.02 else "lowered" if lastv < first * 0.98 else "held"
        out.append({"metric": metric, "horizon": horizon, "sequence": seq, "move": move, "unit": items[0].get("unit"),
                    "lower_is_better": metric in LOWER_BETTER})
    return out


LOWER_BETTER = {"credit_cost", "debt", "working_capital", "asset_quality"}


# ---------------------------------------------------------------------------------------------
# assemble
# ---------------------------------------------------------------------------------------------


def _exchange_copy(co: dict, month: date | None) -> str | None:
    """Find the exchange-filed transcript for a call held in `month` among recent announcements."""
    if not month:
        return None
    for a in screener.recent_announcements(co):
        if not a["dt"] or "transcript" not in (a["title"] + " " + a["summary_src"]).lower():
            continue
        delta = (a["dt"].date() - month).days
        if -5 <= delta <= 50 and a.get("url"):
            return a["url"]
    return None


def guidance_ledger(co: dict, an: dict, n_calls: int = 4) -> dict:
    transcripts = screener.concall_transcripts(co, n=n_calls + 1)
    ledger, tones, calls, opening_ctx, status_ctx, pending = [], [], [], [], [], 0
    gid = 0
    seen_docs: set[str] = set()
    seen_calls: set[str] = set()
    seen_quotes: set[str] = set()
    for t in transcripts[:n_calls]:
        if not t["month_date"] or t["transcript"] in seen_docs:
            continue   # screener occasionally lists one transcript under two call months
        label = fy_quarter(call_quarter(t["month_date"]))
        if label in seen_calls:
            continue   # ...or the same call twice (exchange copy + company-site copy)
        seen_docs.add(t["transcript"])
        seen_calls.add(label)
        qe = call_quarter(t["month_date"])
        tag = fy_quarter(qe).replace(" ", "")
        try:
            pages = pdf_pages(t["transcript"])
        except Exception as exc:
            # Company IR sites sometimes block non-browser clients or serve broken TLS chains. SEBI requires the
            # transcript to be filed with the exchanges too, so fall back to that copy when we can find it.
            alt = _exchange_copy(co, t["month_date"])
            pages = None
            if alt:
                try:
                    pages = pdf_pages(alt)
                    t = {**t, "transcript": alt}
                except Exception:
                    pages = None
            if pages is None:
                calls.append({"call": fy_quarter(qe), "month": t["month"], "url": t["transcript"],
                              "status": "unavailable — company site refused the download and no exchange copy was found"})
                continue
        if not pages or is_scanned(pages):
            calls.append({"call": fy_quarter(qe), "month": t["month"], "url": t["transcript"], "status": "scanned PDF — skipped"})
            continue
        passages, opening = select_passages(pages, tag)
        full_norm = _norm(" ".join(pages))
        total_chars = sum(len(p) for p in pages)
        sel_chars = sum(len(p["text"]) for p in passages)
        call_rec = {"call": fy_quarter(qe), "call_end": qe.isoformat(), "month": t["month"], "url": t["transcript"], "doc": doc_id(t["transcript"]),
                    "pages": len(pages), "chars_total": total_chars, "chars_sent": sel_chars, "passages": len(passages)}
        if not opening_ctx:
            # opening remarks of the most recent call we could actually read, labelled with THAT call
            opening_ctx.extend({**o, "call": fy_quarter(qe)} for o in opening[:3])
        for p in passages:
            if re.search(r"\b(delay\w*|postpon\w*|commissioned|on track|behind schedule|ramp[- ]?up|stabili[sz]\w*)\b", p["text"], re.I):
                status_ctx.append({"id": p["id"], "call": fy_quarter(qe), "text": p["text"]})
        out = llm.run("guidance", {"company": co["name"], "call": fy_quarter(qe), "call_month": t["month"],
                                    "passages": [{"id": p["id"], "speaker": p["speaker"], "text": p["text"]} for p in passages]},
                      label=f"{co['symbol']} guidance {fy_quarter(qe)}")
        if out is None:
            pending += 1
            call_rec["status"] = "awaiting model"
            calls.append(call_rec)
            continue
        kept = dropped = 0
        pmap = {p["id"]: p for p in passages}
        for it in out.get("items", []):
            if not verify_quote(it.get("quote", ""), full_norm):
                dropped += 1
                continue
            qn = _norm(it.get("quote", ""))
            if qn in seen_quotes:
                continue
            seen_quotes.add(qn)
            gid += 1
            src = pmap.get(it.get("passage_id"), {})
            g = {**it, "id": f"G{gid}", "call": fy_quarter(qe), "call_end": qe.isoformat(), "page": src.get("page"), "doc_url": t["transcript"]}
            g["check"] = check_promise(g, an)
            ledger.append(g)
            kept += 1
        tones.append({"call": fy_quarter(qe), **(out.get("tone") or {})})
        call_rec.update({"status": "analysed", "items": kept, "dropped_unverified": dropped})
        calls.append(call_rec)
    return {"ledger": ledger, "tones": tones, "calls": calls, "drift": drift(ledger),
            "context": opening_ctx[:3] + status_ctx[:6], "pending": pending}


def prioritise(ledger: list[dict], n: int) -> list[dict]:
    """The promises worth a PM's attention first: numeric, specific, recent, confidently extracted."""
    calls = sorted({x["call_end"] for x in ledger}, reverse=True)
    rank = {c: i for i, c in enumerate(calls)}

    def score(x):
        s = {"quantitative": 3, "milestone": 2, "qualitative": 0.5}.get(x["kind"], 0)
        s += {"high": 2, "medium": 1, "low": 0}.get(x.get("confidence"), 0)
        s += max(0, 2 - rank.get(x["call_end"], 3))
        s += 1 if _quarter_ends_for(x.get("horizon", "")) else 0
        s += 1.5 if x.get("check") else 0
        s += 1 if x["metric"] in ("revenue_growth", "ebitda_margin", "pat_growth", "capex", "revenue", "loan_growth", "asset_quality", "order_inflow") else 0
        return s

    for x in ledger:
        x["priority"] = round(score(x), 1)
    return sorted(ledger, key=lambda x: -x["priority"])[:n]


def synthesis(co: dict, an: dict, g: dict) -> dict | None:
    out = _synthesis(co, an, g)
    if out is None:
        # Inputs changed (a new quarter, a new call) and no model is available right now:
        # serve the last judgement, clearly labelled, rather than an empty page.
        prev = llm.latest("synthesis", f"{co['symbol']} synthesis")
        if prev:
            out = {**prev["output"], "stale_as_of": prev["meta"].get("at")}
    return out


def _synthesis(co: dict, an: dict, g: dict) -> dict | None:
    # Synthesis judges the whole ledger; wait until every available call has been read.
    if g["pending"] or (not g["ledger"] and not g["context"]):
        return None
    ctx = [{"id": f"C{i + 1}", "call": c.get("call", g["calls"][0]["call"] if g["calls"] else ""), "text": c["text"][:1500]} for i, c in enumerate(g["context"])]
    top = prioritise(g["ledger"], 24)
    ledger = [{k: x.get(k) for k in ("id", "call", "metric", "kind", "statement", "quote", "horizon", "target_low", "target_high", "unit", "check")} for x in top]
    facts = {k: v for k, v in an["facts"].items() if v is not None}
    return llm.run("synthesis", {"company": co["name"], "kind": co["kind"], "as_of": now_ist().date().isoformat(),
                                  "facts": facts, "ledger": ledger, "drift": g["drift"], "context": ctx},
                   label=f"{co['symbol']} synthesis")


def dossier(symbol: str, with_llm: bool = True) -> dict:
    co = screener.fetch_company(symbol)
    if not co.get("quarters") and not co.get("annual"):
        return {"symbol": symbol, "status": "not_found", "name": co.get("name", symbol)}
    capex = screener.fetch_capex(co)
    an = analytics(co, capex)
    try:
        px = prices.eod(symbol, "1y")
    except Exception:
        px = []
    g = guidance_ledger(co, an) if with_llm else {"ledger": [], "tones": [], "calls": [], "drift": [], "context": [], "pending": 0}
    syn = synthesis(co, an, g) if with_llm else None
    promises = {p["guidance_id"]: p for p in (syn or {}).get("promises", [])}
    for x in g["ledger"]:
        p = promises.get(x["id"])
        if p:
            x["verdict"] = p["status"]
            x["evidence"] = p["evidence"]
            x["actual_text"] = p.get("actual")
        elif x.get("check"):
            x["verdict"] = x["check"]["status"]
    tr = co["top_ratios"]
    hi_lo = tr.get("High / Low", "")
    return {
        "symbol": symbol, "name": co["name"], "status": "ok", "kind": co["kind"], "basis": co.get("basis"),
        "sector_path": co.get("sector_path", []), "about": co.get("about", ""),
        "generated_at": now_ist().isoformat(timespec="minutes"),
        "quote": {"price": tr.get("Current Price"), "market_cap": tr.get("Market Cap"), "pe": tr.get("Stock P/E"),
                  "roce": tr.get("ROCE"), "roe": tr.get("ROE"), "div_yield": tr.get("Dividend Yield"), "high_low": hi_lo,
                  "spark": [[r["d"], r["c"]] for r in px[-120:]]},
        **{k: an[k] for k in ("quarters", "years", "ttm", "trajectory", "statements", "balance", "cash", "flags")},
        "facts": an["facts"],
        "guidance": {k: g[k] for k in ("ledger", "tones", "calls", "drift", "pending")},
        "context": [{"id": f"C{i + 1}", **c} for i, c in enumerate(g["context"])],
        "synthesis": syn,
        "documents": {"transcripts": [{"month": t["month"], "url": t["transcript"]} for t in screener.concall_transcripts(co, 6)],
                      "annual_reports": co["docs"]["annual_reports"][:3]},
        "sources": ["Reported financials (standardised tables, screener.in)", "Earnings-call transcripts (BSE filings)",
                    "End-of-day prices (Yahoo Finance)"],
    }
