"""Classifier regression tests — every case here is a real filing that once misfired."""
from finn.classify import classify, tier


def c(title, summary=""):
    return classify(title, "", summary)


def test_results_filing_is_material():
    r = c("Unaudited Financial Results For The Quarter Ended 30 September 2026 And 2Nd Interim Dividend 2026-27")
    assert r["category"] == "results" and tier(r["score"]) == "material"


def test_results_newspaper_ad_is_routine():
    r = c("Announcement under Regulation 30 (LODR)-Newspaper Publication", "Newspaper Publication on Unaudited Financial Results")
    assert tier(r["score"]) == "routine"


def test_postal_ballot_outcome_appointing_ceo_is_a_management_change():
    r = c("Shareholder Meeting / Postal Ballot-Outcome of Postal_Ballot", "Shareholders approved Anup Bagchi as Director and MD & CEO on November 6, 2026.")
    assert r["category"] == "management_change" and r["subtype"] == "top"


def test_bundled_board_outcome_prefers_ceo_exit_and_keeps_results_as_also():
    r = c("Announcement under Regulation 30 (LODR)-Change in Management", "Apollo Hospitals approved Q2 FY27 results; CEO Madhu Sasidhar exits Nov 14")
    assert r["category"] == "management_change"
    assert "results" in r["facts"]["also"]


def test_disclosure_does_not_match_closure():
    r = c("Disclosure Under Regulation 30 Read With Para A Of Schedule III", "ICICI Bank to hold debt market investor meetings on November 17, 2026.")
    assert r["category"] == "investor_meetings"


def test_small_penalty_is_not_material():
    r = c("Disclosure Under Regulation 30 Of SEBI (LODR) Regulations", "DoT levied penalties of Rs.1.60 lakh and Rs.1.02 lakh for subscriber verification lapses")
    assert r["category"] == "litigation" and r["facts"]["immaterial"] and tier(r["score"]) == "routine"


def test_researchers_prize_is_not_litigation():
    r = c("Six Promising Researchers Win The Infosys Prize 2026 Awarded By The Infosys Science Foundation")
    assert r["category"] == "unclassified"


def test_order_win_extracts_amount():
    r = c("Announcement under Regulation 30 (LODR)-Award_of_Order_Receipt_of_Order", "BEL secured additional orders worth Rs.619 crore for communication equipment")
    assert r["category"] == "press_release" and r["subtype"] == "order" and r["facts"]["amount_cr"] == 619.0


def test_esg_rating_is_not_credit_rating():
    r = c("Disclosure Under Regulation 30 Of The SEBI (LODR) Regulations, 2015", "Morningstar Sustainalytics improved AAVAS ESG risk rating to 21.4")
    assert r["category"] == "unclassified"


def test_internal_merger_is_downgraded_but_real_acquisition_is_not():
    internal = c("Announcement under Regulation 30 (LODR)-Scheme of Arrangement", "ITC board approved merger of wholly owned subsidiary Sproutlife Foods")
    real = c("General Updates", "HAL to acquire CAE Canada's 50% stake in HATSOFF, making it wholly-owned")
    assert internal["facts"].get("internal") and internal["score"] < 50
    assert real["category"] == "M&A" and real["score"] >= 70


def test_commercial_paper_is_not_an_equity_raise():
    r = c("Announcement under Regulation 30 (LODR)-Allotment", "Persistent allotted 12,000 commercial papers worth INR 6 billion")
    assert r["category"] == "fund_raise" and r["subtype"] == "debt" and tier(r["score"]) == "routine"


def test_dematerialise_reminder_is_routine():
    r = c("Reminder Letter To Shareholders To Dematerialise The Shares")
    assert r["category"] == "unclassified"
