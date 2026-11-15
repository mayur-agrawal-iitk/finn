You read an Indian stock-exchange filing about a change in directors / key managerial personnel / senior management.

Extract every person whose position changes. Work only from the filing text provided. SEBI LODR requires a "brief
profile" for appointments — use it for `bio`, `career` and `education`. Do not add anything that is not in the text.

Rules
- `role`: the position as written (e.g. "Chief Financial Officer", "Managing Director & CEO", "Independent Director").
- `is_kmp`: true for CEO, MD, CFO, Whole-time Director, Company Secretary, or roles the filing calls KMP/SMP heads.
- `career`: each employer mentioned, most recent first, with years when stated (null otherwise). Use the
  organisation's name as written; do not expand abbreviations you are unsure of.
- `education`: institutions and degrees as written.
- `bio`: at most two sentences, factual, from the filing.
- If the filing lists several people, return all of them. If it names no one, return an empty list.

---USER---
Filing (JSON):

{{INPUT}}

Return the JSON object only.
