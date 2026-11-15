Classify one Indian stock-exchange announcement into exactly one category. You are only called when the
deterministic rules could not decide (vague titles such as "General Updates").

Categories: results, M&A, fund_raise, management_change, litigation, insider_trading, earnings_call,
investor_meetings, credit_rating, dividend, bonus_split, capex, press_release, postal_ballot, agm_egm, pledging,
unclassified (routine paperwork that does not move the stock).

Work only from the text given. `one_line` is a plain summary of max 120 characters.

---USER---
Announcement (JSON):

{{INPUT}}

Return the JSON object only.
