"""Deterministic research helpers: fiscal calendar, quote verification, promise checks, drift."""
from datetime import date

from finn.research import _norm, check_promise, drift, select_passages, verify_quote
from finn.util import call_quarter, fy_quarter, num, parse_short_date


def test_indian_fiscal_labels():
    assert fy_quarter(date(2026, 9, 30)) == "Q2 FY27"
    assert fy_quarter(date(2027, 3, 31)) == "Q4 FY27"
    assert call_quarter(date(2026, 11, 1)) == date(2026, 9, 30)
    assert call_quarter(date(2026, 5, 1)) == date(2026, 3, 31)


def test_number_parsing():
    assert num("65,799") == 65799
    assert num("27%") == 27
    assert num("-2,273") == -2273
    assert num("") is None


def test_short_dates_roll_back_a_year():
    assert parse_short_date("9 Nov", date(2026, 11, 15)) == date(2026, 11, 9)
    assert parse_short_date("20 Dec", date(2026, 11, 15)) == date(2025, 12, 20)


def test_quote_verification_rejects_paraphrase():
    src = _norm("We remain confident of delivering revenue growth of 18% to 20% for FY27, driven by exports.")
    assert verify_quote("delivering revenue growth of 18% to 20% for FY27", src)
    assert not verify_quote("we expect strong growth of around twenty percent next year", src)


def _an(quarters):
    return {"quarters": quarters}


def test_promise_check_completed_year_miss():
    q = [{"end": f"{y}-{m:02d}-{d}", "revenue": r, "ebitda": r * 0.15, "pat": r * 0.08}
         for (y, m, d, r) in [(2024, 6, 30, 700), (2024, 9, 30, 700), (2024, 12, 31, 700), (2025, 3, 31, 700),
                              (2025, 6, 30, 770), (2025, 9, 30, 770), (2025, 12, 31, 770), (2026, 3, 31, 770)]]
    item = {"kind": "quantitative", "metric": "revenue_growth", "unit": "%", "target_low": 15, "target_high": 18, "horizon": "FY26",
            "statement": "FY26 revenue growth of 15-18%"}
    chk = check_promise(item, _an(q))
    assert chk["complete"] and chk["status"] == "missed" and round(chk["actual"]) == 10


def test_segment_targets_are_not_checked_against_company_numbers():
    item = {"kind": "quantitative", "metric": "ebitda_margin", "unit": "%", "target_low": 30, "target_high": None, "horizon": "FY27",
            "statement": "Rail margins above 30% in FY27"}
    assert check_promise(item, _an([{"end": "2026-06-30", "revenue": 100, "ebitda": 15, "pat": 8}])) is None


def test_segment_detection_reads_the_subject_only():
    from finn.research import is_segment
    assert is_segment("Rail margins above 30% in FY27")
    assert is_segment("Rail business growth of 20-25% in FY27")
    assert not is_segment("FY27 capex of about INR 850 crore: OSAT 300, PCB 300, EMS 250")
    assert not is_segment("FY26 revenue of at least INR 4,000 crore including Q4")


def test_drift_ignores_unrelated_metrics():
    led = [
        {"id": "G1", "kind": "quantitative", "metric": "other", "horizon": "FY27", "target_low": 5, "target_high": 5, "unit": "x", "call": "Q3 FY26", "call_end": "2025-12-31", "statement": "ARPU"},
        {"id": "G2", "kind": "quantitative", "metric": "other", "horizon": "FY27", "target_low": 90, "target_high": 90, "unit": "%", "call": "Q1 FY27", "call_end": "2026-06-30", "statement": "installs"},
    ]
    assert drift(led) == []


def test_drift_detects_cut_guidance():
    led = [
        {"id": "G1", "kind": "quantitative", "metric": "capex", "horizon": "FY27", "target_low": 1400, "target_high": 1400, "unit": "INR crore", "call": "Q3 FY26", "call_end": "2025-12-31"},
        {"id": "G2", "kind": "quantitative", "metric": "capex", "horizon": "FY27", "target_low": 850, "target_high": 850, "unit": "INR crore", "call": "Q1 FY27", "call_end": "2026-06-30"},
    ]
    d = drift(led)
    assert d and d[0]["move"] == "lowered"


def test_drift_small_percentage_revision_and_mixed_groups():
    base = {"kind": "quantitative", "unit": "%", "statement": ""}
    credit = [{**base, "id": "G1", "metric": "credit_cost", "horizon": "FY27", "target_low": 1.5, "target_high": 1.5, "call": "Q4 FY26", "call_end": "2026-03-31"},
              {**base, "id": "G2", "metric": "credit_cost", "horizon": "FY27", "target_low": 1.4, "target_high": 1.4, "call": "Q1 FY27", "call_end": "2026-06-30"}]
    d = drift(credit)
    assert d[0]["move"] == "lowered" and d[0]["lower_is_better"]
    rev = {"kind": "quantitative", "unit": "INR crore", "statement": "", "metric": "revenue", "horizon": "FY27"}
    mixed = [{**rev, "id": "G3", "target_low": 3500, "target_high": 4000, "call": "Q4 FY26", "call_end": "2026-03-31"},
             {**rev, "id": "G4", "target_low": 56000, "target_high": 56000, "call": "Q4 FY26", "call_end": "2026-03-31"},
             {**rev, "id": "G5", "target_low": 1200, "target_high": 1200, "call": "Q1 FY27", "call_end": "2026-06-30"}]
    assert drift(mixed) == []


def test_retrieval_keeps_forward_looking_numbers_and_drops_questions():
    pages = ["Moderator: Welcome everyone.\n"
             "Ravi Kumar: For FY27 we expect revenue growth of 18% to 20%, and EBITDA margin should be in the 14% band going forward as the new plant ramps up.\n"
             "Analyst: Can you give us colour on margins next year?\n"
             "Ravi Kumar: The quarter was impacted by monsoon. Our dealers had a tough time, and we lost a few accounts in the north region overall."]
    keep, _ = select_passages(pages, "Q2FY27")
    texts = " ".join(p["text"] for p in keep)
    assert "18% to 20%" in texts and "Can you give" not in texts
