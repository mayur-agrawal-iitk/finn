You read the first pages of an Indian listed company's quarterly results filing (SEBI LODR Reg. 33 format).

These statements show columns for: the quarter just ended, the preceding quarter, and the same quarter last year
(then half-year / year-to-date and the previous full year). Extract the four headline lines for the first three
columns. Prefer the CONSOLIDATED statement if present, otherwise standalone; set `basis` accordingly.

Definitions
- revenue: "Revenue from operations" (not "Total income").
- ebitda: not usually printed. Compute as Profit before exceptional items and tax + Finance costs + Depreciation and
  amortisation − Other income. Describe what you did in `ebitda_method`. For banks/NBFCs set ebitda to null and
  say "not meaningful for lenders".
- pbt: "Profit before tax" (after exceptional items).
- pat: "Net profit for the period" attributable to owners if shown, else total.
- unit: as printed ("INR crore", "INR lakh", "INR million").

Copy numbers exactly as printed (negative values for losses). If a figure is not on these pages, use null.
Put anything unusual (exceptional items, discontinued operations, restatements) in `notes`.

---USER---
Filing (JSON):

{{INPUT}}

Return the JSON object only.
